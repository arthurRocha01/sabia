import type { ErrorResponse } from './types'
import { sessionKey, tokenKey } from '../storage'

const API_PREFIX = '/api'

function authHeaders(init?: RequestInit) {
  const headers = new Headers(init?.headers)
  const token = localStorage.getItem(tokenKey)
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  return headers
}

/**
 * É o corpo que decide o cabeçalho: num GET não há corpo, e declarar JSON ali
 * descreve uma requisição que não existe.
 */
function requestHeaders(init?: RequestInit) {
  const headers = authHeaders(init)
  if (init?.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  return headers
}

/** A mensagem que a tela mostra: a do contrato quando ela vem, a nossa quando não. */
export function formatError(error: unknown): string {
  const apiError = error as Partial<ErrorResponse> | undefined
  return apiError?.message || 'Não foi possível concluir a operação.'
}

function sessaoExpirou() {
  localStorage.removeItem(tokenKey)
  localStorage.removeItem(sessionKey)
  window.dispatchEvent(new Event('sabia:session-expired'))
}

/**
 * Resposta fora do ok passa por aqui, num lugar só: o 401 derruba a sessão, e o
 * corpo do erro vira o formato do contrato mesmo quando não há corpo.
 */
function falha(status: number, data: unknown, fallback: string): ErrorResponse {
  if (status === 401) sessaoExpirou()
  const corpo = (data ?? {}) as Partial<ErrorResponse>
  return {
    code: corpo.code || 'internal_error',
    message: corpo.message || fallback,
    detail: corpo.detail,
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers: requestHeaders(init),
  })

  if (response.status === 204) {
    return undefined as T
  }

  const data = await response.json().catch(() => null)
  if (!response.ok) {
    throw falha(response.status, data, 'Erro ao acessar a API.')
  }

  return data as T
}

export async function fetchBookFile(bookId: string): Promise<ArrayBuffer> {
  const response = await fetch(`${API_PREFIX}/books/${bookId}/file`, {
    headers: authHeaders(),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw falha(response.status, data, 'Não foi possível abrir o arquivo do livro.')
  }
  return response.arrayBuffer()
}
