"""Aplicação do motor.

Responsabilidade: montar a aplicação, ligar as rotas e converter os erros
tipados no formato único do contrato. O tratamento de erro fica em **um** lugar:
nenhuma rota monta resposta de erro por conta própria.

Pedido fora do formato também responde no formato do contrato: sem isso, o
cliente teria de tratar duas formas de erro — a nossa e a do framework.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from engine.api import schemas
from engine.core.errors import InvalidInput, SabiaError

# Local: as variáveis vêm do arquivo .env. Publicado: vêm do painel da Vercel, e
# não existe arquivo nenhum — a chamada não faz nada.
try:  # pragma: no cover - depende do ambiente
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def create_app(allowed_origins: tuple[str, ...] = ()) -> FastAPI:
    """Monta a aplicação com as rotas e o tratamento de erro do contrato.

    `allowed_origins` vazio — o padrão — não adiciona CORS nenhum: em produção o
    cliente e o motor estão no mesmo endereço, e abrir a porta para qualquer
    origem é convite que ninguém pediu. Quem precisa de outro domínio declara.
    """
    from engine.api import routes_books, routes_connect, routes_jobs, routes_profile, routes_read

    erro = {"model": schemas.ErrorResponse}
    app = FastAPI(
        title="Sabiá",
        version="0.1.0",
        description=(
            "Motor de conexões entre livros: ingestão, busca por similaridade e "
            "interpretação da relação entre trechos."
        ),
        # Os códigos de erro do contrato, para o cliente gerar os tipos do que
        # pode voltar. O corpo é sempre o mesmo formato.
        responses={
            400: {**erro, "description": "Pedido inválido"},
            401: {**erro, "description": "Sessão inválida"},
            404: {**erro, "description": "Não encontrado no acervo"},
            422: {**erro, "description": "Fonte sem camada de texto legível"},
            429: {**erro, "description": "Cota do dia esgotada"},
            500: {**erro, "description": "Falha do motor"},
            502: {**erro, "description": "Provedor indisponível"},
            504: {**erro, "description": "Operação excedeu o tempo"},
        },
    )
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_methods=["*"],
            allow_headers=["*"],
            # O leitor de PDF precisa ler o intervalo de bytes da resposta.
            expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
        )

    @app.exception_handler(SabiaError)
    async def erro_do_contrato(_: Request, falha: SabiaError) -> JSONResponse:
        return JSONResponse(status_code=falha.http_status, content=falha.to_payload())

    @app.exception_handler(RequestValidationError)
    async def erro_de_validacao(_: Request, falha: RequestValidationError) -> JSONResponse:
        primeiro = falha.errors()[0] if falha.errors() else {}
        onde = ".".join(str(p) for p in primeiro.get("loc", ()) if p != "body")
        mensagem = f"pedido inválido: {onde}" if onde else "pedido inválido"
        return JSONResponse(status_code=400, content=InvalidInput(mensagem).to_payload())

    for modulo in (routes_books, routes_jobs, routes_connect, routes_profile, routes_read):
        app.include_router(modulo.router)
    return app
