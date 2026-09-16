"""Ponto de entrada das funções do Vercel.

Expõe a aplicação do motor como uma única função, com as rotas definidas em
`engine/api`. Todo o roteamento fica dentro da aplicação.
"""

from engine.api.app import app  # noqa: F401
