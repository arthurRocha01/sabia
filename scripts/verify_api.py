"""Verificação ponta a ponta do motor, contra o banco e os modelos de verdade.

Cria contas de teste, entra com elas como o leitor entraria, exercita todas as
rotas e apaga tudo no fim. É verificação pontual, não teste de rotina: consome
cota de embeddings e de interpretação.

O que só este script prova:

- a identidade pelas políticas de acesso (nunca exercitadas até aqui);
- o gatilho que cria o perfil quando uma conta nasce;
- a consulta vetorial com escopo e limiar, contra o índice de verdade;
- o envio para o armazenamento, o download com faixa e a remoção;
- a corrente de lotes pela API, do envio ao livro pronto;
- o isolamento entre contas: uma não enxerga o acervo da outra.

Uso:

    PYTHONPATH=. .venv/bin/python scripts/verify_api.py

Limpa o que criou, mesmo falhando no meio.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

from dotenv import load_dotenv

load_dotenv()

import pymupdf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from engine.api.app import create_app  # noqa: E402
from engine.core.config import load_settings  # noqa: E402

RELATIONS = ("complement", "contradiction", "nuance", "same_concept")
FALHAS: list[str] = []


def confere(rotulo: str, condicao: bool, detalhe: str = "") -> None:
    marca = "OK " if condicao else "FALHA"
    print(f"  [{marca}] {rotulo}{'  ' + detalhe if detalhe else ''}")
    if not condicao:
        FALHAS.append(rotulo)


# ---------------------------------------------------------------------------
# Contas de teste (API administrativa do Supabase)
# ---------------------------------------------------------------------------
def _admin(url: str, segredo: str, metodo: str, caminho: str, corpo: dict | None = None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    requisicao = urllib.request.Request(f"{url}{caminho}", data=dados, method=metodo)
    requisicao.add_header("apikey", segredo)
    requisicao.add_header("Authorization", f"Bearer {segredo}")
    requisicao.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(requisicao, timeout=30) as resposta:  # noqa: S310
        return json.loads(resposta.read() or b"null")


def cria_conta(url: str, segredo: str, email: str, senha: str) -> str:
    criada = _admin(
        url, segredo, "POST", "/auth/v1/admin/users",
        {"email": email, "password": senha, "email_confirm": True},
    )
    return str(criada["id"])


def apaga_conta(url: str, segredo: str, usuario_id: str) -> None:
    try:
        _admin(url, segredo, "DELETE", f"/auth/v1/admin/users/{usuario_id}")
    except urllib.error.HTTPError as erro:
        print(f"  (limpeza da conta {usuario_id[:8]}… respondeu {erro.code})")


def entra(url: str, publica: str, email: str, senha: str) -> dict:
    """Entra como o leitor entraria, e devolve os cabeçalhos com o token."""
    dados = json.dumps({"email": email, "password": senha}).encode()
    requisicao = urllib.request.Request(
        f"{url}/auth/v1/token?grant_type=password", data=dados, method="POST"
    )
    requisicao.add_header("apikey", publica)
    requisicao.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(requisicao, timeout=30) as resposta:  # noqa: S310
        sessao = json.loads(resposta.read())
    return {
        "Authorization": f"Bearer {sessao['access_token']}",
        "apikey": publica,
    }


# ---------------------------------------------------------------------------
# Livros de teste
# ---------------------------------------------------------------------------
def livro_de_teste(titulo: str, assunto: str) -> bytes:
    """PDF pequeno e distinto, para gastar pouca cota."""
    documento = pymupdf.open()
    for pagina in range(4):
        folha = documento.new_page()
        linhas = "\n".join(
            f"{assunto} — parte {pagina}, linha {i}: o metodo exige disciplina, "
            f"paciencia e leitura atenta do que o outro lado faz."
            for i in range(9)
        )
        folha.insert_text((60, 60), linhas, fontsize=10)
    destino = io.BytesIO()
    documento.save(destino)
    documento.close()
    return destino.getvalue()


def main() -> int:
    settings = load_settings()
    url, segredo, publica = (
        settings.supabase_url,
        settings.supabase_secret_key,
        settings.supabase_publishable_key,
    )
    sufixo = uuid.uuid4().hex[:8]
    email_um = f"verificacao-{sufixo}@exemplo.com"
    email_dois = f"verificacao-{sufixo}-b@exemplo.com"
    senha = f"Verificacao-{sufixo}!"
    contas: list[str] = []
    app = create_app()

    try:
        print("=== contas de teste ===")
        contas.append(cria_conta(url, segredo, email_um, senha))
        contas.append(cria_conta(url, segredo, email_dois, senha))
        cabecalhos = entra(url, publica, email_um, senha)
        cliente = TestClient(app, headers=cabecalhos)
        outro = TestClient(app, headers=entra(url, publica, email_dois, senha))
        confere("entrar com a conta devolve token", bool(cabecalhos["Authorization"]))

        print("\n=== identidade e perfil (RLS e o gatilho de criação) ===")
        perfil = cliente.get("/api/profile")
        confere(
            "o perfil lê pela identidade do token",
            perfil.status_code == 200,
            str(perfil.status_code),
        )
        confere(
            "o gatilho criou o perfil junto com a conta",
            perfil.status_code == 200 and "current_line" in perfil.json(),
        )
        troca = cliente.patch("/api/profile", json={"current_line": "estrategia"})
        confere(
            "o tamanho do card começa no padrão",
            cliente.get("/api/profile").json()["card_length"] == "default",
        )
        tamanho = cliente.patch("/api/profile", json={"card_length": "long"})
        confere("o tamanho do card é atualizável", tamanho.json()["card_length"] == "long")
        confere(
            "mudar o tamanho não toca a linha corrente",
            tamanho.json()["current_line"] == "estrategia",
        )
        preferencias = cliente.patch(
            "/api/profile",
            json={"interpretation_profile": "Valorize a contradição antes da concordância."},
        )
        confere(
            "o perfil de interpretação é gravado",
            preferencias.json()["interpretation_profile"]
            == "Valorize a contradição antes da concordância.",
        )
        confere(
            "o perfil de interpretação não mexe na linha",
            preferencias.json()["current_line"] == "estrategia",
        )
        confere("a linha corrente é atualizável", troca.status_code == 200)

        print("\n=== acervo ===")
        confere("acervo novo começa vazio", cliente.get("/api/books").json()["books"] == [])

        print("\n=== envio e ingestão (corrente de lotes) ===")
        enviados = []
        for titulo, assunto in (("Livro Um", "Primeiro autor"), ("Livro Dois", "Segundo autor")):
            resposta = cliente.post(
                "/api/books",
                data={"title": titulo, "author": "Autor de teste"},
                files={
                    "file": (
                        f"{titulo}.pdf",
                        livro_de_teste(titulo, assunto),
                        "application/pdf",
                    )
                },
            )
            confere(f"envio de {titulo}", resposta.status_code == 202, str(resposta.status_code))
            enviados.append(resposta.json())

        for envio in enviados:
            estado = None
            for _ in range(12):
                consulta = cliente.get(f"/api/jobs/{envio['job_id']}")
                estado = consulta.json().get("state")
                if estado in ("done", "failed"):
                    break
            confere(
                f"ingestão concluída ({envio['estimated_texts']} trechos)",
                estado == "done",
                f"estado {estado}",
            )

        acervo = cliente.get("/api/books").json()["books"]
        confere("o acervo lista os dois livros", len(acervo) == 2, f"{len(acervo)} livros")
        prontos = all(livro["status"] == "ready" for livro in acervo)
        contados = all(livro["n_chunks"] for livro in acervo)
        confere("os livros ficaram prontos", prontos)
        confere("os trechos foram contados", contados)

        print("\n=== leitura (arquivo com faixa) ===")
        arquivo = cliente.get(f"/api/books/{acervo[0]['id']}/file", headers={"Range": "bytes=0-99"})
        confere(
            "o arquivo responde com faixa", arquivo.status_code == 206, str(arquivo.status_code)
        )
        confere("o arquivo tem conteúdo", len(arquivo.content) > 0)

        print("\n=== conexões e interpretação (modelos de verdade) ===")
        pedido = {
            "text": "conhecer o inimigo e conhecer a si mesmo exige metodo",
            "scope": "others",
            "book_id": acervo[0]["id"],
        }
        conexoes = cliente.post("/api/connect", json=pedido)
        confere("a busca responde", conexoes.status_code == 200, str(conexoes.status_code))
        corpo = conexoes.json()
        hits = corpo.get("hits", [])
        confere(
            "o limiar aplicado é o piso da instalação",
            corpo.get("min_score") == 0.65,
            f"min_score={corpo.get('min_score')}",
        )
        confere("a busca encontrou trechos no outro livro", bool(hits), f"{len(hits)} trechos")
        confere(
            "o trecho devolvido veio da outra obra",
            all(h["book_id"] != acervo[0]["id"] for h in hits),
        )
        if hits:
            print(f"    melhor score: {hits[0]['score']:.3f} — {hits[0]['text'][:60]}…")

        confere(
            "o card veio na mesma resposta",
            bool(corpo.get("card")),
            str(corpo.get("card"))[:70],
        )
        confere(
            "a classificação veio de lista fechada ou vazia",
            corpo.get("relation") in RELATIONS + (None,),
        )
        fontes = corpo.get("citations") or []
        confere("as fontes foram montadas pelo motor", bool(fontes) and "page_index" in fontes[0])

        print("\n=== isolamento entre contas ===")
        confere("a outra conta não vê acervo alheio", outro.get("/api/books").json()["books"] == [])
        alheio = outro.get(f"/api/books/{acervo[0]['id']}/file")
        confere(
            "a outra conta não abre o arquivo alheio",
            alheio.status_code == 404,
            str(alheio.status_code),
        )
        apagar = outro.delete(f"/api/books/{acervo[0]['id']}")
        confere(
            "a outra conta não remove livro alheio",
            apagar.status_code == 404,
            str(apagar.status_code),
        )

        print("\n=== remoção ===")
        remocao = cliente.delete(f"/api/books/{acervo[0]['id']}")
        confere("o livro é removido", remocao.status_code == 204, str(remocao.status_code))
        confere("o acervo ficou com um livro", len(cliente.get("/api/books").json()["books"]) == 1)
    except Exception as erro:  # noqa: BLE001 - o script relata e limpa
        FALHAS.append(f"exceção: {type(erro).__name__}: {erro}")
        import traceback

        traceback.print_exc()
    finally:
        print("\n=== limpeza ===")
        # Apagar a conta não apaga o arquivo no Storage (defeito conhecido), e um
        # livro que ficou para trás deixa pasta órfã no bucket. Os livros saem
        # pela API primeiro, que é quem remove o arquivo junto.
        try:
            for sessao in (cliente, outro):
                for livro in sessao.get("/api/books").json().get("books", []):
                    sessao.delete(f"/api/books/{livro['id']}")
        except NameError:
            pass
        for conta in contas:
            apaga_conta(url, segredo, conta)
        print(f"  contas removidas: {len(contas)} (as tabelas caem em cascata com o dono)")

    print()
    if FALHAS:
        print(f"{len(FALHAS)} verificações falharam:")
        for falha in FALHAS:
            print(f"  - {falha}")
        return 1
    print("todas as verificações passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
