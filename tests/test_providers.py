"""Testes do provedor de embeddings.

Offline: o cliente do provedor entra por parâmetro, então lote, pausa, tipo de
tarefa e os dois erros de cota são exercitados sem rede e sem gastar cota.
"""

from __future__ import annotations

import pytest

from engine.core.errors import ProviderUnavailable, QuotaExhausted, TimedOut
from engine.infra.providers import GeminiEmbeddings

DIMENSOES = 8


class _Item:
    def __init__(self, dimensoes: int = DIMENSOES) -> None:
        self.values = [0.25] * dimensoes


class _Resposta:
    def __init__(self, quantos: int) -> None:
        self.embeddings = [_Item() for _ in range(quantos)]


class _ErroFalso(Exception):
    def __init__(self, codigo: int, mensagem: str = "") -> None:
        super().__init__(mensagem or f"erro {codigo}")
        self.code = codigo


class _Models:
    def __init__(self, cliente: _ClienteFalso) -> None:
        self.cliente = cliente

    def embed_content(self, *, model, contents, config):
        self.cliente.chamadas.append((list(contents), config))
        resposta = self.cliente.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


class _ClienteFalso:
    def __init__(self, respostas: list) -> None:
        self.respostas = list(respostas)
        self.chamadas: list[tuple] = []
        self.models = _Models(self)


def _embeddings(cliente, **kwargs) -> tuple[GeminiEmbeddings, list[float]]:
    pausas: list[float] = []
    provedor = GeminiEmbeddings(
        api_key="chave-de-teste",
        model="modelo-de-teste",
        dimensions=DIMENSOES,
        client=cliente,
        sleep=pausas.append,
        **kwargs,
    )
    return provedor, pausas


def test_batches_by_character_budget():
    cliente = _ClienteFalso([_Resposta(2), _Resposta(2), _Resposta(1)])
    provedor, _ = _embeddings(cliente, batch_chars=250)

    vetores = provedor.embed_documents(["x" * 100] * 5)

    assert [len(chamada[0]) for chamada in cliente.chamadas] == [2, 2, 1]
    assert len(vetores) == 5


def test_pause_grows_with_the_batch_size():
    """O limite por minuto conta textos: a pausa sai do tamanho do lote."""
    provedor, _ = _embeddings(_ClienteFalso([]), batch_delay=2.0, texts_per_minute=100)
    assert provedor.pause_after(20) == pytest.approx(12.0)
    assert provedor.pause_after(3) == 2.0  # lote pequeno: o piso configurado manda


def test_pauses_between_batches_but_not_after_the_last():
    cliente = _ClienteFalso([_Resposta(2), _Resposta(2), _Resposta(1)])
    provedor, pausas = _embeddings(cliente, batch_chars=250, batch_delay=7.0)

    provedor.embed_documents(["x" * 100] * 5)

    assert pausas == [7.0, 7.0]


def test_documents_use_document_task_and_query_uses_query_task():
    cliente = _ClienteFalso([_Resposta(1), _Resposta(1)])
    provedor, _ = _embeddings(cliente)

    provedor.embed_documents(["um trecho"])
    provedor.embed_query("uma pergunta")

    assert cliente.chamadas[0][1]["task_type"] == "RETRIEVAL_DOCUMENT"
    assert cliente.chamadas[1][1]["task_type"] == "RETRIEVAL_QUERY"


def test_asks_for_the_configured_dimensions():
    cliente = _ClienteFalso([_Resposta(1)])
    provedor, _ = _embeddings(cliente)

    provedor.embed_query("pergunta")

    assert cliente.chamadas[0][1]["output_dimensionality"] == DIMENSOES


def test_daily_quota_fails_at_once_and_does_not_wait():
    """Cota do dia esgotada não melhora esperando: nenhuma nova tentativa."""
    erro = _ErroFalso(429, "quotaId: EmbedContentRequestsPerDayPerUser...")
    cliente = _ClienteFalso([erro, _Resposta(1)])
    provedor, pausas = _embeddings(cliente)

    with pytest.raises(QuotaExhausted):
        provedor.embed_documents(["um trecho"])

    assert len(cliente.chamadas) == 1
    assert pausas == []


def test_per_minute_quota_waits_the_informed_delay_and_retries():
    erro = _ErroFalso(429, '{"retryDelay": "3s"}')
    cliente = _ClienteFalso([erro, _Resposta(1)])
    provedor, pausas = _embeddings(cliente)

    vetores = provedor.embed_documents(["um trecho"])

    assert pausas == [3.0]
    assert len(vetores) == 1


def test_transient_server_error_retries():
    erro = _ErroFalso(503, "servico indisponivel")
    cliente = _ClienteFalso([erro, _Resposta(1)])
    provedor, pausas = _embeddings(cliente)

    assert len(provedor.embed_documents(["um trecho"])) == 1
    assert pausas == [1.0]


def test_server_error_gives_up_with_provider_error():
    erros = [_ErroFalso(500, "erro interno") for _ in range(3)]
    cliente = _ClienteFalso(erros)
    provedor, _ = _embeddings(cliente, attempts=3)

    with pytest.raises(ProviderUnavailable):
        provedor.embed_documents(["um trecho"])
    assert len(cliente.chamadas) == 3


def test_timeout_becomes_timed_out():
    cliente = _ClienteFalso([TimeoutError("estourou o tempo")])
    provedor, _ = _embeddings(cliente)

    with pytest.raises(TimedOut):
        provedor.embed_documents(["um trecho"])


def test_batches_helper_keeps_order():
    provedor, _ = _embeddings(_ClienteFalso([]), batch_chars=10)
    # O lote enche até o orçamento: com 10 caracteres, os três primeiros cabem.
    assert provedor.batches(["aaaa", "bbbb", "cc", "dd"]) == [["aaaa", "bbbb", "cc"], ["dd"]]
