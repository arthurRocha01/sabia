"""Rotas do perfil.

O perfil guarda a linha de aprendizado corrente — o valor que vale como padrão
para novos livros. Ela é texto livre do leitor: o sistema não sugere, não limita
e não pré-define linha nenhuma.
"""

from __future__ import annotations

from fastapi import APIRouter

from engine.api import schemas
from engine.api.deps import ConexaoDep, ConfigDep, ReaderDep
from engine.infra import db

router = APIRouter(prefix="/api", tags=["perfil"])


def _ficha(cursor, leitor, settings) -> schemas.Profile:
    perfil = db.get_profile(cursor) or {}
    return schemas.Profile(
        current_line=perfil.get("current_line"),
        texts_today=db.texts_embedded_today(cursor, leitor.id),
        daily_limit=settings.quota_daily_texts,
    )


@router.get("/profile", response_model=schemas.Profile)
def ler(leitor: ReaderDep, conexao: ConexaoDep, settings: ConfigDep) -> schemas.Profile:
    with conexao.cursor() as cursor:
        return _ficha(cursor, leitor, settings)


@router.patch("/profile", response_model=schemas.Profile)
def atualizar(
    mudanca: schemas.ProfileUpdate, leitor: ReaderDep, conexao: ConexaoDep, settings: ConfigDep
) -> schemas.Profile:
    """Troca a linha corrente. Nenhum vetor é tocado, nada é re-ingido."""
    with conexao.cursor() as cursor:
        db.set_current_line(cursor, mudanca.current_line.strip())
        return _ficha(cursor, leitor, settings)
