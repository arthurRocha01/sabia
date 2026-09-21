"""Ponto de entrada da função.

A plataforma reconhece uma instância de `FastAPI` chamada `app` neste arquivo e
passa a entregar **todas** as requisições a ela — é o preset de FastAPI, e é o
que faz `/api/*` chegar ao motor. No modo arquivo-por-rota, cada `.py` dentro de
`api/` vira uma função servida no próprio caminho, e um app único com todas as
rotas sob `/api` só seria alcançado em `/api`.

O cliente é servido pelo próprio app, a partir do que o build deixou em
`web/dist`: a plataforma promove esses arquivos ao CDN e mantém o retrocesso de
navegação para as rotas do aplicativo, o que dispensa a *rewrite* da SPA.
"""

from __future__ import annotations

import os
from pathlib import Path

from engine.api.app import create_app
from engine.core.config import get_settings

# As origens de outro domínio, se houver alguma declarada no ambiente. Vazio é o
# caso de produção: cliente e motor no mesmo endereço.
app = create_app(get_settings().allowed_origins)

# Só na plataforma: localmente quem serve o cliente é o Vite, e o `dist` pode nem
# existir. No build de lá o cliente já foi construído antes de empacotar a
# função, e o `frontend()` confere o diretório — faltando, o deploy falha alto em
# vez de subir sem interface.
if os.environ.get("VERCEL"):
    app.frontend("/", directory=Path(__file__).parent / "web" / "dist")
