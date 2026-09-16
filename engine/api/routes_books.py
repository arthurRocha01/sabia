"""Rotas do acervo.

Enviar, listar, editar metadados, remover e servir o arquivo do livro.

O envio faz o portão inteiro antes de gravar qualquer coisa: confere o que o
leitor informou, extrai o texto e mede o livro. Fonte sem camada de texto é
recusada aqui — a ausência desse portão no POC queimou cota com lixo.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, Header, Response, UploadFile, status

from engine.api import schemas
from engine.api.deps import AutorizacaoDep, ConexaoDep, ConfigDep, ReaderDep
from engine.api.stores import StorageFiles
from engine.core.errors import BookNotFound
from engine.domain.books import file_hash, quota_from, validate_meta
from engine.domain.ingest import plan_batches, prepare
from engine.infra import db, storage
from engine.infra.pdf import read_book

router = APIRouter(prefix="/api", tags=["acervo"])


@router.get("/books", response_model=schemas.BooksResponse)
def listar(leitor: ReaderDep, conexao: ConexaoDep) -> schemas.BooksResponse:
    """Acervo de quem pediu, do mais recente para o mais antigo."""
    with conexao.cursor() as cursor:
        return schemas.BooksResponse(books=db.list_books(cursor, leitor.id))


@router.post(
    "/books",
    response_model=schemas.IngestionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enviar(
    leitor: ReaderDep,
    settings: ConfigDep,
    conexao: ConexaoDep,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()],
    author: Annotated[str, Form()],
    line: Annotated[str | None, Form()] = None,
    authorization: AutorizacaoDep = None,
) -> schemas.IngestionAccepted:
    """Recebe o arquivo e devolve a tarefa de ingestão.

    Reenviar o mesmo arquivo substitui o livro anterior: a identidade é o
    resumo do conteúdo, porque na web não há caminho de arquivo.
    """
    dados = await file.read()
    with conexao.cursor() as cursor:
        perfil = db.get_profile(cursor) or {}
        linha = (line if line is not None else perfil.get("current_line")) or ""
        meta = validate_meta(title, author, linha)

        # Portão: nada é gravado antes disto.
        preparado = prepare(read_book(dados))
        lotes = plan_batches(preparado.chunks)
        resumo = file_hash(dados)
        arquivos = StorageFiles(settings.supabase_url, authorization or "")

        anterior = db.find_book(cursor, leitor.id, resumo)
        if anterior:
            antigo = db.get_book(cursor, anterior) or {}
            db.delete_book(cursor, anterior)
            if antigo.get("storage_path"):
                arquivos.remove(antigo["storage_path"])

        livro = str(uuid4())
        caminho = storage.object_path(leitor.id, livro)
        db.create_book(
            cursor,
            book_id=livro,
            owner_id=leitor.id,
            title=meta.title,
            author=meta.author,
            line=meta.line,
            file_hash=resumo,
            storage_path=caminho,
            page_count=preparado.page_count,
            n_chunks=len(preparado.chunks),
            segment_map=preparado.segment_map(),
        )
        arquivos.upload(caminho, dados)
        tarefa = db.create_job(
            cursor, owner_id=leitor.id, book_id=livro, total_batches=len(lotes)
        )
        cota = quota_from(
            settings.quota_daily_texts, db.texts_embedded_today(cursor, leitor.id)
        )
        return schemas.IngestionAccepted(
            job_id=tarefa,
            book_id=livro,
            estimated_texts=len(preparado.chunks),
            quota_remaining=cota.remaining,
            quota_fits=cota.fits(len(preparado.chunks)),
        )


@router.patch("/books/{book_id}", response_model=schemas.Book)
def editar(
    book_id: UUID,
    mudanca: schemas.BookUpdate,
    leitor: ReaderDep,
    conexao: ConexaoDep,
) -> schemas.Book:
    """Edita título, autor ou linha: é metadado, nada é re-ingerido."""
    with conexao.cursor() as cursor:
        if not db.get_book(cursor, str(book_id)):
            raise BookNotFound("livro não encontrado no seu acervo")
        db.update_book(
            cursor,
            str(book_id),
            title=mudanca.title,
            author=mudanca.author,
            line=mudanca.line,
        )
        return schemas.Book(**db.get_book(cursor, str(book_id)))


@router.delete("/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(
    book_id: UUID,
    leitor: ReaderDep,
    settings: ConfigDep,
    conexao: ConexaoDep,
    authorization: AutorizacaoDep = None,
) -> Response:
    """Remove o livro, os trechos (em cascata) e o arquivo."""
    with conexao.cursor() as cursor:
        livro = db.get_book(cursor, str(book_id))
        if not livro:
            raise BookNotFound("livro não encontrado no seu acervo")
        db.delete_book(cursor, str(book_id))
        StorageFiles(settings.supabase_url, authorization or "").remove(
            livro["storage_path"]
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/books/{book_id}/file")
def arquivo(
    book_id: UUID,
    leitor: ReaderDep,
    settings: ConfigDep,
    conexao: ConexaoDep,
    authorization: AutorizacaoDep = None,
    range: Annotated[str | None, Header()] = None,
) -> Response:
    """Serve o PDF do livro, repassando o pedido de faixa do leitor de PDF."""
    with conexao.cursor() as cursor:
        livro = db.get_book(cursor, str(book_id))
    if not livro:
        raise BookNotFound("livro não encontrado no seu acervo")

    codigo, corpo, cabecalhos = storage.fetch(
        settings.supabase_url,
        livro["storage_path"],
        token=authorization or "",
        range_header=range,
    )
    return Response(content=corpo, status_code=codigo, headers=cabecalhos)
