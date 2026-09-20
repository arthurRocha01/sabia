import type { ErrorResponse } from './types'

const API_PREFIX = '/api'

function authHeaders(init?: RequestInit) {
  const headers = new Headers(init?.headers)
  const token = localStorage.getItem('sabia_token')
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  return headers
}

function jsonHeaders(init?: RequestInit) {
  const headers = authHeaders(init)
  if (!(init?.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  return headers
}

export function formatError(error: unknown): string {
  const apiError = error as ErrorResponse | undefined
  return apiError?.message ?? 'Não foi possível concluir a operação.'
}

function sessaoExpirou() {
  localStorage.removeItem('sabia_token')
  localStorage.removeItem('sabia_session')
  window.dispatchEvent(new Event('sabia:session-expired'))
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    headers: jsonHeaders(init),
    credentials: 'same-origin',
  })

  if (response.status === 204) {
    return undefined as T
  }

  const data = await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 401) sessaoExpirou()
    const error = (data ?? { code: 'internal_error', message: 'Erro ao acessar a API.' }) as ErrorResponse
    throw error
  }

  return data as T
}

export async function fetchBookFile(bookId: string): Promise<ArrayBuffer> {
  const response = await fetch(`${API_PREFIX}/books/${bookId}/file`, {
    headers: authHeaders(),
  })
  if (!response.ok) {
    if (response.status === 401) sessaoExpirou()
    const data = await response.json().catch(() => null)
    throw (data ?? {
      code: 'internal_error',
      message: 'Não foi possível abrir o arquivo do livro.',
    }) as ErrorResponse
  }
  return response.arrayBuffer()
}
