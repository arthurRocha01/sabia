export type Scope = 'others' | 'same'
export type Relation = 'complement' | 'contradiction' | 'nuance' | 'same_concept'
export type BookStatus = 'preparing' | 'ready' | 'failed'
export type JobState = 'queued' | 'running' | 'done' | 'failed'

export interface Book {
  id: string
  title: string
  author: string
  // Sem linha: ela é corrente, do perfil, e não um atributo do livro.
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
}

export interface ConnectResponse {
  hits: Hit[]
  word_count: number
  truncated: boolean
  /** Limiar efetivamente aplicado: o maior entre o piso do motor e o que foi pedido. */
  min_score: number
  /** Síntese; `null` quando a interpretação não voltou — a evidência vem mesmo assim. */
  card: string | null
  relation: Relation | null
  citations: Citation[]
}

export interface Citation {
  book_id: string
  title: string
  author: string
  page_index: number
  page_label: string | null
}

/** O card: o que a interpretação acrescenta à evidência, na mesma resposta. */
export type InterpretationResponse = Pick<ConnectResponse, 'card' | 'relation' | 'citations'>

/** Tamanho do card: valor corrente do perfil, que a política do motor referencia. */
export type CardLength = 'default' | 'long' | 'free'

export interface Profile {
  current_line: string | null
  card_length: CardLength
  /** Como o leitor quer a interpretação. Não é a linha de aprendizado. */
  interpretation_profile: string
  texts_today: number
  daily_limit: number
}

export interface ErrorResponse {
  code: string
  message: string
  detail?: string
}
