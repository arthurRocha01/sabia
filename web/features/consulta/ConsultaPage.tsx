import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { Book, ConnectRequest, ConnectResponse, InterpretationResponse } from '../../api/types'
import { formatError } from '../../api/client'
import { connect } from '../../api/connect'
import { listBooks } from '../../api/books'
import { useProfile } from '../../app/profile'
import Dica from '../../ui/Dica'
import LeitorPage from '../leitura/LeitorPage'
import Cabecalho from '../../ui/Cabecalho'
import Indicador from '../../ui/Indicador'

const consultationStoragePrefix = 'sabia_last_consultation:'

type SavedConsultation = {
  text: string
  scope: 'others' | 'same'
  k: number
  minScore: number
  hits: ConnectResponse['hits']
  card: InterpretationResponse | null
}

export default function ConsultaPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [books, setBooks] = useState<Book[]>([])
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
  const [findRequest, setFindRequest] = useState<{ id: number; text: string } | undefined>()
  const [errorVersion, setErrorVersion] = useState(0)
  const [errorDismissing, setErrorDismissing] = useState(false)
  const requestedBookId = searchParams.get('book') ?? ''
  const { profile } = useProfile()
  const mostrarErro = (mensagem: string) => {
    setError(mensagem)
    setErrorDismissing(false)
    setErrorVersion((versao) => versao + 1)
  }

  useEffect(() => {
    if (!error) return
    const saida = window.setTimeout(() => setErrorDismissing(true), 4500)
    const remocao = window.setTimeout(() => setError(''), 5000)
    return () => {
      window.clearTimeout(saida)
      window.clearTimeout(remocao)
    }
  }, [error, errorVersion])

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
    setMinScore((escolhido) => escolhido ?? profile?.min_score_floor ?? null)
  }, [profile?.min_score_floor])

  useEffect(() => {
    setLoadingBooks(true)
    void listBooks().then((items) => {
      setBooks(items)
      if (!bookId && items[0]) {
        setBookId(items[0].id)
        setSearchParams({ book: items[0].id }, { replace: true })
      }
    }).catch((caught) => mostrarErro(formatError(caught)))
      .finally(() => setLoadingBooks(false))
  }, [bookId, setSearchParams])

  const handleSubmit = async () => {
    const query = text.trim()
    if (!query) {
      mostrarErro('Digite um trecho ou texto para consultar.')
      return
    }

    if (scope === 'same' && !bookId) {
      mostrarErro('Escolha um livro para consultar apenas dentro dele.')
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
      if (requestRef.current === requestKey) mostrarErro(formatError(caught))
    } finally {
      if (requestRef.current === requestKey) setLoadingConnections(false)
    }
  }

  return (
    <>
      <Cabecalho books={books} loading={loadingBooks} />

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
                <textarea
                  rows={5}
                  value={text}
                  onChange={(event) => {
                    const valor = event.target.value
                    setText(valor)
                    setError('')
                    setFindRequest((atual) => ({ id: (atual?.id ?? 0) + 1, text: valor }))
                  }}
                  placeholder="Cole aqui um trecho ou selecione uma passagem no livro"
                />
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
                    <Dica>As conexões abaixo deste valor não são retornadas. O piso da instalação é o menor valor permitido.</Dica>
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

              {error ? <p key={errorVersion} className={`inline-error${errorDismissing ? ' is-dismissing' : ''}`} role="alert" aria-live="assertive">{error}</p> : null}

              <div className="consult-results">
                {loadingConnections ? <Indicador label="Construindo conexões" /> : null}
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
              <LeitorPage
                embedded
                bookIdOverride={bookId}
                externalSelectedText={text}
                onSelectionChange={setText}
                findRequest={findRequest}
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
