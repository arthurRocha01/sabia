"""Dublês dos testes de rota.

Os testes de rota conferem o **contrato** — formato, código de erro, validação,
encadeamento — e não o SQL. Banco, provedores e armazenamento entram dublados; o
acesso real a banco é verificado por script, contra o banco de verdade.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from engine.api import deps
from engine.api.app import create_app
from engine.core.config import load_settings
from engine.infra import db
from engine.infra.auth import Reader

ENV = {
    "GOOGLE_API_KEY": "chave-de-teste",
    "DEEPSEEK_API_KEY": "chave-de-teste",
    "DATABASE_URL": "postgresql://usuario:senha@host.pooler.supabase.com:6543/postgres",
    "SUPABASE_URL": "https://projeto.supabase.co",
    "SUPABASE_JWKS_URL": "https://projeto.supabase.co/auth/v1/.well-known/jwks.json",
}
LEITOR = "11111111-1111-1111-1111-111111111111"
LIVRO = "22222222-2222-2222-2222-222222222222"
TAREFA = "33333333-3333-3333-3333-333333333333"
TOKEN = "token-de-teste-sem-prefixo"


class CursorFalso:
    def __enter__(self) -> CursorFalso:
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def execute(self, *_: object, **__: object) -> None: ...

    def executemany(self, *_: object, **__: object) -> None: ...

    def fetchone(self) -> None:
        return None

    def fetchall(self) -> list:
        return []


class ConexaoFalsa:
    """Conexão de mentira: as funções do banco são substituídas nos testes."""

    def __init__(self) -> None:
        self.desfez = 0
        self.confirmou = 0

    def cursor(self) -> CursorFalso:
        return CursorFalso()

    def rollback(self) -> None:
        self.desfez += 1

    def commit(self) -> None:
        self.confirmou += 1


class BancoFalso:
    """Substitui as funções de `infra/db.py` e anota o que foi chamado."""

    def __init__(self) -> None:
        self.chamadas: list[tuple[str, dict]] = []
        self.livros: list[dict] = []
        self.livro: dict | None = None
        self.tarefa: dict | None = None
        self.perfil: dict | None = {
            "id": LEITOR,
            "current_line": "estrategia",
            "card_length": "default",
            "interpretation_profile": "",
        }
        self.hits: list[dict] = []
        self.arquivo_existente: str | None = None

    def _anota(self, nome: str, **dados: object) -> None:
        self.chamadas.append((nome, dados))

    # acervo
    def list_books(self, _cursor, owner_id):
        self._anota("list_books", owner_id=owner_id)
        return self.livros

    def get_profile(self, _cursor):
        return self.perfil

    def set_current_line(self, _cursor, line):
        self._anota("set_current_line", line=line)
        self.perfil = {**(self.perfil or {}), "id": LEITOR, "current_line": line}

    def set_interpretation_profile(self, _cursor, texto):
        self._anota("set_interpretation_profile", texto=texto)
        self.perfil = {**(self.perfil or {}), "id": LEITOR, "interpretation_profile": texto}

    def set_card_length(self, _cursor, card_length):
        self._anota("set_card_length", card_length=card_length)
        self.perfil = {**(self.perfil or {}), "id": LEITOR, "card_length": card_length}

    def get_book(self, _cursor, book_id):
        self._anota("get_book", book_id=book_id)
        return self.livro

    def update_book(self, _cursor, book_id, **campos):
        self._anota("update_book", book_id=book_id, **campos)
        if self.livro:
            self.livro.update({k: v for k, v in campos.items() if v is not None})

    def delete_book(self, _cursor, book_id):
        self._anota("delete_book", book_id=book_id)

    def find_book(self, _cursor, owner_id, file_hash):
        self._anota("find_book", owner_id=owner_id, file_hash=file_hash)
        return self.arquivo_existente

    def create_book(self, _cursor, **campos):
        self._anota("create_book", **campos)
        return campos.get("book_id")

    def create_job(self, _cursor, **campos):
        self._anota("create_job", **campos)
        self.tarefa = {
            "id": TAREFA,
            "book_id": campos["book_id"],
            "state": "queued",
            "next_batch": 0,
            "total_batches": campos["total_batches"],
            "total_texts": campos["total_texts"],
            "texts_embedded": 0,
            "error_code": None,
        }
        return TAREFA

    def get_job(self, _cursor, job_id):
        self._anota("get_job", job_id=job_id)
        return self.tarefa

    def start_job(self, _cursor, job_id):
        self._anota("start_job", job_id=job_id)
        if self.tarefa and self.tarefa["state"] != "running":
            self.tarefa["state"] = "running"
            return True
        return False

    def advance_job(self, _cursor, *, job_id, next_batch, texts_embedded, state):
        self._anota("advance_job", job_id=job_id, next_batch=next_batch, state=state)
        if self.tarefa:
            self.tarefa["next_batch"] = next_batch
            self.tarefa["texts_embedded"] += texts_embedded
            self.tarefa["state"] = state

    def finish_book(self, _cursor, *, book_id, n_chunks):
        self._anota("finish_book", book_id=book_id, n_chunks=n_chunks)

    def fail_job(self, _cursor, *, job_id, error_code):
        self._anota("fail_job", job_id=job_id, error_code=error_code)

    def fail_book(self, _cursor, *, book_id):
        self._anota("fail_book", book_id=book_id)

    def texts_embedded_today(self, _cursor, owner_id):
        return 0

    def save_query(self, _cursor, **campos):
        self._anota("save_query", **campos)

    def search_chunks(self, _cursor, **campos):
        self._anota("search_chunks", **campos)
        return self.hits

    def chamou(self, nome: str) -> bool:
        return any(nome == chamada for chamada, _ in self.chamadas)

    def dados(self, nome: str) -> dict:
        return next(dados for chamada, dados in self.chamadas if chamada == nome)


class EmbedderFalso:
    def embed_query(self, text):
        return [0.1] * 8

    def embed_documents(self, texts):
        return [[0.2] * 8 for _ in texts]


class InterpretadorFalso:
    def __init__(self, resposta: str | None = None) -> None:
        self.resposta = resposta or (
            '{"relation": "complement", "used": [1],'
            ' "card": "Os dois textos tratam do mesmo problema."}'
        )
        self.pedidos: list[str] = []

    def interpret(self, prompt: str) -> str:
        self.pedidos.append(prompt)
        return self.resposta


@pytest.fixture
def settings():
    return load_settings(dict(ENV))


@pytest.fixture
def banco(monkeypatch) -> BancoFalso:
    falso = BancoFalso()
    for nome in (
        "list_books", "get_profile", "set_current_line", "get_book", "update_book",
        "delete_book", "find_book", "create_book", "create_job", "get_job",
        "start_job", "advance_job", "finish_book", "fail_job", "fail_book",
        "texts_embedded_today", "save_query", "search_chunks",
        "set_card_length", "set_interpretation_profile",
    ):
        monkeypatch.setattr(db, nome, getattr(falso, nome))
    return falso


@pytest.fixture
def arquivos(monkeypatch):
    """Dublê do armazenamento: guarda o que foi enviado, baixado e removido."""
    registro = {"enviados": [], "removidos": [], "faixa": None, "conteudo": b""}

    def upload(_base, path, data, *, token):
        registro["enviados"].append((path, len(data), token))

    def download(_base, path, *, token):
        registro["baixados"] = (path, token)
        return registro["conteudo"]

    def remove(_base, path, *, token):
        registro["removidos"].append(path)

    def fetch(_base, path, *, token, range_header=None):
        registro["faixa"] = range_header
        return 206, registro["conteudo"] or b"%PDF-faixa", {
            "content-type": "application/pdf",
            "content-range": "bytes 0-9/100",
        }

    monkeypatch.setattr("engine.infra.storage.upload", upload)
    monkeypatch.setattr("engine.infra.storage.download", download)
    monkeypatch.setattr("engine.infra.storage.remove", remove)
    monkeypatch.setattr("engine.infra.storage.fetch", fetch)
    return registro


@pytest.fixture
def interpretador() -> InterpretadorFalso:
    return InterpretadorFalso()


@pytest.fixture
def cliente(settings, banco, arquivos, interpretador) -> TestClient:
    app = create_app()
    app.dependency_overrides[deps.configuracao] = lambda: settings
    app.dependency_overrides[deps.leitor_autenticado] = lambda: Reader(
        id=LEITOR, claims={"sub": LEITOR}
    )
    app.dependency_overrides[deps.conexao_do_leitor] = ConexaoFalsa
    app.dependency_overrides[deps.token_do_leitor] = lambda: TOKEN
    app.dependency_overrides[deps.embeddings] = EmbedderFalso
    app.dependency_overrides[deps.interpretador] = lambda: interpretador
    return TestClient(app)


@pytest.fixture
def sem_sessao(settings) -> TestClient:
    """Aplicação sem dublê de identidade: para conferir a sessão inválida."""
    app = create_app()
    app.dependency_overrides[deps.configuracao] = lambda: settings
    return TestClient(app)


@pytest.fixture
def pdf_com_texto(tmp_path):
    """PDF de uma página com texto suficiente para virar trecho."""
    import pymupdf

    caminho = tmp_path / "livro.pdf"
    documento = pymupdf.open()
    pagina = documento.new_page()
    linhas = "\n".join(
        f"Linha {i}: conhecer o inimigo exige metodo, paciencia e disciplina." for i in range(12)
    )
    pagina.insert_text((60, 60), linhas, fontsize=10)
    documento.save(caminho)
    documento.close()
    return caminho.read_bytes()


@pytest.fixture
def pdf_sem_texto(tmp_path):
    import pymupdf

    caminho = tmp_path / "sem-texto.pdf"
    documento = pymupdf.open()
    for _ in range(3):
        documento.new_page().draw_rect(pymupdf.Rect(60, 60, 400, 400))
    documento.save(caminho)
    documento.close()
    return caminho.read_bytes()


def novo_id() -> str:
    return str(uuid.uuid4())
