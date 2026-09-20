"""Acesso ao banco.

Responsabilidade: todo o SQL do sistema, em um único lugar. Nenhuma regra de
negócio mora aqui — o que é um trecho, quando gravar e o que fazer com o erro
é decisão do domínio.

A identidade do usuário na conexão (RLS) continua sendo ponto deferido
(`Sabiá - Infra.md`, seção de dados). Até ela existir, a conexão usa a
credencial do pooler e o dono é **parâmetro de toda instrução**: quando a
identidade entrar, ela entra na preparação da conexão e nenhuma função daqui
muda.

Ver `Sabiá - Arquitetura.md`, seção do modelo de dados, para tabelas, campos e políticas.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Any

import psycopg

from engine.core.errors import SabiaError

# O vetor vai em texto com conversão explícita: o cliente não conhece o tipo
# `halfvec`, e a conversão no banco é o que garante a meia precisão.
HALFVEC = "%s::halfvec"


def connect(url: str) -> psycopg.Connection:
    """Conexão ao banco pela URL do pooler em modo transação.

    `prepare_threshold=None` desliga a preparação automática de instruções no
    servidor, e isso **não é detalhe**: no modo transação o pooler entrega a
    próxima execução a outra conexão do pool, e a instrução preparada numa
    delas não existe na outra. O erro medido foi
    `DuplicatePreparedStatement: prepared statement "_pg3_0" already exists`,
    e só aparecia depois de algumas execuções da mesma instrução.
    """
    return psycopg.connect(url, connect_timeout=20, prepare_threshold=None)


def open_session(url: str, claims: dict[str, Any]) -> psycopg.Connection:
    """Abre a conexão já **em nome do leitor**.

    O papel autenticado e os dados do token entram na transação, e é isso que
    faz `auth.uid()` responder e as políticas de acesso valerem: daí em diante
    nenhuma consulta precisa escrever o filtro de dono. O ajuste é local, então
    ele morre com a transação e não vaza para o próximo pedido que usar a mesma
    conexão do pooler.
    """
    conexao = connect(url)
    with conexao.cursor() as cursor:
        cursor.execute("set local role authenticated")
        cursor.execute(
            "select set_config('request.jwt.claims', %s, true)", (json.dumps(claims),)
        )
    return conexao


def _only(cur: psycopg.Cursor, o_que: str) -> tuple:
    """A linha que a instrução devolveu — ou erro, porque isso é defeito nosso."""
    linha = cur.fetchone()
    if linha is None:
        raise SabiaError(f"o banco não devolveu {o_que}")
    return tuple(linha)


def halfvec(vector: Sequence[float]) -> str:
    """Vetor no formato que o banco entende."""
    return "[" + ",".join(f"{valor:.6g}" for valor in vector) + "]"


# ---------------------------------------------------------------------------
# Acervo
# ---------------------------------------------------------------------------
def find_book(cur: psycopg.Cursor, owner_id: str, file_hash: str) -> str | None:
    """Livro com este arquivo, se já existir no acervo de quem enviou.

    O mesmo arquivo substitui o anterior; título igual vindo de arquivo
    diferente é livro novo.
    """
    cur.execute(
        "select id from public.books where owner_id = %s and file_hash = %s",
        (owner_id, file_hash),
    )
    linha = cur.fetchone()
    return str(linha[0]) if linha else None


def create_book(
    cur: psycopg.Cursor,
    *,
    book_id: str | None = None,
    owner_id: str,
    title: str,
    author: str,
    file_hash: str,
    storage_path: str,
    page_count: int,
    n_chunks: int,
    segment_map: Iterable[dict],
) -> str:
    """Cria o livro em preparo. A busca só enxerga livro pronto."""
    cur.execute(
        """
        insert into public.books
            (id, owner_id, title, author, status, file_hash, storage_path,
             page_count, n_chunks, segment_map)
        values (coalesce(%s::uuid, gen_random_uuid()), %s, %s, %s, 'preparing',
                %s, %s, %s, %s, %s::jsonb)
        returning id
        """,
        (
            book_id,
            owner_id,
            title,
            author,
            file_hash,
            storage_path,
            page_count,
            n_chunks,
            json.dumps(list(segment_map), ensure_ascii=False),
        ),
    )
    return str(_only(cur, "o identificador do livro")[0])


def get_book(cur: psycopg.Cursor, book_id: str) -> dict | None:
    """Ficha de um livro. A política de acesso já limita ao dono."""
    cur.execute(
        """
        select id, title, author, status, file_hash, storage_path,
               page_count, n_chunks, ingested_at, created_at
        from public.books where id = %s
        """,
        (book_id,),
    )
    linha = cur.fetchone()
    if not linha:
        return None
    colunas = ("id", "title", "author", "status", "file_hash",
               "storage_path", "page_count", "n_chunks", "ingested_at", "created_at")
    return dict(zip(colunas, linha, strict=True))


def update_book(
    cur: psycopg.Cursor, book_id: str, *, title: str | None, author: str | None
) -> None:
    """Edita metadados: não exige re-ingerir nada."""
    cur.execute(
        """
        update public.books
        set title = coalesce(%s, title), author = coalesce(%s, author)
        where id = %s
        """,
        (title, author, book_id),
    )


def delete_book(cur: psycopg.Cursor, book_id: str) -> None:
    """Remove o livro; os trechos e as tarefas caem em cascata."""
    cur.execute("delete from public.books where id = %s", (book_id,))


def list_books(cur: psycopg.Cursor, owner_id: str) -> list[dict]:
    """Acervo de quem pediu, do mais recente para o mais antigo."""
    cur.execute(
        """
        select id, title, author, status, page_count, n_chunks,
               ingested_at, created_at
        from public.books
        where owner_id = %s
        order by created_at desc
        """,
        (owner_id,),
    )
    colunas = ("id", "title", "author", "status", "page_count", "n_chunks",
               "ingested_at", "created_at")
    return [dict(zip(colunas, linha, strict=True)) for linha in cur.fetchall()]


def finish_book(cur: psycopg.Cursor, *, book_id: str, n_chunks: int) -> None:
    """Marca o livro como pronto, com a contagem de trechos gravados."""
    cur.execute(
        """
        update public.books
        set status = 'ready', n_chunks = %s, ingested_at = now()
        where id = %s
        """,
        (n_chunks, book_id),
    )


def fail_book(cur: psycopg.Cursor, *, book_id: str) -> None:
    """Marca o livro como falhado: ele não aparece no acervo nem na busca."""
    cur.execute("update public.books set status = 'failed' where id = %s", (book_id,))


# ---------------------------------------------------------------------------
# Perfil
# ---------------------------------------------------------------------------
def get_profile(cur: psycopg.Cursor) -> dict | None:
    """Perfil de quem está conectado. O dono vem da política, não do código."""
    cur.execute(
        "select id, current_line, card_length, interpretation_profile from public.profiles limit 1"
    )
    linha = cur.fetchone()
    if not linha:
        return None
    return {
        "id": str(linha[0]),
        "current_line": linha[1],
        "card_length": linha[2],
        "interpretation_profile": linha[3],
    }


def set_current_line(cur: psycopg.Cursor, line: str) -> None:
    """Grava a linha corrente do perfil.

    Mudar a linha é atualização de metadado: nenhum vetor é tocado e nada é
    re-ingerido.
    """
    cur.execute("update public.profiles set current_line = %s", (line,))


def set_interpretation_profile(cur: psycopg.Cursor, texto: str) -> None:
    """Grava o perfil de interpretação do leitor.

    É texto dele sobre como quer a leitura — não é a linha de aprendizado, que
    diz sobre o que ele lê. Vazio significa "sem preferências", e o pedido ao
    modelo sai sem a seção.
    """
    cur.execute("update public.profiles set interpretation_profile = %s", (texto,))


def set_card_length(cur: psycopg.Cursor, card_length: str) -> None:
    """Grava o tamanho do card escolhido pelo leitor.

    É valor que a política referencia, não texto de política: mudar aqui não
    muda a redação nem a versão, só o tamanho que o modelo recebe.
    """
    cur.execute("update public.profiles set card_length = %s", (card_length,))


# ---------------------------------------------------------------------------
# Tarefas de ingestão
# ---------------------------------------------------------------------------
def create_job(
    cur: psycopg.Cursor,
    *,
    owner_id: str,
    book_id: str,
    total_batches: int,
    total_texts: int,
) -> str:
    cur.execute(
        """
        insert into public.jobs (owner_id, book_id, state, next_batch,
                                 total_batches, total_texts)
        values (%s, %s, 'queued', 0, %s, %s)
        returning id
        """,
        (owner_id, book_id, total_batches, total_texts),
    )
    return str(_only(cur, "o identificador da tarefa")[0])


def start_job(cur: psycopg.Cursor, job_id: str) -> bool:
    """Marca a tarefa como em execução — e diz se esta invocação conseguiu.

    A atualização é condicional de propósito: com dois pedidos ao mesmo tempo,
    só um consegue marcar e o outro desiste, em vez de duas invocações
    processarem o mesmo lote.
    """
    cur.execute(
        """
        update public.jobs
        set state = 'running'
        where id = %s and state <> 'running'
        returning id
        """,
        (job_id,),
    )
    return cur.fetchone() is not None


def advance_job(
    cur: psycopg.Cursor,
    *,
    job_id: str,
    next_batch: int,
    texts_embedded: int,
    state: str,
) -> None:
    """Grava o ponto de continuação depois de um lote.

    É este registro que faz a corrente de invocações andar: sem ele, uma parada
    no meio perderia tudo o que já foi gasto.
    """
    cur.execute(
        """
        update public.jobs
        set next_batch = %s, texts_embedded = texts_embedded + %s, state = %s,
            finished_at = case when %s = 'done' then now() else finished_at end
        where id = %s
        """,
        (next_batch, texts_embedded, state, state, job_id),
    )


def fail_job(cur: psycopg.Cursor, *, job_id: str, error_code: str) -> None:
    cur.execute(
        """
        update public.jobs
        set state = 'failed', error_code = %s, finished_at = now()
        where id = %s
        """,
        (error_code, job_id),
    )


def get_job(cur: psycopg.Cursor, job_id: str) -> dict | None:
    """Estado da tarefa, para a consulta de progresso."""
    cur.execute(
        """
        select id, book_id, state, next_batch, total_batches, total_texts,
               texts_embedded, error_code
        from public.jobs where id = %s
        """,
        (job_id,),
    )
    linha = cur.fetchone()
    if not linha:
        return None
    colunas = ("id", "book_id", "state", "next_batch", "total_batches",
               "total_texts", "texts_embedded", "error_code")
    return dict(zip(colunas, linha, strict=True))


def activity_today(cur: psycopg.Cursor, owner_id: str) -> dict:
    """A atividade do dia: consultas feitas e conexões que voltaram.

    Sai do próprio registro de calibração (`queries`), que já guarda cada
    consulta com os trechos devolvidos — não há contador separado para manter em
    sincronia. O dia é o mesmo do consumo: o dia UTC.
    """
    cur.execute(
        """
        select count(*), coalesce(sum(jsonb_array_length(hits)), 0)
        from public.queries
        where owner_id = %s and created_at >= date_trunc('day', now() at time zone 'utc')
        """,
        (owner_id,),
    )
    consultas, conexoes = _only(cur, "a atividade do dia")
    return {"queries_today": int(consultas), "connections_today": int(conexoes)}


def texts_embedded_today(cur: psycopg.Cursor, owner_id: str) -> int:
    """Consumo do dia: a soma do que as tarefas já embedaram.

    Não há contador separado — o número sai da própria tarefa, e é o que
    permite avisar antes de uma ingestão que não cabe na cota.
    """
    cur.execute(
        """
        select coalesce(sum(texts_embedded), 0)
        from public.jobs
        where owner_id = %s and created_at >= date_trunc('day', now() at time zone 'utc')
        """,
        (owner_id,),
    )
    return int(_only(cur, "o consumo do dia")[0])


# ---------------------------------------------------------------------------
# Registro de calibração
# ---------------------------------------------------------------------------
def save_query(
    cur: psycopg.Cursor,
    *,
    owner_id: str,
    book_id: str | None,
    query_text: str,
    word_count: int,
    scope: str,
    min_score: float,
    k: int,
    line: str | None,
    policy_version: str,
    card_length: str,
    interpretation_profile: str,
    hits: Iterable[dict],
) -> None:
    """Registra a consulta e o que ela devolveu.

    É a base para, mais adiante, sugerir tamanho de seleção e limiar com dados —
    em vez de com palpite.
    """
    cur.execute(
        """
        insert into public.queries
            (owner_id, book_id, query_text, word_count, scope, min_score, k, line,
             policy_version, card_length, interpretation_profile, hits)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            owner_id,
            book_id,
            query_text,
            word_count,
            scope,
            min_score,
            k,
            line,
            policy_version,
            card_length,
            interpretation_profile,
            json.dumps(list(hits), ensure_ascii=False),
        ),
    )


# ---------------------------------------------------------------------------
# Trechos
# ---------------------------------------------------------------------------
def search_chunks(
    cur: psycopg.Cursor,
    *,
    embedding: str,
    scope: str,
    book_id: str | None,
    k: int,
    min_score: float,
) -> list[dict]:
    """Trechos mais próximos do vetor da consulta.

    Só o corpo participa da busca, e só livro pronto. O filtro de dono **não**
    aparece aqui: quem filtra é a política de acesso, porque a conexão está em
    nome do leitor.

    O escopo é escolha explícita: `others` exclui o livro aberto, `same` fica só
    nele. Um dos dois, nunca os dois.
    """
    # A ordem dos parâmetros segue a ordem dos marcadores: o vetor aparece três
    # vezes na consulta (seleção, filtro de limiar e ordenação).
    filtro = ""
    parametros: list = []
    if scope == "same":
        filtro = "and c.book_id = %s"
        parametros.append(book_id)
    elif book_id:
        filtro = "and c.book_id <> %s"
        parametros.append(book_id)

    cur.execute(
        f"""
        select c.book_id, b.title, b.author, c.page_index, c.page_label, c.text,
               1 - (c.embedding <=> %s::halfvec) as score
        from public.chunks c
        join public.books b on b.id = c.book_id
        where c.segment = 'body'
          and b.status = 'ready'
          {filtro}
          and 1 - (c.embedding <=> %s::halfvec) >= %s
        order by c.embedding <=> %s::halfvec
        limit %s
        """,
        (embedding, *parametros, embedding, min_score, embedding, k),
    )
    colunas = ("book_id", "title", "author", "page_index", "page_label", "text", "score")
    return [dict(zip(colunas, linha, strict=True)) for linha in cur.fetchall()]


def save_chunks(
    cur: psycopg.Cursor,
    *,
    book_id: str,
    owner_id: str,
    segment: str,
    items: Sequence[tuple[str, int, str | None, Sequence[float]]],
) -> int:
    """Grava um lote de trechos com os seus vetores.

    Gravação por lote é o que impede que uma parada no meio desperdice todo o
    consumo já feito.
    """
    cur.executemany(
        f"""
        insert into public.chunks
            (book_id, owner_id, segment, page_index, page_label, text, embedding)
        values (%s, %s, %s, %s, %s, %s, {HALFVEC})
        """,
        [
            (book_id, owner_id, segment, pagina, rotulo, texto, halfvec(vetor))
            for texto, pagina, rotulo, vetor in items
        ],
    )
    return len(items)
