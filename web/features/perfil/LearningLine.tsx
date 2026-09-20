import type { FormEvent } from 'react'
import type { Profile } from '../../api/types'
import { formatError } from '../../api/client'
import Tip from '../../ui/Tip'

/** O assunto da leitura: texto livre, corrente, que vale para toda consulta. */
export default function LearningLine({
  profile,
  onSave,
  onError,
  onSaved,
}: {
  profile: Profile
  onSave: (mudanca: { current_line?: string }) => Promise<unknown>
  onError: (mensagem: string) => void
  onSaved: () => void
}) {
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = event.currentTarget
    const currentLine = (form.elements.namedItem('current_line') as HTMLInputElement).value
    try {
      await onSave({ current_line: currentLine })
      onSaved()
    } catch (caught) {
      onError(formatError(caught))
    }
  }

  return (
    <section className="side-block">
      <p className="eyebrow">Leitura</p>
      <h2>Assunto atual</h2>
      <form className="line-form" onSubmit={submit}>
        <label className="field-group">
          <span className="field-label-with-help">
            Linha de aprendizado
            <Tip>O assunto da leitura. Ele fica como contexto corrente para as consultas.</Tip>
          </span>
          <input
            name="current_line"
            defaultValue={profile.current_line ?? ''}
            placeholder="Sobre o que você está lendo"
          />
        </label>
        <button type="submit" className="secondary-button">Salvar linha</button>
      </form>
    </section>
  )
}
