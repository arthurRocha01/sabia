import type { InterpretationResponse } from '../../api/types'

/** O card: síntese compacta que abre numa lupa ao passar o mouse ou focar. */
export default function InterpretationCard({ card }: { card: InterpretationResponse }) {
  return (
    <article className="rail-card interpretation-card" tabIndex={0}>
      <p className="rail-card-summary">{card.card}</p>
      <span className="relation-badge">{card.relation ?? 'Sem classificação'}</span>
      <div className="interpretation-preview" role="tooltip" tabIndex={0}>
        <p>{card.card}</p>
      </div>
    </article>
  )
}
