"""Interpretação da conexão.

Responsabilidade: pedir ao modelo a síntese e a classificação da relação, e
devolver isso como **dado** — `relation` fora da frase, para a tela poder selar,
filtrar e testar — junto das fontes, que são montadas aqui a partir dos trechos
enviados.

O modelo nunca produz número de página: ele diz apenas quais trechos usou, por
índice. Modelo que inventa fonte produz erro com aparência confiável, que é o
pior tipo — e busca por palavra dentro de uma frase acha o oposto ("não há
contradição" contém "contradição").

Ver `Sabiá - Sistema.md`, seção 3.4.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from engine.core.errors import ProviderUnavailable

RELATIONS = ("complement", "contradiction", "nuance", "same_concept")
NO_CONNECTION = "Nenhuma conexão relevante identificada."

# Primeiro objeto da resposta: o modelo às vezes embrulha o JSON em texto ou em
# cerca de código, e exigir resposta perfeita derrubaria a síntese por nada.
FIRST_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class Citation:
    """Fonte de uma interpretação."""

    book_id: str
    title: str
    author: str
    page_index: int
    page_label: str | None


@dataclass(frozen=True)
class Interpretation:
    """A resposta da interpretação, como dado."""

    card: str
    relation: str | None
    citations: tuple[Citation, ...]


class Interpreter(Protocol):
    """O que a interpretação precisa do provedor de modelo."""

    def interpret(self, prompt: str) -> str: ...


def build_prompt(
    selection: str, hits: Sequence, line: str | None = None
) -> str:
    """Monta o pedido ao modelo a partir dos trechos efetivamente recuperados."""
    trechos = "\n\n".join(
        f"[{posicao}] {hit.title} — {hit.author}, {_page(hit)}:\n{hit.text}"
        for posicao, hit in enumerate(hits, start=1)
    )
    contexto = f"\nLinha de aprendizado do leitor: {line}\n" if line else ""
    return f"""Você ajuda um leitor a comparar ideias entre livros.

Trecho consultado pelo leitor:
{selection}
{contexto}
Trechos recuperados:
{trechos}

Escreva uma síntese de até três frases sobre o que os trechos recuperados
acrescentam ao trecho consultado, em português, sem repetir os títulos.
Classifique a relação predominante com uma destas palavras, em inglês:
complement, contradiction, nuance, same_concept.

Responda apenas com um objeto JSON, sem texto em volta:
{{"relation": "<uma das quatro palavras>", "used": [<números usados>],
 "card": "<a síntese>"}}

Regras: não escreva número de página no texto; quando precisar citar um trecho,
use o número dele entre colchetes. Se nenhum trecho tiver relação com o trecho
consultado, responda exatamente:
{{"relation": null, "used": [], "card": "{NO_CONNECTION}"}}"""


def parse_answer(raw: str, hits: Sequence) -> Interpretation:
    """Lê a resposta do modelo com tolerância, e nunca levanta por formato.

    Fora de formato, o card é o texto que voltou e a classificação fica vazia: a
    tela mostra o card sem selo e nada quebra. É o plano B do contrato.
    """
    achado = FIRST_OBJECT.search(raw or "")
    if not achado:
        return Interpretation(card=(raw or "").strip(), relation=None, citations=())

    try:
        dados = json.loads(achado.group(0))
    except json.JSONDecodeError:
        return Interpretation(card=(raw or "").strip(), relation=None, citations=())

    card = str(dados.get("card") or "").strip()
    relacao = dados.get("relation")
    if relacao not in RELATIONS:
        relacao = None
    if not card:
        return Interpretation(card=(raw or "").strip(), relation=None, citations=())
    return Interpretation(
        card=card, relation=relacao, citations=_citations(dados.get("used"), hits)
    )


def interpret(
    selection: str, *, hits: Sequence, interpreter: Interpreter, line: str | None = None
) -> Interpretation:
    """Interpreta a conexão a partir dos trechos recuperados.

    Sem trecho recuperado não há chamada ao modelo: o guard é consequência do
    limiar, não julgamento do modelo.
    """
    if not hits:
        return Interpretation(card=NO_CONNECTION, relation=None, citations=())

    bruto = interpreter.interpret(build_prompt(selection, hits, line))
    if not bruto.strip():
        raise ProviderUnavailable("o provedor de interpretação devolveu resposta vazia")
    return parse_answer(bruto, hits)


def _citations(used: object, hits: Sequence) -> tuple[Citation, ...]:
    """Fontes dos trechos que o modelo disse usar, validadas contra a lista."""
    if not isinstance(used, list):
        return ()
    citacoes: list[Citation] = []
    for indice in used:
        if not isinstance(indice, int) or isinstance(indice, bool):
            continue
        if not 1 <= indice <= len(hits):
            continue
        hit = hits[indice - 1]
        citacoes.append(
            Citation(
                book_id=hit.book_id,
                title=hit.title,
                author=hit.author,
                page_index=hit.page_index,
                page_label=hit.page_label,
            )
        )
    return tuple(citacoes)


def _page(hit) -> str:
    return f"página {hit.page_label}" if hit.page_label else f"posição {hit.page_index + 1}"
