"""Rotas do perfil.

O perfil guarda os **valores correntes** do leitor: a linha de aprendizado, que
vale como padrão para novos livros, e o tamanho do card, que a política
referencia ao montar o pedido ao modelo. A linha é texto livre — o sistema não
sugere, não limita e não pré-define nenhuma. O tamanho é escolha fechada, entre
os três que a política conhece.
"""

from __future__ import annotations

from fastapi import APIRouter

from engine.api import schemas
from engine.api.deps import ConexaoDep, ConfigDep, ReaderDep
from engine.core.errors import InvalidInput
from engine.infra import db

router = APIRouter(prefix="/api", tags=["perfil"])


def _ficha(cursor, leitor, settings) -> schemas.Profile:
    perfil = db.get_profile(cursor) or {}
    return schemas.Profile(
        current_line=perfil.get("current_line"),
        card_length=perfil.get("card_length") or schemas.CardLength.default,
        interpretation_profile=perfil.get("interpretation_profile") or "",
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
    """Troca o que o leitor mudou. Nenhum vetor é tocado, nada é re-ingido."""
    if (
        mudanca.current_line is None
        and mudanca.card_length is None
        and mudanca.interpretation_profile is None
    ):
        raise InvalidInput(
            "nada a mudar: informe a linha, o tamanho do card ou o perfil de interpretação"
        )
    with conexao.cursor() as cursor:
        if mudanca.current_line is not None:
            db.set_current_line(cursor, mudanca.current_line.strip())
        if mudanca.card_length is not None:
            db.set_card_length(cursor, mudanca.card_length.value)
        if mudanca.interpretation_profile is not None:
            db.set_interpretation_profile(cursor, mudanca.interpretation_profile.strip())
        return _ficha(cursor, leitor, settings)
