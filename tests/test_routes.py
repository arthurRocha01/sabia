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
        "id", "title", "author", "status", "page_count", "n_chunks",
        "ingested_at", "created_at",
    }
    # O livro não carrega linha: ela é corrente, do perfil, e lida na consulta.
    assert "line" not in livro


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
    assert "line" not in criado, "o livro não guarda linha de aprendizado"
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
    resposta = cliente.patch(f"/api/books/{LIVRO}", json={"title": "A Arte da Guerra (ed. 2)"})
    assert resposta.status_code == 200
    mudanca = banco.dados("update_book")
    assert mudanca["title"] == "A Arte da Guerra (ed. 2)"
    # A linha saiu do livro: mandá-la não muda nada.
    assert "line" not in mudanca


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
        "card_length": "default",
        "interpretation_profile": "",
        "texts_today": 0,
        "daily_limit": 1000,
        "queries_today": 0,
        "connections_today": 0,
        "min_score_floor": 0.65,
    }


def test_profile_reports_the_day_activity(cliente, banco):
    """Consultas e conexões do dia saem do registro de calibração."""
    banco.consultas_hoje = 4
    banco.conexoes_hoje = 11
    corpo = cliente.get("/api/profile").json()
    assert corpo["queries_today"] == 4
    assert corpo["connections_today"] == 11
    assert banco.dados("activity_today")["owner_id"] == LEITOR


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
    assert set(corpo) == {
        "hits", "word_count", "truncated", "min_score", "card", "relation", "citations",
    }
    assert corpo["relation"] == "complement"
    assert corpo["card"]
    # Sem MIN_SCORE_FLOOR no ambiente, vale o padrão da instalação.
    assert corpo["min_score"] == 0.65
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


def test_interpretation_comes_in_the_same_response(cliente, banco, interpretador):
    """O card e a evidência num pedido só: o cliente não junta dois estados."""
    banco.hits = [_hit()]
    resposta = cliente.post("/api/connect", json={"text": "conhecer o inimigo"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["relation"] == "complement"
    assert corpo["card"]
    assert set(corpo["citations"][0]) == {
        "book_id", "title", "author", "page_index", "page_label",
    }
    assert interpretador.pedidos, "o modelo precisa ter sido chamado"


def test_without_hits_the_model_is_not_called(cliente, banco, interpretador):
    """Sem trecho acima do limiar, o card é a frase-guarda e nada é chamado."""
    banco.hits = []
    resposta = cliente.post("/api/connect", json={"text": "conhecer o inimigo"})
    assert resposta.status_code == 200
    assert resposta.json()["relation"] is None
    assert resposta.json()["citations"] == []
    assert resposta.json()["card"], "a frase-guarda é do motor, não do modelo"
    assert not interpretador.pedidos


def test_the_card_length_changes_the_prompt(cliente, banco, interpretador):
    """O tamanho é valor que a política referencia: muda a redação, não a política."""
    from engine.domain.policy import POLICY_VERSION

    banco.hits = [_hit()]
    banco.perfil["card_length"] = "long"
    cliente.post("/api/connect", json={"text": "conhecer o inimigo"})
    assert "oito frases" in interpretador.pedidos[0]
    assert banco.dados("save_query")["card_length"] == "long"
    assert banco.dados("save_query")["policy_version"] == POLICY_VERSION


def test_free_card_length_lets_the_material_decide(cliente, banco, interpretador):
    banco.hits = [_hit()]
    banco.perfil["card_length"] = "free"
    cliente.post("/api/connect", json={"text": "conhecer o inimigo"})
    assert "tão longa quanto o material pedir" in interpretador.pedidos[0]


def test_the_query_records_the_effective_line_and_size(cliente, banco):
    """Registra-se o que foi usado, não o que foi pedido: o resto veio do perfil."""
    banco.hits = []
    cliente.post("/api/connect", json={"text": "conexoes"})
    registro = banco.dados("save_query")
    assert registro["line"] == "estrategia"
    assert registro["card_length"] == "default"


def test_the_floor_holds_even_when_the_reader_asks_below(cliente, banco):
    """O piso é da instalação: o pedido só sobe, e o valor usado volta na resposta."""
    banco.hits = []
    resposta = cliente.post("/api/connect", json={"text": "conexoes", "min_score": 0.1})
    assert resposta.status_code == 200
    assert banco.dados("search_chunks")["min_score"] == 0.65
    assert resposta.json()["min_score"] == 0.65


def test_model_failure_does_not_take_the_evidence(cliente, banco, interpretador, monkeypatch):
    """Card que não volta não pode custar os trechos: a busca já deu certo."""
    banco.hits = [_hit()]

    def explodir(prompt: str) -> str:
        from engine.core.errors import TimedOut

        raise TimedOut("o modelo não respondeu a tempo")

    monkeypatch.setattr(interpretador, "interpret", explodir)
    resposta = cliente.post("/api/connect", json={"text": "conhecer o inimigo"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo["hits"]) == 1
    assert corpo["card"] is None
    assert corpo["relation"] is None
    assert corpo["citations"] == []


def test_answer_out_of_json_falls_back_to_the_raw_text(cliente, banco, interpretador):
    banco.hits = [_hit()]
    interpretador.resposta = "Desculpe, não consegui responder em JSON."
    resposta = cliente.post("/api/connect", json={"text": "conhecer o inimigo"})
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
    # O tamanho do card não é tocado por uma mudança que não falou dele.
    assert not banco.chamou("set_card_length")


def test_profile_returns_the_default_card_length(cliente):
    assert cliente.get("/api/profile").json()["card_length"] == "default"


def test_profile_updates_the_card_length(cliente, banco):
    resposta = cliente.patch("/api/profile", json={"card_length": "long"})
    assert resposta.status_code == 200
    assert banco.dados("set_card_length")["card_length"] == "long"
    assert resposta.json()["card_length"] == "long"


def test_profile_returns_an_empty_interpretation_profile(cliente):
    assert cliente.get("/api/profile").json()["interpretation_profile"] == ""


def test_profile_updates_the_interpretation_profile(cliente, banco):
    texto = "Valorize a contradição e seja direto; sem metáfora."
    resposta = cliente.patch("/api/profile", json={"interpretation_profile": texto})
    assert resposta.status_code == 200
    assert banco.dados("set_interpretation_profile")["texto"] == texto
    assert resposta.json()["interpretation_profile"] == texto
    # Perfil de interpretação não é a linha de aprendizado: mexer num não toca o outro.
    assert not banco.chamou("set_current_line")


def test_the_reader_preferences_enter_the_prompt_with_hierarchy(cliente, banco, interpretador):
    """O texto do leitor entra em seção nomeada, e não como igual à política."""
    banco.hits = [_hit()]
    banco.perfil["interpretation_profile"] = "Valorize a contradição e seja direto."
    cliente.post("/api/connect", json={"text": "conhecer o inimigo"})
    prompt = interpretador.pedidos[0]
    assert "Preferências do leitor" in prompt
    assert "Valorize a contradição e seja direto." in prompt
    assert "não mudam o" in prompt
    assert "formato da resposta" in prompt
    # A política continua no lugar dela, e a consulta guarda o que foi usado.
    assert "Não invente" in prompt
    registro = banco.dados("save_query")
    assert registro["interpretation_profile"] == "Valorize a contradição e seja direto."


def test_without_preferences_the_section_does_not_appear(cliente, banco, interpretador):
    banco.hits = [_hit()]
    banco.perfil["interpretation_profile"] = "   "
    cliente.post("/api/connect", json={"text": "conhecer o inimigo"})
    assert "Preferências do leitor" not in interpretador.pedidos[0]


def test_profile_rejects_a_patch_with_nothing_to_change(cliente):
    resposta = cliente.patch("/api/profile", json={})
    assert resposta.status_code == 400
    assert resposta.json()["code"] == "invalid_input"


# ---------------------------------------------------------------------------
# Contrato publicado
# ---------------------------------------------------------------------------
def test_no_cors_by_default_and_cors_only_for_declared_origins():
    """O motor não abre porta para qualquer origem: quem precisa declara."""
    from fastapi.testclient import TestClient

    from engine.api.app import create_app

    fechado = TestClient(create_app()).get("/api/books", headers={"Origin": "https://de.fora"})
    assert "access-control-allow-origin" not in fechado.headers

    aberto = TestClient(create_app(("https://declarado.exemplo",))).get(
        "/api/books", headers={"Origin": "https://declarado.exemplo"}
    )
    assert aberto.headers["access-control-allow-origin"] == "https://declarado.exemplo"


def test_openapi_pins_the_contract_field_names(cliente):
    esquema = cliente.get("/openapi.json").json()
    componentes = esquema["components"]["schemas"]
    assert set(componentes["IngestionAccepted"]["properties"]) == {
        "job_id", "book_id", "estimated_texts", "quota_remaining", "quota_fits",
    }
    assert set(componentes["Hit"]["properties"]) == {
        "book_id", "title", "author", "page_index", "page_label", "text", "score",
    }
    assert set(componentes["ConnectResponse"]["properties"]) == {
        "hits", "word_count", "truncated", "min_score", "card", "relation", "citations",
    }
    assert set(componentes["ErrorResponse"]["properties"]) == {"code", "message", "detail"}
    assert set(esquema["paths"]) == {
        "/api/books", "/api/books/{book_id}", "/api/books/{book_id}/file",
        "/api/jobs/{job_id}", "/api/connect", "/api/profile",
    }
