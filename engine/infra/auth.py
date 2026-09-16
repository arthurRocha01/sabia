"""Identidade do leitor.

Responsabilidade: conferir o token que o navegador apresenta e devolver o que o
banco precisa para responder em nome dele. É a única peça que decide se um
pedido entra.

A conferência é contra as chaves públicas do projeto (`JWKS`), guardadas em
memória: buscá-las a cada pedido custaria uma ida à rede por consulta. Só
algoritmos assimétricos são aceitos — aceitar `none`, ou conferir com um segredo
simétrico, é a confusão clássica de JWT.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import jwt

from engine.core.errors import Unauthorized

ALGORITHMS = ("ES256", "ES384", "ES512", "RS256", "RS384", "RS512")
BEARER = "bearer "

# Tolerância para desvio entre o relógio de quem emitiu o token e o de quem o
# confere. Medido na verificação ponta a ponta: o `iat` chegou 37 segundos "no
# futuro" porque o relógio da máquina estava atrasado — e sem tolerância o motor
# recusa um token legítimo. Desvio de relógio entre máquinas é normal.
CLOCK_SKEW_SECONDS = 60


@dataclass(frozen=True)
class Reader:
    """Quem está pedindo, e o que o token afirma sobre ele."""

    id: str
    claims: dict[str, Any]


def _fetch_jwks(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resposta:  # noqa: S310
        return json.loads(resposta.read())


class TokenVerifier:
    """Confere o token do leitor contra as chaves públicas do projeto."""

    def __init__(
        self,
        jwks_url: str,
        *,
        audience: str = "authenticated",
        issuer: str | None = None,
        fetch: Callable[[str], dict] | None = None,
    ) -> None:
        self.jwks_url = jwks_url
        self.audience = audience
        self.issuer = issuer
        self._fetch = fetch or _fetch_jwks
        self._keys: dict[str, Any] = {}

    def verify(self, authorization: str | None) -> Reader:
        """O leitor por trás do cabeçalho de autorização."""
        token = self._token(authorization)
        chave = self._key(token)
        try:
            claims = jwt.decode(
                token,
                key=chave,
                algorithms=list(ALGORITHMS),
                audience=self.audience,
                issuer=self.issuer,
                leeway=CLOCK_SKEW_SECONDS,
                options={"require": ["exp", "sub"]},
            )
        except jwt.PyJWTError as erro:
            raise Unauthorized(
                "a sessão não é válida", detail="entre de novo para continuar"
            ) from erro
        return Reader(id=str(claims["sub"]), claims=claims)

    def _token(self, authorization: str | None) -> str:
        if not authorization or not authorization.lower().startswith(BEARER):
            raise Unauthorized("pedido sem sessão", detail="entre para continuar")
        return authorization[len(BEARER) :].strip()

    def _key(self, token: str) -> Any:
        try:
            cabecalho = jwt.get_unverified_header(token)
        except jwt.PyJWTError as erro:
            raise Unauthorized("a sessão não é válida") from erro

        identificador = cabecalho.get("kid")
        if identificador not in self._keys:
            self._keys = {
                chave["kid"]: jwt.PyJWK(chave)
                for chave in self._fetch(self.jwks_url).get("keys", [])
                if "kid" in chave
            }
        if identificador not in self._keys:
            raise Unauthorized("a chave da sessão não é conhecida")
        return self._keys[identificador]
