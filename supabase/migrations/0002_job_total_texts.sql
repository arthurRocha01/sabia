-- A tarefa passa a guardar quantos trechos o livro terá.
--
-- Sem isso, a consulta de progresso só sabia dizer quantos LOTES existem, e o
-- cliente não tinha como montar uma fração de progresso: `processed` conta
-- trechos e `total_batches` conta lotes. O contrato sempre disse "trechos que o
-- livro terá" para o campo `total`; era o banco que não tinha onde guardá-lo.

alter table public.jobs
    add column if not exists total_texts int not null default 0;
