import type { FormEvent } from 'react'
import type { CardLength, Profile } from '../../api/types'
import { formatError } from '../../api/client'
import Tip from '../../ui/Tip'

const SIZES = [
  ['default', 'Curto'],
  ['long', 'Longo'],
  ['free', 'Livre'],
] as const

/** Como o leitor quer a interpretação: o texto dele e o tamanho do card. */
export default function InterpretationProfile({
  profile,
  onSave,
  onError,
  onSaved,
}: {
  profile: Profile
  onSave: (mudanca: { interpretation_profile?: string; card_length?: CardLength }) => Promise<unknown>
  onError: (mensagem: string) => void
  onSaved: () => void
}) {
  const saveText = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = event.currentTarget
    const texto = (form.elements.namedItem('interpretation_profile') as HTMLTextAreaElement).value
    try {
      await onSave({ interpretation_profile: texto })
      onSaved()
    } catch (caught) {
      onError(formatError(caught))
    }
  }

  const saveSize = async (valor: CardLength) => {
    try {
      await onSave({ card_length: valor })
      onSaved()
    } catch (caught) {
      onError(formatError(caught))
    }
  }

  return (
    <section className="side-block">
      <p className="eyebrow">Como ler</p>
      <h2>Perfil de interpretação</h2>

      <form className="profile-form" onSubmit={saveText}>
        <label className="field-group">
          <span className="field-label-with-help">
            Como interpretar
            <Tip>Oriente o tom e os aspectos que o Sabiá deve priorizar ao relacionar suas ideias com os livros.</Tip>
          </span>
          <textarea
            name="interpretation_profile"
            rows={4}
            maxLength={1200}
            defaultValue={profile.interpretation_profile}
            placeholder="Ex.: valorize a contradição antes da concordância; sem metáfora; compare com o meu trabalho."
          />
        </label>
        <button type="submit" className="secondary-button">Salvar perfil</button>
      </form>

      <div className="field-group card-length">
        <span className="field-label-with-help">
          Tamanho da interpretação
          <Tip>Define o espaço esperado para o card: Curto tem até três frases, Longo até oito e Livre deixa o modelo decidir.</Tip>
        </span>
        <div className="segmented" role="group" aria-label="Tamanho da interpretação">
          {SIZES.map(([valor, rotulo]) => (
            <button
              key={valor}
              type="button"
              className="segment"
              aria-pressed={profile.card_length === valor}
              onClick={() => void saveSize(valor)}
            >
              {rotulo}
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}
