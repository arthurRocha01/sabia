-- O perfil de interpretação: o texto em que o leitor diz como quer a leitura.
--
-- É coisa diferente da linha de aprendizado — a linha é contexto (sobre o que
-- se lê) e o perfil é preferência (como se quer a interpretação). No pedido ao
-- modelo ocupam lugares distintos: a linha vai como dado, o perfil entra numa
-- seção nomeada, com a hierarquia declarada (ajusta tom e ênfase; não muda
-- formato, língua, fontes nem vocabulário).
--
-- A consulta guarda o texto usado, pela mesma razão de guardar a versão da
-- política: sem isso, a calibração juntaria julgamentos feitos sob preferências
-- diferentes como se fossem o mesmo dado.

alter table public.profiles
    add column if not exists interpretation_profile text not null default '';

alter table public.queries
    add column if not exists interpretation_profile text;
