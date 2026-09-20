/** A barra do leitor em página inteira: navegação, ir para e zoom. */
export default function BookToolbar({
  page,
  pageCount,
  target,
  zoom,
  zoomStep,
  onGoTo,
  onTarget,
  onZoom,
}: {
  page: number
  pageCount: number
  target: string
  zoom: number
  zoomStep: number
  onGoTo: (pagina: number) => void
  onTarget: (valor: string) => void
  onZoom: (passo: number) => void
}) {
  return (
    <div className="pdf-toolbar minimal-pdf-toolbar">
      <button
        type="button"
        className="ghost-button"
        onClick={() => onGoTo(page - 1)}
        disabled={page <= 1}
        aria-label="Página anterior"
        title="Página anterior"
      >
        Anterior
      </button>
      <span className="pdf-position">
        página <strong>{page}</strong> de {pageCount || '—'}
      </span>
      <button
        type="button"
        className="ghost-button"
        onClick={() => onGoTo(page + 1)}
        disabled={pageCount === 0 || page >= pageCount}
        aria-label="Próxima página"
        title="Próxima página"
      >
        Próxima
      </button>

      <label className="field-group pdf-goto">
        <span>Ir para</span>
        <input
          type="number"
          min={1}
          max={pageCount || 1}
          value={target}
          onChange={(evento) => onTarget(evento.target.value)}
          onKeyDown={(evento) => {
            if (evento.key === 'Enter') onGoTo(Number(target))
          }}
        />
      </label>

      <span className="pdf-zoom">
        <button type="button" className="ghost-button" onClick={() => onZoom(-zoomStep)}>−</button>
        <span className="muted-copy">{Math.round(zoom * 100)}%</span>
        <button type="button" className="ghost-button" onClick={() => onZoom(zoomStep)}>+</button>
      </span>
    </div>
  )
}
