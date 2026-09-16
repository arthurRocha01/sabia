"""Testes da leitura de PDF.

Offline e sem arquivo do usuário: os PDFs são gerados na hora. Teste que aponta
para um PDF de `resources/` fica vermelho quando ele troca o arquivo — foi o que
aconteceu com o teste de PDF digitalizado no POC.
"""

from __future__ import annotations

import pymupdf
import pytest

from engine.core.errors import FileUnavailable, TextLayerMissing
from engine.infra.pdf import Page, page_signals, read_book, remove_repeated_lines

TEXTO = (
    "A estrategia sem tatica e o caminho mais lento para a vitoria. "
    "Conhecer o inimigo e conhecer a si mesmo sao as duas metades do "
    "mesmo problema pratico, e quem descuida de uma delas perde a outra."
)


def _linhas_do_autor(i: int) -> str:
    """Três linhas distintas por página, como o corpo de um livro de verdade."""
    return "\n".join(
        f"Linha {i} numero {j}: conhecer o inimigo exige metodo e paciencia."
        for j in range(3)
    )


def _pdf_com_texto(caminho, paginas, rotulos=None, sumario=None):
    documento = pymupdf.open()
    for texto in paginas:
        pagina = documento.new_page()
        pagina.insert_text((60, 60), texto, fontsize=10)
    if rotulos:
        documento.set_page_labels(rotulos)
    if sumario:
        documento.set_toc(sumario)
    documento.save(caminho)
    documento.close()
    return caminho


def _pdf_sem_texto(caminho, paginas=3):
    documento = pymupdf.open()
    for _ in range(paginas):
        pagina = documento.new_page()
        pagina.draw_rect(pymupdf.Rect(60, 60, 400, 400))
    documento.save(caminho)
    documento.close()
    return caminho


def test_page_signals_counts_words_letters_digits_and_dotted_lines():
    sinais = page_signals("Capitulo 1 ......... 9\nSegunda linha 2")
    assert sinais.lines == 2
    assert sinais.words == 7
    assert sinais.digits == 3
    assert sinais.dotted_lines == 1
    assert sinais.letter_ratio > 0.5


def test_page_signals_does_not_treat_line_breaks_as_control():
    """Quebra de linha é texto; caractere de controle de verdade é lixo."""
    assert page_signals("texto\nde linha\naqui\n").controls == 0
    assert page_signals("texto\x00com lixo").controls == 1


def test_page_signals_handles_empty_page():
    sinais = page_signals("")
    assert sinais.characters == 0
    assert sinais.letter_ratio == 0.0


def test_read_book_extracts_pages_with_signals(tmp_path):
    caminho = _pdf_com_texto(tmp_path / "livro.pdf", [TEXTO] * 6)
    livro = read_book(caminho)
    assert livro.page_count == 6
    assert "estrategia" in livro.pages[0].text
    assert livro.pages[0].signals.letter_ratio > 0.45
    assert livro.pages[0].label is None
    assert livro.outline_pages == frozenset()


def test_read_book_reads_printed_labels(tmp_path):
    """O número impresso pode trocar no meio do livro: romano na abertura."""
    caminho = _pdf_com_texto(
        tmp_path / "livro.pdf",
        [TEXTO] * 8,
        rotulos=[
            {"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1},
            {"startpage": 4, "prefix": "", "style": "D", "firstpagenum": 1},
        ],
    )
    livro = read_book(caminho)
    assert [p.label for p in livro.pages] == ["i", "ii", "iii", "iv", "1", "2", "3", "4"]


def test_read_book_finds_outline_pages(tmp_path):
    caminho = _pdf_com_texto(
        tmp_path / "livro.pdf",
        [TEXTO] * 6,
        sumario=[[1, "Indice", 2], [2, "Notas", 5]],
    )
    livro = read_book(caminho)
    assert livro.outline_pages == frozenset({1, 4})
    assert [(e.level, e.title) for e in livro.outline] == [(1, "Indice"), (2, "Notas")]


def test_read_book_rejects_missing_file(tmp_path):
    with pytest.raises(FileUnavailable, match="não encontrado"):
        read_book(tmp_path / "nao-existe.pdf")


def test_read_book_rejects_file_that_is_not_pdf(tmp_path):
    caminho = tmp_path / "falso.pdf"
    caminho.write_bytes(b"isto nao e um pdf")
    with pytest.raises(FileUnavailable):
        read_book(caminho)


def test_read_book_rejects_page_without_text_layer(tmp_path):
    """Página só de imagem: o arquivo é recusado antes de custar qualquer coisa."""
    with pytest.raises(TextLayerMissing, match="camada de texto"):
        read_book(_pdf_sem_texto(tmp_path / "digitalizado.pdf"))


def test_read_book_rejects_text_that_is_not_language(tmp_path):
    """Extração que não parece linguagem é recusada, mesmo tendo caracteres."""
    caminho = _pdf_com_texto(tmp_path / "numeros.pdf", ["1234567890 ..... " * 20] * 6)
    with pytest.raises(TextLayerMissing, match="camada de texto"):
        read_book(caminho)


def test_remove_repeated_lines_drops_header_of_the_book(tmp_path):
    # O corpo varia de página para página — como num livro de verdade. Se as
    # páginas fossem idênticas, a própria linha de conteúdo seria "repetida" e
    # cairia também: é o limite conhecido da regra.
    paginas = tuple(f"COLECAO ESTUDOS\n{_linhas_do_autor(i)}" for i in range(5))
    livro = read_book(_pdf_com_texto(tmp_path / "livro.pdf", paginas))

    limpas = remove_repeated_lines(livro.pages)

    assert all("COLECAO" not in pagina.text for pagina in limpas)
    assert all("conhecer o inimigo" in pagina.text for pagina in limpas)
    assert limpas[0].signals.words < livro.pages[0].signals.words
    assert limpas[0].index == livro.pages[0].index


def test_remove_repeated_lines_keeps_line_repeated_in_one_page_only():
    """Repetir três vezes na mesma página não faz da linha um cabeçalho."""
    paginas = tuple(
        _pagina(i, "SOLTO\n" * 3 + TEXTO if i == 0 else TEXTO) for i in range(5)
    )
    assert "SOLTO" in remove_repeated_lines(paginas)[0].text


def test_remove_repeated_lines_is_identity_without_repetition(tmp_path):
    paginas = [_linhas_do_autor(i) for i in range(5)]
    livro = read_book(_pdf_com_texto(tmp_path / "livro.pdf", paginas))
    assert remove_repeated_lines(livro.pages) is livro.pages


def test_remove_repeated_lines_does_not_mistake_body_for_header(tmp_path):
    """Metade das páginas com a mesma frase ainda é conteúdo, não cabeçalho."""
    paginas = tuple(_linhas_do_autor(0) if i % 2 == 0 else _linhas_do_autor(9) for i in range(6))
    livro = read_book(_pdf_com_texto(tmp_path / "livro.pdf", paginas))
    assert remove_repeated_lines(livro.pages) is livro.pages


def _pagina(index: int, texto: str) -> Page:
    return Page(index=index, label=None, text=texto, signals=page_signals(texto))
