"""Testes das rotas: o contrato, não o SQL.

Cada teste confere o formato que o cliente vai consumir — nome de campo, código
de erro, validação — com banco, provedores e armazenamento dublados.
"""

from __future__ import annotations

from conftest import LEITOR, LIVRO, TAREFA


def _livro_json(**extras) -> dict:
    base = {
        "id": LIVRO,
        "title": "A Arte da Guerra",
        "author": "Sun Tzu",
        "line": "estrategia",
        "status": "ready",
        "page_count": 128,
        "n_chunks": 179,
        "ingested_at": "2026-09-16T12:00:00Z",
        "created_at": "2026-09-16T11:00:00Z",
    }
    base.update(extras)
    return base


# ---------------------------------------------------------------------------
# Sessão
# ---------------------------------------------------------------------------
def test_books_without_session_returns_unauthorized(sem_sessao):
    resposta = sem_sessao.get("/api/books")
    assert resposta.status_code == 401
    corpo = resposta.json()
    assert corpo["code"] == "unauthorized"
    assert corpo["message"]  # a mensagem que o leitor vê


def test_books_with_invalid_session_returns_unauthorized(sem_sessao):
    resposta = sem_sessao.get("/api/books", headers={"Authorization": "Bearer nao-e-token"})
    assert resposta.status_code == 401
    assert resposta.json()["code"] == "unauthorized"


# ---------------------------------------------------------------------------
# Acervo
# ---------------------------------------------------------------------------
def test_lists_books_with_contract_fields(cliente, banco):
    banco.livros = [_livro_json()]
    resposta = cliente.get("/api/books")
    assert resposta.status_code == 200
    livro = resposta.json()["books"][0]
    assert set(livro) == {
        "id", "title", "author", "line", "status", "page_count", "n_chunks",
        "ingested_at", "created_at",
    }


def test_rejects_book_without_title(cliente, pdf_com_texto):
    resposta = cliente.post(
        "/api/books",
        data={"title": " ", "author": "Sun Tzu"},
        files={"file": ("livro.pdf", pdf_com_texto, "application/pdf")},
    )
    assert resposta.status_code == 400
    assert resposta.json()["code"] == "invalid_input"


def test_rejects_file_without_text_layer(cliente, pdf_sem_texto):
    resposta = cliente.post(
        "/api/books",
        data={"title": "A Arte da Guerra", "author": "Sun Tzu"},
        files={"file": ("digitalizado.pdf", pdf_sem_texto, "application/pdf")},
    )
    assert resposta.status_code == 422
    assert resposta.json()["code"] == "text_layer_missing"


def test_accepts_book_and_creates_job(cliente, banco, arquivos, pdf_com_texto):
    resposta = cliente.post(
        "/api/books",
        data={"title": "A Arte da Guerra", "author": "Sun Tzu"},
        files={"file": ("livro.pdf", pdf_com_texto, "application/pdf")},
    )
    assert resposta.status_code == 202
    corpo = resposta.json()
    assert set(corpo) == {
        "job_id", "book_id", "estimated_texts", "quota_remaining", "quota_fits",
    }
    assert corpo["estimated_texts"] > 0
    assert corpo["quota_fits"] is True

    # O token chega ao armazenamento sem o prefixo "Bearer": com ele, o
    # armazenamento recusava o envio ("JWS Protected Header is invalid").
    from conftest import TOKEN

    _, _, token_recebido = arquivos["enviados"][0]
    assert token_recebido == TOKEN

    criado = banco.dados("create_book")
    assert criado["n_chunks"] == corpo["estimated_texts"]
    assert criado["owner_id"] == LEITOR
    assert criado["line"] == "estrategia"  # veio do perfil, sem linha no envio
    assert arquivos["enviados"], "o arquivo precisa subir para o armazenamento"


def test_replacing_the_same_file_removes_the_previous_one(cliente, banco, arquivos, pdf_com_texto):
    banco.arquivo_existente = LIVRO
    banco.livro = _livro_json(storage_path=f"{LEITOR}/{LIVRO}.pdf")

    resposta = cliente.post(
        "/api/books",
        data={"title": "A Arte da Guerra", "author": "Sun Tzu"},
        files={"file": ("livro.pdf", pdf_com_texto, "application/pdf")},
    )

    assert resposta.status_code == 202
    assert banco.chamou("delete_book")
    assert arquivos["removidos"] == [f"{LEITOR}/{LIVRO}.pdf"]


def test_patch_updates_metadata(cliente, banco):
    banco.livro = _livro_json()
    resposta = cliente.patch(f"/api/books/{LIVRO}", json={"line": "poder"})
    assert resposta.status_code == 200
    assert banco.dados("update_book")["line"] == "poder"


def test_patch_unknown_book_returns_not_found(cliente, banco):
    banco.livro = None
    resposta = cliente.patch(f"/api/books/{LIVRO}", json={"line": "poder"})
    assert resposta.status_code == 404
    assert resposta.json()["code"] == "book_not_found"


def test_delete_removes_row_and_file(cliente, banco, arquivos):
    banco.livro = _livro_json(storage_path=f"{LEITOR}/{LIVRO}.pdf")
    resposta = cliente.delete(f"/api/books/{LIVRO}")
    assert resposta.status_code == 204
    assert banco.chamou("delete_book")
    assert arquivos["removidos"] == [f"{LEITOR}/{LIVRO}.pdf"]


def test_file_forwards_the_range_request(cliente, banco, arquivos):
    banco.livro = _livro_json(storage_path=f"{LEITOR}/{LIVRO}.pdf")
    resposta = cliente.get(
        f"/api/books/{LIVRO}/file", headers={"Range": "bytes=0-9"}
    )
    assert resposta.status_code == 206
    assert arquivos["faixa"] == "bytes=0-9"
    assert resposta.headers["content-range"] == "bytes 0-9/100"


# ---------------------------------------------------------------------------
# Ingestão
# ---------------------------------------------------------------------------
def test_job_progress_returns_contract_fields(cliente, banco):
    # Tarefa já terminada: esta rota não dirige a corrente (isso é outro teste).
    banco.livro = _livro_json()
    banco.tarefa = {
        "id": TAREFA, "book_id": LIVRO, "state": "done", "next_batch": 3,
        "total_batches": 3, "total_texts": 120, "texts_embedded": 40, "error_code": None,
    }
    resposta = cliente.get(f"/api/jobs/{TAREFA}")
    assert resposta.status_code == 200
    assert set(resposta.json()) == {"id", "book_id", "state", "processed", "total", "error_code"}
    # `total` conta TRECHOS (o que o livro terá), não lotes: é o que permite
    # ao cliente montar uma fração de progresso honesta.
    assert resposta.json()["total"] == 120
    assert resposta.json()["processed"] == 40


def test_job_progress_drives_one_batch_and_finishes(cliente, banco, arquivos, pdf_com_texto):
    """Uma página de texto cabe num lote: a consulta leva a tarefa até o fim."""
    arquivos["conteudo"] = pdf_com_texto
    banco.livro = _livro_json(status="preparing", storage_path=f"{LEITOR}/{LIVRO}.pdf")
    banco.tarefa = {
        "id": TAREFA, "book_id": LIVRO, "state": "queued", "next_batch": 0,
        "total_batches": 1, "total_texts": 6, "texts_embedded": 0, "error_code": None,
    }

    resposta = cliente.get(f"/api/jobs/{TAREFA}")

    assert resposta.status_code == 200
    assert banco.chamou("advance_job")
    assert banco.dados("advance_job")["state"] == "done"
    assert banco.chamou("finish_book")
    assert resposta.json()["state"] == "done"
    assert resposta.json()["processed"] > 0


def test_job_progress_does_nothing_when_already_done(cliente, banco):
    banco.livro = _livro_json()
    banco.tarefa = {
        "id": TAREFA, "book_id": LIVRO, "state": "done", "next_batch": 3,
        "total_batches": 3, "total_texts": 120, "texts_embedded": 40, "error_code": None,
    }
    resposta = cliente.get(f"/api/jobs/{TAREFA}")
    assert resposta.status_code == 200
    assert not banco.chamou("advance_job")


def test_falha_no_lote_marca_tarefa_e_livro_e_devolve_a_causa(
    cliente, banco, arquivos, pdf_com_texto
):
    """Falha no lote: registra a falha e devolve a CAUSA, sem mascará-la.

    A transação do pedido pode estar morta quando o erro acontece — se o
    registro da falha dependesse dela, a causa real desapareceria.
    """
    from engine.api import deps
    from engine.core.errors import QuotaExhausted

    arquivos["conteudo"] = pdf_com_texto
    banco.livro = _livro_json(status="preparing", storage_path=f"{LEITOR}/{LIVRO}.pdf")
    banco.tarefa = {
        "id": TAREFA, "book_id": LIVRO, "state": "queued", "next_batch": 0,
        "total_batches": 1, "total_texts": 6, "texts_embedded": 0, "error_code": None,
    }

    class EmbedderQueFalha:
        def embed_documents(self, textos):
            raise QuotaExhausted("a cota diária de embeddings acabou")

        def embed_query(self, texto):
            raise QuotaExhausted("a cota diária de embeddings acabou")

    cliente.app.dependency_overrides[deps.embeddings] = EmbedderQueFalha

    resposta = cliente.get(f"/api/jobs/{TAREFA}")

    assert resposta.status_code == 429
    assert resposta.json()["code"] == "quota_exhausted"
    assert banco.dados("fail_job")["error_code"] == "quota_exhausted"
    assert banco.chamou("fail_book")


def test_profile_reports_the_day_usage(cliente, banco):
    """O perfil carrega o consumo do dia: é o que decide se cabe nova ingestão."""
    resposta = cliente.get("/api/profile")

    assert resposta.status_code == 200
    assert resposta.json() == {
        "current_line": "estrategia",
        "texts_today": 0,
        "daily_limit": 1000,
    }


def test_job_unknown_returns_not_found(cliente, banco):
    banco.tarefa = None
    resposta = cliente.get(f"/api/jobs/{TAREFA}")
    assert resposta.status_code == 404


# ---------------------------------------------------------------------------
# Conexões e interpretação
# ---------------------------------------------------------------------------
def _hit(**extras) -> dict:
    base = {
        "book_id": LIVRO, "title": "A Arte da Guerra", "author": "Sun Tzu",
        "page_index": 21, "page_label": "18", "text": "Conhecer o inimigo...",
        "score": 0.7891,
    }
    base.update(extras)
    return base


def test_connect_returns_hits_and_records_the_query(cliente, banco):
    banco.hits = [_hit()]
    resposta = cliente.post("/api/connect", json={"text": "conhecer o inimigo"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {"hits", "word_count", "truncated"}
    assert set(corpo["hits"][0]) == {
        "book_id", "title", "author", "page_index", "page_label", "text", "score",
    }
    assert banco.chamou("save_query")
    assert banco.dados("search_chunks")["scope"] == "others"


def test_connect_truncates_the_text_and_says_so(cliente, banco):
    banco.hits = []
    resposta = cliente.post("/api/connect", json={"text": "palavra " * 200})
    assert resposta.status_code == 200
    assert resposta.json()["word_count"] == 120
    assert resposta.json()["truncated"] is True


def test_connect_requires_book_for_same_scope(cliente):
    resposta = cliente.post("/api/connect", json={"text": "conexoes", "scope": "same"})
    assert resposta.status_code == 400
    assert resposta.json()["code"] == "invalid_input"


def test_connect_rejects_empty_text(cliente):
    resposta = cliente.post("/api/connect", json={"text": "   "})
    assert resposta.status_code == 400


def test_pedido_fora_do_formato_responde_no_formato_do_contrato(cliente):
    """Quantidade acima do teto: erro do contrato, não o formato do FastAPI."""
    resposta = cliente.post("/api/connect", json={"text": "conexoes", "k": 99})
    assert resposta.status_code == 400
    assert resposta.json()["code"] == "invalid_input"
    assert resposta.json()["message"]


def test_connect_passes_the_excluded_book(cliente, banco):
    banco.hits = []
    cliente.post("/api/connect", json={"text": "conexoes", "book_id": LIVRO})
    assert banco.dados("search_chunks")["book_id"] == LIVRO
    assert banco.dados("search_chunks")["scope"] == "others"


def test_interpret_returns_card_relation_and_citations(cliente, banco, interpretador):
    banco.hits = [_hit()]
    resposta = cliente.post("/api/interpret", json={"text": "conhecer o inimigo"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["relation"] == "complement"
    assert corpo["card"]
    assert set(corpo["citations"][0]) == {
        "book_id", "title", "author", "page_index", "page_label",
    }
    assert interpretador.pedidos, "o modelo precisa ter sido chamado"


def test_interpret_without_hits_does_not_call_the_model(cliente, banco, interpretador):
    banco.hits = []
    resposta = cliente.post("/api/interpret", json={"text": "conhecer o inimigo"})
    assert resposta.status_code == 200
    assert resposta.json()["relation"] is None
    assert resposta.json()["citations"] == []
    assert not interpretador.pedidos


def test_interpret_falls_back_when_answer_is_not_json(cliente, banco, interpretador):
    banco.hits = [_hit()]
    interpretador.resposta = "Desculpe, não consegui responder em JSON."
    resposta = cliente.post("/api/interpret", json={"text": "conhecer o inimigo"})
    assert resposta.status_code == 200
    assert resposta.json()["relation"] is None
    assert "Desculpe" in resposta.json()["card"]


# ---------------------------------------------------------------------------
# Perfil
# ---------------------------------------------------------------------------
def test_profile_reads_the_current_line(cliente):
    resposta = cliente.get("/api/profile")
    assert resposta.status_code == 200
    assert resposta.json()["current_line"] == "estrategia"


def test_profile_updates_the_current_line(cliente, banco):
    resposta = cliente.patch("/api/profile", json={"current_line": "poder"})
    assert resposta.status_code == 200
    assert banco.dados("set_current_line")["line"] == "poder"
    assert resposta.json()["current_line"] == "poder"


# ---------------------------------------------------------------------------
# Contrato publicado
# ---------------------------------------------------------------------------
def test_openapi_pins_the_contract_field_names(cliente):
    esquema = cliente.get("/openapi.json").json()
    componentes = esquema["components"]["schemas"]
    assert set(componentes["IngestionAccepted"]["properties"]) == {
        "job_id", "book_id", "estimated_texts", "quota_remaining", "quota_fits",
    }
    assert set(componentes["Hit"]["properties"]) == {
        "book_id", "title", "author", "page_index", "page_label", "text", "score",
    }
    assert set(componentes["InterpretationResponse"]["properties"]) == {
        "card", "relation", "citations",
    }
    assert set(componentes["ErrorResponse"]["properties"]) == {"code", "message", "detail"}
    assert set(esquema["paths"]) == {
        "/api/books", "/api/books/{book_id}", "/api/books/{book_id}/file",
        "/api/jobs/{job_id}", "/api/connect", "/api/interpret", "/api/profile",
    }
