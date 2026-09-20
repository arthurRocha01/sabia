# Sabiá

Revelador de conexões entre livros: o leitor seleciona um trecho e vê o que outros autores dizem sobre a mesma ideia, interpretado, com as fontes.

Este repositório contém o **cliente** (aplicação web) e o **motor** (serviço que guarda o acervo, gera os vetores e chama os modelos). A documentação do projeto fica no vault Obsidian, em `2 - Projects/Sabiá` — o comportamento em `Sabiá - Sistema.md`, a arquitetura e o contrato em `Sabiá - Arquitetura.md` e a plataforma em `Sabiá - Infra.md` são o ponto de entrada.

## Estrutura

    prototype/    design aprovado em HTML/CSS/JS (referência visual; tags view-v1 e view-v2)
    api/          ponto de entrada das funções do Vercel
    engine/       o motor
      api/        rotas, validação e códigos de erro
      domain/     as operações: ingerir, buscar, interpretar, manter o acervo
      infra/      banco, arquivos, PDF, modelos
      core/       configuração, erros e registro
    web/          cliente React, a partir do protótipo
    supabase/     migrações do banco
    scripts/      dev, migrações, conta do dono e verificação real
    tests/        testes do motor, offline por padrão

## Ambiente

    cp .env.example .env      # e preencha as chaves

## Como rodar localmente

Um comando sobe os dois:

    python scripts/dev.py      # motor em :8000 e cliente em :5173 — Ctrl+C derruba tudo

Uma vez, antes:

    python -m venv .venv && .venv/bin/pip install -r requirements.txt
    cd web && npm install
    cp .env.example .env && cp web/.env.example web/.env    # e preencha as chaves

A conta do dono não vem de cadastro — é criada pela chave administrativa:

    .venv/bin/python scripts/create_user.py seu@email.com

Outros comandos:

    .venv/bin/python scripts/migrate.py --status     estado das migrações do banco
    .venv/bin/python scripts/verify_api.py           verificação real (consome cota de embeddings)
    .venv/bin/python -m pytest -q                    testes do motor, offline
