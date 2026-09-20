"""A política do card: o texto que instrui o modelo na interpretação.

É a camada fechada do harness — o leitor não edita nada aqui. O que ele escolhe
são **valores** que a política referencia: hoje o tamanho do card; amanhã o
complemento, que entra numa seção própria e não substitui este texto.

Toda a redação vai em português. Fica em inglês só o que é identificador de
máquina — as chaves do JSON e as quatro palavras de relação —, porque atravessa
o contrato, o banco e a interface.

O que a política **não** diz, de propósito: limiar, escopo, quantidade de
trechos, modelo e tempo. Nada disso é decisão do modelo; é mecânica do motor.

Mudar a redação aqui é mudar a política: sobe `POLICY_VERSION`, e a versão fica
gravada em cada consulta. Sem isso, a calibração juntaria julgamentos feitos sob
políticas diferentes como se fossem o mesmo dado.
"""

from __future__ import annotations

from collections.abc import Sequence

from engine.core.errors import InvalidInput

POLICY_VERSION = "1"

NO_CONNECTION = "Nenhuma conexão relevante identificada."

# Tamanho do card, escolhido pelo leitor no perfil. O padrão é o de sempre.
CARD_LENGTHS = ("default", "long", "free")
CARD_LENGTH_CLAUSE = {
    "default": (
        "Escreva uma síntese de até três frases sobre o que os trechos recuperados"
        " acrescentam ao trecho consultado"
    ),
    "long": (
        "Escreva uma síntese de até oito frases sobre o que os trechos recuperados"
        " acrescentam ao trecho consultado"
    ),
    "free": (
        "Escreva uma síntese tão longa quanto o material pedir — nem mais curta nem"
        " mais longa do que ele sustenta — sobre o que os trechos recuperados"
        " acrescentam ao trecho consultado"
    ),
}


def _page(hit) -> str:
    """Como a página do trecho aparece para o modelo, e só para ele."""
    return f"página {hit.page_label}" if hit.page_label else f"posição {hit.page_index + 1}"


def build_prompt(
    selection: str,
    hits: Sequence,
    line: str | None = None,
    card_length: str = "default",
) -> str:
    """Monta o pedido ao modelo a partir dos trechos efetivamente recuperados."""
    if card_length not in CARD_LENGTHS:
        raise InvalidInput(f"tamanho de card desconhecido: {card_length!r}")

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

{CARD_LENGTH_CLAUSE[card_length]}, em português, sem preâmbulo, sem repetir o
trecho consultado e sem repetir os títulos — a interface já os mostra.
Classifique a relação predominante com uma destas palavras, em inglês:
complement, contradiction, nuance, same_concept. Se as relações estiverem
misturadas, a que predomina no conjunto.

Não invente: toda afirmação sobre uma obra, um autor ou uma passagem precisa
estar sustentada no trecho citado. Não atribua a um autor o que o trecho não
diz, e não invente página nem fonte.

Responda apenas com um objeto JSON, sem texto em volta:
{{"relation": "<uma das quatro palavras>", "used": [<números usados>],
 "card": "<a síntese>"}}

Regras: não escreva número de página no texto; quando precisar citar um trecho,
use o número dele entre colchetes. Se nenhum trecho tiver relação com o trecho
consultado, responda exatamente:
{{"relation": null, "used": [], "card": "{NO_CONNECTION}"}}"""
