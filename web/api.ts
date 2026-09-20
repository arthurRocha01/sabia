import type { Book, BooksResponse, ConnectRequest, ConnectResponse, ErrorResponse, Profile } from './types'

const API_PREFIX = '/api'

/** O token da sessão, anexado num lugar só. */
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

/** A mensagem do contrato, que já vem em português, é o que se mostra. */
export function formatError(error: unknown): string {
  const apiError = error as ErrorResponse | undefined
  return apiError?.message ?? 'Não foi possível concluir a operação.'
}

/**
 * Sessão que expirou: limpa o que está guardado e avisa o aplicativo.
 *
 * Mora aqui, num lugar só, porque é aqui que todo 401 aparece — de rota em
 * rota, o tratamento repetido acabaria esquecido em alguma.
 */
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

/**
 * Os bytes do PDF, com o token.
 *
 * Não é um `src` de tag: tag nenhuma manda cabeçalho de autorização, e a rota
 * exige sessão. Quem pede o arquivo é este código, e o que volta são os bytes
 * que o pdf.js interpreta no navegador.
 */
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

export async function getProfile(): Promise<Profile> {
  return apiFetch<Profile>('/profile')
}

export async function updateProfile(currentLine: string): Promise<Profile> {
  return apiFetch<Profile>('/profile', {
    method: 'PATCH',
    body: JSON.stringify({ current_line: currentLine }),
  })
}

export async function listBooks(): Promise<Book[]> {
  const response = await apiFetch<BooksResponse>('/books')
  return response.books
}

export async function uploadBook(formData: FormData): Promise<{ job_id: string; book_id: string; estimated_texts: number; quota_remaining: number; quota_fits: boolean }> {
  return apiFetch('/books', {
    method: 'POST',
    body: formData,
  })
}

export async function updateBook(bookId: string, payload: { title?: string; author?: string; line?: string }): Promise<Book> {
  return apiFetch<Book>(`/books/${bookId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function deleteBook(bookId: string): Promise<void> {
  await apiFetch<void>(`/books/${bookId}`, { method: 'DELETE' })
}

export async function getJob(jobId: string) {
  return apiFetch(`/jobs/${jobId}`)
}

export async function connect(payload: ConnectRequest): Promise<ConnectResponse> {
  return apiFetch<ConnectResponse>('/connect', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

