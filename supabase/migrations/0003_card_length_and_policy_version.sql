-- O tamanho do card é escolha do leitor, e a política ganhou versão.
--
-- As duas precisam ficar registradas em cada consulta: sem o tamanho, não se
-- sabe sob que limite o card foi escrito; sem a versão, a calibração juntaria
-- julgamentos feitos sob políticas diferentes como se fossem o mesmo dado.
-- O perfil guarda o tamanho como valor corrente, com o de sempre como padrão.

alter table public.profiles
    add column if not exists card_length text not null default 'default'
    check (card_length in ('default', 'long', 'free'));

alter table public.queries
    add column if not exists policy_version text,
    add column if not exists card_length text;
