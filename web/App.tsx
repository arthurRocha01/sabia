import { useEffect, useState, type FormEvent } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { createClient } from '@supabase/supabase-js'
import type { Book, ConnectRequest, ConnectResponse, ErrorResponse, InterpretationResponse, JobProgress, Profile } from './types'
import { connect, deleteBook, formatError, getJob, getProfile, interpret, listBooks, updateBook, updateProfile, uploadBook } from './api'
import ReaderPage from './ReaderPage'

const storageKey = 'sabia_session'
const tokenKey = 'sabia_token'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || ''
const supabaseKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || import.meta.env.VITE_SUPABASE_ANON_KEY || ''
const supabase = supabaseUrl && supabaseKey ? createClient(supabaseUrl, supabaseKey) : null

type ProcessState = {
  jobId: string
  bookId: string
  status: string
}

function App() {
  const [hasSession, setHasSession] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    return localStorage.getItem(storageKey) === 'active'
  })

  const signOut = () => {
    localStorage.removeItem(storageKey)
    localStorage.removeItem(tokenKey)
    setHasSession(false)
  }

  // O token vence em uma hora e o SDK o renova sozinho — mas ele guarda a
  // sessão dele, não a nossa cópia. Sem estas assinaturas, o aplicativo
  // começaria a receber 401 depois de uma hora de uso.
  useEffect(() => {
    if (!supabase) return

    void supabase.auth.getSession().then(({ data }) => {
      if (data.session?.access_token) {
        localStorage.setItem(tokenKey, data.session.access_token)
      }
    })

    const { data: assinatura } = supabase.auth.onAuthStateChange((_evento, sessao) => {
      if (sessao?.access_token) {
        localStorage.setItem(tokenKey, sessao.access_token)
      } else {
        signOut()
      }
    })

    return () => assinatura.subscription.unsubscribe()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Sessão recusada pelo motor: volta para a entrada.
  useEffect(() => {
    const sair = () => signOut()
    window.addEventListener('sabia:session-expired', sair)
    return () => window.removeEventListener('sabia:session-expired', sair)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="app-shell">
      <Routes>
        <Route path="/entrar" element={hasSession ? <Navigate to="/perfil" replace /> : <LoginPage onSignedIn={() => setHasSession(true)} />} />
        <Route path="/perfil" element={hasSession ? <ProfilePage onSignOut={signOut} /> : <Navigate to="/entrar" replace />} />
        <Route path="/ler/:bookId" element={hasSession ? <ReaderPage /> : <Navigate to="/entrar" replace />} />
        <Route path="/consultar" element={hasSession ? <ConsultPage /> : <Navigate to="/entrar" replace />} />
        <Route path="*" element={<Navigate to={hasSession ? '/perfil' : '/entrar'} replace />} />
      </Routes>
    </div>
  )
}

function LoginPage({ onSignedIn }: { onSignedIn: () => void }) {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')
    setBusy(true)

    try {
      if (!supabase) {
        throw new Error('Configure VITE_SUPABASE_URL e VITE_SUPABASE_PUBLISHABLE_KEY antes de entrar.')
      }

      const { data, error: loginError } = await supabase.auth.signInWithPassword({ email, password })
      if (loginError || !data.session) {
        throw loginError ?? new Error('Sessão não criada.')
      }

      localStorage.setItem(storageKey, 'active')
      localStorage.setItem(tokenKey, data.session.access_token)
      onSignedIn()
      navigate('/perfil')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Não foi possível entrar.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-panel">
        <p className="eyebrow">Sabiá</p>
        <h1>Entrar</h1>
        <p className="muted-copy">Use sua conta do Supabase para continuar.</p>

        <form className="stack-form" onSubmit={handleSubmit}>
          <label className="field-group">
            <span>E-mail</span>
            <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="nome@email.com" required />
          </label>

          <label className="field-group">
            <span>Senha</span>
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="••••••••" required />
          </label>

          {error ? <p className="inline-error">{error}</p> : null}

          <button type="submit" className="primary-button" disabled={busy}>
            {busy ? 'Entrando…' : 'Entrar'}
          </button>
        </form>
      </div>
    </div>
  )
}

function ProfilePage({ onSignOut }: { onSignOut: () => void }) {
  const navigate = useNavigate()
  const [books, setBooks] = useState<Book[]>([])
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [jobState, setJobState] = useState<Record<string, ProcessState>>({})

  const loadData = async () => {
    try {
      const [booksData, profileData] = await Promise.all([listBooks(), getProfile()])
      setBooks(booksData)
      setProfile(profileData)
      setError('')
    } catch (caught) {
      setError(formatError(caught))
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
        [result.job_id]: { jobId: result.job_id, bookId: result.book_id, status: 'queued' },
      }))
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
      <header className="topbar">
        <div className="brand-block">
          <p className="brand-name">Sabiá</p>
          <p className="brand-tagline">Conexões entre livros</p>
        </div>
        <nav className="main-nav" aria-label="Menu principal">
          <NavLink to="/perfil" className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>Perfil</NavLink>
          <NavLink to="/consultar" className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>Consultar</NavLink>
        </nav>
        <button type="button" className="ghost-button" onClick={onSignOut}>Sair</button>
      </header>

      <main className="workspace-grid">
        <section className="panel panel-large">
          <div className="panel-title-row">
            <div>
              <p className="eyebrow">Perfil</p>
              <h1>Seu acervo</h1>
            </div>
            <span className="status-badge">{profile ? `${profile.texts_today}/${profile.daily_limit}` : '0/0'}</span>
          </div>

          {error ? <p className="inline-error">{error}</p> : null}

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
            <label className="field-group">
              <span>Linha (opcional)</span>
              <input type="text" name="line" placeholder="Linha de aprendizado" />
            </label>
            <button type="submit" className="primary-button" disabled={busy}>
              {busy ? 'Enviando…' : 'Enviar PDF'}
            </button>
          </form>

          <div className="book-list">
            {books.length === 0 ? (
              <div className="empty-card">
                <p>Seu acervo está vazio. Envie um PDF para começar.</p>
              </div>
            ) : (
              books.map((book) => (
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

                  <div className="book-actions">
                    <button type="button" className="secondary-button" onClick={() => navigate(`/ler/${book.id}`)}>Abrir</button>
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
                      const line = (form.elements.namedItem('line') as HTMLInputElement)?.value
                      try {
                        await updateBook(book.id, { title: title || undefined, author: author || undefined, line: line || undefined })
                        await loadData()
                      } catch (caught) {
                        setError(formatError(caught))
                      }
                    }}
                  >
                    <input type="text" name="title" defaultValue={book.title} />
                    <input type="text" name="author" defaultValue={book.author} />
                    <input type="text" name="line" defaultValue={book.line ?? ''} />
                    <button type="submit" className="ghost-button">Salvar</button>
                  </form>
                </article>
              ))
            )}
          </div>
        </section>

        <aside className="panel sidebar-panel">
          <p className="eyebrow">Conta</p>
          <h2>Consumo do dia</h2>
          {profile ? (
            <>
              <div className="metric-row">
                <span>Textos hoje</span>
                <strong>{profile.texts_today}</strong>
              </div>
              <div className="metric-row">
                <span>Limite diário</span>
                <strong>{profile.daily_limit}</strong>
              </div>
            </>
          ) : (
            <p className="muted-copy">Carregando perfil…</p>
          )}

          <div className="divider" />

          <button type="button" className="ghost-button" onClick={async () => {
            await updateProfile(profile?.current_line ?? '')
            onSignOut()
          }}>
            Sair da conta
          </button>
        </aside>
      </main>
    </>
  )
}

function ConsultPage() {
  const [text, setText] = useState('')
  const [scope, setScope] = useState<'others' | 'same'>('others')
  const [k, setK] = useState(3)
  const [minScore, setMinScore] = useState(0)
  const [error, setError] = useState('')
  const [hits, setHits] = useState<ConnectResponse['hits']>([])
  const [card, setCard] = useState<InterpretationResponse | null>(null)

  const handleSubmit = async () => {
    const query = text.trim()
    if (!query) {
      setError('Digite um trecho ou texto para consultar.')
      return
    }

    const payload: ConnectRequest = { text: query, scope, k, min_score: minScore }

    try {
      const [connectResponse, interpretResponse] = await Promise.all([connect(payload), interpret(payload)])
      setHits(connectResponse.hits)
      setCard(interpretResponse)
      setError('')
    } catch (caught) {
      setError(formatError(caught))
    }
  }

  return (
    <>
      <header className="topbar">
        <div className="brand-block">
          <p className="brand-name">Sabiá</p>
          <p className="brand-tagline">Consulta</p>
        </div>
        <nav className="main-nav" aria-label="Navegação da consulta">
          <Link to="/perfil" className="nav-link">Perfil</Link>
          <Link to="/consultar" className="nav-link active">Consultar</Link>
        </nav>
      </header>

      <main className="consult-layout">
        <section className="panel panel-large">
          <div className="panel-title-row">
            <div>
              <p className="eyebrow">Modo II</p>
              <h1>Consultar</h1>
            </div>
          </div>

          <div className="query-box">
            <label className="field-group">
              <span>Texto para consultar</span>
              <textarea rows={8} value={text} onChange={(event) => setText(event.target.value)} placeholder="Cole um trecho ou uma ideia para consultar no acervo." />
            </label>

            <div className="query-controls">
              <label className="field-group">
                <span>Escopo</span>
                <select value={scope} onChange={(event) => setScope(event.target.value as 'others' | 'same')}>
                  <option value="others">Outros livros</option>
                  <option value="same">Só o livro aberto</option>
                </select>
              </label>

              <label className="field-group">
                <span>Quantidade</span>
                <input type="number" min={1} max={10} value={k} onChange={(event) => setK(Number(event.target.value) || 1)} />
              </label>

              <label className="field-group">
                <span>mín. score</span>
                <input type="number" min={0} max={1} step={0.1} value={minScore} onChange={(event) => setMinScore(Number(event.target.value) || 0)} />
              </label>
            </div>

            {error ? <p className="inline-error">{error}</p> : null}

            <button type="button" className="primary-button" onClick={handleSubmit}>Buscar</button>
          </div>
        </section>

        <aside className="panel sidebar-panel">
          <p className="eyebrow">Resultado</p>
          <h2>Evidência</h2>
          <div className="result-stack">
            {hits.length === 0 ? <p className="muted-copy">Os trechos mais relevantes aparecerão aqui.</p> : hits.map((hit) => (
              <article key={`${hit.book_id}-${hit.page_index}-${hit.text.slice(0, 12)}`} className="result-card">
                <div className="result-head">
                  <strong>{hit.title}</strong>
                  <span>{hit.score.toFixed(2)}</span>
                </div>
                <p>{hit.text}</p>
                <small>{hit.author} · página {hit.page_label ?? hit.page_index + 1}</small>
              </article>
            ))}
          </div>

          <div className="divider" />

          {card ? (
            <article className="result-card emphasis">
              <div className="result-head">
                <strong>{card.relation ?? 'Sem classificação'}</strong>
              </div>
              <p>{card.card}</p>
            </article>
          ) : (
            <p className="muted-copy">O card de interpretação aparece depois da busca.</p>
          )}
        </aside>
      </main>
    </>
  )
}

export default App
