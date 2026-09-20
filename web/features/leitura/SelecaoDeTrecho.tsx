type SelecaoDeTrechoProps = {
  text: string
  busy: boolean
  onChange: (text: string) => void
  onSubmit: () => void
}

export default function SelecaoDeTrecho({ text, busy, onChange, onSubmit }: SelecaoDeTrechoProps) {
  return (
    <div className="selection-box">
      <label className="field-group">
        <span>Trecho selecionado</span>
        <textarea
          rows={5}
          value={text}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Selecione um trecho no livro ou cole aqui."
        />
      </label>
      <button type="button" className="primary-button" onClick={onSubmit} disabled={busy}>
        {busy ? 'Buscando conexões…' : 'Buscar conexões'}
      </button>
    </div>
  )
}
