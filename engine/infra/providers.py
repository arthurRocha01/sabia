"""Provedores de modelo.

Responsabilidade: falar com o provedor de embeddings e traduzir o que ele
responde em erro do contrato. Nenhuma regra de negócio mora aqui: quantos
trechos, em que ordem e o que gravar é do domínio.

Os dois erros de 429 do plano gratuito são tratados como coisas diferentes,
porque são: cota diária esgotada não melhora esperando, e o limite por minuto
melhora — a própria resposta diz quanto esperar. Tratar os dois igual já custou
seis minutos de espera inútil numa execução do POC.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from typing import Any

from google import genai

from engine.core.errors import ProviderUnavailable, QuotaExhausted, TimedOut

DAILY_QUOTA = "perday"
RETRY_DELAY = re.compile(r"retrydelay[\"']?\s*:\s*[\"']?(\d+(?:\.\d+)?)s", re.IGNORECASE)
SERVER_ERRORS = (500, 502, 503, 504)
TOO_MANY_REQUESTS = 429


class GeminiEmbeddings:
    """Embeddings pelo Gemini, em lotes por orçamento de caracteres.

    O orçamento existe por causa do limite por minuto do plano gratuito: mandar
    tudo de uma vez devolve 429, e o lote grande é justamente o que estoura.

    Medido no plano gratuito: o limite por minuto conta **textos**, não
    requisições — cerca de 100 por minuto. Um lote de 20 trechos a cada 10
    segundos passa de 120 por minuto e leva 429, por isso a pausa depois de cada
    lote sai do tamanho dele, e não de um valor fixo.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int,
        batch_chars: int = 16_000,
        batch_delay: float = 10.0,
        texts_per_minute: int = 100,
        attempts: int = 3,
        # O cliente do provedor entra por parâmetro para os testes poderem
        # exercitar lote, pausa e cota sem rede.
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        self.batch_chars = batch_chars
        self.batch_delay = batch_delay
        self.texts_per_minute = texts_per_minute
        self.attempts = attempts
        self._client: Any = client if client is not None else genai.Client(api_key=api_key)
        self._sleep = sleep

    # -- API pública ------------------------------------------------------
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Vetores para os trechos do livro, na mesma ordem da entrada."""
        vetores: list[list[float]] = []
        lotes = self.batches(texts)
        for posicao, lote in enumerate(lotes):
            vetores.extend(self._embed(lote, "RETRIEVAL_DOCUMENT"))
            # Pausa entre lotes, nunca depois do último.
            if posicao + 1 < len(lotes):
                self._sleep(self.pause_after(len(lote)))
        return vetores

    def embed_query(self, text: str) -> list[float]:
        """Vetor da consulta do leitor."""
        return self._embed([text], "RETRIEVAL_QUERY")[0]

    def pause_after(self, quantos: int) -> float:
        """Pausa depois de um lote, para não estourar o limite por minuto."""
        return max(self.batch_delay, quantos / self.texts_per_minute * 60)

    def batches(self, texts: Sequence[str]) -> list[list[str]]:
        """Agrupa os textos por orçamento de caracteres."""
        lotes: list[list[str]] = []
        atual: list[str] = []
        tamanho = 0
        for texto in texts:
            if atual and tamanho + len(texto) > self.batch_chars:
                lotes.append(atual)
                atual, tamanho = [], 0
            atual.append(texto)
            tamanho += len(texto)
        if atual:
            lotes.append(atual)
        return lotes

    # -- Interno ----------------------------------------------------------
    def _embed(self, contents: Sequence[str], task_type: str) -> list[list[float]]:
        resposta = self._call(contents, task_type)
        return [list(item.values or []) for item in resposta.embeddings]

    def _call(self, contents: Sequence[str], task_type: str):
        for tentativa in range(self.attempts):
            try:
                return self._client.models.embed_content(
                    model=self.model,
                    contents=list(contents),
                    config={
                        "task_type": task_type,
                        "output_dimensionality": self.dimensions,
                    },
                )
            except Exception as erro:  # o cliente levanta tipos próprios
                codigo = self._code(erro)
                texto = str(erro)
                if codigo == TOO_MANY_REQUESTS and DAILY_QUOTA in texto.casefold():
                    raise QuotaExhausted(
                        "a cota diária de embeddings acabou",
                        detail="ela volta à meia-noite do Pacífico",
                    ) from erro
                ultima = tentativa + 1 >= self.attempts
                if codigo == TOO_MANY_REQUESTS and not ultima:
                    self._sleep(self._delay(erro))
                    continue
                if codigo in SERVER_ERRORS and not ultima:
                    self._sleep(2**tentativa)
                    continue
                if codigo is None and isinstance(erro, TimeoutError):
                    raise TimedOut("o provedor de embeddings não respondeu a tempo") from erro
                if codigo in (408, 504) or (codigo is None and isinstance(erro, TimeoutError)):
                    raise TimedOut("o provedor de embeddings não respondeu a tempo") from erro
                raise ProviderUnavailable(
                    "o provedor de embeddings não respondeu",
                    detail=f"erro {codigo}" if codigo else type(erro).__name__,
                ) from erro
        raise ProviderUnavailable("o provedor de embeddings não respondeu")  # pragma: no cover

    @staticmethod
    def _code(erro: Exception) -> int | None:
        """Código HTTP do erro, quando o cliente informa."""
        for atributo in ("code", "status_code"):
            valor = getattr(erro, atributo, None)
            if isinstance(valor, int):
                return valor
        return None

    @staticmethod
    def _delay(erro: Exception) -> float:
        """Tempo de espera que o provedor indicou, com teto de segurança."""
        achado = RETRY_DELAY.search(str(erro))
        if not achado:
            return 20.0
        return min(float(achado.group(1)), 60.0)


class GeminiVision:
    """Leitura de um recorte de imagem.

    Serve a uma coisa só: quando a página não tem camada de texto — capa, página
    escaneada, ilustração — o recorte vira pergunta e o modelo transcreve. Não é
    interpretação nem busca: é leitura, e volta como texto puro.
    """

    INSTRUCAO = (
        "Transcreva apenas o texto que aparece nesta imagem, em português. "
        "Não descreva a imagem, não comente e não acrescente nada. "
        "Se não houver texto legível, responda com uma linha vazia."
    )

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        attempts: int = 2,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self.attempts = attempts
        self._client: Any = client if client is not None else genai.Client(api_key=api_key)
        self._sleep = sleep

    def read_image(self, imagem: bytes, mime: str = "image/png") -> str:
        """Devolve o texto que aparece no recorte."""
        for tentativa in range(self.attempts):
            try:
                resposta = self._client.models.generate_content(
                    model=self.model,
                    contents=[
                        genai.types.Part.from_bytes(data=imagem, mime_type=mime),
                        self.INSTRUCAO,
                    ],
                )
                return (resposta.text or "").strip()
            except Exception as erro:  # o cliente levanta tipos próprios
                codigo = self._code(erro)
                ultima = tentativa + 1 >= self.attempts
                if codigo in SERVER_ERRORS and not ultima:
                    self._sleep(2**tentativa)
                    continue
                if codigo is None and isinstance(erro, TimeoutError):
                    raise TimedOut("o provedor de visão não respondeu a tempo") from erro
                raise ProviderUnavailable(
                    "não consegui ler o recorte",
                    detail="página sem texto precisa do provedor de visão de pé",
                ) from erro
        raise ProviderUnavailable("não consegui ler o recorte")

    @staticmethod
    def _code(erro: Exception) -> int | None:
        return GeminiEmbeddings._code(erro)


class DeepSeekInterpretation:
    """Síntese e classificação da relação, num pedido só.

    O tempo é declarado no contrato (o card tem até 15 s), então o pedido tem
    teto próprio e **nenhuma** tentativa extra por dentro do cliente: retry
    cego é o que fazia o card pendurar minutos sem uma linha de registro.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.deepseek.com",
        timeout: int = 60,
        attempts: int = 2,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.attempts = attempts
        self._sleep = sleep
        if client is not None:
            self._client: Any = client
        else:
            from openai import OpenAI

            self._client = OpenAI(api_key=api_key, base_url=base_url, max_retries=0)

    def interpret(self, prompt: str) -> str:
        """Devolve o texto que o modelo respondeu. Interpretar é do domínio."""
        for tentativa in range(self.attempts):
            try:
                resposta = self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=self.timeout,
                )
                return str(resposta.choices[0].message.content or "")
            except Exception as erro:  # o cliente levanta tipos próprios
                codigo = getattr(erro, "status_code", None) or getattr(erro, "code", None)
                ultima = tentativa + 1 >= self.attempts
                if codigo in (429, *SERVER_ERRORS) and not ultima:
                    self._sleep(2**tentativa)
                    continue
                if isinstance(erro, TimeoutError):
                    raise TimedOut("a interpretação não voltou a tempo") from erro
                raise ProviderUnavailable(
                    "o provedor de interpretação não respondeu",
                    detail=f"erro {codigo}" if codigo else type(erro).__name__,
                ) from erro
        raise ProviderUnavailable("o provedor de interpretação não respondeu")  # pragma: no cover
