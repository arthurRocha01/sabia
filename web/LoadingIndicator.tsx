type LoadingIndicatorProps = {
  label: string
  compact?: boolean
}

export default function LoadingIndicator({ label, compact = false }: LoadingIndicatorProps) {
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
