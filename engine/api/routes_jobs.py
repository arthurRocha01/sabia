"""Rota de progresso da ingestão.

A consulta de progresso **move a corrente de lotes**: é ela que dispara o lote
seguinte quando há trabalho pendente. Nesta arquitetura não há ninguém de
plantão entre as invocações, então o empurrão vem de quem já está consultando.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from engine.api import schemas
from engine.api.deps import ConexaoDep, ConfigDep, EmbeddingsDep, ReaderDep, TokenDep
from engine.api.stores import SqlIngestStore
from engine.core.errors import BookNotFound
from engine.domain.ingest import plan_batches, prepare, run_batch
from engine.infra import db, storage
from engine.infra.pdf import read_book

router = APIRouter(prefix="/api", tags=["ingestão"])

PENDENTES = ("queued", "running")


@router.get("/jobs/{job_id}", response_model=schemas.JobProgress)
def progresso(
    job_id: UUID,
    leitor: ReaderDep,
    settings: ConfigDep,
    conexao: ConexaoDep,
    embedder: EmbeddingsDep,
    token: TokenDep = "",
) -> schemas.JobProgress:
    """Estado da tarefa — e, havendo lote pendente, o lote seguinte."""
    with conexao.cursor() as cursor:
        tarefa = db.get_job(cursor, str(job_id))
        if not tarefa:
            raise BookNotFound("tarefa não encontrada")
        livro = db.get_book(cursor, str(tarefa["book_id"]))
        if not livro:
            raise BookNotFound("tarefa sem livro correspondente")

        if tarefa["state"] in PENDENTES and db.start_job(cursor, str(job_id)):
            try:
                _processa(
                    cursor, tarefa, livro, str(job_id), leitor.id, settings, embedder, token
                )
            except Exception as erro:
                _registra_falha(conexao, str(job_id), str(tarefa["book_id"]), erro)
                raise
        depois = db.get_job(cursor, str(job_id)) or tarefa
        return _progresso(depois)


def _registra_falha(conexao, job_id: str, book_id: str, erro: Exception) -> None:
    """Marca a tarefa e o livro como falhados, sem depender da transação que faliu.

    Se o erro veio do banco, a transação do pedido já está morta: qualquer
    instrução nela é recusada. Então desfaz o que houver e registra a falha numa
    transação nova — e se nem isso der certo, o erro original é que aparece,
    porque mascarar a causa é pior do que não registrar.
    """
    codigo = getattr(erro, "code", "internal_error")
    try:
        conexao.rollback()
        with conexao.cursor() as cursor:
            db.fail_job(cursor, job_id=job_id, error_code=codigo)
            db.fail_book(cursor, book_id=book_id)
        conexao.commit()
    except Exception:  # noqa: BLE001 - o erro original é o que importa
        import logging

        logging.getLogger(__name__).exception(
            "não foi possível registrar a falha da tarefa %s", job_id
        )


def _processa(cursor, tarefa, livro, job_id, owner_id, settings, embedder, token) -> None:
    """Baixa o arquivo, refaz a preparação e processa um lote.

    A preparação é refeita a cada invocação de propósito: ela é local, rápida e
    determinística, então o ponto de continuação pode ser um número de lote em
    vez de texto guardado no banco.
    """
    dados = storage.download(settings.supabase_url, livro["storage_path"], token=token)
    preparado = prepare(read_book(dados))
    lotes = plan_batches(preparado.chunks)
    indice = int(tarefa["next_batch"])
    if indice >= len(lotes):
        db.finish_book(
            cursor,
            book_id=str(tarefa["book_id"]),
            n_chunks=int(tarefa["texts_embedded"]),
        )
        return

    store = SqlIngestStore(
        cursor, book_id=str(tarefa["book_id"]), owner_id=owner_id, job_id=job_id
    )
    resultado = run_batch(preparado, lotes, index=indice, embedder=embedder, store=store)
    if resultado.done:
        db.finish_book(
            cursor,
            book_id=str(tarefa["book_id"]),
            n_chunks=int(tarefa["texts_embedded"]) + resultado.texts,
        )


def _progresso(tarefa: dict) -> schemas.JobProgress:
    return schemas.JobProgress(
        id=tarefa["id"],
        book_id=tarefa["book_id"],
        state=tarefa["state"],
        processed=tarefa["texts_embedded"],
        total=tarefa["total_batches"],
        error_code=tarefa["error_code"],
    )
