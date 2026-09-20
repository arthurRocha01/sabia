import { apiFetch } from './client'
import type { ReadImageResponse } from './types'

/** Transcreve um recorte de página: o caminho das páginas sem camada de texto. */
export async function readImage(image: string, mime = 'image/png'): Promise<string> {
  const resposta = await apiFetch<ReadImageResponse>('/read-image', {
    method: 'POST',
    body: JSON.stringify({ image, mime }),
  })
  return resposta.text
}
