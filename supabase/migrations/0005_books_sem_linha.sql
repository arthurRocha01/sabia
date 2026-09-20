-- O livro deixa de carregar linha de aprendizado.
--
-- A linha é corrente e do perfil: uma só, escrita pelo leitor, lida no momento
-- da consulta. Guardá-la no livro fixava no envio uma decisão que é do leitor —
-- e um livro enviado sem linha ficava sem contexto nenhum, em silêncio, porque o
-- campo vazio do formulário não é o mesmo que campo ausente.
--
-- O histórico não se perde: cada consulta continua gravando a linha que usou.

alter table public.books drop column if exists line;
