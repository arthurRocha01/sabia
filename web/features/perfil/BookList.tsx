import type { Book } from '../../api/types'
import { updateBook } from '../../api/books'
import { formatError } from '../../api/client'
import Indicator from '../../ui/Indicator'
import TaskProgress from './TaskProgress'
import type { TaskState } from './types'

/** O acervo: ficha, estado, progresso da ingestão, edição e remoção. */
export default function BookList({
  books,
  loading,
  jobState,
  onOpen,
  onDelete,
  onSaved,
  onError,
}: {
  books: Book[]
  loading: boolean
  jobState: Record<string, TaskState>
  onOpen: (bookId: string) => void
  onDelete: (bookId: string) => void
  onSaved: () => Promise<void>
  onError: (mensagem: string) => void
}) {
  if (loading) {
    return <Indicator label="Carregando livros" />
  }

  if (books.length === 0) {
    return (
      <div className="empty-card">
        <p>Seu acervo está vazio. Envie um PDF para começar.</p>
      </div>
    )
  }

  return (
    <div className="book-list">
      {books.map((book) => {
        const job = Object.values(jobState).find((item) => item.bookId === book.id)

        return (
          <article className="book-card" key={book.id}>
            <div>
              <p className="mini-label">{book.author}</p>
              <h3>{book.title}</h3>
            </div>

            <div className="book-meta">
              <span>{book.status}</span>
              <span>{book.n_chunks ?? 0} trechos</span>
              <span>{book.page_count ?? 0} páginas</span>
            </div>
            {job ? <TaskProgress job={job} /> : null}

            <div className="book-actions">
              <button type="button" className="secondary-button" onClick={() => onOpen(book.id)}>
                Abrir na consulta
              </button>
              <button type="button" className="secondary-button warn" onClick={() => onDelete(book.id)}>
                Remover
              </button>
            </div>

            <form
              className="inline-edit"
              onSubmit={async (event) => {
                event.preventDefault()
                const form = event.currentTarget
                const title = (form.elements.namedItem('title') as HTMLInputElement)?.value
                const author = (form.elements.namedItem('author') as HTMLInputElement)?.value
                try {
                  await updateBook(book.id, { title: title || undefined, author: author || undefined })
                  await onSaved()
                } catch (caught) {
                  onError(formatError(caught))
                }
              }}
            >
              <input type="text" name="title" defaultValue={book.title} />
              <input type="text" name="author" defaultValue={book.author} />
              <button type="submit" className="ghost-button">Salvar</button>
            </form>
          </article>
        )
      })}
    </div>
  )
}
