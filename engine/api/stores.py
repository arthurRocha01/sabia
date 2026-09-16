"""Adaptadores entre o domínio e a infraestrutura.

Responsabilidade: ligar as interfaces que o domínio pede (busca, gravação,
arquivos) às peças que falam com o banco e com o armazenamento, já presos ao
leitor e ao livro desta requisição.

É aqui que o "o que gravar" vira instrução SQL — e só aqui. O domínio continua
sem saber que existe Postgres.
"""

from __future__ import annotations

from collections.abc import Sequence

import psycopg

from engine.infra import db, storage


class SqlSearchStore:
    """Busca por similaridade, pela conexão do leitor."""

    def __init__(self, cursor: psycopg.Cursor) -> None:
        self.cursor = cursor

    def search_chunks(
        self, *, embedding: str, scope: str, book_id: str | None, k: int, min_score: float
    ) -> list[dict]:
        return db.search_chunks(
            self.cursor,
            embedding=embedding,
            scope=scope,
            book_id=book_id,
            k=k,
            min_score=min_score,
        )


class SqlIngestStore:
    """Gravação de um lote da ingestão, presa a um livro e a uma tarefa."""

    def __init__(
        self, cursor: psycopg.Cursor, *, book_id: str, owner_id: str, job_id: str
    ) -> None:
        self.cursor = cursor
        self.book_id = book_id
        self.owner_id = owner_id
        self.job_id = job_id
        self.saved = 0

    def save_chunks(
        self, *, segment: str, items: Sequence[tuple[str, int, str | None, Sequence[float]]]
    ) -> int:
        quantos = db.save_chunks(
            self.cursor,
            book_id=self.book_id,
            owner_id=self.owner_id,
            segment=segment,
            items=items,
        )
        self.saved += quantos
        return quantos

    def advance(self, *, next_batch: int, texts: int, done: bool) -> None:
        """Grava o ponto de continuação.

        Terminando, a tarefa fica `done`; faltando lote, ela volta a `queued` —
        é o que permite a próxima consulta de progresso pegar o lote seguinte,
        sem que duas invocações peguem o mesmo.
        """
        db.advance_job(
            self.cursor,
            job_id=self.job_id,
            next_batch=next_batch,
            texts_embedded=texts,
            state="done" if done else "queued",
        )


class StorageFiles:
    """Arquivos do livro, pelas políticas do bucket (token do leitor)."""

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url
        self.token = token

    def upload(self, path: str, data: bytes) -> None:
        storage.upload(self.base_url, path, data, token=self.token)

    def remove(self, path: str) -> None:
        storage.remove(self.base_url, path, token=self.token)
