import type { TaskState } from './types'

/** O andamento da ingestão de um livro, dentro do cartão dele. */
export default function TaskProgress({ job }: { job: TaskState }) {
  return (
    <div className="job-progress">
      <span>{job.status}</span>
      <strong>
        {job.processed}/{job.total ?? '—'} trechos
      </strong>
    </div>
  )
}
