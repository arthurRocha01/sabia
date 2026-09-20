import { apiFetch, fetchBookFile } from './client'
import type { Book, BooksResponse, JobProgress } from './types'

export { fetchBookFile }

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

export async function updateBook(bookId: string, payload: { title?: string; author?: string }): Promise<Book> {
  return apiFetch<Book>(`/books/${bookId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function deleteBook(bookId: string): Promise<void> {
  await apiFetch<void>(`/books/${bookId}`, { method: 'DELETE' })
}

export async function getJob(jobId: string): Promise<JobProgress> {
  return apiFetch<JobProgress>(`/jobs/${jobId}`)
}
