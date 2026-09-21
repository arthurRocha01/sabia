import type { TaskState } from './types'

/** Os estados da tarefa de ingestão, na língua de quem lê a tela. */
const ESTADO: Record<string, string> = {
  queued: 'na fila',
  running: 'em preparo',
  done: 'pronto',
  failed: 'falhou',
}

/** O andamento da ingestão de um livro, dentro do cartão dele. */
export default function TaskProgress({ job }: { job: TaskState }) {
  return (
    <div className="job-progress">
      <span>{ESTADO[job.status] ?? job.status}</span>
      <strong>
        {job.processed}/{job.total ?? '—'} trechos
      </strong>
    </div>
  )
}
