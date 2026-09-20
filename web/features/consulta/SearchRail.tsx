import type { ConnectResponse, InterpretationResponse } from '../../api/types'
import Tip from '../../ui/Tip'
import Indicator from '../../ui/Indicator'
import InterpretationCard from './InterpretationCard'

/** O rail: o trecho, o escopo, a count, a precisão e o card. */
export default function SearchRail({
  text,
  scope,
  count,
  precision,
  floor,
  card,
  error,
  errorVersion,
  errorFading,
  busy,
  booksLoading,
  onText,
  onScope,
  onCount,
  onPrecision,
  onSearch,
}: {
  text: string
  scope: 'others' | 'same'
  count: number
  precision: number | null
  floor: number
  card: InterpretationResponse | null
  error: string
  errorVersion: number
  errorFading: boolean
  busy: boolean
  booksLoading: boolean
  onText: (valor: string) => void
  onScope: (valor: 'others' | 'same') => void
  onCount: (valor: number) => void
  onPrecision: (valor: number) => void
  onSearch: () => void
}) {
  return (
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
              onChange={(event) => onText(event.target.value)}
              placeholder="Cole aqui um trecho ou selecione uma passagem no livro"
            />
          </label>

          <div className="rail-row">
            <label className="rail-field rail-field-grow">
              <span>Escopo</span>
              <select value={scope} onChange={(event) => onScope(event.target.value as 'others' | 'same')}>
                <option value="others">Outros livros</option>
                <option value="same">Só este livro</option>
              </select>
            </label>
            <label className="rail-field rail-k-field">
              <span>Nº conexões</span>
              <input
                type="number"
                min={1}
                max={10}
                value={count}
                onChange={(event) => onCount(Math.min(10, Math.max(1, Number(event.target.value) || 1)))}
              />
            </label>
          </div>

          <label className="rail-field rail-precision">
            <span className="field-label-with-help">
              <span>
                Precisão mínima
                <Tip>As conexões abaixo deste valor não são retornadas. O floor da instalação é o menor valor permitido.</Tip>
              </span>
              <strong>{precision === null ? '—' : precision.toFixed(2)}</strong>
            </span>
            <input
              type="range"
              min={floor}
              max={0.95}
              step={0.01}
              value={precision ?? 0}
              onChange={(event) => onPrecision(Number(event.target.value))}
            />
          </label>

          <button
            type="button"
            className="primary-button rail-search-button"
            onClick={onSearch}
            disabled={busy || booksLoading}
          >
            {busy ? 'Buscando conexões…' : 'Buscar conexões'}
          </button>
          <p className="rail-hint">Ou selecione um trecho diretamente no livro.</p>

          {error ? (
            <p
              key={errorVersion}
              className={`inline-error${errorFading ? ' is-dismissing' : ''}`}
              role="alert"
              aria-live="assertive"
            >
              {error}
            </p>
          ) : null}

          <div className="consult-results">
            {busy ? <Indicator label="Construindo conexões" /> : null}
            {!busy && card && card.card ? <InterpretationCard card={card} /> : null}
          </div>
        </section>
      </div>
    </aside>
  )
}
