"""Ingestão de um livro.

Responsabilidade, em passos: ler o arquivo, limpar cabeçalho e rodapé repetidos,
classificar as páginas em corpo e matéria editorial, recortar o corpo em trechos
que terminam em fim de frase e preparar o que vai ser embedado em lotes.

Este módulo não fala com a rede nem com o banco: tudo aqui é função pura sobre
as páginas lidas. O que consome cota e grava acontece depois, com as peças que
vivem em `infra/`.

As regras estão em `Sabiá - Sistema.md`, seções de preparo do texto e de ingestão. Os números da
classificação foram medidos no acervo e são pontos de partida a re-medir.
"""

from __future__ import annotations

import bisect
import re
import statistics as st
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from engine.core.errors import ProviderUnavailable
from engine.infra.pdf import Book, Page, remove_repeated_lines

# ---------------------------------------------------------------------------
# Parâmetros da classificação (medidos; ver o documento)
# ---------------------------------------------------------------------------
LEVEL_BODY = 0.75  # abertura: nível do corpo, relativo à referência
LEVEL_NOTE = 0.25  # fechamento: abaixo disto é nota clara
CONSECUTIVE_PAGES = 3  # páginas seguidas no nível do corpo marcam o começo dele
EMPTY_WORDS = 5  # menos que isto é página vazia
DOTTED_LINES = 3  # menos que isto não é sumário (com uma, o prefácio caía)

CREDIT_WORDS = (
    "copyright",
    "direitos reservados",
    "todos os direitos",
    "isbn",
    "expediente",
    "editora",
)

OUTLINE_MATTER = (
    "índice",
    "indice",
    "sumário",
    "sumario",
    "notas",
    "bibliografia",
    "glossário",
    "glossario",
)

# ---------------------------------------------------------------------------
# Parâmetros do recorte (ver o documento)
# ---------------------------------------------------------------------------
TARGET_WORDS = 120  # acumula frases até passar disto e fecha no fim da última
CAP_WORDS = 160  # teto do alvo; cede para a frase (nunca se corta a frase)

FRONT, BODY, BACK = "front", "body", "back"


@dataclass(frozen=True)
class PageClassification:
    """O que a página é, e por quê. O motivo aparece no mapa exibido."""

    index: int
    segment: str
    reason: str | None
    words: int


@dataclass(frozen=True)
class Chunk:
    """Um trecho do corpo, pronto para virar vetor."""

    text: str
    page_index: int
    page_label: str | None


@dataclass(frozen=True)
class PreparedBook:
    """O livro lido e preparado, sem nada de rede nem de banco."""

    classifications: tuple[PageClassification, ...]
    chunks: tuple[Chunk, ...]
    page_count: int

    @property
    def body_pages(self) -> int:
        return sum(1 for c in self.classifications if c.segment == BODY)

    def segment_map(self) -> list[dict]:
        """Mapa por página, para o registro visível em `books.segment_map`."""
        return [
            {
                "page": c.index,
                "segment": c.segment,
                "reason": c.reason,
                "words": c.words,
            }
            for c in self.classifications
        ]


# ---------------------------------------------------------------------------
# Fim de frase
# ---------------------------------------------------------------------------
# Abreviações do português que terminam com ponto e não terminam frase.
ABBREVIATIONS = frozenset(
    """
    p pp pág pág págs pag pag páginas
    etc art arts sr sra srs dr dra drs prof profa
    cap caps fig figs nº no nos num
    séc sécs sec ed eds vol vols
    cf obs apud op cit id ibid et al
    i.e e.g vs ex exmo ilmo
    """.split()
)

# Sinal de fim: pontuação final, aspas ou parêntese que a fecham, e espaço.
SENTENCE_END = re.compile(r"""([.!?…]+)(["'»”’)\]】]*)(\s+|$)""")

# Depois do fim, a frase seguinte começa com maiúscula, dígito, aspas ou o fim
# do texto. Sem esta exigência, "p. 44" ou uma abreviatura fora da lista
# fechariam um trecho no meio do pensamento — e o trecho é o que o leitor vê.
NEXT_SENTENCE = re.compile(r"""(?:["'«“‘(\[—-]\s*)*[A-ZÀ-Þ0-9]""")


def sentence_spans(text: str) -> list[tuple[int, str]]:
    """As frases do texto, cada uma com a posição onde começa.

    Conservadora de propósito: quando não tem certeza, **não** divide. Uma
    divisão errada corta o pensamento que o leitor vê no painel; uma divisão
    perdida só faz o trecho ficar um pouco maior.
    """
    frases: list[tuple[int, str]] = []
    inicio = 0
    for achado in SENTENCE_END.finditer(text):
        pontuacao = achado.group(1)
        anterior = text[: achado.start(1)].rstrip()
        palavra = re.split(r"[\s(«“‘\[]", anterior)[-1] if anterior else ""
        depois = text[achado.end() :]

        if pontuacao == "." and palavra.casefold().strip(".") in ABBREVIATIONS:
            continue
        if pontuacao == "." and not NEXT_SENTENCE.match(depois):
            continue

        pedaco = text[inicio : achado.end()]
        if pedaco.strip():
            frases.append((inicio + len(pedaco) - len(pedaco.lstrip()), pedaco.strip()))
        inicio = achado.end()

    sobra = text[inicio:]
    if sobra.strip():
        frases.append((inicio + len(sobra) - len(sobra.lstrip()), sobra.strip()))
    return frases


def split_sentences(text: str) -> list[str]:
    """As frases do texto, sem a posição."""
    return [frase for _, frase in sentence_spans(text)]


def _words(text: str) -> int:
    return len(text.split())


def split_into_chunks(text: str, target: int = TARGET_WORDS) -> list[tuple[int, str]]:
    """Recorta em trechos que terminam em fim de frase.

    Devolve cada trecho com a posição onde ele começa, porque o trecho precisa
    saber de que página veio. A sobreposição entre trechos é a última frase do
    anterior, e ela conta no total do seguinte.
    """
    spans = sentence_spans(text)
    if not spans:
        return []

    trechos: list[tuple[int, str]] = []
    primeira = 0  # índice da primeira frase do trecho em construção
    total = 0
    for i, (_, frase) in enumerate(spans):
        total += _words(frase)
        if total >= target:
            trechos.append((spans[primeira][0], " ".join(f for _, f in spans[primeira : i + 1])))
            # A última frase abre o trecho seguinte, e conta no total dele.
            primeira = i
            total = _words(frase)

    # O resto só vira trecho se trouxer algo além da sobreposição.
    if len(spans) - primeira > 1 or not trechos:
        trechos.append((spans[primeira][0], " ".join(f for _, f in spans[primeira:])))
    return trechos


# ---------------------------------------------------------------------------
# Classificação das páginas
# ---------------------------------------------------------------------------
def _mark(page: Page, outline_pages: set[int]) -> str | None:
    """Marca do próprio arquivo, ou nada.

    Cada marca vale por si, mas só dentro das faixas: página vazia também
    existe no meio do livro, como abertura de capítulo, e ali é corpo.
    """
    sinais = page.signals
    if sinais.characters == 0 or sinais.words < EMPTY_WORDS:
        return "página vazia"
    if sinais.dotted_lines >= DOTTED_LINES:
        return "sumário"
    if page.text.lstrip().startswith("[←"):
        return "nota"
    if any(palavra in page.text.casefold() for palavra in CREDIT_WORDS):
        return "crédito ou expediente"
    if page.index in outline_pages:
        return "título do sumário"
    return None


def classify_pages(
    pages: tuple[Page, ...], book: Book | None = None
) -> tuple[PageClassification, ...]:
    """Classifica cada página em abertura, corpo ou fechamento.

    A extensão da matéria editorial não é calculada: a fronteira é encontrada
    no conteúdo. O corpo começa na primeira de três páginas seguidas no nível
    do corpo; o fechamento é o trecho final que tem marca ou nota clara. Fora
    disso, corpo — e na dúvida, corpo.
    """
    titulos = {
        entrada.page_index
        for entrada in (book.outline if book else ())
        if any(t in entrada.title.casefold() for t in OUTLINE_MATTER)
    }
    marcas = [_mark(pagina, titulos) for pagina in pages]
    palavras = [pagina.signals.words for pagina in pages]

    # A referência ignora as páginas marcadas: num livro em que metade das
    # páginas é nota, a mediana de tudo derruba o nível e nada classifica.
    sem_marca = [p for p, marca in zip(palavras, marcas, strict=True) if not marca]
    referencia = st.median(sem_marca) if sem_marca else st.median(palavras)
    nivel, fundo = referencia * LEVEL_BODY, referencia * LEVEL_NOTE
    n = len(pages)

    def no_nivel(i: int) -> bool:
        return all(palavras[j] >= nivel for j in range(i, min(i + CONSECUTIVE_PAGES, n)))

    corpo_comeca = next(
        (i for i in range(max(n - CONSECUTIVE_PAGES + 1, 1)) if no_nivel(i)), n
    )

    def nota_clara(i: int) -> bool:
        vizinhas = [j for j in (i - 1, i + 1) if 0 <= j < n]
        return palavras[i] < fundo and any(palavras[j] < fundo for j in vizinhas)

    fechamento: set[int] = set()
    i = n - 1
    while i >= 0 and (marcas[i] or nota_clara(i)):
        fechamento.add(i)
        i -= 1

    classificacoes: list[PageClassification] = []
    for indice in range(n):
        if indice < corpo_comeca and (marcas[indice] or palavras[indice] < nivel):
            motivo = marcas[indice] or "abertura, abaixo do nível do corpo"
            classificacoes.append(PageClassification(indice, FRONT, motivo, palavras[indice]))
        elif indice in fechamento:
            motivo = marcas[indice] or "nota clara, abaixo de um quarto da referência"
            classificacoes.append(PageClassification(indice, BACK, motivo, palavras[indice]))
        else:
            classificacoes.append(PageClassification(indice, BODY, None, palavras[indice]))
    return tuple(classificacoes)


# ---------------------------------------------------------------------------
# Preparação
# ---------------------------------------------------------------------------
def chunk_body(
    pages: tuple[Page, ...], classifications: tuple[PageClassification, ...]
) -> tuple[Chunk, ...]:
    """Recorta o corpo, guardando de que página cada trecho veio.

    Trecho que atravessa a fronteira permanece corpo: a preferência é por
    ruído, nunca por silêncio.
    """
    corpo = [
        pagina
        for pagina, classe in zip(pages, classifications, strict=True)
        if classe.segment == BODY
    ]
    if not corpo:
        return ()

    offset = 0
    inicios: list[int] = []
    pedacos: list[str] = []
    for pagina in corpo:
        inicios.append(offset)
        pedacos.append(pagina.text)
        offset += len(pagina.text) + 1

    trechos: list[Chunk] = []
    for posicao, texto in split_into_chunks("\n".join(pedacos)):
        qual = bisect.bisect_right(inicios, posicao) - 1
        pagina = corpo[max(qual, 0)]
        trechos.append(Chunk(text=texto, page_index=pagina.index, page_label=pagina.label))
    return tuple(trechos)


# ---------------------------------------------------------------------------
# Lotes e execução
# ---------------------------------------------------------------------------
BATCH_CHARS = 16_000


@dataclass(frozen=True)
class Batch:
    """Um lote de trechos: o que uma invocação processa por vez."""

    index: int
    first: int
    last: int

    @property
    def size(self) -> int:
        return self.last - self.first + 1


class IngestStore(Protocol):
    """O que a ingestão precisa do armazenamento, em termos de negócio."""

    def save_chunks(
        self, *, segment: str, items: Sequence[tuple[str, int, str | None, Sequence[float]]]
    ) -> int: ...

    def advance(self, *, next_batch: int, texts: int, done: bool) -> None: ...


class Embedder(Protocol):
    """O que a ingestão precisa do provedor de embeddings."""

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class BatchResult:
    """O que um lote produziu, para a tarefa registrar."""

    next_batch: int
    texts: int
    done: bool


def plan_batches(
    chunks: Sequence[Chunk], *, batch_chars: int = BATCH_CHARS
) -> tuple[Batch, ...]:
    """Divide os trechos em lotes por orçamento de caracteres.

    O orçamento existe pelo limite por minuto do provedor: lote grande demais
    devolve 429 e desperdiça a chamada. Função pura — a divisão é testável sem
    provedor e sem banco.
    """
    lotes: list[Batch] = []
    primeiro = 0
    tamanho = 0
    for posicao, trecho in enumerate(chunks):
        if posicao > primeiro and tamanho + len(trecho.text) > batch_chars:
            lotes.append(Batch(index=len(lotes), first=primeiro, last=posicao - 1))
            primeiro, tamanho = posicao, 0
        tamanho += len(trecho.text)
    if primeiro < len(chunks):
        lotes.append(Batch(index=len(lotes), first=primeiro, last=len(chunks) - 1))
    return tuple(lotes)


def run_batch(
    prepared: PreparedBook,
    batches: Sequence[Batch],
    *,
    index: int,
    embedder: Embedder,
    store: IngestStore,
) -> BatchResult:
    """Embeda um lote e grava. É a unidade de trabalho de uma invocação.

    Grava antes de devolver: parada no meio não pode desperdiçar o que já foi
    consumido de cota.
    """
    lote = batches[index]
    trechos = prepared.chunks[lote.first : lote.last + 1]
    vetores = embedder.embed_documents([trecho.text for trecho in trechos])
    if len(vetores) != len(trechos):
        raise ProviderUnavailable(
            "o provedor de embeddings devolveu uma quantidade diferente da pedida"
        )

    store.save_chunks(
        segment=BODY,
        items=[
            (trecho.text, trecho.page_index, trecho.page_label, vetor)
            for trecho, vetor in zip(trechos, vetores, strict=True)
        ],
    )
    proximo = index + 1
    pronto = proximo >= len(batches)
    store.advance(next_batch=proximo, texts=len(trechos), done=pronto)
    return BatchResult(next_batch=proximo, texts=len(trechos), done=pronto)


def prepare(book: Book) -> PreparedBook:
    """Prepara o livro inteiro: limpeza, classificação e recorte.

    A limpeza vem primeiro: a classificação mede o texto que vai para a busca,
    e não o original com cabeçalho e rodapé repetidos.
    """
    paginas = remove_repeated_lines(book.pages)
    classificacoes = classify_pages(paginas, book)
    trechos = chunk_body(paginas, classificacoes)
    return PreparedBook(
        classifications=classificacoes, chunks=trechos, page_count=len(paginas)
    )
