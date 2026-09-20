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
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import * as pdfjs from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

import { formatError } from '../../api/client'
import { connect } from '../../api/connect'
import { fetchBookFile, listBooks } from '../../api/books'
import type { Book, ConnectRequest, ConnectResponse, InterpretationResponse } from '../../api/types'
import { useProfile } from '../../app/profile'
import { usePrecision } from '../../app/precision'
import Header from '../../ui/Header'
import Indicator from '../../ui/Indicator'
import Citation from './Citation'
import PdfPage from './PdfPage'
import BookToolbar from './BookToolbar'
import EvidencePanel from './EvidencePanel'
import BookFooter from './BookFooter'
import TextSelection from './TextSelection'
import type { PointerEvent as ReactPointerEvent } from 'react'
import { readImage } from '../../api/read'

// O parsing roda fora da linha principal, num worker; é ele que não deixa a
// rolagem travar em página grande.
pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

const ZOOM_INICIAL = 1.3
const ZOOM_MINIMO = 0.6
const ZOOM_MAXIMO = 3
const PASSO_ZOOM = 0.2
const paginaStoragePrefix = 'sabia_reader_page:'

type ReaderPageProps = {
  embedded?: boolean
  bookIdOverride?: string
  externalSelectedText?: string
  onSelectionChange?: (text: string) => void
  findRequest?: {
    id: number
    text: string
  }
}

type TextPosition = {
  node: Text
  start: number
  end: number
}

const normalizarTexto = (texto: string) => texto.replace(/\s+/g, ' ').trim()

type CaixaDeMarcacao = {
  esquerda: number
  topo: number
  largura: number
  altura: number
}

export default function ReaderPage({
  embedded = false,
  bookIdOverride,
  externalSelectedText,
  onSelectionChange,
  findRequest,
}: ReaderPageProps) {
  const { profile } = useProfile()
  const { minScore } = usePrecision()
  const params = useParams()
  const bookId = bookIdOverride ?? params.bookId
  const navegar = useNavigate()
  const local = useLocation()

  const [books, setBooks] = useState<Book[]>([])
  const [activeBook, setActiveBook] = useState<Book | null>(null)
  const [pageCount, setPageCount] = useState(0)
  const [page, setPage] = useState(1)
  const [pageTarget, setPageTarget] = useState('1')
  const [paginasVisiveis, setPaginasVisiveis] = useState(2)
  // Uma página por página: capa e ilustração não têm texto, e sem isto o
  // arraste simplesmente não faz nada, sem explicação.
  const [paginasComTexto, setPaginasComTexto] = useState<boolean[]>([])
  const [marcando, setMarcando] = useState(false)
  const [caixaDaMarcacao, setCaixaDaMarcacao] = useState<CaixaDeMarcacao | null>(null)
  const [zoom, setZoom] = useState(ZOOM_INICIAL)
  const [status, setStatus] = useState('carregando o arquivo…')
  const [selectedText, setSelectedText] = useState(externalSelectedText ?? '')
  const [hits, setHits] = useState<ConnectResponse['hits']>([])
  const [card, setCard] = useState<InterpretationResponse | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [paginaRenderizada, setPaginaRenderizada] = useState(false)
  const [connectionsOpen, setConnectionsOpen] = useState(true)
  const [bookWidth, setBookWidth] = useState(0)
  const [errorVersion, setErrorVersion] = useState(0)
  const [errorDismissing, setErrorDismissing] = useState(false)

  const canvasRefs = useRef<Array<HTMLCanvasElement | null>>([])
  const layerRefs = useRef<Array<HTMLDivElement | null>>([])
  // A marcação é uma faixa: o dedo define a altura e a largura é a da página.
  const origemDaMarcacao = useRef<{
    y: number
    esquerda: number
    largura: number
    base: DOMRect
  } | null>(null)
  const pageRefs = useRef<Array<HTMLDivElement | null>>([])
  const bookStageRef = useRef<HTMLDivElement | null>(null)
  const docRef = useRef<pdfjs.PDFDocumentProxy | null>(null)
  const desenhoRef = useRef(0)
  const pedidoRef = useRef(0)
  const buscaRef = useRef(0)
  const ultimaBuscaRef = useRef(0)
  const selecaoPendenteRef = useRef<{ page: number; text: string } | null>(null)
  const [documentReady, setDocumentReady] = useState(false)
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
    const atualizarPaginasVisiveis = () => {
      const largura = embedded && bookStageRef.current
        ? bookStageRef.current.clientWidth
        : window.innerWidth
      setPaginasVisiveis(largura <= 800 ? 1 : 2)
    }
    atualizarPaginasVisiveis()
    window.addEventListener('resize', atualizarPaginasVisiveis)
    const stage = bookStageRef.current
    const observer = stage ? new ResizeObserver(atualizarPaginasVisiveis) : null
    if (stage && observer) observer.observe(stage)
    return () => {
      window.removeEventListener('resize', atualizarPaginasVisiveis)
      observer?.disconnect()
    }
  }, [embedded])

  useEffect(() => {
    if (!embedded || !bookStageRef.current) return

    const stage = bookStageRef.current
    const atualizarLargura = () => setBookWidth(stage.clientWidth)
    atualizarLargura()

    const observer = new ResizeObserver(atualizarLargura)
    observer.observe(stage)
    return () => observer.disconnect()
  }, [embedded])

  // Acervo, bytes do arquivo e documento. Refaz tudo quando o livro muda.
  useEffect(() => {
    let vivo = true
    setStatus('carregando o arquivo…')
    setError('')
    setHits([])
    setCard(null)
    setSelectedText(externalSelectedText ?? '')
    setDocumentReady(false)

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
        setDocumentReady(true)

        // Uma citação tem prioridade; caso contrário, retoma a última página
        // visitada neste livro.
        const pedida = (local.state as { pagina?: number } | null)?.pagina
        const salva = Number(localStorage.getItem(`${paginaStoragePrefix}${bookId}`))
        const paginaSalva = Number.isInteger(salva) && salva >= 1 && salva <= documento.numPages ? salva : 1
        const inicial = pedida && pedida >= 1 && pedida <= documento.numPages ? pedida : paginaSalva
        setPage(inicial)
        setPageTarget(String(inicial))
        localStorage.setItem(`${paginaStoragePrefix}${bookId}`, String(inicial))
        setStatus('')
      } catch (caught) {
        if (!vivo) return
        setStatus('')
        mostrarErro(formatError(caught))
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

  const selecionarTextoNaCamada = useCallback((layer: HTMLDivElement, texto: string) => {
    const desejado = normalizarTexto(texto)
    if (!desejado) return false

    const walker = document.createTreeWalker(layer, NodeFilter.SHOW_TEXT)
    const posicoes: TextPosition[] = []
    let atual: Node | null
    while ((atual = walker.nextNode())) {
      const node = atual as Text
      const elemento = node.parentElement
      if (!elemento || elemento.closest('.endOfContent') || elemento.closest('[role="img"]')) continue
      posicoes.push({ node, start: 0, end: node.data.length })
    }

    const normalizado: string[] = []
    const mapa: TextPosition[] = []
    let espacoPendente: TextPosition | null = null
    let temTexto = false

    for (const [indicePosicao, posicao] of posicoes.entries()) {
      const primeiroCaractere = posicao.node.data[0]
      if (
        indicePosicao > 0
        && temTexto
        && primeiroCaractere
        && !/\s/.test(primeiroCaractere)
        && normalizado[normalizado.length - 1] !== ' '
      ) {
        normalizado.push(' ')
        mapa.push({ node: posicao.node, start: 0, end: 0 })
      }

      for (let indice = 0; indice < posicao.node.data.length; indice += 1) {
        const caractere = posicao.node.data[indice]
        if (/\s/.test(caractere)) {
          if (temTexto) {
            espacoPendente ??= { node: posicao.node, start: indice, end: indice + 1 }
          }
          continue
        }

        if (espacoPendente) {
          normalizado.push(' ')
          mapa.push(espacoPendente)
          espacoPendente = null
        }
        normalizado.push(caractere)
        mapa.push({ node: posicao.node, start: indice, end: indice + 1 })
        temTexto = true
      }
    }

    const inicio = normalizado.join('').indexOf(desejado)
    if (inicio < 0) return false

    const fim = inicio + desejado.length - 1
    const inicioPosicao = mapa[inicio]
    const fimPosicao = mapa[fim]
    if (!inicioPosicao || !fimPosicao) return false

    const range = document.createRange()
    range.setStart(inicioPosicao.node, inicioPosicao.start)
    range.setEnd(fimPosicao.node, fimPosicao.end)
    const selecao = window.getSelection()
    selecao?.removeAllRanges()
    selecao?.addRange(range)
    range.commonAncestorContainer.parentElement?.scrollIntoView({ block: 'center', inline: 'nearest' })
    return true
  }, [])

  const selecionarTextoPendente = useCallback(() => {
    const pendente = selecaoPendenteRef.current
    if (!pendente || !paginaRenderizada) return
    const indice = pendente.page - page
    const layer = layerRefs.current[indice]
    if (!layer) return
    if (selecionarTextoNaCamada(layer, pendente.text)) {
      selecaoPendenteRef.current = null
    }
  }, [page, paginaRenderizada, selecionarTextoNaCamada])

  useEffect(() => {
    selecionarTextoPendente()
    if (!selecaoPendenteRef.current || !paginaRenderizada) return

    let tentativas = 0
    let quadro = 0
    const tentarNovamente = () => {
      selecionarTextoPendente()
      tentativas += 1
      if (selecaoPendenteRef.current && tentativas < 8) {
        quadro = window.requestAnimationFrame(tentarNovamente)
      }
    }
    quadro = window.requestAnimationFrame(tentarNovamente)
    return () => window.cancelAnimationFrame(quadro)
  }, [selecionarTextoPendente])

  useEffect(() => {
    const solicitado = findRequest
    const documento = docRef.current
    const texto = solicitado ? normalizarTexto(solicitado.text) : ''
    if (!documentReady || !documento || !texto || !solicitado || solicitado.id === ultimaBuscaRef.current) return

    ultimaBuscaRef.current = solicitado.id
    const marca = ++buscaRef.current
    selecaoPendenteRef.current = null
    void (async () => {
      let paginaEncontrada = 0
      let ocorrencias = 0

      for (let numero = 1; numero <= documento.numPages; numero += 1) {
        const pagina = await documento.getPage(numero)
        const conteudo = await pagina.getTextContent()
        const paginaTexto = normalizarTexto(conteudo.items
          .map((item) => ('str' in item ? item.str : ''))
          .join(' '))
        if (marca !== buscaRef.current) return

        let inicio = paginaTexto.indexOf(texto)
        while (inicio >= 0) {
          ocorrencias += 1
          paginaEncontrada = paginaEncontrada || numero
          if (ocorrencias > 1) {
            mostrarErro('O texto não pode ser buscado porque há mais de uma correspondência neste livro.')
            return
          }
          inicio = paginaTexto.indexOf(texto, inicio + texto.length)
        }
      }

      if (marca === buscaRef.current) {
        if (ocorrencias === 1) {
          selecaoPendenteRef.current = { page: paginaEncontrada, text: texto }
          irPara(paginaEncontrada)
        } else {
          mostrarErro('O texto consultado não foi encontrado neste livro.')
        }
      }
    })().catch((caught) => {
      if (marca === buscaRef.current) mostrarErro(formatError(caught))
    })
  }, [documentReady, findRequest, pageCount])

  // Desenho da página atual: canvas na resolução da tela, camada de texto por cima.
  useEffect(() => {
    const documento = docRef.current
    if (!documento || pageCount === 0) return

    const marca = ++desenhoRef.current
    setPaginaRenderizada(false)
    canvasRefs.current.forEach((canvas, index) => {
      const layer = layerRefs.current[index]
      const pageElement = pageRefs.current[index]
      if (layer) layer.replaceChildren()
      if (canvas) {
        canvas.width = 1
        canvas.height = 1
        canvas.style.width = '1px'
        canvas.style.height = '1px'
      }
      if (pageElement) {
        pageElement.style.width = '1px'
        pageElement.style.height = '1px'
      }
    })

    const comTexto: boolean[] = []
    void (async () => {
      const paginas = Array.from({ length: paginasVisiveis }, (_, index) => page + index)
        .filter((numero) => numero <= pageCount)
      await Promise.all(paginas.map(async (numero, index) => {
        const canvas = canvasRefs.current[index]
        const layer = layerRefs.current[index]
        const pageElement = pageRefs.current[index]
        if (!canvas || !layer || !pageElement) return

        const pagina = await documento.getPage(numero)
        if (marca !== desenhoRef.current) return

        const densidade = Math.min(window.devicePixelRatio || 1, 2)
        const larguraBase = pagina.getViewport({ scale: 1 }).width
        const colunas = paginasVisiveis
        const larguraDisponivel = bookWidth > 0
          ? (bookWidth - Math.max(0, colunas - 1)) / colunas
          : 0
        const escalaDeEncaixe = bookWidth > 0
          ? larguraDisponivel / larguraBase
          : zoom
        const escala = embedded ? escalaDeEncaixe : zoom
        const vista = pagina.getViewport({ scale: escala })
        const nitida = pagina.getViewport({ scale: escala * densidade })

        canvas.width = Math.floor(nitida.width)
        canvas.height = Math.floor(nitida.height)
        canvas.style.width = `${vista.width}px`
        canvas.style.height = `${vista.height}px`
        pageElement.style.width = `${vista.width}px`
        pageElement.style.height = `${vista.height}px`

        const contexto = canvas.getContext('2d')
        if (!contexto) throw new Error('Não foi possível preparar o canvas do PDF.')
        contexto.clearRect(0, 0, canvas.width, canvas.height)
        await pagina.render({ canvas, canvasContext: contexto, viewport: nitida }).promise
        if (marca !== desenhoRef.current) return

        layer.replaceChildren()
        layer.style.setProperty('--total-scale-factor', String(escala))
        const conteudo = await pagina.getTextContent()
        if (marca !== desenhoRef.current) return
        comTexto[index] = conteudo.items.some(
          (item) => 'str' in item && item.str.trim().length > 1,
        )

        const camada = new pdfjs.TextLayer({
          textContentSource: conteudo,
          container: layer,
          viewport: vista,
        })
        await camada.render()
        pdfjs.setLayerDimensions(layer, vista)
      }))

      if (marca === desenhoRef.current) {
        setPaginaRenderizada(true)
        setPaginasComTexto([...comTexto])
      }
    })().catch((caught) => {
      if (marca === desenhoRef.current) mostrarErro(formatError(caught))
    })
    // `documentReady` entra nas dependências porque trocar de livro pode manter
    // página, zoom e contagem iguais: sem ele, o desenho não é refeito e a tela
    // segue mostrando o livro anterior sob o título do novo.
  }, [documentReady, embedded, page, zoom, pageCount, bookWidth, paginasVisiveis])

  /** Ao soltar o mouse, o que ficou selecionado vira o trecho a conectar. */
  const capturarSelecao = useCallback(() => {
    const selecao = window.getSelection()
    const bruto = selecao?.toString() ?? ''
    // A seleção só vale se estiver inteira dentro de uma camada de texto do
    // livro. Arrastar sobre a interface (ou do rail para a página) produz uma
    // seleção de elementos alheios, que não é trecho de obra nenhuma — e ela
    // já entrou no campo uma vez, misturando rótulos da tela com o livro.
    const dentroDaLayer = (() => {
      if (!selecao || selecao.rangeCount === 0) return false
      const faixa = selecao.getRangeAt(0)
      return layerRefs.current.some(
        (layer) => layer && layer.contains(faixa.startContainer) && layer.contains(faixa.endContainer),
      )
    })()
    // Os trechos vêm fatiados por linha: junta os espaços e as quebras.
    const limpo = bruto.replace(/\s+/g, ' ').trim()
    if (dentroDaLayer && limpo) {
      setSelectedText(limpo)
      onSelectionChange?.(limpo)
    }
  }, [])

  useEffect(() => {
    const atualizarSelecao = () => {
      const selecao = window.getSelection()
      const ancora = selecao?.anchorNode
      const elemento = ancora instanceof Element ? ancora : ancora?.parentElement
      if (!elemento?.closest('.pdf-page') || !selecao?.toString()) return
      capturarSelecao()
    }
    document.addEventListener('selectionchange', atualizarSelecao)
    return () => document.removeEventListener('selectionchange', atualizarSelecao)
  }, [capturarSelecao])

  /**
   * No celular não existe arrastar para selecionar: arrastar rola a página, e o
   * toque longo sobre texto quase invisível não abre a seleção. Aqui o toque
   * longo escolhe a palavra sob o dedo e entrega ao navegador — a partir daí os
   * marcadores nativos aparecem e a seleção pode ser esticada à vontade.
   */
  useEffect(() => {
    const palco = bookStageRef.current
    if (!palco || !('caretRangeFromPoint' in document)) return

    let relogio = 0
    let inicio: { x: number; y: number } | null = null

    const cancelar = () => {
      window.clearTimeout(relogio)
      inicio = null
    }

    const escolherPalavra = () => {
      if (!inicio) return
      const faixa = document.caretRangeFromPoint(inicio.x, inicio.y)
      const no = faixa?.startContainer
      if (!faixa || !no || no.nodeType !== Node.TEXT_NODE) return
      if (!no.parentElement?.closest('.textLayer')) return

      const texto = (no as Text).data
      const ehLetra = (indice: number) =>
        indice >= 0 && indice < texto.length && /[\p{L}\p{N}]/u.test(texto[indice])
      let comeco = faixa.startOffset
      let fim = faixa.startOffset
      while (ehLetra(comeco - 1)) comeco -= 1
      while (ehLetra(fim)) fim += 1
      if (comeco === fim) return

      const palavra = document.createRange()
      palavra.setStart(no, comeco)
      palavra.setEnd(no, fim)
      const selecao = window.getSelection()
      selecao?.removeAllRanges()
      selecao?.addRange(palavra)
    }

    const aoTocar = (evento: TouchEvent) => {
      const toque = evento.touches[0]
      const alvo = toque?.target
      if (!toque || !(alvo instanceof Element) || !alvo.closest('.textLayer')) return
      inicio = { x: toque.clientX, y: toque.clientY }
      window.clearTimeout(relogio)
      relogio = window.setTimeout(escolherPalavra, 320)
    }

    const aoMover = (evento: TouchEvent) => {
      const toque = evento.touches[0]
      if (!toque || !inicio) return
      if (Math.hypot(toque.clientX - inicio.x, toque.clientY - inicio.y) > 12) cancelar()
    }

    palco.addEventListener('touchstart', aoTocar, { passive: true })
    palco.addEventListener('touchmove', aoMover, { passive: true })
    palco.addEventListener('touchend', cancelar, { passive: true })
    palco.addEventListener('touchcancel', cancelar, { passive: true })
    return () => {
      window.clearTimeout(relogio)
      palco.removeEventListener('touchstart', aoTocar)
      palco.removeEventListener('touchmove', aoMover)
      palco.removeEventListener('touchend', cancelar)
      palco.removeEventListener('touchcancel', cancelar)
    }
  }, [])

  /** O texto que está dentro da região marcada, na ordem de leitura da página. */
  const textoNaRegiao = (regiao: DOMRect) => {
    const partes: { topo: number; esquerda: number; texto: string }[] = []
    for (const camada of layerRefs.current) {
      for (const span of camada?.querySelectorAll('span') ?? []) {
        const caixa = span.getBoundingClientRect()
        if (!caixa.width || !caixa.height) continue
        const toca = caixa.right > regiao.left && caixa.left < regiao.right
          && caixa.bottom > regiao.top && caixa.top < regiao.bottom
        const texto = (span.textContent ?? '').trim()
        if (toca && texto) partes.push({ topo: caixa.top, esquerda: caixa.left, texto })
      }
    }
    partes.sort((a, b) => a.topo - b.topo || a.esquerda - b.esquerda)
    return partes.map((parte) => parte.texto).join(' ').replace(/\s+/g, ' ').trim()
  }

  /** O recorte da região em PNG: o caminho das páginas que não têm texto. */
  const recorteDaRegiao = (regiao: DOMRect) => {
    const canvas = canvasRefs.current
      .filter((item): item is HTMLCanvasElement => Boolean(item))
      .find((item) => {
        const caixa = item.getBoundingClientRect()
        return caixa.right > regiao.left && caixa.left < regiao.right
          && caixa.bottom > regiao.top && caixa.top < regiao.bottom
      })
    if (!canvas) return ''
    const caixaDoCanvas = canvas.getBoundingClientRect()
    const escala = canvas.width / caixaDoCanvas.width
    const recorte = document.createElement('canvas')
    recorte.width = Math.max(1, Math.round(regiao.width * escala))
    recorte.height = Math.max(1, Math.round(regiao.height * escala))
    const contexto = recorte.getContext('2d')
    if (!contexto) return ''
    contexto.drawImage(
      canvas,
      (regiao.left - caixaDoCanvas.left) * escala,
      (regiao.top - caixaDoCanvas.top) * escala,
      recorte.width,
      recorte.height,
      0,
      0,
      recorte.width,
      recorte.height,
    )
    return recorte.toDataURL('image/png').split(',')[1] ?? ''
  }

  const inicioDaMarcacao = (evento: ReactPointerEvent) => {
    const palco = bookStageRef.current
    if (!palco) return
    const pagina = (evento.target as Element | null)?.closest('.pdf-page')
    if (!pagina) return
    palco.setPointerCapture(evento.pointerId)
    const base = palco.getBoundingClientRect()
    const caixaDaPagina = pagina.getBoundingClientRect()
    // A faixa ocupa a página inteira na horizontal: só a altura é escolhida.
    origemDaMarcacao.current = {
      y: evento.clientY - base.top,
      esquerda: caixaDaPagina.left - base.left,
      largura: caixaDaPagina.width,
      base,
    }
    setCaixaDaMarcacao({
      esquerda: caixaDaPagina.left - base.left,
      topo: evento.clientY - base.top,
      largura: caixaDaPagina.width,
      altura: 0,
    })
  }

  const duranteAMarcacao = (evento: ReactPointerEvent) => {
    const origem = origemDaMarcacao.current
    if (!origem) return
    const atual = evento.clientY - origem.base.top
    setCaixaDaMarcacao({
      esquerda: origem.esquerda,
      largura: origem.largura,
      topo: Math.min(origem.y, atual),
      altura: Math.abs(atual - origem.y),
    })
  }

  /** Ao soltar: o texto da região; sem texto na página, o recorte vira pergunta. */
  const fimDaMarcacao = async (evento: ReactPointerEvent) => {
    const palco = bookStageRef.current
    const origem = origemDaMarcacao.current
    origemDaMarcacao.current = null
    setMarcando(false)
    const atual = caixaDaMarcacao
    setCaixaDaMarcacao(null)
    if (!palco || !origem || !atual || atual.altura < 8) return
    const regiao = new DOMRect(
      origem.base.left + atual.esquerda,
      origem.base.top + atual.topo,
      atual.largura,
      atual.altura,
    )
    const texto = textoNaRegiao(regiao)
    if (texto) {
      setSelectedText(texto)
      onSelectionChange?.(texto)
      return
    }
    const imagem = recorteDaRegiao(regiao)
    if (!imagem) return
    setStatus('lendo o recorte…')
    try {
      const lido = (await readImage(imagem)).replace(/\s+/g, ' ').trim()
      if (lido) {
        setSelectedText(lido)
        onSelectionChange?.(lido)
      } else {
        mostrarErro('não encontrei texto neste recorte')
      }
    } catch (caught) {
      mostrarErro(formatError(caught))
    } finally {
      setStatus('')
    }
    void evento
  }

  const irPara = useCallback((numero: number) => {
    if (!Number.isFinite(numero)) return
    const solicitado = Math.min(Math.max(1, Math.trunc(numero)), Math.max(1, pageCount))
    const destino = paginasVisiveis === 1
      ? solicitado
      : Math.min(
        Math.max(1, Math.floor((solicitado - 1) / paginasVisiveis) * paginasVisiveis + 1),
        Math.max(1, pageCount),
      )
    setPage(destino)
    setPageTarget(String(destino))
    if (bookId) localStorage.setItem(`${paginaStoragePrefix}${bookId}`, String(destino))
  }, [bookId, pageCount, paginasVisiveis])

  useEffect(() => {
    if (pageCount === 0 || paginasVisiveis === 1) return
    const alinhada = Math.min(
      Math.max(1, Math.floor((page - 1) / paginasVisiveis) * paginasVisiveis + 1),
      pageCount,
    )
    if (alinhada !== page) {
      setPage(alinhada)
      setPageTarget(String(alinhada))
    }
  }, [page, pageCount, paginasVisiveis])

  const buscarConexoes = async () => {
    const texto = selectedText.trim()
    if (!texto || !bookId) {
      mostrarErro('Selecione um trecho no livro para buscar conexões.')
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
        ...(minScore === null ? {} : { min_score: minScore }),
      }
      const resposta = await connect(payload)
      if (marca !== pedidoRef.current) return
      setHits(resposta.hits)
      setCard(resposta)
      setError('')
    } catch (caught) {
      if (marca === pedidoRef.current) mostrarErro(formatError(caught))
    } finally {
      if (marca === pedidoRef.current) setBusy(false)
    }
  }

  /** A citação abre a página: no mesmo livro, aqui; em outro, lá. */
  const openCitation = (citacao: InterpretationResponse['citations'][number]) => {
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
      {!embedded ? <Header books={books} loading={Boolean(status)} /> : null}

      <main className={embedded ? 'workspace-layout' : 'reader-layout workspace-grid'}>
        <section className={embedded ? 'book-workspace' : 'panel viewer-panel'}>
          <div className={embedded ? 'book-toolbar' : 'panel-title-row book-toolbar-header'}>
            <div>
              {embedded ? <p className="eyebrow">Leitura</p> : null}
              {embedded ? <h2>{activeBook?.title ?? 'Livro'}</h2> : <h1>{activeBook?.title ?? 'Livro'}</h1>}
              {activeBook ? <p className="book-author">{activeBook.author}</p> : null}
            </div>
            <label className="book-picker">
              <span>Livro</span>
              <select
                value={bookId ?? ''}
                onChange={(evento) => navegar(`/consultar?book=${evento.target.value}`)}
                aria-label="Trocar de livro"
              >
                {books.map((book) => (
                  <option key={book.id} value={book.id}>{book.title}</option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="ghost-button mark-button"
              onClick={() => {
                setMarcando((atual) => !atual)
                setCaixaDaMarcacao(null)
              }}
              aria-pressed={marcando}
            >
              {marcando ? 'Cancelar' : 'Marcar trecho'}
            </button>
          </div>

          {paginasComTexto.length > 0 && paginasComTexto.every((tem) => !tem) ? (
            <p className="page-sem-texto">
              Esta página não tem texto — é uma imagem. Use <strong>Próxima</strong> para chegar a uma página com texto.
            </p>
          ) : null}
          {error ? <p key={errorVersion} className={`inline-error${errorDismissing ? ' is-dismissing' : ''}`} role="alert" aria-live="assertive">{error}</p> : null}
          {status ? <Indicator label={status} /> : null}

          <div className="pdf-frame">
            {!embedded ? <BookToolbar
              page={page}
              pageCount={pageCount}
              pageStep={paginasVisiveis}
              target={pageTarget}
              zoom={zoom}
              zoomStep={PASSO_ZOOM}
              onGoTo={irPara}
              onTarget={setPageTarget}
              onZoom={mudarZoom}
            /> : null}
            <div
              ref={bookStageRef}
              className={`pdf-stage open-book${paginaRenderizada ? '' : ' is-loading'}${marcando ? ' is-marking' : ''}`}
              onPointerDown={marcando ? inicioDaMarcacao : undefined}
              onPointerMove={marcando ? duranteAMarcacao : undefined}
              onPointerUp={marcando ? fimDaMarcacao : undefined}
            >
              {caixaDaMarcacao ? (
                <div
                  className="marcacao-caixa"
                  style={{
                    left: caixaDaMarcacao.esquerda,
                    top: caixaDaMarcacao.topo,
                    width: caixaDaMarcacao.largura,
                    height: caixaDaMarcacao.altura,
                  }}
                />
              ) : null}
              {Array.from({ length: paginasVisiveis }, (_, index) => index).map((index) => (
                <PdfPage
                  key={`${page}-${zoom}-${index}`}
                  page={page}
                  index={index}
                  pageCount={pageCount}
                  zoom={zoom}
                  pageRef={(element) => { pageRefs.current[index] = element }}
                  canvasRef={(element) => { canvasRefs.current[index] = element }}
                  layerRef={(element) => { layerRefs.current[index] = element }}
                  onSelect={capturarSelecao}
                />
              ))}
            </div>
          </div>

          {embedded ? (
            <BookFooter page={page} pageCount={pageCount} pageStep={paginasVisiveis} onGoTo={irPara} />
          ) : null}

          {!embedded ? (
            <TextSelection
              text={selectedText}
              busy={busy}
              onChange={(text) => {
                setSelectedText(text)
                onSelectionChange?.(text)
              }}
              onSubmit={buscarConexoes}
            />
          ) : null}
        </section>

        {!embedded && connectionsOpen ? <aside className="panel sidebar-panel connections-panel-wrapper">
          <EvidencePanel
            hits={hits}
            card={card}
            busy={busy}
            onClose={() => setConnectionsOpen(false)}
            onOpenCitation={openCitation}
          />
        </aside> : null}
        {!embedded && !connectionsOpen ? (
          <button type="button" className="open-panel-button" onClick={() => setConnectionsOpen(true)}>
            Abrir conexões
          </button>
        ) : null}
      </main>
    </>
  )
}
