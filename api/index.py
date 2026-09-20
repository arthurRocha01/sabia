"""Ponto de entrada da função.

O Vercel transforma cada arquivo sob `api/` em um endereço; por isso este
arquivo só expõe a aplicação — o motor mora em `engine/`.
"""

from __future__ import annotations

from engine.api.app import create_app
from engine.core.config import get_settings

# As origens de outro domínio, se houver alguma declarada no ambiente. Vazio é o
# caso de produção: cliente e motor no mesmo endereço.
app = create_app(get_settings().allowed_origins)
