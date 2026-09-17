export type Scope = 'others' | 'same'
export type Relation = 'complement' | 'contradiction' | 'nuance' | 'same_concept'
export type BookStatus = 'preparing' | 'ready' | 'failed'
export type JobState = 'queued' | 'running' | 'done' | 'failed'

export interface Book {
  id: string
  title: string
  author: string
  line: string | null
  status: BookStatus
  page_count: number | null
  n_chunks: number | null
  ingested_at: string | null
  created_at: string
}

export interface BooksResponse {
  books: Book[]
}

export interface JobProgress {
  id: string
  book_id: string
  state: JobState
  processed: number
  total: number | null
  error_code: string | null
}

export interface Hit {
  book_id: string
  title: string
  author: string
  page_index: number
  page_label: string | null
  text: string
  score: number
}

export interface ConnectRequest {
  text: string
  scope: Scope
  book_id?: string | null
  k?: number
  min_score?: number
  line?: string | null
}

export interface ConnectResponse {
  hits: Hit[]
  word_count: number
  truncated: boolean
}

export interface Citation {
  book_id: string
  title: string
  author: string
  page_index: number
  page_label: string | null
}

export interface InterpretationResponse {
  card: string
  relation: Relation | null
  citations: Citation[]
}

export interface Profile {
  current_line: string | null
  texts_today: number
  daily_limit: number
}

export interface ErrorResponse {
  code: string
  message: string
  detail?: string
}
