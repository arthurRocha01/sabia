# Sabiá

Revelador de conexões entre livros: o leitor seleciona um trecho e vê o que outros autores dizem sobre a mesma ideia, interpretado, com as fontes.

Este repositório contém o **cliente** (aplicação web) e o **motor** (serviço que guarda o acervo, gera os vetores e chama os modelos). A documentação do projeto fica no vault Obsidian, em `2 - Projects/Sabiá` — o comportamento e o contrato em `Sabiá - Sistema.md` são o ponto de entrada.

## Estrutura

    prototype/    design aprovado em HTML/CSS/JS (referência visual; tags view-v1 e view-v2)
    api/          ponto de entrada das funções do Vercel
    engine/       o motor
      api/        rotas, validação e códigos de erro
      domain/     as operações: ingerir, buscar, interpretar, manter o acervo
      infra/      banco, arquivos, PDF, modelos
      core/       configuração, erros e registro
    web/          cliente React (a construir a partir do protótipo)
    supabase/     migrações do banco
    tests/        testes do motor, offline por padrão

## Ambiente

    cp .env.example .env      # e preencha as chaves

Detalhes de instalação, execução local e publicação entram conforme as camadas forem implementadas.
