import type { Profile } from '../../api/types'
import Tip from '../../ui/Tip'

/** O que o leitor fez hoje e o que a ingestão consumiu da cota. */
export default function DailyActivity({ profile }: { profile: Profile }) {
  return (
    <section className="side-block">
      <p className="eyebrow">Conta</p>
      <h2>Hoje</h2>
      <div className="metric-row">
        <span>Consultas</span>
        <strong>{profile.queries_today}</strong>
      </div>
      <div className="metric-row">
        <span>Conexões</span>
        <strong>{profile.connections_today}</strong>
      </div>
      <div className="metric-row">
        <span className="metric-label-with-help">
          Cota diária usada
          <Tip>Consultas e conexões mostram o que você leu. A cota representa os trechos consumidos pela ingestão contra o limite do dia.</Tip>
        </span>
        <strong>
          {profile.texts_today} / {profile.daily_limit}
        </strong>
      </div>
    </section>
  )
}
