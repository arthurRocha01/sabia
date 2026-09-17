"""Formato das respostas do motor: o contrato entre cliente e motor.

Responsabilidade: declarar, em um lugar só, os nomes de campo e os valores de
cada resposta. É daqui que sai o OpenAPI, e o cliente gera os tipos TypeScript a
partir dele — por isso o formato não é escrito duas vezes.

Convenções: nomes de campo em inglês, `snake_case`; valores de classificação e
de escopo em inglês, porque são identificadores estáveis; tudo o que o leitor lê
(mensagens de erro, texto do card) em português.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

MAX_QUERY_WORDS = 120
MAX_K = 10


class Scope(StrEnum):
    """De onde vêm as conexões.

    `others` — de outros livros do acervo (o livro aberto fica de fora).
    `same` — de dentro do próprio livro aberto.
    """

    others = "others"
    same = "same"


class Relation(StrEnum):
    """Classificação da relação entre o trecho e o que foi consultado."""

    complement = "complement"
    contradiction = "contradiction"
    nuance = "nuance"
    same_concept = "same_concept"


class BookStatus(StrEnum):
    preparing = "preparing"
    ready = "ready"
    failed = "failed"


class JobState(StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class ErrorResponse(BaseModel):
    """Formato único de erro do motor."""

    code: str = Field(description="Identificador estável do erro.")
    message: str = Field(description="Mensagem que o leitor vê, em português.")
    detail: str | None = Field(default=None, description="Explicação adicional, quando houver.")


class Book(BaseModel):
    """Um livro do acervo."""

    id: UUID
    title: str
    author: str
    line: str = Field(description="Linha de aprendizado do livro, escrita pelo usuário.")
    status: BookStatus
    page_count: int | None = None
    n_chunks: int | None = Field(default=None, description="Trechos do livro.")
    ingested_at: datetime | None = None
    created_at: datetime


class BooksResponse(BaseModel):
    books: list[Book]


class BookUpdate(BaseModel):
    """Edição de metadados: não exige re-ingerir nada."""

    title: str | None = None
    author: str | None = None
    line: str | None = None


class IngestionAccepted(BaseModel):
    """Resposta ao envio de um arquivo."""

    job_id: UUID
    book_id: UUID
    estimated_texts: int = Field(description="Trechos que o livro terá, contados na extração.")
    quota_remaining: int = Field(description="Textos que ainda cabem na cota do dia.")
    quota_fits: bool = Field(description="Se a ingestão cabe na cota do dia.")


class JobProgress(BaseModel):
    """Progresso da ingestão. Esta consulta também move a corrente de lotes."""

    id: UUID
    book_id: UUID
    state: JobState
    processed: int = Field(description="Trechos já embedados.")
    total: int | None = Field(default=None, description="Trechos que o livro terá.")
    error_code: str | None = None


class Hit(BaseModel):
    """Um trecho recuperado."""

    book_id: UUID
    title: str
    author: str
    page_index: int = Field(description="Posição física da página, base zero: é o que navega.")
    page_label: str | None = Field(default=None, description="Número impresso: é o que cita.")
    text: str
    score: float = Field(description="Similaridade de cosseno, de 0 a 1.")


class ConnectRequest(BaseModel):
    """Pedido de conexões."""

    text: str = Field(description="O trecho selecionado ou o texto consultado.")
    scope: Scope = Scope.others
    book_id: UUID | None = Field(
        default=None,
        description="Livro aberto no leitor: fica de fora em `others` e é o único em `same`.",
    )
    k: int = Field(default=3, ge=1, le=MAX_K)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    line: str | None = Field(
        default=None, description="Linha de aprendizado em uso; sem ela, usa a do perfil."
    )


class ConnectResponse(BaseModel):
    hits: list[Hit]
    word_count: int = Field(description="Palavras do texto consultado, depois do teto.")
    truncated: bool = Field(description="Se o texto consultado foi cortado no teto de palavras.")


class Citation(BaseModel):
    """Fonte de uma interpretação. Montada pelo motor, nunca pelo modelo."""

    book_id: UUID
    title: str
    author: str
    page_index: int
    page_label: str | None = None


class InterpretationResponse(BaseModel):
    """O card: síntese, classificação e fontes.

    `relation` vazia significa que a classificação não veio; o card aparece
    assim mesmo, sem selo. É o plano B do contrato, não um erro.
    """

    card: str
    relation: Relation | None = None
    citations: list[Citation]


class Profile(BaseModel):
    """A linha corrente e o consumo do dia.

    O consumo entra aqui porque é a informação que o leitor precisa ver ao
    enviar um livro: a cota é do projeto, não da conta, e o que resta no dia
    decide se cabe mais uma ingestão.
    """
    """Perfil do leitor. A linha corrente vale como padrão para novos livros."""

    current_line: Annotated[str | None, Field(default=None)] = None
    texts_today: int = 0
    daily_limit: int = 0


class ProfileUpdate(BaseModel):
    current_line: str
