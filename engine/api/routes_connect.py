"""Rotas de conexões e de interpretação.

São duas chamadas separadas, emitidas em paralelo pelo cliente, e recebem os
**mesmos parâmetros**: sem isso, o card falaria de trechos diferentes dos que a
evidência mostra.

A consulta fica registrada (texto, limiar, quantidade e o que voltou) — é o dado
que vai permitir sugerir tamanho de seleção e limiar por medição, em vez de por
palpite.
"""

from __future__ import annotations

from fastapi import APIRouter

from engine.api import schemas
from engine.api.deps import ConexaoDep, EmbeddingsDep, InterpretadorDep, ReaderDep
from engine.api.stores import SqlSearchStore
from engine.domain.interpret import interpret
from engine.domain.search import find_connections
from engine.infra import db

router = APIRouter(prefix="/api", tags=["conexões"])


@router.post("/connect", response_model=schemas.ConnectResponse)
def conectar(
    pedido: schemas.ConnectRequest,
    leitor: ReaderDep,
    conexao: ConexaoDep,
    embedder: EmbeddingsDep,
) -> schemas.ConnectResponse:
    """Trechos de outras obras, ou paralelos dentro da obra aberta."""
    with conexao.cursor() as cursor:
        resultado = find_connections(
            pedido.text,
            scope=pedido.scope.value,
            book_id=str(pedido.book_id) if pedido.book_id else None,
            k=pedido.k,
            min_score=pedido.min_score,
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
            min_score=pedido.min_score,
            k=pedido.k,
            line=pedido.line,
            hits=[
                {"book_id": hit.book_id, "page_index": hit.page_index, "score": round(hit.score, 4)}
                for hit in resultado.hits
            ],
        )
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
    )


@router.post("/interpret", response_model=schemas.InterpretationResponse)
def interpretar(
    pedido: schemas.ConnectRequest,
    leitor: ReaderDep,
    conexao: ConexaoDep,
    embedder: EmbeddingsDep,
    interpretador_provedor: InterpretadorDep,
) -> schemas.InterpretationResponse:
    """Síntese, classificação e fontes dos mesmos trechos que a evidência mostra."""
    with conexao.cursor() as cursor:
        resultado = find_connections(
            pedido.text,
            scope=pedido.scope.value,
            book_id=str(pedido.book_id) if pedido.book_id else None,
            k=pedido.k,
            min_score=pedido.min_score,
            embedder=embedder,
            store=SqlSearchStore(cursor),
        )
        linha = pedido.line
        if linha is None:
            linha = (db.get_profile(cursor) or {}).get("current_line")

    card = interpret(
        pedido.text,
        hits=resultado.hits,
        interpreter=interpretador_provedor,
        line=linha,
    )
    return schemas.InterpretationResponse(
        card=card.card,
        relation=card.relation,
        citations=[
            schemas.Citation(
                book_id=c.book_id,
                title=c.title,
                author=c.author,
                page_index=c.page_index,
                page_label=c.page_label,
            )
            for c in card.citations
        ],
    )
