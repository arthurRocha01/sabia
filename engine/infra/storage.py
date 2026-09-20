"""Arquivos no armazenamento do Supabase.

Responsabilidade: enviar, baixar e remover o PDF do livro. Toda chamada vai com
o **token do leitor**, e não com a chave administrativa: as políticas do bucket
autorizam pelo dono (o primeiro segmento do caminho é o identificador dele), e
usar a chave administrativa apagaria justamente essa proteção.

Ver `Sabiá - Arquitetura.md`, seção do modelo de dados.
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request

from engine.core.errors import FileUnavailable, IngestionFailed

BUCKET = "books"


def object_path(owner_id: str, book_id: str) -> str:
    """Caminho do arquivo: o dono é o primeiro segmento, como a política exige."""
    return f"{owner_id}/{book_id}.pdf"


def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/storage/v1/object/{BUCKET}/{urllib.parse.quote(path)}"


def _request(
    method: str, url: str, token: str, *, data: bytes | None = None, extra: dict | None = None
):
    requisicao = urllib.request.Request(url, data=data, method=method)
    requisicao.add_header("Authorization", f"Bearer {token}")
    requisicao.add_header("apikey", token)
    for chave, valor in (extra or {}).items():
        requisicao.add_header(chave, valor)
    return urllib.request.urlopen(requisicao, timeout=60)  # noqa: S310


def upload(base_url: str, path: str, data: bytes, *, token: str) -> None:
    """Envia o arquivo do livro."""
    try:
        with _request("POST", _url(base_url, path), token, data=data) as resposta:
            resposta.read()
    except urllib.error.HTTPError as erro:
        # O corpo da resposta do armazenamento diz o motivo exato; sem ele, o
        # erro vira um número e a investigação começa do zero.
        motivo = erro.read()[:200].decode("utf-8", "replace") if erro.fp else ""
        raise IngestionFailed(
            "não foi possível guardar o arquivo do livro",
            detail=f"o armazenamento respondeu {erro.code}: {motivo}",
        ) from erro


HEADERS = ("content-type", "content-length", "content-range", "accept-ranges")


def fetch(
    base_url: str, path: str, *, token: str, range_header: str | None = None
) -> tuple[int, bytes, dict[str, str]]:
    """Busca o arquivo, repassando o pedido de faixa do leitor de PDF.

    Sem faixa, o leitor de PDF baixa o arquivo inteiro antes de mostrar a
    primeira página; com faixa, ele pede só o pedaço que vai exibir.
    """
    extra = {"Range": range_header} if range_header else None
    try:
        with _request("GET", _url(base_url, path), token, extra=extra) as resposta:
            return resposta.status, resposta.read(), {
                nome: valor for nome, valor in resposta.headers.items() if nome.lower() in HEADERS
            }
    except urllib.error.HTTPError as erro:
        if erro.code in (404, 416):
            raise FileUnavailable(
                "o arquivo do livro não está disponível",
                detail=f"o armazenamento respondeu {erro.code}",
            ) from erro
        raise FileUnavailable(
            "não foi possível abrir o arquivo do livro",
            detail=f"o armazenamento respondeu {erro.code}",
        ) from erro
    except urllib.error.URLError as erro:
        raise FileUnavailable(
            "não foi possível alcançar o armazenamento", detail=str(erro.reason)
        ) from erro


def download(base_url: str, path: str, *, token: str) -> bytes:
    """Baixa o arquivo inteiro, para extrair o texto."""
    return fetch(base_url, path, token=token)[1]


def remove(base_url: str, path: str, *, token: str) -> None:
    """Apaga o arquivo do livro."""
    try:
        with _request("DELETE", _url(base_url, path), token) as resposta:
            resposta.read()
    except urllib.error.HTTPError as erro:
        if erro.code != 404:  # já não existir não é falha de quem remove
            motivo = erro.read()[:200].decode("utf-8", "replace") if erro.fp else ""
            raise IngestionFailed(
                "não foi possível apagar o arquivo do livro",
                detail=f"o armazenamento respondeu {erro.code}: {motivo}",
            ) from erro
