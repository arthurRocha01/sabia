"""Modelos externos: embeddings e interpretação.

Responsabilidade: encapsular as chamadas ao provedor de embeddings e ao
modelo de interpretação, com o tratamento de cota (diária e por minuto) e o
ritmo entre lotes. Trocar de provedor deve significar trocar apenas esta peça.
"""
