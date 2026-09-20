type DicaProps = {
  children: string
}

export default function Dica({ children }: DicaProps) {
  return (
    <span className="help-tip">
      <button type="button" className="help-tip-button" aria-label="Mais informações">?</button>
      <span className="help-tip-content" role="tooltip">{children}</span>
    </span>
  )
}
