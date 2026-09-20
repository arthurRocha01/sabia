"""Conexões e interpretação: um fluxo, uma chamada.

O cliente faz **um** pedido e recebe tudo junto — os trechos e o card. Dividir em
duas chamadas custava duas buscas e dois embeddings por consulta (contra a cota),
dava duas chances de as metades falarem de trechos diferentes e obrigava a tela a
juntar dois estados.

A evidência não depende do modelo: se a interpretação falhar ou estourar o tempo,
os trechos vêm completos e o card vem vazio. Nunca é tela de erro quando a busca
deu certo.

A consulta fica registrada (texto, limiar, quantidade e o que voltou) — é o dado
que vai permitir sugerir tamanho de seleção e limiar por medição, em vez de por
palpite. O registro acontece antes da chamada ao modelo, para não se perder.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from engine.api import schemas
from engine.api.deps import (
    ConexaoDep,
    ConfigDep,
    EmbeddingsDep,
    InterpretadorDep,
    ReaderDep,
)
from engine.api.stores import SqlSearchStore
from engine.core.errors import ProviderUnavailable, TimedOut
from engine.domain.interpret import Interpretation, interpret
from engine.domain.search import SearchResult, find_connections
from engine.infra import db

router = APIRouter(prefix="/api", tags=["conexões"])


def _interpretar(
    texto: str,
    resultado: SearchResult,
    *,
    linha: str | None,
    interpretador: InterpretadorDep,
) -> Interpretation | None:
    """A interpretação, ou nada quando o modelo não responde.

    Falha de tempo ou de provedor não é erro do pedido: os trechos já são
    resposta. O erro é engolido de propósito, e o card vazio conta o que houve.
    """
    try:
        return interpret(texto, hits=resultado.hits, interpreter=interpretador, line=linha)
    except (TimedOut, ProviderUnavailable):
        return None


@router.post("/connect", response_model=schemas.ConnectResponse)
def conectar(
    pedido: schemas.ConnectRequest,
    leitor: ReaderDep,
    conexao: ConexaoDep,
    embedder: EmbeddingsDep,
    interpretador: InterpretadorDep,
    configuracao: ConfigDep,
) -> schemas.ConnectResponse:
    """Trechos de outras obras (ou paralelos na obra aberta) e o card que os liga."""
    with conexao.cursor() as cursor:
        resultado = find_connections(
            pedido.text,
            scope=pedido.scope.value,
            book_id=str(pedido.book_id) if pedido.book_id else None,
            k=pedido.k,
            min_score=pedido.min_score,
            floor=configuracao.min_score_floor,
            embedder=embedder,
            store=SqlSearchStore(cursor),
        )
        db.save_query(
            cursor,
            owner_id=leitor.id,
            book_id=str(pedido.book_id) if pedido.book_id else None,
            query_text=pedido.text,
            word_count=resultado.word_count,
            scope=pedido.scope.value,
            min_score=resultado.min_score,
            k=pedido.k,
            line=pedido.line,
            hits=[
                {"book_id": hit.book_id, "page_index": hit.page_index, "score": round(hit.score, 4)}
                for hit in resultado.hits
            ],
        )
        linha = pedido.line
        if linha is None:
            linha = (db.get_profile(cursor) or {}).get("current_line")

    card = _interpretar(pedido.text, resultado, linha=linha, interpretador=interpretador)
    return schemas.ConnectResponse(
        hits=[
            schemas.Hit(
                book_id=hit.book_id,
                title=hit.title,
                author=hit.author,
                page_index=hit.page_index,
                page_label=hit.page_label,
                text=hit.text,
                score=hit.score,
            )
            for hit in resultado.hits
        ],
        word_count=resultado.word_count,
        truncated=resultado.truncated,
        min_score=resultado.min_score,
        card=card.card if card else None,
        relation=schemas.Relation(card.relation) if card and card.relation else None,
        citations=(
            [
                schemas.Citation(
                    book_id=UUID(c.book_id),
                    title=c.title,
                    author=c.author,
                    page_index=c.page_index,
                    page_label=c.page_label,
                )
                for c in card.citations
            ]
            if card
            else []
        ),
    )
