"""Testes da identidade do leitor.

Offline: as chaves são geradas no teste e o endereço das chaves públicas é
substituído por um dicionário. Nada aqui depende do projeto no Supabase.
"""

from __future__ import annotations

import json

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from engine.core.errors import Unauthorized
from engine.infra.auth import TokenVerifier

KID = "chave-de-teste"


def _par_de_chaves():
    """Chave privada para assinar e o conjunto público correspondente."""
    privada = ec.generate_private_key(ec.SECP256R1())
    publica = json.loads(pyjwt.algorithms.ECAlgorithm.to_jwk(privada.public_key()))
    publica.update({"kid": KID, "alg": "ES256", "use": "sig"})
    return privada, {"keys": [publica]}


def _token(
    privada, *, aud="authenticated", exp_delta=3600, iat_delta=0, sub="leitor-1", kid=KID, **extras
):
    import time

    agora = int(time.time())
    claims = {
        "sub": sub,
        "aud": aud,
        "iat": agora + iat_delta,
        "exp": agora + exp_delta,
        **extras,
    }
    return pyjwt.encode(claims, privada, algorithm="ES256", headers={"kid": kid})


def _verificador(chaves, **kwargs):
    buscas: list[str] = []

    def fetch(url: str) -> dict:
        buscas.append(url)
        return chaves

    return TokenVerifier("https://exemplo/jwks", fetch=fetch, **kwargs), buscas


def test_accepts_a_valid_token():
    privada, chaves = _par_de_chaves()
    verificador, _ = _verificador(chaves)

    leitor = verificador.verify(f"Bearer {_token(privada)}")

    assert leitor.id == "leitor-1"
    assert leitor.claims["sub"] == "leitor-1"


def test_rejects_missing_or_malformed_header():
    privada, chaves = _par_de_chaves()
    verificador, _ = _verificador(chaves)

    for cabecalho in (None, "", "token-solto", "Basic abc"):
        with pytest.raises(Unauthorized):
            verificador.verify(cabecalho)


def test_rejects_expired_token():
    privada, chaves = _par_de_chaves()
    verificador, _ = _verificador(chaves)

    with pytest.raises(Unauthorized):
        verificador.verify(f"Bearer {_token(privada, exp_delta=-600)}")


def test_accepts_a_few_seconds_of_clock_skew():
    """Desvio de relógio entre quem emite e quem confere é normal.

    Medido na verificação real: o `iat` chegou 37 segundos no futuro, porque o
    relógio da máquina estava atrasado — e o token era legítimo.
    """
    privada, chaves = _par_de_chaves()
    verificador, _ = _verificador(chaves)
    token = _token(privada, iat_delta=-30, exp_delta=-5)

    assert verificador.verify(f"Bearer {token}").id == "leitor-1"


def test_rejects_token_signed_by_another_key():
    _, chaves = _par_de_chaves()
    outra, _ = _par_de_chaves()
    verificador, _ = _verificador(chaves)

    with pytest.raises(Unauthorized):
        verificador.verify(f"Bearer {_token(outra)}")


def test_rejects_unknown_key_id():
    privada, chaves = _par_de_chaves()
    verificador, _ = _verificador(chaves)

    with pytest.raises(Unauthorized):
        verificador.verify(f"Bearer {_token(privada, kid='outra-chave')}")


def test_rejects_wrong_audience():
    privada, chaves = _par_de_chaves()
    verificador, _ = _verificador(chaves)

    with pytest.raises(Unauthorized):
        verificador.verify(f"Bearer {_token(privada, aud='outro-publico')}")


def test_fetches_the_public_keys_only_once():
    privada, chaves = _par_de_chaves()
    verificador, buscas = _verificador(chaves)

    for _ in range(3):
        verificador.verify(f"Bearer {_token(privada)}")

    assert len(buscas) == 1


def test_keeps_the_other_claims_for_the_session():
    privada, chaves = _par_de_chaves()
    verificador, _ = _verificador(chaves)

    token = _token(privada, email="leitor@exemplo.com", role="authenticated")
    leitor = verificador.verify(f"Bearer {token}")

    assert leitor.claims["email"] == "leitor@exemplo.com"
    assert leitor.claims["role"] == "authenticated"
