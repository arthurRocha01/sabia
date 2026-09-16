"""Leitura do arquivo PDF.

Responsabilidade: transformar o arquivo enviado nas páginas do livro — texto,
posição física e número impresso — junto dos sinais crus de cada página
(palavras, letras, dígitos, linhas pontilhadas, caracteres de controle).

Nenhuma decisão de negócio mora aqui. Dizer o que é corpo e o que é matéria
editorial é do domínio; este módulo apenas entrega o que mediu, sem interpretar.
A separação existe para que a regra de classificação possa ser testada sem
arquivo e ajustada sem tocar na leitura.

Ver `Sabiá - Sistema.md`, seções 3.5 e 3.6.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pymupdf

from engine.core.errors import FileUnavailable, TextLayerMissing

# Portão de qualidade da fonte, herdado do POC. Abaixo destes valores a extração
# não é linguagem: ou o PDF é digitalizado, ou a fonte não tem mapeamento
# Unicode (medido: 2% de letras e 86% de caracteres de controle num arquivo
# corrompido, que passou despercebido e queimou cota).
MIN_LETTER_RATIO = 0.45
MAX_CONTROL_RATIO = 0.05
MIN_SAMPLE_PAGES = 5

# Uma linha é considerada pontilhada a partir de três pontos seguidos, o padrão
# de sumário ("Introdução ......... 9").
DOTTED_LINE = "..."

# Uma linha só é candidata a cabeçalho se aparecer em mais de uma página.
MIN_REPEATS = 2

# Controles que não são separação normal de linha: tabulação e quebras contam
# como texto, não como lixo.
PLAIN_CONTROLS = {"\n", "\r", "\t"}


@dataclass(frozen=True)
class PageSignals:
    """Números crus de uma página, sem interpretação."""

    lines: int
    words: int
    letters: int
    digits: int
    characters: int
    controls: int
    dotted_lines: int

    @property
    def letter_ratio(self) -> float:
        """Proporção de letras — o sinal mais direto de texto corrido."""
        return self.letters / self.characters if self.characters else 0.0

    @property
    def control_ratio(self) -> float:
        """Proporção de caracteres de controle — indício de fonte sem mapa."""
        return self.controls / self.characters if self.characters else 0.0

    @property
    def digit_ratio(self) -> float:
        """Proporção de dígitos — alta em índice, notas e tabelas."""
        return self.digits / self.characters if self.characters else 0.0


@dataclass(frozen=True)
class Page:
    """Uma página do arquivo.

    `index` é a posição física, base zero: é o que navega. `label` é o número
    impresso, quando o próprio arquivo declara: é o que cita.
    """

    index: int
    label: str | None
    text: str
    signals: PageSignals


@dataclass(frozen=True)
class OutlineEntry:
    """Uma entrada do sumário embutido no arquivo.

    O título é o sinal útil: é ele que nomeia o aparelho de referência ("Índice",
    "Notas", "Bibliografia"). A página sozinha não distingue — no acervo medido,
    quase todas as páginas apontadas pelo sumário são capítulos do corpo.
    """

    level: int
    title: str
    page_index: int


@dataclass(frozen=True)
class Book:
    """O arquivo lido, com as páginas e o sumário embutido, quando existe."""

    pages: tuple[Page, ...]
    outline: tuple[OutlineEntry, ...]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def outline_pages(self) -> frozenset[int]:
        """Páginas que o sumário aponta, base zero."""
        return frozenset(entrada.page_index for entrada in self.outline)


def page_signals(text: str) -> PageSignals:
    """Mede uma página. Função pura: testável sem arquivo nenhum."""
    letters = digits = controls = 0
    for character in text:
        if character.isalpha():
            letters += 1
        elif character.isdigit():
            digits += 1
        elif unicodedata.category(character) == "Cc" and character not in PLAIN_CONTROLS:
            controls += 1

    lines = [line for line in text.splitlines() if line.strip()]
    return PageSignals(
        lines=len(lines),
        words=len(text.split()),
        letters=letters,
        digits=digits,
        characters=len(text),
        controls=controls,
        dotted_lines=sum(1 for line in lines if DOTTED_LINE in line),
    )


def read_book(path: str | Path | bytes) -> Book:
    """Lê o arquivo e devolve as páginas.

    Recusa o que não dá para ler: arquivo ausente, arquivo que não é PDF, PDF
    protegido por senha e arquivo sem camada de texto utilizável. A recusa
    acontece antes de qualquer custo — foi a ausência desse portão que queimou
    cota com centenas de trechos de lixo no POC.
    """
    # O envio do cliente chega como bytes: abrir direto evita passar por
    # arquivo temporário no meio do caminho.
    try:
        if isinstance(path, bytes):
            documento = pymupdf.open(stream=path, filetype="pdf")
        else:
            arquivo = Path(path)
            if not arquivo.is_file():
                raise FileUnavailable(f"arquivo não encontrado: {arquivo.name}")
            documento = pymupdf.open(arquivo)
    except FileUnavailable:
        raise
    except Exception as erro:  # pymupdf levanta tipos próprios para cada defeito
        raise FileUnavailable(f"não foi possível abrir o arquivo: {erro}") from erro

    with documento:
        if not documento.is_pdf or documento.page_count == 0:
            raise FileUnavailable("o arquivo não é um PDF com páginas")
        if documento.needs_pass:
            raise FileUnavailable("o PDF está protegido por senha")

        rotulos = _page_labels(documento)
        paginas: list[Page] = []
        for numero in range(documento.page_count):
            # "text" sempre devolve texto; o stubs do pymupdf tipa a união
            # das três formas de extração.
            texto = cast(str, documento[numero].get_text("text"))
            paginas.append(
                Page(
                    index=numero,
                    label=_label_for(rotulos, numero),
                    text=texto,
                    signals=page_signals(texto),
                )
            )

        paginas_lidas = tuple(paginas)
        _check_text_layer(paginas_lidas)
        return Book(pages=paginas_lidas, outline=_outline(documento))


def remove_repeated_lines(pages: tuple[Page, ...]) -> tuple[Page, ...]:
    """Descarta cabeçalho e rodapé que se repetem na maioria das páginas.

    O critério é a repetição, não a posição nem o tamanho da fonte: a medição
    mostrou que não existe fonte menor nesses livros (todas as linhas têm o
    mesmo tamanho), então uma regra tipográfica descartaria texto do autor.
    """

    def normalizada(linha: str) -> str:
        return " ".join(linha.split()).casefold()

    contagem: Counter[str] = Counter()
    for pagina in pages:
        # Cada linha conta uma vez por página: repetir três vezes na mesma
        # página não é sinal de cabeçalho.
        contagem.update({normalizada(linha) for linha in pagina.text.splitlines() if linha.strip()})

    # Repetição precisa ser repetição: numa página só não existe cabeçalho — e
    # num livro de uma página a maioria deixaria tudo "repetido".
    maioria = len(pages) / 2
    repetidas = {
        linha for linha, vezes in contagem.items() if vezes >= MIN_REPEATS and vezes > maioria
    }
    if not repetidas:
        return pages

    limpas: list[Page] = []
    for pagina in pages:
        mantidas = [
            linha for linha in pagina.text.splitlines() if normalizada(linha) not in repetidas
        ]
        texto = "\n".join(mantidas)
        limpas.append(
            Page(
                index=pagina.index,
                label=pagina.label,
                text=texto,
                signals=page_signals(texto),
            )
        )
    return tuple(limpas)


def _check_text_layer(pages: tuple[Page, ...]) -> None:
    """Recusa a fonte que não traz linguagem.

    A amostra evita julgar o livro por uma página de rosto; e a comparação é
    de proporção, não de valor absoluto, porque os livros do acervo têm
    formatos de página completamente diferentes.
    """
    amostra = pages[:MIN_SAMPLE_PAGES] if len(pages) > MIN_SAMPLE_PAGES else pages
    caracteres = sum(p.signals.characters for p in amostra)
    if not caracteres:
        raise TextLayerMissing("o arquivo não tem camada de texto: nenhum caractere extraído")

    letras = sum(p.signals.letters for p in amostra) / caracteres
    controles = sum(p.signals.controls for p in amostra) / caracteres
    if letras < MIN_LETTER_RATIO:
        raise TextLayerMissing(
            "o arquivo não tem camada de texto legível "
            f"({letras:.0%} de letras nas primeiras páginas)"
        )
    if controles > MAX_CONTROL_RATIO:
        raise TextLayerMissing(
            "a camada de texto do arquivo está corrompida "
            f"({controles:.0%} de caracteres de controle nas primeiras páginas)"
        )


def _outline(documento: pymupdf.Document) -> tuple[OutlineEntry, ...]:
    """Sumário embutido do arquivo, quando existe.

    Quando não existe, a lista fica vazia e a classificação segue apenas com os
    sinais da página — os dois livros do acervo mostram os dois casos: um traz
    71 entradas, o outro nenhuma.
    """
    entradas: list[OutlineEntry] = []
    for item in documento.get_toc() or []:
        nivel, titulo, pagina = item[0], item[1], item[2]
        if isinstance(pagina, int) and 1 <= pagina <= documento.page_count:
            entradas.append(
                OutlineEntry(level=int(nivel), title=str(titulo), page_index=pagina - 1)
            )
    return tuple(entradas)


def _page_labels(documento: pymupdf.Document) -> list[dict]:
    try:
        return list(documento.get_page_labels() or [])
    except Exception:
        return []


def _label_for(rotulos: list[dict], index: int) -> str | None:
    """Número impresso da página, quando o arquivo o declara.

    As faixas de rótulo do PDF valem por trecho: procura-se a última que começa
    nesta página ou antes dela, e conta-se a partir do primeiro número dela.
    """
    atual = None
    for rotulo in rotulos:
        if rotulo.get("startpage", 0) <= index:
            atual = rotulo
        else:
            break
    if atual is None:
        return None

    numero = atual.get("firstpagenum", 1) + index - atual.get("startpage", 0)
    estilo = atual.get("style", "D")
    prefixo = atual.get("prefix", "")
    if estilo == "D":
        corpo = str(numero)
    elif estilo in ("r", "R"):
        corpo = _roman(numero)
        corpo = corpo if estilo == "r" else corpo.upper()
    elif estilo in ("a", "A"):
        corpo = _letters(numero)
        corpo = corpo if estilo == "a" else corpo.upper()
    else:
        return None
    return f"{prefixo}{corpo}" if corpo else None


def _roman(numero: int) -> str:
    if not 0 < numero < 4000:
        return ""
    tabela = (
        (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
        (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
        (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
    )
    partes: list[str] = []
    for valor, simbolo in tabela:
        while numero >= valor:
            partes.append(simbolo)
            numero -= valor
    return "".join(partes)


def _letters(numero: int) -> str:
    """Numeração alfabética, como nas páginas de abertura de alguns livros."""
    if numero < 1:
        return ""
    resultado = ""
    while numero > 0:
        numero, resto = divmod(numero - 1, 26)
        resultado = chr(ord("a") + resto) + resultado
    return resultado
