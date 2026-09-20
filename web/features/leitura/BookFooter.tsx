/** A navegação do livro embutido na consulta: anterior, progresso e próxima. */
export default function BookFooter({
  page,
  pageCount,
  onGoTo,
}: {
  page: number
  pageCount: number
  onGoTo: (pagina: number) => void
}) {
  return (
    <footer className="book-footer">
      <button type="button" className="page-button" onClick={() => onGoTo(page - 1)} disabled={page <= 1}>
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
        onClick={() => onGoTo(page + 1)}
        disabled={pageCount === 0 || page >= pageCount}
      >
        Próxima →
      </button>
    </footer>
  )
}
