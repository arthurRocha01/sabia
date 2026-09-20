/** O progresso de uma tarefa de ingestão, como a tela o acompanha. */
export type TaskState = {
  jobId: string
  bookId: string
  status: string
  processed: number
  total: number | null
}
