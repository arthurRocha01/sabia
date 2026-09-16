"""Acesso ao banco.

Responsabilidade: todo o SQL do sistema, em um único lugar. Nenhuma regra de
negócio mora aqui — o que é um trecho, quando gravar e o que fazer com o erro
é decisão do domínio.

A identidade do usuário na conexão (RLS) continua sendo ponto deferido
(`Sabiá - Infraestrutura.md`, seção 2). Até ela existir, a conexão usa a
credencial do pooler e o dono é **parâmetro de toda instrução**: quando a
identidade entrar, ela entra na preparação da conexão e nenhuma função daqui
muda.

Ver `Sabiá - Esquema do banco.md` para tabelas, campos e políticas.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence

import psycopg

from engine.core.errors import SabiaError

# O vetor vai em texto com conversão explícita: o cliente não conhece o tipo
# `halfvec`, e a conversão no banco é o que garante a meia precisão.
HALFVEC = "%s::halfvec"


def connect(url: str) -> psycopg.Connection:
    """Conexão ao banco pela URL do pooler em modo transação."""
    return psycopg.connect(url, connect_timeout=20)


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
    owner_id: str,
    title: str,
    author: str,
    line: str,
    file_hash: str,
    storage_path: str,
    page_count: int,
    segment_map: Iterable[dict],
) -> str:
    """Cria o livro em preparo. A busca só enxerga livro pronto."""
    cur.execute(
        """
        insert into public.books
            (owner_id, title, author, line, status, file_hash, storage_path,
             page_count, segment_map)
        values (%s, %s, %s, %s, 'preparing', %s, %s, %s, %s::jsonb)
        returning id
        """,
        (
            owner_id,
            title,
            author,
            line,
            file_hash,
            storage_path,
            page_count,
            json.dumps(list(segment_map), ensure_ascii=False),
        ),
    )
    return str(_only(cur, "o identificador do livro")[0])


def delete_book(cur: psycopg.Cursor, book_id: str) -> None:
    """Remove o livro; os trechos e as tarefas caem em cascata."""
    cur.execute("delete from public.books where id = %s", (book_id,))


def list_books(cur: psycopg.Cursor, owner_id: str) -> list[dict]:
    """Acervo de quem pediu, do mais recente para o mais antigo."""
    cur.execute(
        """
        select id, title, author, line, status, page_count, n_chunks,
               ingested_at, created_at
        from public.books
        where owner_id = %s
        order by created_at desc
        """,
        (owner_id,),
    )
    colunas = ("id", "title", "author", "line", "status", "page_count", "n_chunks",
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
# Tarefas de ingestão
# ---------------------------------------------------------------------------
def create_job(
    cur: psycopg.Cursor, *, owner_id: str, book_id: str, total_batches: int
) -> str:
    cur.execute(
        """
        insert into public.jobs (owner_id, book_id, state, next_batch, total_batches)
        values (%s, %s, 'queued', 0, %s)
        returning id
        """,
        (owner_id, book_id, total_batches),
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
        select id, book_id, state, next_batch, total_batches, texts_embedded,
               error_code
        from public.jobs where id = %s
        """,
        (job_id,),
    )
    linha = cur.fetchone()
    if not linha:
        return None
    colunas = ("id", "book_id", "state", "next_batch", "total_batches",
               "texts_embedded", "error_code")
    return dict(zip(colunas, linha, strict=True))


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
# Trechos
# ---------------------------------------------------------------------------
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
