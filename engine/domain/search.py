"""Busca por conexões.

Responsabilidade: receber o texto do leitor, virar vetor de consulta e devolver
os trechos mais próximos, respeitando o escopo, a quantidade pedida e o limiar.
Explicar a conexão é do `interpret.py`.

O teto de palavras do texto consultado vive aqui, e não na interface: o cliente
orienta, o motor garante. O texto cortado é sinalizado na resposta — cortar em
silêncio faria o leitor perguntar uma coisa e receber resposta sobre outra.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from engine.core.errors import InvalidInput

MAX_QUERY_WORDS = 120
MAX_K = 10


@dataclass(frozen=True)
class FoundChunk:
    """Um trecho recuperado, com a obra de onde veio."""

    book_id: str
    title: str
    author: str
    page_index: int
    page_label: str | None
    text: str
    score: float


class SearchStore(Protocol):
    """O que a busca precisa do armazenamento."""

    def search_chunks(
        self,
        *,
        embedding: str,
        scope: str,
        book_id: str | None,
        k: int,
        min_score: float,
    ) -> list[dict]: ...


class QueryEmbedder(Protocol):
    def embed_query(self, text: str) -> Sequence[float]: ...


@dataclass(frozen=True)
class SearchResult:
    hits: tuple[FoundChunk, ...]
    word_count: int
    truncated: bool
    min_score: float


def limit_words(text: str, limit: int = MAX_QUERY_WORDS) -> tuple[str, bool]:
    """Corta o texto no teto de palavras, dizendo se cortou."""
    palavras = text.split()
    if len(palavras) <= limit:
        return text.strip(), False
    return " ".join(palavras[:limit]), True


def find_connections(
    text: str,
    *,
    scope: str,
    book_id: str | None,
    k: int,
    min_score: float,
    floor: float = 0.0,
    embedder: QueryEmbedder,
    store: SearchStore,
) -> SearchResult:
    """Trechos mais próximos do texto consultado.

    O escopo é exclusivo: ou o leitor quer conexões com outros livros, ou quer
    paralelos dentro da obra aberta. Para os paralelos internos é obrigatório
    dizer qual é a obra.
    """
    if not text.strip():
        raise InvalidInput("o texto da consulta está vazio")
    if scope == "same" and not book_id:
        raise InvalidInput(
            "para procurar paralelos dentro da obra, é preciso dizer qual é a obra"
        )
    if not 1 <= k <= MAX_K:
        raise InvalidInput(f"a quantidade de conexões precisa ficar entre 1 e {MAX_K}")

    # O piso é da instalação e o pedido do leitor só sobe: pedir abaixo dele é
    # lido como "use o piso", e nunca como erro — o valor usado volta na
    # resposta, para a tela não oferecer um ajuste que o motor ignoraria.
    limiar = max(min_score, floor)

    consulta, truncado = limit_words(text)
    vetor = embedder.embed_query(consulta)
    linhas = store.search_chunks(
        embedding=_halfvec(vetor),
        scope=scope,
        book_id=book_id,
        k=k,
        min_score=limiar,
    )
    hits = tuple(
        FoundChunk(
            book_id=str(linha["book_id"]),
            title=linha["title"],
            author=linha["author"],
            page_index=linha["page_index"],
            page_label=linha["page_label"],
            text=linha["text"],
            score=float(linha["score"]),
        )
        for linha in linhas
    )
    return SearchResult(
        hits=hits, word_count=len(consulta.split()), truncated=truncado, min_score=limiar
    )


def _halfvec(vector: Sequence[float]) -> str:
    return "[" + ",".join(f"{valor:.6g}" for valor in vector) + "]"
