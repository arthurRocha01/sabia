import type { Citation } from '../../api/types'

type CitacaoProps = {
  citation: Citation
  onOpen: (citation: Citation) => void
}

export default function Citacao({ citation, onOpen }: CitacaoProps) {
  return (
    <li>
      <button type="button" className="link-button" onClick={() => onOpen(citation)}>
        {citation.title} · página {citation.page_label ?? citation.page_index + 1}
      </button>
    </li>
  )
}
