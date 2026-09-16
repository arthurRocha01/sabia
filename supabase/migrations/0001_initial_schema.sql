-- 0001 — esquema inicial
--
-- Cria as cinco estruturas, os índices vetoriais e as políticas de acesso por
-- linha descritas em "Sabiá - Esquema do banco.md".
--
-- O banco é escrito como código, e não montado no painel, para ser
-- reconstruível: um ambiente novo sobe igual ao primeiro com um comando, e
-- toda alteração de estrutura fica registrada e revisável.
--
-- Aplicar pela conexão de sessão (porta 5432):
--     psql "$DIRECT_URL" -f supabase/migrations/0001_initial_schema.sql
--
-- Escrito para poder ser rodado mais de uma vez sem quebrar.

-- ---------------------------------------------------------------------------
-- 1. Extensão vetorial
-- ---------------------------------------------------------------------------
create extension if not exists vector;

-- ---------------------------------------------------------------------------
-- 2. Perfil
-- ---------------------------------------------------------------------------
create table if not exists public.profiles (
    id uuid primary key references auth.users (id) on delete cascade,
    current_line text,
    created_at timestamptz not null default now()
);

comment on table public.profiles is
    'Perfil do usuário, criado automaticamente no primeiro acesso.';
comment on column public.profiles.current_line is
    'Linha de aprendizado corrente: texto livre escrito pelo usuário, usado como padrão.';

-- O perfil nasce junto com o usuário, em vez de depender de o cliente lembrar
-- de criá-lo no primeiro acesso.
create or replace function public.create_profile_for_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id) values (new.id) on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.create_profile_for_new_user();

-- ---------------------------------------------------------------------------
-- 3. Livros
-- ---------------------------------------------------------------------------
create table if not exists public.books (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null references auth.users (id) on delete cascade,
    title text not null,
    author text not null,
    line text not null,
    status text not null default 'preparing'
        check (status in ('preparing', 'ready', 'failed')),
    file_hash text not null,
    storage_path text not null,
    page_count int,
    n_chunks int,
    segment_map jsonb,
    ingested_at timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists books_owner_idx on public.books (owner_id);

-- ---------------------------------------------------------------------------
-- 4. Trechos
-- ---------------------------------------------------------------------------
create table if not exists public.chunks (
    id uuid primary key default gen_random_uuid(),
    book_id uuid not null references public.books (id) on delete cascade,
    owner_id uuid not null references auth.users (id) on delete cascade,
    segment text not null check (segment in ('body', 'front', 'back')),
    page_index int,
    page_label text,
    text text not null,
    embedding halfvec(3072),
    created_at timestamptz not null default now()
);

-- O vetor é halfvec, e não vector, por limite físico do índice: vector(3072)
-- gera linha de índice de 12.304 bytes, acima dos 8.191 que o Postgres aceita.
-- O halfvec indexa até 4.000 dimensões e ocupa metade do espaço.
create index if not exists chunks_embedding_idx
    on public.chunks using hnsw (embedding halfvec_cosine_ops);
create index if not exists chunks_book_idx on public.chunks (book_id);
create index if not exists chunks_owner_segment_idx on public.chunks (owner_id, segment);
create index if not exists chunks_owner_book_idx on public.chunks (owner_id, book_id);

-- ---------------------------------------------------------------------------
-- 5. Tarefas de ingestão
-- ---------------------------------------------------------------------------
create table if not exists public.jobs (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null references auth.users (id) on delete cascade,
    book_id uuid not null references public.books (id) on delete cascade,
    state text not null default 'queued'
        check (state in ('queued', 'running', 'done', 'failed')),
    next_batch int not null default 0,
    total_batches int,
    texts_embedded int not null default 0,
    error_code text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    finished_at timestamptz
);

create index if not exists jobs_owner_state_idx on public.jobs (owner_id, state);

-- updated_at sempre fiel, sem depender de o código lembrar de atualizá-lo.
create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists jobs_touch_updated_at on public.jobs;
create trigger jobs_touch_updated_at
    before update on public.jobs
    for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- 6. Registro de calibração
-- ---------------------------------------------------------------------------
create table if not exists public.queries (
    id uuid primary key default gen_random_uuid(),
    owner_id uuid not null references auth.users (id) on delete cascade,
    book_id uuid references public.books (id) on delete set null,
    query_text text not null,
    word_count int,
    scope text not null check (scope in ('others', 'same')),
    min_score numeric(4, 3),
    k int,
    line text,
    hits jsonb,
    used_hit int,
    created_at timestamptz not null default now()
);

create index if not exists queries_owner_idx on public.queries (owner_id);

-- ---------------------------------------------------------------------------
-- 7. Políticas de acesso por linha
--
-- A autorização mora no banco, não no código. Como o padrão do Postgres é
-- negar, tabela sem política fica inacessível — durante a construção, erra
-- para o lado de não vazar.
--
-- A expressão de dono é sempre a mesma; muda só a tabela. Inserção e alteração
-- repetem a condição também na verificação, o que impede gravar linha em nome
-- de outro dono.
--
-- auth.uid() vem embrulhado em subconsulta de propósito: assim o Postgres o
-- avalia uma vez por instrução, em vez de uma vez por linha.
-- ---------------------------------------------------------------------------
alter table public.profiles enable row level security;
alter table public.books enable row level security;
alter table public.chunks enable row level security;
alter table public.jobs enable row level security;
alter table public.queries enable row level security;

-- Perfil: cada um lê e altera apenas a própria linha. Não há política de
-- inserção nem de remoção: a linha nasce pelo gatilho do usuário e morre junto
-- com ele.
drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own on public.profiles
    for select to authenticated using (id = (select auth.uid()));

drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own on public.profiles
    for update to authenticated
    using (id = (select auth.uid()))
    with check (id = (select auth.uid()));

-- Livros
drop policy if exists books_select_own on public.books;
create policy books_select_own on public.books
    for select to authenticated using (owner_id = (select auth.uid()));

drop policy if exists books_insert_own on public.books;
create policy books_insert_own on public.books
    for insert to authenticated with check (owner_id = (select auth.uid()));

drop policy if exists books_update_own on public.books;
create policy books_update_own on public.books
    for update to authenticated
    using (owner_id = (select auth.uid()))
    with check (owner_id = (select auth.uid()));

drop policy if exists books_delete_own on public.books;
create policy books_delete_own on public.books
    for delete to authenticated using (owner_id = (select auth.uid()));

-- Trechos
drop policy if exists chunks_select_own on public.chunks;
create policy chunks_select_own on public.chunks
    for select to authenticated using (owner_id = (select auth.uid()));

drop policy if exists chunks_insert_own on public.chunks;
create policy chunks_insert_own on public.chunks
    for insert to authenticated with check (owner_id = (select auth.uid()));

drop policy if exists chunks_update_own on public.chunks;
create policy chunks_update_own on public.chunks
    for update to authenticated
    using (owner_id = (select auth.uid()))
    with check (owner_id = (select auth.uid()));

drop policy if exists chunks_delete_own on public.chunks;
create policy chunks_delete_own on public.chunks
    for delete to authenticated using (owner_id = (select auth.uid()));

-- Tarefas de ingestão
drop policy if exists jobs_select_own on public.jobs;
create policy jobs_select_own on public.jobs
    for select to authenticated using (owner_id = (select auth.uid()));

drop policy if exists jobs_insert_own on public.jobs;
create policy jobs_insert_own on public.jobs
    for insert to authenticated with check (owner_id = (select auth.uid()));

drop policy if exists jobs_update_own on public.jobs;
create policy jobs_update_own on public.jobs
    for update to authenticated
    using (owner_id = (select auth.uid()))
    with check (owner_id = (select auth.uid()));

drop policy if exists jobs_delete_own on public.jobs;
create policy jobs_delete_own on public.jobs
    for delete to authenticated using (owner_id = (select auth.uid()));

-- Registro de calibração
drop policy if exists queries_select_own on public.queries;
create policy queries_select_own on public.queries
    for select to authenticated using (owner_id = (select auth.uid()));

drop policy if exists queries_insert_own on public.queries;
create policy queries_insert_own on public.queries
    for insert to authenticated with check (owner_id = (select auth.uid()));

drop policy if exists queries_update_own on public.queries;
create policy queries_update_own on public.queries
    for update to authenticated
    using (owner_id = (select auth.uid()))
    with check (owner_id = (select auth.uid()));

drop policy if exists queries_delete_own on public.queries;
create policy queries_delete_own on public.queries
    for delete to authenticated using (owner_id = (select auth.uid()));

-- Permissão de acesso às tabelas. A política diz o que pode; a permissão diz
-- que o papel pode tentar. As duas são necessárias.
grant select, insert, update, delete
    on public.profiles, public.books, public.chunks, public.jobs, public.queries
    to authenticated;

-- ---------------------------------------------------------------------------
-- 8. Arquivos
--
-- Um único bucket, e o dono é o primeiro segmento do caminho do arquivo
-- (`{owner_id}/{book_id}.pdf`) — é exatamente o que a política usa para
-- autorizar. O bucket é privado: o acesso se dá por endereço assinado.
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('books', 'books', false)
on conflict (id) do nothing;

drop policy if exists books_files_select_own on storage.objects;
create policy books_files_select_own on storage.objects
    for select to authenticated
    using (
        bucket_id = 'books'
        and (storage.foldername(name))[1] = (select auth.uid())::text
    );

drop policy if exists books_files_insert_own on storage.objects;
create policy books_files_insert_own on storage.objects
    for insert to authenticated
    with check (
        bucket_id = 'books'
        and (storage.foldername(name))[1] = (select auth.uid())::text
    );

-- Não há política de alteração: trocar o arquivo é remover e enviar de novo.
drop policy if exists books_files_delete_own on storage.objects;
create policy books_files_delete_own on storage.objects
    for delete to authenticated
    using (
        bucket_id = 'books'
        and (storage.foldername(name))[1] = (select auth.uid())::text
    );
