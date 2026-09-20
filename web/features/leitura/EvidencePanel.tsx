import type { ConnectResponse, InterpretationResponse } from '../../api/types'
import Indicator from '../../ui/Indicator'
import Citation from './Citation'

/** O painel do leitor em página inteira: as evidências e o card. */
export default function EvidencePanel({
  hits,
  card,
  busy,
  onClose,
  onOpenCitation,
}: {
  hits: ConnectResponse['hits']
  card: InterpretationResponse | null
  busy: boolean
  onClose: () => void
  onOpenCitation: (citacao: InterpretationResponse['citations'][number]) => void
}) {
  return (
    <>
      <div className="connections-title">
        <div>
          <p className="eyebrow">Conexões</p>
          <h2>Evidência</h2>
        </div>
        <button
          type="button"
          className="panel-control"
          onClick={onClose}
          aria-label="Recolher conexões"
        >
          ×
        </button>
      </div>

      {busy ? <Indicator label="Buscando conexões" compact /> : null}

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
              <small>
                {hit.author} · página {hit.page_label ?? hit.page_index + 1}
              </small>
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
                  <Citation
                    key={`${citacao.book_id}-${citacao.page_index}`}
                    citation={citacao}
                    onOpen={onOpenCitation}
                  />
                ))}
              </ul>
            ) : null}
          </article>
        ) : (
          <p className="muted-copy">O card de interpretação aparecerá aqui.</p>
        )}
      </div>
    </>
  )
}
