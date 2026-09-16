"""Aplicação das migrações.

Responsabilidade: aplicar, em ordem, os arquivos de `supabase/migrations/` que
ainda não foram aplicados, e registrar cada um numa tabela de controle. Aplicar
duas vezes não repete nada, e o estado do banco pode ser consultado sem abrir o
painel do provedor.

Uso:

    .venv/bin/python scripts/migrate.py --status   # só mostra o estado
    .venv/bin/python scripts/migrate.py            # aplica o que falta

A conexão usada é a de sessão (`DIRECT_URL`, porta 5432): migração é um script
longo, que não pode ser trocado de conexão no meio.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg
from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "supabase" / "migrations"

# Tabela de controle. Nasce junto com a primeira migração aplicada, e não por
# uma migração: ela é o que permite saber quais migrações existem.
CONTROLE = """
create table if not exists public.schema_migrations (
    name text primary key,
    applied_at timestamptz not null default now()
)
"""


def arquivos() -> list[Path]:
    """Migrações em ordem alfabética — o prefixo numérico define a ordem."""
    return sorted(PASTA.glob("*.sql"))


def aplicadas(conexao) -> set[str]:
    with conexao.cursor() as cursor:
        cursor.execute(CONTROLE)
        cursor.execute("select name from public.schema_migrations")
        return {linha[0] for linha in cursor.fetchall()}


def aplica(conexao, caminho: Path) -> None:
    """Aplica um arquivo e registra, na mesma transação.

    Se o arquivo falhar no meio, nada dele fica no banco — nem o registro.
    """
    sql = caminho.read_text(encoding="utf-8")
    with conexao.transaction():
        with conexao.cursor() as cursor:
            cursor.execute(sql)
            cursor.execute(
                "insert into public.schema_migrations (name) values (%s)", (caminho.name,)
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Aplica as migrações pendentes.")
    parser.add_argument("--status", action="store_true", help="apenas mostra o estado")
    argumentos = parser.parse_args()

    encontradas = arquivos()
    if not encontradas:
        print(f"nenhuma migração em {PASTA}")
        return 0

    url = dotenv_values(RAIZ / ".env").get("DIRECT_URL")
    if not url:
        print("DIRECT_URL não está no .env: é a conexão de sessão (porta 5432)")
        return 1

    try:
        with psycopg.connect(url, connect_timeout=20) as conexao:
            prontas = aplicadas(conexao)
            pendentes = [c for c in encontradas if c.name not in prontas]

            for caminho in encontradas:
                marca = "aplicada" if caminho.name in prontas else "pendente"
                print(f"  [{marca:>8}] {caminho.name}")

            if argumentos.status:
                return 0
            if not pendentes:
                print("nada a aplicar")
                return 0

            for caminho in pendentes:
                aplica(conexao, caminho)
                print(f"  aplicada: {caminho.name}")
    except psycopg.Error as erro:
        print(f"falha ao aplicar migração: {erro}")
        return 1

    print(f"{len(pendentes)} migração(ões) aplicada(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
