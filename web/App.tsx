import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useNavigate, useSearchParams } from 'react-router-dom'
import { createClient } from '@supabase/supabase-js'
import type { Book, ConnectRequest, ConnectResponse, ErrorResponse, InterpretationResponse, JobProgress, Profile } from './types'
import { connect, deleteBook, formatError, getJob, getProfile, listBooks, updateBook, updateProfile, uploadBook } from './api'
import ReaderPage from './ReaderPage'
import ToolHeader from './ToolHeader'
import LoadingIndicator from './LoadingIndicator'

const storageKey = 'sabia_session'
const tokenKey = 'sabia_token'
const consultationStoragePrefix = 'sabia_last_consultation:'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || ''
const supabaseKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || import.meta.env.VITE_SUPABASE_ANON_KEY || ''
const supabase = supabaseUrl && supabaseKey ? createClient(supabaseUrl, supabaseKey) : null

type ProcessState = {
  jobId: string
  bookId: string
  status: string
  processed: number
  total: number | null
}

type SavedConsultation = {
  text: string
  scope: 'others' | 'same'
  k: number
  minScore: number
  hits: ConnectResponse['hits']
  card: InterpretationResponse | null
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
    <div className="workspace-page">
      <div className="workspace-shell">
        <Routes>
          <Route path="/entrar" element={hasSession ? <Navigate to="/perfil" replace /> : <LoginPage onSignedIn={() => setHasSession(true)} />} />
          <Route path="/perfil" element={hasSession ? <ProfilePage onSignOut={signOut} /> : <Navigate to="/entrar" replace />} />
          <Route path="/consultar" element={hasSession ? <ConsultPage /> : <Navigate to="/entrar" replace />} />
          <Route path="*" element={<Navigate to={hasSession ? '/perfil' : '/entrar'} replace />} />
        </Routes>
      </div>
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

function HelpTip({ children }: { children: string }) {
  return (
    <span className="help-tip">
      <button type="button" className="help-tip-button" aria-label="Mais informações">?</button>
      <span className="help-tip-content" role="tooltip">{children}</span>
    </span>
  )
}

function ProfilePage({ onSignOut }: { onSignOut: () => void }) {
  const navigate = useNavigate()
  const [books, setBooks] = useState<Book[]>([])
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loadingBooks, setLoadingBooks] = useState(true)
  const [jobState, setJobState] = useState<Record<string, ProcessState>>({})

  const loadData = async () => {
    try {
      const [booksData, profileData] = await Promise.all([listBooks(), getProfile()])
      setBooks(booksData)
      setProfile(profileData)
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
      <ToolHeader mode="profile" />

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
            <button type="submit" className="primary-button" disabled={busy}>
              {busy ? 'Enviando…' : 'Enviar PDF'}
            </button>
          </form>

          <div className="book-list">
            {loadingBooks ? (
              <LoadingIndicator label="Carregando livros" />
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
                    setProfile(await updateProfile({ current_line: currentLine }))
                    setError('')
                  } catch (caught) {
                    setError(formatError(caught))
                  }
                }}>
                  <label className="field-group">
                    <span className="field-label-with-help">
                      Linha de aprendizado
                      <HelpTip>O assunto da leitura. Ele fica como contexto corrente para as consultas.</HelpTip>
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
                    setProfile(await updateProfile({ interpretation_profile: texto }))
                    setError('')
                  } catch (caught) {
                    setError(formatError(caught))
                  }
                }}>
                  <label className="field-group">
                    <span className="field-label-with-help">
                      Como interpretar
                      <HelpTip>Oriente o tom e os aspectos que o Sabiá deve priorizar ao relacionar suas ideias com os livros.</HelpTip>
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
                  <HelpTip>Define o espaço esperado para o card: Padrão tem até três frases, Alto até oito e Livre deixa o modelo decidir.</HelpTip>
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
                          setProfile(await updateProfile({ card_length: valor }))
                          setError('')
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
                    <HelpTip>Consultas e conexões mostram o que você leu. A cota representa os trechos consumidos pela ingestão contra o limite do dia.</HelpTip>
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

function ConsultPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [books, setBooks] = useState<Book[]>([])
  const [profile, setProfile] = useState<Profile | null>(null)
  const [bookId, setBookId] = useState(() => searchParams.get('book') ?? '')
  const [text, setText] = useState('')
  const [scope, setScope] = useState<'others' | 'same'>('others')
  const [k, setK] = useState(3)
  // A precisão começa no piso da instalação, que vem no perfil: o leitor só sobe.
  const [minScore, setMinScore] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [hits, setHits] = useState<ConnectResponse['hits']>([])
  const [card, setCard] = useState<InterpretationResponse | null>(null)
  const requestRef = useRef('')
  const [loadingBooks, setLoadingBooks] = useState(true)
  const [loadingConnections, setLoadingConnections] = useState(false)
  const requestedBookId = searchParams.get('book') ?? ''

  useEffect(() => {
    if (requestedBookId && requestedBookId !== bookId) {
      setBookId(requestedBookId)
      setHits([])
      setCard(null)
    }
  }, [bookId, requestedBookId])

  useEffect(() => {
    if (!bookId) return

    const raw = localStorage.getItem(`${consultationStoragePrefix}${bookId}`)
    if (!raw) {
      setText('')
      setHits([])
      setCard(null)
      return
    }

    try {
      const saved = JSON.parse(raw) as SavedConsultation
      setText(typeof saved.text === 'string' ? saved.text : '')
      setScope(saved.scope === 'same' ? 'same' : 'others')
      setK(Math.min(10, Math.max(1, Number(saved.k) || 1)))
      setMinScore(typeof saved.minScore === 'number' ? saved.minScore : null)
      setHits(Array.isArray(saved.hits) ? saved.hits : [])
      setCard(saved.card && typeof saved.card.card === 'string' ? saved.card : null)
    } catch {
      setText('')
      setHits([])
      setCard(null)
    }
  }, [bookId])

  useEffect(() => {
    void getProfile()
      .then((atual) => {
        setProfile(atual)
        setMinScore((escolhido) => escolhido ?? atual.min_score_floor)
      })
      .catch(() => setMinScore((escolhido) => escolhido ?? 0))
  }, [])

  useEffect(() => {
    setLoadingBooks(true)
    void listBooks().then((items) => {
      setBooks(items)
      if (!bookId && items[0]) {
        setBookId(items[0].id)
        setSearchParams({ book: items[0].id }, { replace: true })
      }
    }).catch((caught) => setError(formatError(caught)))
      .finally(() => setLoadingBooks(false))
  }, [bookId, setSearchParams])

  const handleSubmit = async () => {
    const query = text.trim()
    if (!query) {
      setError('Digite um trecho ou texto para consultar.')
      return
    }

    if (scope === 'same' && !bookId) {
      setError('Escolha um livro para consultar apenas dentro dele.')
      return
    }

    const payload: ConnectRequest = {
      text: query,
      scope,
      book_id: bookId || undefined,
      k,
      ...(minScore === null ? {} : { min_score: minScore }),
    }
    const requestKey = `${query}|${scope}|${bookId}|${k}|${minScore}`
    requestRef.current = requestKey
    setLoadingConnections(true)

    try {
      const resposta = await connect(payload)
      if (requestRef.current !== requestKey) return
      setHits(resposta.hits)
      setCard(resposta)
      // O valor efetivo volta do motor: subir nunca fica só na tela.
      setMinScore(resposta.min_score)
      localStorage.setItem(`${consultationStoragePrefix}${bookId}`, JSON.stringify({
        text: query,
        scope,
        k,
        minScore: resposta.min_score,
        hits: resposta.hits,
        card: resposta.card === null ? null : {
          card: resposta.card,
          relation: resposta.relation,
          citations: resposta.citations,
        },
      } satisfies SavedConsultation))
      setError('')
    } catch (caught) {
      if (requestRef.current === requestKey) setError(formatError(caught))
    } finally {
      if (requestRef.current === requestKey) setLoadingConnections(false)
    }
  }

  return (
    <>
      <ToolHeader />

      <main className="consult-layout">
        <aside className="connections-rail consult-rail" aria-label="Busca e interpretação">
          <div className="rail-header">
            <div>
              <p className="eyebrow">Ferramenta de consulta</p>
              <h1>Interpretação</h1>
            </div>
            <span className="rail-dot" aria-hidden="true" />
          </div>

          <div className="rail-content">
            <section className="rail-view">
              <p className="rail-intro">Encontre o que outros autores dizem sobre uma ideia do livro.</p>

              <label className="rail-field">
                <span>Trecho para buscar</span>
                <textarea rows={5} value={text} onChange={(event) => setText(event.target.value)} placeholder="Cole aqui um trecho ou selecione uma passagem no livro" />
              </label>

              <div className="rail-row">
                <label className="rail-field rail-field-grow">
                  <span>Escopo</span>
                  <select value={scope} onChange={(event) => setScope(event.target.value as 'others' | 'same')}>
                    <option value="others">Outros livros</option>
                    <option value="same">Só este livro</option>
                  </select>
                </label>
                <label className="rail-field rail-k-field">
                  <span>Nº conexões</span>
                  <input type="number" min={1} max={10} value={k} onChange={(event) => setK(Math.min(10, Math.max(1, Number(event.target.value) || 1)))} />
                </label>
              </div>

              <label className="rail-field rail-precision">
                <span className="field-label-with-help">
                  <span>
                    Precisão mínima
                    <HelpTip>As conexões abaixo deste valor não são retornadas. O piso da instalação é o menor valor permitido.</HelpTip>
                  </span>
                  <strong>{minScore === null ? '—' : minScore.toFixed(2)}</strong>
                </span>
                <input
                  type="range"
                  min={profile?.min_score_floor ?? 0}
                  max={0.95}
                  step={0.01}
                  value={minScore ?? 0}
                  onChange={(event) => setMinScore(Number(event.target.value))}
                />
              </label>

              <button type="button" className="primary-button rail-search-button" onClick={handleSubmit} disabled={loadingConnections || loadingBooks}>
                {loadingConnections ? 'Buscando conexões…' : 'Buscar conexões'}
              </button>
              <p className="rail-hint">Ou selecione um trecho diretamente no livro.</p>

              {error ? <p className="inline-error">{error}</p> : null}

              <div className="consult-results">
                {loadingConnections ? <LoadingIndicator label="Construindo conexões" /> : null}
                {!loadingConnections && card ? (
                  <article className="rail-card interpretation-card" tabIndex={0}>
                    <p className="rail-card-summary">{card.card}</p>
                    <span className="relation-badge">{card.relation ?? 'Sem classificação'}</span>
                    <div className="interpretation-preview" role="tooltip" tabIndex={0}>
                      <p>{card.card}</p>
                    </div>
                  </article>
                ) : null}
              </div>
            </section>
          </div>
        </aside>

        <div className="consult-main">
          <section className="consult-book">
            {bookId ? (
              <ReaderPage
                embedded
                bookIdOverride={bookId}
                externalSelectedText={text}
                onSelectionChange={setText}
              />
            ) : (
              <div className="empty-card">Envie um livro no perfil para começar a consultar.</div>
            )}
          </section>

          <section className="consult-connections" aria-label="Conexões encontradas">
            <div className="connections-title">
              <div>
                <p className="eyebrow">Conexões</p>
                <h2>Evidências encontradas</h2>
              </div>
            </div>

            <div className="consult-results">
              {!loadingConnections && hits.length === 0 ? (
                <p className="muted-copy">As conexões encontradas aparecerão aqui.</p>
              ) : null}
              {!loadingConnections && hits.map((hit) => (
                <article key={`${hit.book_id}-${hit.page_index}-${hit.text.slice(0, 12)}`} className="rail-hit">
                  <p className="rail-hit-meta"><strong>{hit.author}</strong> · <span>{hit.title}, pág. {hit.page_label ?? hit.page_index + 1}</span><b>score {hit.score.toFixed(3)}</b></p>
                  <p className="rail-hit-text">{hit.text}</p>
                </article>
              ))}
            </div>
          </section>
        </div>
      </main>
    </>
  )
}

export default App
