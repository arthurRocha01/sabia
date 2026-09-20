import type { ConnectResponse } from '../../api/types'

/** As evidências: cada trecho recuperado com autor, obra, página e score. */
export default function ConnectionList({
  hits,
  loading,
}: {
  hits: ConnectResponse['hits']
  loading: boolean
}) {
  if (loading) return null

  if (hits.length === 0) {
    return <p className="muted-copy">As conexões encontradas aparecerão aqui.</p>
  }

  return (
    <>
      {hits.map((hit) => (
        <article
          key={`${hit.book_id}-${hit.page_index}-${hit.text.slice(0, 12)}`}
          className="rail-hit"
        >
          <p className="rail-hit-meta">
            <strong>{hit.author}</strong> ·{' '}
            <span>
              {hit.title}, pág. {hit.page_label ?? hit.page_index + 1}
            </span>
            <b>score {hit.score.toFixed(3)}</b>
          </p>
          <p className="rail-hit-text">{hit.text}</p>
        </article>
      ))}
    </>
  )
}
