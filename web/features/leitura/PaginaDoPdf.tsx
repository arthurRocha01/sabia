import type { RefCallback } from 'react'

type PaginaDoPdfProps = {
  page: number
  index: number
  pageCount: number
  zoom: number
  pageRef: RefCallback<HTMLDivElement>
  canvasRef: RefCallback<HTMLCanvasElement>
  layerRef: RefCallback<HTMLDivElement>
  onMouseUp: () => void
}

export default function PaginaDoPdf({
  page,
  index,
  pageCount,
  zoom,
  pageRef,
  canvasRef,
  layerRef,
  onMouseUp,
}: PaginaDoPdfProps) {
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
        onMouseUp={onMouseUp}
      />
    </div>
  )
}
