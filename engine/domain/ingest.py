"""Ingestão de um livro.

Responsabilidade, em passos: validar a fonte, extrair o texto por página,
classificar as páginas em corpo e matéria editorial, recortar em fim de frase,
embeddar em lotes e gravar por lote com o ponto de continuação — porque a
execução é uma corrente de invocações.

Ver `Sabiá - Sistema.md`, seções 3.6 e 3.7.
"""
