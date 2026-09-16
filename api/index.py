"""Ponto de entrada da função.

O Vercel transforma cada arquivo sob `api/` em um endereço; por isso este
arquivo só expõe a aplicação — o motor mora em `engine/`.
"""

from __future__ import annotations

from engine.api.app import create_app

app = create_app()
