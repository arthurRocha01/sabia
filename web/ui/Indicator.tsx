type IndicatorProps = {
  label: string
  compact?: boolean
}

export default function Indicator({ label, compact = false }: IndicatorProps) {
  return (
    <div className={compact ? 'loading-indicator compact' : 'loading-indicator'} role="status" aria-live="polite">
      <span className="loading-orbit" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span>{label}</span>
    </div>
  )
}
