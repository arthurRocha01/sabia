import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Book, JobProgress } from '../../api/types'
import { formatError } from '../../api/client'
import { deleteBook, getJob, listBooks, updateBook, uploadBook } from '../../api/books'
import { useProfile } from '../../app/profile'
import Dica from '../../ui/Dica'
import Cabecalho from '../../ui/Cabecalho'
import Indicador from '../../ui/Indicador'

type ProcessState = {
  jobId: string
  bookId: string
  status: string
  processed: number
  total: number | null
}

export default function PerfilPage({ onSignOut }: { onSignOut: () => void }) {
  const navigate = useNavigate()
  const [books, setBooks] = useState<Book[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loadingBooks, setLoadingBooks] = useState(true)
  const [jobState, setJobState] = useState<Record<string, ProcessState>>({})
  const { profile, saveProfile, error: profileError, clearError } = useProfile()
  const displayError = error || profileError

  const loadData = async () => {
    try {
      const booksData = await listBooks()
      setBooks(booksData)
      setError('')
    } catch (caught) {
      setError(formatError(caught))
    } finally {
      setLoadingBooks(false)
    }
  }

  useEffect(() => {
    void loadData()
  }, [])

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = event.currentTarget
    const formData = new FormData(form)
    const file = formData.get('file')
    if (!(file instanceof File) || file.size === 0) {
      setError('Selecione um PDF para enviar.')
      return
    }

    try {
      setBusy(true)
      const result = await uploadBook(formData)
      setJobState((current) => ({
        ...current,
        [result.job_id]: { jobId: result.job_id, bookId: result.book_id, status: 'queued', processed: 0, total: null },
      }))
      if (!result.quota_fits) {
        const continuar = window.confirm(
          `A cota do dia não comporta a estimativa deste livro: ${result.estimated_texts} trechos estimados e ${result.quota_remaining} restantes. Deseja continuar?`,
        )
        if (!continuar) {
          setBusy(false)
          return
        }
      }
      await pollJob(result.job_id)
      await loadData()
      form.reset()
    } catch (caught) {
      setError(formatError(caught))
    } finally {
      setBusy(false)
    }
  }

  const pollJob = async (jobId: string) => {
    const progress = await getJob(jobId)

    setJobState((current) => ({
      ...current,
      [jobId]: {
        jobId,
        bookId: String((progress as JobProgress).book_id ?? ''),
        status: String((progress as JobProgress).state ?? 'queued'),
        processed: Number((progress as JobProgress).processed ?? 0),
        total: (progress as JobProgress).total ?? null,
      },
    }))

    if ((progress as JobProgress).state === 'done' || (progress as JobProgress).state === 'failed') {
      return
    }

    await new Promise((resolve) => setTimeout(resolve, 3000))
    await pollJob(jobId)
  }

  const handleDelete = async (bookId: string) => {
    try {
      await deleteBook(bookId)
      await loadData()
    } catch (caught) {
      setError(formatError(caught))
    }
  }

  return (
    <>
      <Cabecalho books={books} loading={loadingBooks} mode="profile" />

      <main className="workspace-grid">
        <section className="panel panel-large">
          <div className="panel-title-row">
            <div>
              <p className="eyebrow">Perfil</p>
              <h1>Seu acervo</h1>
            </div>
            <span className="status-badge">{profile ? `${profile.texts_today}/${profile.daily_limit}` : '0/0'}</span>
          </div>

          {displayError ? <p className="inline-error">{displayError}</p> : null}

          <form className="upload-form" onSubmit={handleUpload}>
            <label className="field-group">
              <span>Arquivo PDF</span>
              <input type="file" name="file" accept="application/pdf" required />
            </label>
            <label className="field-group">
              <span>Título</span>
              <input type="text" name="title" placeholder="Título do livro" required />
            </label>
            <label className="field-group">
              <span>Autor</span>
              <input type="text" name="author" placeholder="Autor" required />
            </label>
            <button type="submit" className="primary-button" disabled={busy}>
              {busy ? 'Enviando…' : 'Enviar PDF'}
            </button>
          </form>

          <div className="book-list">
            {loadingBooks ? (
              <Indicador label="Carregando livros" />
            ) : books.length === 0 ? (
              <div className="empty-card">
                <p>Seu acervo está vazio. Envie um PDF para começar.</p>
              </div>
            ) : (
              books.map((book) => {
                const job = Object.values(jobState).find((item) => item.bookId === book.id)

                return <article className="book-card" key={book.id}>
                  <div>
                    <p className="mini-label">{book.author}</p>
                    <h3>{book.title}</h3>
                  </div>

                  <div className="book-meta">
                    <span>{book.status}</span>
                    <span>{book.n_chunks ?? 0} trechos</span>
                    <span>{book.page_count ?? 0} páginas</span>
                  </div>
                  {job ? (
                    <div className="job-progress">
                      <span>{job.status}</span>
                      <strong>{job.processed}/{job.total ?? '—'} trechos</strong>
                    </div>
                  ) : null}

                  <div className="book-actions">
                    <button type="button" className="secondary-button" onClick={() => navigate(`/consultar?book=${book.id}`)}>Abrir na consulta</button>
                    <button
                      type="button"
                      className="secondary-button warn"
                      onClick={() => handleDelete(book.id)}
                    >
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
                        await loadData()
                      } catch (caught) {
                        setError(formatError(caught))
                      }
                    }}
                  >
                    <input type="text" name="title" defaultValue={book.title} />
                    <input type="text" name="author" defaultValue={book.author} />
                    <button type="submit" className="ghost-button">Salvar</button>
                  </form>
                </article>
              })
            )}
          </div>
        </section>

        <aside className="panel sidebar-panel">
          {profile ? (
            <>
              <section className="side-block">
                <p className="eyebrow">Leitura</p>
                <h2>Assunto atual</h2>
                <form className="line-form" onSubmit={async (event) => {
                  event.preventDefault()
                  const form = event.currentTarget
                  const currentLine = (form.elements.namedItem('current_line') as HTMLInputElement).value
                  try {
                    await saveProfile({ current_line: currentLine })
                    clearError()
                  } catch (caught) {
                    setError(formatError(caught))
                  }
                }}>
                  <label className="field-group">
                    <span className="field-label-with-help">
                      Linha de aprendizado
                      <Dica>O assunto da leitura. Ele fica como contexto corrente para as consultas.</Dica>
                    </span>
                    <input name="current_line" defaultValue={profile.current_line ?? ''} placeholder="Sobre o que você está lendo" />
                  </label>
                  <button type="submit" className="secondary-button">Salvar linha</button>
                </form>
              </section>

              <section className="side-block">
                <p className="eyebrow">Como ler</p>
                <h2>Perfil de interpretação</h2>

                <form className="profile-form" onSubmit={async (event) => {
                  event.preventDefault()
                  const form = event.currentTarget
                  const texto = (form.elements.namedItem('interpretation_profile') as HTMLTextAreaElement).value
                  try {
                    await saveProfile({ interpretation_profile: texto })
                    clearError()
                  } catch (caught) {
                    setError(formatError(caught))
                  }
                }}>
                  <label className="field-group">
                    <span className="field-label-with-help">
                      Como interpretar
                      <Dica>Oriente o tom e os aspectos que o Sabiá deve priorizar ao relacionar suas ideias com os livros.</Dica>
                    </span>
                    <textarea
                      name="interpretation_profile"
                      rows={4}
                      maxLength={1200}
                      defaultValue={profile.interpretation_profile}
                      placeholder="Ex.: valorize a contradição antes da concordância; sem metáfora; compare com o meu trabalho."
                    />
                  </label>
                  <button type="submit" className="secondary-button">Salvar perfil</button>
                </form>

                <div className="field-group card-length">
                <span className="field-label-with-help">
                  Tamanho da interpretação
                  <Dica>Define o espaço esperado para o card: Padrão tem até três frases, Alto até oito e Livre deixa o modelo decidir.</Dica>
                </span>
                <div className="segmented" role="group" aria-label="Tamanho da interpretação">
                  {(
                    [
                      ['default', 'Padrão'],
                      ['long', 'Alto'],
                      ['free', 'Livre'],
                    ] as const
                  ).map(([valor, rotulo]) => (
                    <button
                      key={valor}
                      type="button"
                      className="segment"
                      aria-pressed={profile.card_length === valor}
                      onClick={async () => {
                        try {
                          await saveProfile({ card_length: valor })
                          clearError()
                        } catch (caught) {
                          setError(formatError(caught))
                        }
                      }}
                    >
                      {rotulo}
                    </button>
                  ))}
                </div>
                </div>
              </section>

              <section className="side-block">
                <p className="eyebrow">Conta</p>
                <h2>Hoje</h2>
                <div className="metric-row">
                  <span>Consultas</span>
                  <strong>{profile.queries_today}</strong>
                </div>
                <div className="metric-row">
                  <span>Conexões</span>
                  <strong>{profile.connections_today}</strong>
                </div>
                <div className="metric-row">
                  <span className="metric-label-with-help">
                    Cota diária usada
                    <Dica>Consultas e conexões mostram o que você leu. A cota representa os trechos consumidos pela ingestão contra o limite do dia.</Dica>
                  </span>
                  <strong>
                    {profile.texts_today} / {profile.daily_limit}
                  </strong>
                </div>
              </section>
            </>
          ) : (
            <p className="muted-copy">Carregando perfil…</p>
          )}

          <div className="divider" />

          <button type="button" className="ghost-button" onClick={onSignOut}>Sair da conta</button>
        </aside>
      </main>
    </>
  )
}
