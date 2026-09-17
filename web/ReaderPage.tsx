/**
 * O leitor: o PDF desenhado no navegador, com o pdf.js.
 *
 * O motor entrega os bytes do arquivo (com o token); quem interpreta e desenha
 * é este componente, na máquina de quem lê. Isso dá duas coisas que o
 * visualizador embutido do navegador não daria: a **página de verdade**, e não
 * uma extração nossa, e a **seleção de trecho** — a camada de texto que o
 * pdf.js põe sobre o desenho é texto comum para o navegador, então arrastar o
 * mouse seleciona como em qualquer página.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import * as pdfjs from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

import { connect, fetchBookFile, formatError, interpret, listBooks } from './api'
import type { Book, ConnectRequest, ConnectResponse, InterpretationResponse } from './types'

// O parsing roda fora da linha principal, num worker; é ele que não deixa a
// rolagem travar em página grande.
pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

const ZOOM_INICIAL = 1.3
const ZOOM_MINIMO = 0.6
const ZOOM_MAXIMO = 3
const PASSO_ZOOM = 0.2

export default function ReaderPage() {
  const { bookId } = useParams()
  const navegar = useNavigate()
  const local = useLocation()

  const [books, setBooks] = useState<Book[]>([])
  const [activeBook, setActiveBook] = useState<Book | null>(null)
  const [pageCount, setPageCount] = useState(0)
  const [page, setPage] = useState(1)
  const [alvoDaPagina, setAlvoDaPagina] = useState('1')
  const [zoom, setZoom] = useState(ZOOM_INICIAL)
  const [status, setStatus] = useState('carregando o arquivo…')
  const [selectedText, setSelectedText] = useState('')
  const [hits, setHits] = useState<ConnectResponse['hits']>([])
  const [card, setCard] = useState<InterpretationResponse | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const layerRef = useRef<HTMLDivElement | null>(null)
  const docRef = useRef<pdfjs.PDFDocumentProxy | null>(null)
  const desenhoRef = useRef(0)
  const pedidoRef = useRef(0)

  // Acervo, bytes do arquivo e documento. Refaz tudo quando o livro muda.
  useEffect(() => {
    let vivo = true
    setStatus('carregando o arquivo…')
    setError('')
    setHits([])
    setCard(null)
    setSelectedText('')

    void (async () => {
      try {
        const lista = await listBooks()
        if (!vivo || !bookId) return
        setBooks(lista)
        setActiveBook(lista.find((book) => book.id === bookId) ?? null)

        const bytes = await fetchBookFile(bookId)
        const documento = await pdfjs.getDocument({ data: bytes }).promise
        if (!vivo) {
          void documento.destroy()
          return
        }

        docRef.current?.destroy()
        docRef.current = documento
        setPageCount(documento.numPages)

        // Vindo de uma citação de outro livro, o pedido traz a página.
        const pedida = (local.state as { pagina?: number } | null)?.pagina
        const inicial = pedida && pedida >= 1 && pedida <= documento.numPages ? pedida : 1
        setPage(inicial)
        setAlvoDaPagina(String(inicial))
        setStatus('')
      } catch (caught) {
        if (!vivo) return
        setStatus('')
        setError(formatError(caught))
      }
    })()

    return () => {
      vivo = false
      docRef.current?.destroy()
      docRef.current = null
    }
    // `local.state` só importa na entrada; recarregar por ele voltaria a página.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookId])

  // Desenho da página atual: canvas na resolução da tela, camada de texto por cima.
  useEffect(() => {
    const documento = docRef.current
    const canvas = canvasRef.current
    const layer = layerRef.current
    if (!documento || !canvas || !layer || pageCount === 0) return

    const marca = ++desenhoRef.current

    void (async () => {
      const pagina = await documento.getPage(page)
      if (marca !== desenhoRef.current) return

      const densidade = window.devicePixelRatio || 1
      const vista = pagina.getViewport({ scale: zoom })
      const nitida = pagina.getViewport({ scale: zoom * densidade })

      canvas.width = Math.floor(nitida.width)
      canvas.height = Math.floor(nitida.height)
      canvas.style.width = `${vista.width}px`
      canvas.style.height = `${vista.height}px`

      // No pdf.js 5 o desenho recebe o próprio canvas (era `canvasContext` na 4).
      await pagina.render({ canvas, viewport: nitida }).promise
      if (marca !== desenhoRef.current) return

      // A camada de texto é invisível e posicionada palavra a palavra: é ela
      // que o navegador enxerga como texto para selecionar.
      layer.innerHTML = ''
      layer.style.setProperty('--total-scale-factor', String(zoom))
      const conteudo = await pagina.getTextContent()
      if (marca !== desenhoRef.current) return

      const camada = new pdfjs.TextLayer({
        textContentSource: conteudo,
        container: layer,
        viewport: vista,
      })
      await camada.render()
      pdfjs.setLayerDimensions(layer, vista)
    })().catch((caught) => {
      if (marca === desenhoRef.current) setError(formatError(caught))
    })
  }, [page, zoom, pageCount])

  /** Ao soltar o mouse, o que ficou selecionado vira o trecho a conectar. */
  const capturarSelecao = useCallback(() => {
    const bruto = window.getSelection()?.toString() ?? ''
    // Os trechos vêm fatiados por linha: junta os espaços e as quebras.
    const limpo = bruto.replace(/\s+/g, ' ').trim()
    if (limpo) setSelectedText(limpo)
  }, [])

  const irPara = (numero: number) => {
    if (!Number.isFinite(numero)) return
    const destino = Math.min(Math.max(1, Math.trunc(numero)), Math.max(1, pageCount))
    setPage(destino)
    setAlvoDaPagina(String(destino))
  }

  const buscarConexoes = async () => {
    const texto = selectedText.trim()
    if (!texto || !bookId) {
      setError('Selecione um trecho no livro para buscar conexões.')
      return
    }

    // A marca separa este pedido dos anteriores: resposta de seleção que já
    // não é a atual não se mostra.
    const marca = ++pedidoRef.current
    setBusy(true)
    try {
      const payload: ConnectRequest = {
        text: texto,
        scope: 'others',
        book_id: bookId,
        k: 3,
        min_score: 0,
      }
      const [conexoes, interpretacao] = await Promise.all([connect(payload), interpret(payload)])
      if (marca !== pedidoRef.current) return
      setHits(conexoes.hits)
      setCard(interpretacao)
      setError('')
    } catch (caught) {
      if (marca === pedidoRef.current) setError(formatError(caught))
    } finally {
      if (marca === pedidoRef.current) setBusy(false)
    }
  }

  /** A citação abre a página: no mesmo livro, aqui; em outro, lá. */
  const abrirCitacao = (citacao: InterpretationResponse['citations'][number]) => {
    if (citacao.book_id === bookId) {
      irPara(citacao.page_index + 1)
      return
    }
    navegar(`/ler/${citacao.book_id}`, { state: { pagina: citacao.page_index + 1 } })
  }

  const mudarZoom = (passo: number) => {
    setZoom((atual) => {
      const novo = Math.min(ZOOM_MAXIMO, Math.max(ZOOM_MINIMO, atual + passo))
      return Number(novo.toFixed(2))
    })
  }

  return (
    <>
      <header className="topbar">
        <div className="brand-block">
          <p className="brand-name">Sabiá</p>
          <p className="brand-tagline">Leitura</p>
        </div>
        <nav className="main-nav" aria-label="Menu de leitura">
          <Link to="/perfil" className="nav-link">Perfil</Link>
          <Link to="/consultar" className="nav-link">Consultar</Link>
        </nav>
      </header>

      <main className="reader-layout workspace-grid">
        <section className="panel viewer-panel">
          <div className="panel-title-row">
            <div>
              <p className="eyebrow">Livro</p>
              <h1>{activeBook?.title ?? 'Livro'}</h1>
              {activeBook ? <p className="muted-copy">{activeBook.author}</p> : null}
            </div>
            <select
              value={bookId ?? ''}
              onChange={(evento) => navegar(`/ler/${evento.target.value}`)}
              aria-label="Trocar de livro"
            >
              {books.map((book) => (
                <option key={book.id} value={book.id}>{book.title}</option>
              ))}
            </select>
          </div>

          {error ? <p className="inline-error">{error}</p> : null}
          {status ? <p className="muted-copy">{status}</p> : null}

          <div className="pdf-frame">
            <div className="pdf-toolbar">
              <button
                type="button"
                className="ghost-button"
                onClick={() => irPara(page - 1)}
                disabled={page <= 1}
              >
                Anterior
              </button>
              <span className="pdf-position">
                página <strong>{page}</strong> de {pageCount || '—'}
              </span>
              <button
                type="button"
                className="ghost-button"
                onClick={() => irPara(page + 1)}
                disabled={pageCount === 0 || page >= pageCount}
              >
                Próxima
              </button>

              <label className="field-group pdf-goto">
                <span>Ir para</span>
                <input
                  type="number"
                  min={1}
                  max={pageCount || 1}
                  value={alvoDaPagina}
                  onChange={(evento) => setAlvoDaPagina(evento.target.value)}
                  onKeyDown={(evento) => {
                    if (evento.key === 'Enter') irPara(Number(alvoDaPagina))
                  }}
                />
              </label>

              <span className="pdf-zoom">
                <button type="button" className="ghost-button" onClick={() => mudarZoom(-PASSO_ZOOM)}>−</button>
                <span className="muted-copy">{Math.round(zoom * 100)}%</span>
                <button type="button" className="ghost-button" onClick={() => mudarZoom(PASSO_ZOOM)}>+</button>
              </span>
            </div>

            <div className="pdf-stage">
              <div className="pdf-page">
                <canvas ref={canvasRef} />
                <div ref={layerRef} className="textLayer" onMouseUp={capturarSelecao} />
              </div>
            </div>
          </div>

          <div className="selection-box">
            <label className="field-group">
              <span>Trecho selecionado</span>
              <textarea
                rows={5}
                value={selectedText}
                onChange={(evento) => setSelectedText(evento.target.value)}
                placeholder="Selecione um trecho no livro ou cole aqui."
              />
            </label>
            <button type="button" className="primary-button" onClick={buscarConexoes} disabled={busy}>
              {busy ? 'Buscando conexões…' : 'Buscar conexões'}
            </button>
          </div>
        </section>

        <aside className="panel sidebar-panel">
          <p className="eyebrow">Conexões</p>
          <h2>Evidência</h2>

          <div className="result-stack">
            {hits.length === 0 ? (
              <p className="muted-copy">Selecione um trecho para ver o que outros autores dizem.</p>
            ) : (
              hits.map((hit) => (
                <article
                  key={`${hit.book_id}-${hit.page_index}-${hit.text.slice(0, 24)}`}
                  className="result-card"
                >
                  <div className="result-head">
                    <strong>{hit.title}</strong>
                    <span>{hit.score.toFixed(2)}</span>
                  </div>
                  <p>{hit.text}</p>
                  <small>{hit.author} · página {hit.page_label ?? hit.page_index + 1}</small>
                </article>
              ))
            )}
          </div>

          <div className="divider" />

          <div className="result-stack">
            {card ? (
              <article className="result-card emphasis">
                <div className="result-head">
                  <strong>{card.relation ?? 'Sem classificação'}</strong>
                </div>
                <p>{card.card}</p>
                {card.citations.length > 0 ? (
                  <ul className="citation-list">
                    {card.citations.map((citacao) => (
                      <li key={`${citacao.book_id}-${citacao.page_index}`}>
                        <button type="button" className="link-button" onClick={() => abrirCitacao(citacao)}>
                          {citacao.title} · página {citacao.page_label ?? citacao.page_index + 1}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </article>
            ) : (
              <p className="muted-copy">O card de interpretação aparecerá aqui.</p>
            )}
          </div>
        </aside>
      </main>
    </>
  )
}
