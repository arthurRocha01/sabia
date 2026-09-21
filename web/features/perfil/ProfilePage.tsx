import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Book } from '../../api/types'
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

/** De quanto em quanto tempo a tela pergunta pelo andamento da ingestão. */
const INTERVALO_DA_TAREFA = 3000

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
  // A tarefa continua no banco: sair da tela só interrompe quem pergunta.
  const montadoRef = useRef(true)

  useEffect(() => () => {
    montadoRef.current = false
  }, [])

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
          `A cota do dia não comporta a estimativa deste livro: ${result.estimated_texts} trechos estimados e ${result.quota_remaining} restantes. Continuar mesmo assim?`,
        )
        if (!continuar) {
          // O motor já recebeu o arquivo e criou a tarefa: desistir agora, sem
          // apagar, deixaria um livro pela metade no acervo, sem ninguém
          // acompanhando. Recusar é desfazer.
          await deleteBook(result.book_id)
          await loadData()
          form.reset()
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

  /**
   * Acompanha a tarefa até o fim. É esta consulta que move a ingestão — sem
   * ninguém perguntando, o motor não processa o lote seguinte —, então o laço
   * não tem teto: desistir no meio deixaria o livro pela metade. Quem para é a
   * saída da tela; o ponto de continuação fica no banco e a corrente volta na
   * próxima consulta.
   */
  const pollJob = async (jobId: string) => {
    while (montadoRef.current) {
      const progress = await getJob(jobId)
      if (!montadoRef.current) return

      setJobState((current) => ({
        ...current,
        [jobId]: {
          jobId,
          bookId: progress.book_id,
          status: progress.state,
          processed: progress.processed,
          total: progress.total,
        },
      }))

      if (progress.state === 'done' || progress.state === 'failed') return
      await new Promise((resolve) => setTimeout(resolve, INTERVALO_DA_TAREFA))
    }
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
