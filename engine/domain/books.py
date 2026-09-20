"""Acervo: enviar, listar, editar, remover.

Responsabilidade: validar o que o leitor informou, medir o arquivo enviado e
decidir se a ingestão pode começar. O trabalho de preparar o texto é do
`ingest.py`; o de falar com o banco e com o armazenamento, do `infra/`.

Regra que vem da medição, não do gosto: **nada é gravado antes da validação**.
No POC, a ausência desse portão queimou cota com centenas de trechos de lixo.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from engine.core.errors import InvalidInput

MIN_TITLE = 2


@dataclass(frozen=True)
class NewBook:
    """O que o leitor informa no envio. Título e autor nunca são adivinhados.

    A linha de aprendizado não entra aqui: ela é corrente, do perfil, e lida na
    hora da consulta — o livro não carrega linha.
    """

    title: str
    author: str


@dataclass(frozen=True)
class Quota:
    """Situação da cota do dia."""

    daily_limit: int
    used_today: int

    @property
    def remaining(self) -> int:
        return max(self.daily_limit - self.used_today, 0)

    def fits(self, texts: int) -> bool:
        return texts <= self.remaining


class FileStore(Protocol):
    """O que o acervo precisa do armazenamento de arquivos."""

    def upload(self, path: str, data: bytes) -> None: ...

    def remove(self, path: str) -> None: ...


def validate_meta(title: str, author: str) -> NewBook:
    """Confere o que o leitor informou antes de qualquer custo."""
    titulo, autor = title.strip(), author.strip()
    if len(titulo) < MIN_TITLE:
        raise InvalidInput("informe o título do livro")
    if len(autor) < MIN_TITLE:
        raise InvalidInput("informe o autor do livro")
    return NewBook(title=titulo, author=autor)


def file_hash(data: bytes) -> str:
    """Identidade do livro na web: não há caminho de arquivo para usar."""
    return hashlib.sha256(data).hexdigest()


def quota_from(daily_limit: int, used_today: int) -> Quota:
    return Quota(daily_limit=daily_limit, used_today=used_today)
