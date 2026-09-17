import { existsSync } from 'node:fs'
import { writeFile } from 'node:fs/promises'

const openApiUrl = 'http://localhost:8000/openapi.json'

async function main() {
  try {
    const response = await fetch(openApiUrl)
    if (!response.ok) {
      throw new Error(`openapi status ${response.status}`)
    }
    const schema = await response.text()
    await writeFile(new URL('./openapi.json', import.meta.url), schema, 'utf8')
    console.log('openapi.json atualizado com sucesso.')
  } catch (error) {
    console.warn('Não foi possível gerar os tipos do OpenAPI: o motor local não está respondendo em', openApiUrl)
    console.warn(error instanceof Error ? error.message : String(error))
    const fallback = existsSync(new URL('./openapi.json', import.meta.url))
    if (!fallback) {
      console.warn('Nenhum arquivo openapi.json foi encontrado; a geração foi interrompida.')
      process.exitCode = 1
    }
  }
}

await main()
