import type { RefCallback } from 'react'

type PdfPageProps = {
  page: number
  index: number
  pageCount: number
  zoom: number
  pageRef: RefCallback<HTMLDivElement>
  canvasRef: RefCallback<HTMLCanvasElement>
  layerRef: RefCallback<HTMLDivElement>
  onSelect: () => void
}

export default function PdfPage({
  page,
  index,
  pageCount,
  zoom,
  pageRef,
  canvasRef,
  layerRef,
  onSelect,
}: PdfPageProps) {
  return (
    <div
      ref={pageRef}
      className={`pdf-page book-page-${index === 0 ? 'left' : 'right'}`}
      hidden={index === 1 && page >= pageCount}
    >
      <span className="book-page-number">{page + index}</span>
      <canvas ref={canvasRef} />
      <div
        ref={layerRef}
        className="textLayer"
        onMouseUp={onSelect}
        onTouchEnd={() => {
          window.setTimeout(onSelect, 0)
          window.setTimeout(onSelect, 80)
          window.setTimeout(onSelect, 180)
        }}
      />
    </div>
  )
}
