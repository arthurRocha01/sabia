"""Leitura de um recorte de imagem.

Existe para as páginas que não têm camada de texto: capa, página escaneada,
ilustração. O cliente recorta a região que o leitor marcou e manda como imagem; o
modelo transcreve, e o texto segue o caminho de uma seleção comum. Sem isto,
marcar trecho numa página sem texto não teria o que buscar.

A leitura é mecânica: nenhuma regra do produto mora aqui, nem a decisão de quando
usar este caminho — quem sabe que a página não tem texto é o cliente.
"""

from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter

from engine.api import schemas
from engine.api.deps import ReaderDep, VisionDep
from engine.core.errors import InvalidInput

router = APIRouter(prefix="/api", tags=["leitura"])

# Um recorte de página em PNG passa de 1 MB com facilidade; o teto existe para um
# pedido absurdo não virar chamada de modelo.
TETO_DE_BYTES = 4_000_000


@router.post("/read-image", response_model=schemas.ReadImageResponse)
def ler(
    leitor: ReaderDep,
    visao: VisionDep,
    pedido: schemas.ReadImageRequest,
) -> schemas.ReadImageResponse:
    """Transcreve o texto do recorte enviado."""
    try:
        imagem = base64.b64decode(pedido.image, validate=True)
    except (binascii.Error, ValueError) as erro:
        raise InvalidInput("a imagem enviada não é base64 válido") from erro
    if not imagem:
        raise InvalidInput("a imagem está vazia")
    if len(imagem) > TETO_DE_BYTES:
        raise InvalidInput("o recorte é grande demais")
    return schemas.ReadImageResponse(text=visao.read_image(imagem, pedido.mime))
