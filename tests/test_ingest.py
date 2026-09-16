"""Testes da ingestão: fim de frase, recorte e classificação de páginas.

Offline e sem arquivo: as páginas são construídas no teste. O que depende de
PDF de verdade está em `test_pdf.py`, e o que depende de banco é verificação
pontual, não teste de rotina.
"""

from __future__ import annotations

import pytest

from engine.core.errors import ProviderUnavailable
from engine.domain.ingest import (
    BACK,
    BODY,
    FRONT,
    BatchResult,
    Chunk,
    PreparedBook,
    chunk_body,
    classify_pages,
    plan_batches,
    prepare,
    run_batch,
    sentence_spans,
    split_into_chunks,
    split_sentences,
)
from engine.infra.pdf import Book, OutlineEntry, Page, page_signals


def _pagina(index: int, texto: str, label: str | None = None) -> Page:
    return Page(index=index, label=label, text=texto, signals=page_signals(texto))


def _corpo(index: int, palavras: int = 400) -> Page:
    """Página de corpo: muitas palavras, sem marca nenhuma.

    O texto carrega o índice da página de propósito: páginas idênticas fariam a
    limpeza de linha repetida apagar o próprio corpo (é o limite conhecido da
    regra, e não o que estes testes querem exercitar).
    """
    recheio = palavras // 7
    texto = f"pagina {index}: " + "conteudo do autor sobre estrategia e metodo " * recheio
    return _pagina(index, texto)


def _nota(index: int) -> Page:
    return _pagina(index, "[←3] comentario do editor sobre a passagem citada antes")


def _livro(paginas: list[Page], entradas: list[OutlineEntry] | None = None) -> Book:
    return Book(pages=tuple(paginas), outline=tuple(entradas or ()))


# ---------------------------------------------------------------------------
# Fim de frase
# ---------------------------------------------------------------------------
def test_splits_simple_sentences():
    assert len(split_sentences("Uma frase. Outra frase! E a terceira?")) == 3


def test_does_not_split_on_abbreviation():
    """`p.` não termina frase; `etc.` também não — na dúvida, não divide."""
    assert split_sentences("Veja p. 44 do livro. Depois volte.") == [
        "Veja p. 44 do livro.",
        "Depois volte.",
    ]
    assert len(split_sentences("Comprou livros, revistas, etc. Depois saiu.")) == 1


def test_does_not_split_on_decimal_number():
    assert len(split_sentences("O indice e 2.5 pontos.")) == 1


def test_does_not_split_before_lowercase():
    """Ponto seguido de minúscula é abreviatura fora da lista, não fim de frase."""
    assert len(split_sentences("Disse o autor. que a estrategia importa")) == 1


def test_splits_before_quote_number_and_dialogue_dash():
    assert len(split_sentences('Ele disse: "vou pensar." Depois saiu.')) == 2
    assert len(split_sentences("Sao 3 casos. 4 sao raros.")) == 2
    assert len(split_sentences("Ele recusou. — Nao volto aqui. E saiu.")) == 3


def test_text_without_final_punctuation_is_a_single_sentence():
    assert split_sentences("sem ponto final nenhum") == ["sem ponto final nenhum"]


def test_sentence_spans_point_at_the_text():
    texto = "Primeira frase. Segunda frase."
    spans = sentence_spans(texto)
    assert [texto[posicion : posicion + len(frase)] for posicion, frase in spans]


# ---------------------------------------------------------------------------
# Recorte
# ---------------------------------------------------------------------------
def _frases(n: int, palavras: int = 20) -> str:
    """Texto com `n` frases de `palavras` palavras cada.

    Cada frase começa com maiúscula de propósito: a divisão é conservadora e
    não fecha frase antes de minúscula (é o que protege "p. 44" e abreviaturas
    fora da lista).
    """
    frase = "Palavra " + " ".join(["seguinte"] * (palavras - 2)) + "."
    return " ".join([frase] * n)


def test_chunks_close_at_sentence_end_after_the_target():
    trechos = split_into_chunks(_frases(10), target=120)
    assert len(trechos) >= 2
    for _, texto in trechos:
        assert texto.rstrip().endswith(".")


def test_overlap_is_the_last_sentence_and_counts_in_the_next():
    trechos = split_into_chunks(_frases(10), target=120)
    ultima_do_primeiro = trechos[0][1].split(".")[-2].strip()
    assert trechos[1][1].startswith(ultima_do_primeiro)


def test_no_chunk_grows_beyond_target_when_sentences_are_normal():
    trechos = split_into_chunks(_frases(20), target=120)
    for _, texto in trechos:
        assert len(texto.split()) <= 120 + 20  # alvo mais a maior frase


def test_single_sentence_over_the_cap_goes_whole():
    """O teto cede para a frase: nunca se corta dentro da oração."""
    longa = " ".join(["palavra"] * 200) + "."
    trechos = split_into_chunks(longa, target=120)
    assert len(trechos) == 1
    assert len(trechos[0][1].split()) == 200
    assert trechos[0][1].endswith(".")


def test_short_text_becomes_a_single_chunk():
    trechos = split_into_chunks("Uma frase curta. E outra.", target=120)
    assert len(trechos) == 1


def test_chunks_do_not_repeat_when_only_the_overlap_is_left():
    trechos = split_into_chunks(_frases(6), target=120)
    assert len(trechos) == 1


# ---------------------------------------------------------------------------
# Classificação
# ---------------------------------------------------------------------------
def test_empty_page_in_the_opening_is_front():
    classes = classify_pages((_pagina(0, ""), _corpo(1), _corpo(2), _corpo(3)))
    assert classes[0].segment == FRONT
    assert classes[0].reason == "página vazia"


def test_empty_page_in_the_middle_is_body():
    """Página vazia também é abertura de capítulo: marca só vale nas faixas."""
    paginas = (_corpo(0), _corpo(1), _corpo(2), _pagina(3, ""), _corpo(4), _corpo(5), _corpo(6))
    classes = classify_pages(paginas)
    assert classes[3].segment == BODY
    assert classes[3].reason is None


def test_summary_needs_several_dotted_lines():
    com_tres = _pagina(0, "Capitulo I ....... 9\nCapitulo II ...... 21\nCapitulo III ..... 30")
    com_uma = _pagina(0, "O autor menciona o assunto ...... e segue o texto comum da obra")
    com_sumario = classify_pages((com_tres, _corpo(1), _corpo(2), _corpo(3)))[0]
    com_uma_so = classify_pages((com_uma, _corpo(1), _corpo(2), _corpo(3)))[0]
    assert com_sumario.segment == FRONT and com_sumario.reason == "sumário"
    # uma linha pontilhada solta não é sumário: a página continua sendo abertura
    # só por estar abaixo do nível do corpo, e o motivo registrado é outro.
    assert com_uma_so.reason != "sumário"


def test_credit_page_is_front():
    creditos = _pagina(0, "DADOS DE COPYRIGHT. Todos os direitos reservados. Editora Exemplo.")
    assert classify_pages((creditos, _corpo(1), _corpo(2), _corpo(3)))[0].segment == FRONT


def test_note_pages_at_the_end_are_back():
    paginas = [_corpo(i) for i in range(5)] + [_nota(i) for i in range(5, 12)]
    classes = classify_pages(tuple(paginas))
    assert all(c.segment == BACK for c in classes[5:])
    assert classes[5].reason == "nota"


def test_reference_ignores_marked_pages():
    """Metade do livro em notas não pode derrubar o nível do corpo."""
    paginas = [_corpo(i) for i in range(20)] + [_nota(i) for i in range(20, 50)]
    classes = classify_pages(tuple(paginas))
    assert sum(1 for c in classes if c.segment == BODY) == 20
    assert sum(1 for c in classes if c.segment == BACK) == 30


def test_opening_page_below_the_body_level_is_editorial_by_position():
    """A biografia do autor não tem marca nenhuma e mesmo assim é abertura."""
    biografia = _pagina(0, " ".join(["palavra"] * 100))
    classes = classify_pages((_pagina(1, ""), biografia, *_corpo_pages(2, 8)))
    assert classes[1].segment == FRONT
    assert classes[1].reason == "abertura, abaixo do nível do corpo"


def _corpo_pages(inicio: int, fim: int) -> list[Page]:
    return [_corpo(i) for i in range(inicio, fim)]


def test_outline_title_marks_the_page():
    """Entrada do sumário embutido que nomeia aparato marca a página, no fim."""
    paginas = tuple([*_corpo_pages(0, 6), _corpo(6, 200)])
    livro = _livro(list(paginas), [OutlineEntry(level=1, title="Notas", page_index=6)])
    assert classify_pages(paginas, livro)[6].segment == BACK


def test_single_short_page_at_the_end_stays_body():
    """O fecho do texto pode ser curto: página curta sozinha não é aparato."""
    paginas = _corpo_pages(0, 6) + [_pagina(6, " ".join(["palavra"] * 120))]
    classes = classify_pages(tuple(paginas))
    assert classes[6].segment == BODY


def test_deep_short_run_at_the_end_is_back():
    paginas = _corpo_pages(0, 6) + [_pagina(i, " ".join(["palavra"] * 30)) for i in range(6, 10)]
    classes = classify_pages(tuple(paginas))
    assert all(c.segment == BACK for c in classes[6:])


# ---------------------------------------------------------------------------
# Preparação
# ---------------------------------------------------------------------------
def test_chunk_body_points_at_the_page_where_the_chunk_starts():
    paginas = tuple(_corpo(i) for i in range(4))
    classes = classify_pages(paginas)
    trechos = chunk_body(paginas, classes)
    assert trechos
    assert trechos[0].page_index == 0
    assert all(0 <= t.page_index < 4 for t in trechos)


def test_prepare_leaves_editorial_pages_out_of_the_chunks():
    paginas = [
        _pagina(0, ""),
        _pagina(1, "DADOS DE COPYRIGHT. Todos os direitos reservados."),
    ]
    paginas += _corpo_pages(2, 10)
    paginas += [_nota(i) for i in range(10, 16)]

    preparado = prepare(_livro(paginas))

    assert isinstance(preparado, PreparedBook)
    assert preparado.page_count == 16
    assert all("comentario do editor" not in t.text for t in preparado.chunks)
    assert all(t.page_index not in (0, 1, 10, 11, 12, 13, 14, 15) for t in preparado.chunks)
    assert preparado.body_pages == 8


def test_segment_map_is_one_entry_per_page():
    preparado = prepare(_livro([_pagina(0, ""), *_corpo_pages(1, 6)]))
    mapa = preparado.segment_map()
    assert len(mapa) == 6
    assert mapa[0] == {"page": 0, "segment": FRONT, "reason": "página vazia", "words": 0}
    assert mapa[3]["segment"] == BODY


def test_prepare_keeps_the_printed_label_of_the_page():
    paginas = [
        _pagina(i, f"pagina {i} " + " ".join(["palavra"] * 399), label=str(i + 1))
        for i in range(6)
    ]
    preparado = prepare(_livro(paginas))
    assert preparado.chunks[0].page_label == "1"


# ---------------------------------------------------------------------------
# Lotes e execução
# ---------------------------------------------------------------------------
def _preparado(quantos: int, caracteres: int = 100) -> PreparedBook:
    trechos = tuple(
        Chunk(text="x" * caracteres, page_index=i, page_label=str(i)) for i in range(quantos)
    )
    return PreparedBook(classifications=(), chunks=trechos, page_count=quantos)


class _EmbedderFalso:
    def __init__(self, vetores: int = 3, contagem_errada: bool = False) -> None:
        self.vetores = vetores
        self.contagem_errada = contagem_errada
        self.recebidos: list[list[str]] = []

    def embed_documents(self, texts):
        self.recebidos.append(list(texts))
        quantos = len(texts) + 1 if self.contagem_errada else len(texts)
        return [[0.5] * self.vetores for _ in range(quantos)]


class _StoreFalso:
    """Guarda a ordem das chamadas: gravar tem de vir antes de avançar."""

    def __init__(self) -> None:
        self.chamadas: list[tuple] = []
        self.gravados: list[tuple] = []

    def save_chunks(self, *, segment, items):
        self.chamadas.append(("save", segment))
        self.gravados.extend(items)
        return len(items)

    def advance(self, *, next_batch, texts, done):
        self.chamadas.append(("advance", next_batch, texts, done))


def test_plan_batches_groups_by_character_budget():
    preparado = _preparado(5, caracteres=100)
    lotes = plan_batches(preparado.chunks, batch_chars=250)
    assert [(lote.first, lote.last) for lote in lotes] == [(0, 1), (2, 3), (4, 4)]
    assert [lote.size for lote in lotes] == [2, 2, 1]


def test_plan_batches_with_no_chunks():
    assert plan_batches(()) == ()


def test_plan_batches_puts_an_oversized_chunk_alone():
    preparado = _preparado(3, caracteres=100)
    sozinho = plan_batches(preparado.chunks, batch_chars=150)
    assert [(lote.first, lote.last) for lote in sozinho] == [(0, 0), (1, 1), (2, 2)]


def test_run_batch_saves_and_advances_in_that_order():
    preparado = _preparado(4)
    lotes = plan_batches(preparado.chunks, batch_chars=250)
    store, embedder = _StoreFalso(), _EmbedderFalso()

    resultado = run_batch(preparado, lotes, index=0, embedder=embedder, store=store)

    assert [c[0] for c in store.chamadas] == ["save", "advance"]
    assert store.chamadas[0][1] == BODY
    assert resultado == BatchResult(next_batch=1, texts=2, done=False)


def test_run_batch_only_sends_the_chunks_of_that_batch():
    preparado = _preparado(5)
    lotes = plan_batches(preparado.chunks, batch_chars=250)
    store, embedder = _StoreFalso(), _EmbedderFalso()

    run_batch(preparado, lotes, index=1, embedder=embedder, store=store)

    assert embedder.recebidos[0] == [t.text for t in preparado.chunks[2:4]]
    assert [item[1] for item in store.gravados] == [2, 3]


def test_run_batch_marks_done_on_the_last_batch():
    preparado = _preparado(3)
    lotes = plan_batches(preparado.chunks, batch_chars=250)
    store, embedder = _StoreFalso(), _EmbedderFalso()

    resultado = run_batch(preparado, lotes, index=1, embedder=embedder, store=store)

    assert resultado.done is True
    assert store.chamadas[-1] == ("advance", 2, 1, True)


def test_run_batch_refuses_mismatched_vector_count():
    """Menos vetores que trechos gravaria trecho sem vetor: melhor falhar."""
    preparado = _preparado(3)
    lotes = plan_batches(preparado.chunks, batch_chars=250)
    store, embedder = _StoreFalso(), _EmbedderFalso(contagem_errada=True)

    with pytest.raises(ProviderUnavailable):
        run_batch(preparado, lotes, index=0, embedder=embedder, store=store)
    assert store.chamadas == []
