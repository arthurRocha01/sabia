import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { Book, ConnectRequest, ConnectResponse, InterpretationResponse } from '../../api/types'
import { formatError } from '../../api/client'
import { connect } from '../../api/connect'
import { listBooks } from '../../api/books'
import { useProfile } from '../../app/profile'
import { usePrecision } from '../../app/precision'
import Header from '../../ui/Header'
import ReaderPage from '../leitura/ReaderPage'
import ConnectionList from './ConnectionList'
import SearchRail from './SearchRail'

const consultationStoragePrefix = 'sabia_last_consultation:'

type SavedConsultation = {
  text: string
  scope: 'others' | 'same'
  k: number
  minScore: number
  hits: ConnectResponse['hits']
  card: InterpretationResponse | null
}

/** A consulta: o rail de busca, o livro aberto e as evidências abaixo. */
export default function ConsultPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [books, setBooks] = useState<Book[]>([])
  const [bookId, setBookId] = useState(() => searchParams.get('book') ?? '')
  const [text, setText] = useState('')
  const [scope, setScope] = useState<'others' | 'same'>('others')
  const [k, setK] = useState(3)
  const [error, setError] = useState('')
  const [hits, setHits] = useState<ConnectResponse['hits']>([])
  const [card, setCard] = useState<InterpretationResponse | null>(null)
  const requestRef = useRef('')
  const [loadingBooks, setLoadingBooks] = useState(true)
  const [loadingConnections, setLoadingConnections] = useState(false)
  const [findRequest, setFindRequest] = useState<{ id: number; text: string } | undefined>()
  const [errorVersion, setErrorVersion] = useState(0)
  const [errorDismissing, setErrorDismissing] = useState(false)
  const [mobilePanel, setMobilePanel] = useState<'search' | 'connections' | null>(null)
  const requestedBookId = searchParams.get('book') ?? ''
  const { profile } = useProfile()
  // A precisão é a mesma da leitura: vive no provedor, não nesta tela.
  const { minScore, setMinScore, floor } = usePrecision()

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
  }, [bookId, setMinScore])

  useEffect(() => {
    setLoadingBooks(true)
    void listBooks()
      .then((items) => {
        setBooks(items)
        if (!bookId && items[0]) {
          setBookId(items[0].id)
          setSearchParams({ book: items[0].id }, { replace: true })
        }
      })
      .catch((caught) => mostrarErro(formatError(caught)))
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
      localStorage.setItem(
        `${consultationStoragePrefix}${bookId}`,
        JSON.stringify({
          text: query,
          scope,
          k,
          minScore: resposta.min_score,
          hits: resposta.hits,
          card:
            resposta.card === null
              ? null
              : {
                  card: resposta.card,
                  relation: resposta.relation,
                  citations: resposta.citations,
                },
        } satisfies SavedConsultation),
      )
      setError('')
    } catch (caught) {
      if (requestRef.current === requestKey) mostrarErro(formatError(caught))
    } finally {
      if (requestRef.current === requestKey) setLoadingConnections(false)
    }
  }

  const aoDigitar = (valor: string) => {
    setText(valor)
    setError('')
    setFindRequest((atual) => ({ id: (atual?.id ?? 0) + 1, text: valor }))
  }

  const alternarPainel = (painel: 'search' | 'connections') => {
    setMobilePanel((atual) => (atual === painel ? null : painel))
  }

  return (
    <>
      <Header books={books} loading={loadingBooks} />

      <main className="consult-layout">
        <SearchRail
          className={mobilePanel === 'search' ? 'is-mobile-open' : ''}
          text={text}
          scope={scope}
          count={k}
          precision={minScore}
          floor={profile?.min_score_floor ?? floor}
          card={card}
          error={error}
          errorVersion={errorVersion}
          errorFading={errorDismissing}
          busy={loadingConnections}
          booksLoading={loadingBooks}
          onText={aoDigitar}
          onScope={setScope}
          onCount={setK}
          onPrecision={setMinScore}
          onSearch={handleSubmit}
        />

        <div className="consult-main">
          <section className="consult-book">
            {bookId ? (
              <ReaderPage
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

          <section className={`consult-connections${mobilePanel === 'connections' ? ' is-mobile-open' : ''}`} aria-label="Conexões encontradas">
            <div className="connections-title">
              <div>
                <p className="eyebrow">Conexões</p>
                <h2>Evidências encontradas</h2>
              </div>
              <button type="button" className="panel-control mobile-panel-close" onClick={() => setMobilePanel(null)} aria-label="Fechar painel">
                ×
              </button>
            </div>

            <div className="consult-results">
              <ConnectionList hits={hits} loading={loadingConnections} />
            </div>
          </section>
        </div>
      </main>
      <div className="mobile-consult-actions" aria-label="Painéis da consulta">
        <button
          type="button"
          onClick={() => alternarPainel('search')}
          aria-expanded={mobilePanel === 'search'}
        >
          Interpretação
        </button>
        <button
          type="button"
          onClick={() => alternarPainel('connections')}
          aria-expanded={mobilePanel === 'connections'}
        >
          Conexões{hits.length ? ` (${hits.length})` : ''}
        </button>
      </div>
    </>
  )
}
