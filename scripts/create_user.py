"""Cria e administra a conta do dono, por e-mail e senha.

O login do Sabiá é **e-mail e senha**. A conta é criada por aqui, pela chave
administrativa, e não por cadastro — o cadastro público fica desligado no
painel. Um dono, um acervo.

Como o identificador é o e-mail de verdade (e não um endereço interno), o
provedor consegue fazer o que só ele sabe fazer com um endereço que existe:
mandar o link de recuperação de senha e o de confirmação. O preço é que esses
envelopes saem pelo servidor de e-mail embutido do Supabase, que entrega apenas
para endereços da equipe do projeto e é limitado a poucas mensagens por hora —
suficiente para uso pessoal, insuficiente para serviço. Quando virar serviço,
entra SMTP próprio.

Só a chave administrativa cria contas, e ela vive no servidor: este script roda
na máquina do dono, nunca no navegador.

Uso:
    python scripts/create_user.py arthur@exemplo.com            # cria
    python scripts/create_user.py arthur@exemplo.com --reset    # troca a senha
    python scripts/create_user.py arthur@exemplo.com --recover  # manda o link
    python scripts/create_user.py --list                        # lista
    python scripts/create_user.py arthur@exemplo.com --remove   # remove

A senha é digitada sem eco e nunca aparece na tela, no histórico do shell nem
na saída do script.
"""

from __future__ import annotations

import argparse
import getpass
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from engine.core.config import load_settings  # noqa: E402

SENHA_MINIMA = 8
FORMATO_DE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def conferir_email(endereco: str) -> str:
    """Normaliza e confere a forma do endereço antes de falar com o provedor."""
    limpo = endereco.strip().lower()
    if not FORMATO_DE_EMAIL.match(limpo):
        raise SystemExit(f"endereço fora de forma: {endereco!r}")
    return limpo


def _pedido(
    caminho: str, metodo: str = "GET", corpo: dict | None = None, *, admin: bool = True
) -> dict:
    settings = load_settings()
    base = settings.supabase_url.rstrip("/")
    chave = settings.supabase_secret_key if admin else settings.supabase_publishable_key
    dados = json.dumps(corpo).encode() if corpo is not None else None
    prefixo = "auth/v1/admin/" if admin else "auth/v1/"
    pedido = urllib.request.Request(f"{base}/{prefixo}{caminho}", data=dados, method=metodo)
    pedido.add_header("apikey", chave)
    if admin:
        pedido.add_header("Authorization", f"Bearer {chave}")
    if dados is not None:
        pedido.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(pedido, timeout=30) as resposta:
            return json.loads(resposta.read() or b"{}")
    except urllib.error.HTTPError as erro:
        motivo = erro.read()[:300].decode("utf-8", "replace") if erro.fp else ""
        raise SystemExit(f"o provedor recusou ({erro.code}): {motivo}") from erro


def contas() -> list[dict]:
    """Todas as contas, da mais antiga à mais nova."""
    return _pedido("users").get("users", [])


def encontrar(endereco: str) -> dict | None:
    alvo = conferir_email(endereco)
    for conta in contas():
        if (conta.get("email") or "").lower() == alvo:
            return conta
    return None


def pedir_senha(confirmar: bool = True) -> str:
    while True:
        senha = getpass.getpass("senha: ")
        if len(senha) < SENHA_MINIMA:
            print(f"  curta demais: o mínimo é {SENHA_MINIMA} caracteres")
            continue
        if confirmar and senha != getpass.getpass("repita a senha: "):
            print("  as senhas não coincidem")
            continue
        return senha


def criar(endereco: str, senha: str) -> dict:
    """Cria a conta já confirmada — sem depender de e-mail de confirmação."""
    return _pedido(
        "users",
        "POST",
        {"email": conferir_email(endereco), "password": senha, "email_confirm": True},
    )


def trocar_senha(endereco: str, senha: str) -> dict:
    conta = encontrar(endereco)
    if conta is None:
        raise SystemExit(f"não existe conta para {endereco}")
    return _pedido(f"users/{conta['id']}", "PUT", {"password": senha})


def mandar_recuperacao(endereco: str) -> dict:
    """Pede ao provedor o e-mail de recuperação (endpoint público)."""
    return _pedido("recover", "POST", {"email": conferir_email(endereco)}, admin=False)


def remover(endereco: str) -> None:
    conta = encontrar(endereco)
    if conta is None:
        raise SystemExit(f"não existe conta para {endereco}")
    _pedido(f"users/{conta['id']}", "DELETE")


def main() -> int:
    parser = argparse.ArgumentParser(description="Conta do Sabiá (e-mail e senha, sem cadastro).")
    parser.add_argument("email", nargs="?", help="o endereço da conta")
    parser.add_argument("--reset", action="store_true", help="troca a senha")
    parser.add_argument("--recover", action="store_true", help="manda o e-mail de recuperação")
    parser.add_argument("--remove", action="store_true", help="remove a conta")
    parser.add_argument("--list", action="store_true", help="lista as contas")
    argumentos = parser.parse_args()

    if argumentos.list:
        todas = contas()
        if not todas:
            print("nenhuma conta criada")
            return 0
        for conta in todas:
            print(f"  {conta.get('email', '?'):<34} {conta.get('id')}")
        return 0

    if not argumentos.email:
        parser.error("informe o e-mail (ou use --list)")

    if argumentos.remove:
        remover(argumentos.email)
        print(f"conta removida: {argumentos.email}")
        print("  o acervo cai em cascata com ela")
        return 0

    if argumentos.reset:
        trocar_senha(argumentos.email, pedir_senha())
        print(f"senha trocada para: {argumentos.email}")
        return 0

    if argumentos.recover:
        mandar_recuperacao(argumentos.email)
        print(f"link enviado para: {argumentos.email}")
        print("  cuidado: o servidor de e-mail embutido limita a poucas mensagens por hora")
        return 0

    if encontrar(argumentos.email) is not None:
        print(f"já existe conta para {argumentos.email} — use --reset para trocar a senha")
        return 1
    conta = criar(argumentos.email, pedir_senha())
    print(f"conta criada: {argumentos.email}")
    print(f"  identificador: {conta.get('id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
