/** A navegação do livro embutido na consulta: anterior, progresso e próxima. */
export default function BookFooter({
  page,
  pageCount,
  pageStep,
  onGoTo,
}: {
  page: number
  pageCount: number
  pageStep: number
  onGoTo: (pagina: number) => void
}) {
  return (
    <footer className="book-footer">
      <button type="button" className="page-button" onClick={() => onGoTo(page - pageStep)} disabled={page <= 1}>
        ← Anterior
      </button>
      <div className="book-progress">
        <span>Página {page}</span>
        <div className="progress-track">
          <span style={{ width: `${pageCount ? (page / pageCount) * 100 : 0}%` }} />
        </div>
        <span>{pageCount || '—'}</span>
      </div>
      <button
        type="button"
        className="page-button"
        onClick={() => onGoTo(page + pageStep)}
        disabled={pageCount === 0 || page + pageStep > pageCount}
      >
        Próxima →
      </button>
    </footer>
  )
}
