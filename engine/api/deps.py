"""Peças comuns dos pedidos.

Responsabilidade: montar configuração, identidade, conexão e provedores para as
rotas. É encanamento, não regra — o que entra em cada resposta é decidido nos
módulos de domínio.

A conexão de cada pedido é aberta **em nome do leitor**: o papel autenticado e
os dados do token entram na transação, e é isso que faz as políticas de acesso
filtrarem sem que nenhuma consulta escreva o filtro de dono.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

import psycopg
from fastapi import Depends, Header

from engine.core.config import Settings, load_settings
from engine.infra import db
from engine.infra.auth import Reader, TokenVerifier
from engine.infra.providers import DeepSeekInterpretation, GeminiEmbeddings


@lru_cache
def configuracao() -> Settings:
    """Configuração do motor, lida uma vez por instância da função."""
    return load_settings()


# Toda função usada como dependência recebe as suas próprias dependências
# anotadas: sem a anotação, o FastAPI trata o parâmetro como parte do corpo do
# pedido e o contrato sai errado (o corpo vira {"pedido": ..., "settings": ...}).
ConfigDep = Annotated[Settings, Depends(configuracao)]


@lru_cache
def verificador(jwks_url: str) -> TokenVerifier:
    """Conferidor de token, com as chaves públicas guardadas em memória."""
    return TokenVerifier(jwks_url)


@lru_cache
def embeddings(settings: ConfigDep) -> GeminiEmbeddings:
    """Provedor de embeddings."""
    return GeminiEmbeddings(
        api_key=settings.google_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        batch_chars=settings.embedding_batch_chars,
        batch_delay=settings.embedding_batch_delay,
        texts_per_minute=settings.embedding_texts_per_minute,
    )


@lru_cache
def interpretador(settings: ConfigDep) -> DeepSeekInterpretation:
    """Provedor da interpretação."""
    return DeepSeekInterpretation(
        api_key=settings.deepseek_api_key,
        model=settings.llm_model,
        timeout=settings.llm_timeout,
    )


def leitor_autenticado(
    settings: ConfigDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Reader:
    """Quem está pedindo — ou erro de sessão, antes de qualquer consulta."""
    return verificador(settings.supabase_jwks_url).verify(authorization)


ReaderDep = Annotated[Reader, Depends(leitor_autenticado)]


def conexao_do_leitor(leitor: ReaderDep, settings: ConfigDep) -> Iterator[psycopg.Connection]:
    """Conexão em nome do leitor, com a transação do pedido.

    Confirma no fim e desfaz em caso de erro: um pedido que falha no meio não
    deixa metade do trabalho gravada.
    """
    conexao = db.open_session(settings.database_url, leitor.claims)
    try:
        yield conexao
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()


ConexaoDep = Annotated[psycopg.Connection, Depends(conexao_do_leitor)]
EmbeddingsDep = Annotated[GeminiEmbeddings, Depends(embeddings)]
InterpretadorDep = Annotated[DeepSeekInterpretation, Depends(interpretador)]
AutorizacaoDep = Annotated[str | None, Header()]
