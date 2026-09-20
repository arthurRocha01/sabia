import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Book, JobProgress } from '../../api/types'
import { formatError } from '../../api/client'
import { deleteBook, getJob, listBooks, uploadBook } from '../../api/books'
import { useProfile } from '../../app/profile'
import Header from '../../ui/Header'
import DailyActivity from './DailyActivity'
import LearningLine from './LearningLine'
import BookUpload from './BookUpload'
import BookList from './BookList'
import InterpretationProfile from './InterpretationProfile'
import type { TaskState } from './types'

/** O perfil: o acervo, o envio, e os valores correntes do leitor. */
export default function ProfilePage({ onSignOut }: { onSignOut: () => void }) {
  const navigate = useNavigate()
  const [books, setBooks] = useState<Book[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loadingBooks, setLoadingBooks] = useState(true)
  const [jobState, setJobState] = useState<Record<string, TaskState>>({})
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
      setError('Selecione um PDF para submit.')
      return
    }

    try {
      setBusy(true)
      const result = await uploadBook(formData)
      setJobState((current) => ({
        ...current,
        [result.job_id]: {
          jobId: result.job_id,
          bookId: result.book_id,
          status: 'queued',
          processed: 0,
          total: null,
        },
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
      <Header books={books} loading={loadingBooks} mode="profile" />

      <main className="workspace-grid">
        <section className="panel panel-large">
          <div className="panel-title-row">
            <div>
              <p className="eyebrow">Perfil</p>
              <h1>Seu acervo</h1>
            </div>
            <span className="status-badge">
              {profile ? `${profile.texts_today}/${profile.daily_limit}` : '0/0'}
            </span>
          </div>

          {displayError ? <p className="inline-error">{displayError}</p> : null}

          <BookUpload busy={busy} onSubmit={handleUpload} />

          <BookList
            books={books}
            loading={loadingBooks}
            jobState={jobState}
            onOpen={(bookId) => navigate(`/consultar?book=${bookId}`)}
            onDelete={handleDelete}
            onSaved={loadData}
            onError={setError}
          />
        </section>

        <aside className="panel sidebar-panel">
          {profile ? (
            <>
              <LearningLine
                profile={profile}
                onSave={saveProfile}
                onError={setError}
                onSaved={clearError}
              />
              <InterpretationProfile
                profile={profile}
                onSave={saveProfile}
                onError={setError}
                onSaved={clearError}
              />
              <DailyActivity profile={profile} />
            </>
          ) : (
            <p className="muted-copy">Carregando perfil…</p>
          )}

          <div className="divider" />

          <button type="button" className="ghost-button" onClick={onSignOut}>
            Sair da conta
          </button>
        </aside>
      </main>
    </>
  )
}
