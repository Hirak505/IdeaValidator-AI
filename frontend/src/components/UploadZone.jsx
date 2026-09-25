import { useState, useRef } from 'react'

const UploadIcon = ({ className }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
  </svg>
)

const FileIcon = ({ className }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>
)

const XIcon = ({ className }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
  </svg>
)

export default function UploadZone({ label, accept, hint, file, onFile, icon, accentColor = 'brand-500' }) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) onFile(dropped)
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    setDragging(true)
  }

  const handleDragLeave = () => setDragging(false)

  const formatSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div className="w-full">
      <p className="text-xs font-medium text-slate-400 uppercase tracking-widest mb-2">{label}</p>

      {file ? (
        <div className="relative flex items-center gap-3 p-4 rounded-xl bg-surface-800 border border-brand-500/30 animate-fade-in">
          <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-brand-500/15 flex items-center justify-center">
            <FileIcon className="w-5 h-5 text-brand-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-200 truncate">{file.name}</p>
            <p className="text-xs text-slate-500 mt-0.5">{formatSize(file.size)}</p>
          </div>
          <button
            onClick={() => onFile(null)}
            className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-slate-500 hover:text-rose-400 hover:bg-rose-400/10 transition-colors"
          >
            <XIcon className="w-4 h-4" />
          </button>
          <div className="absolute inset-0 rounded-xl bg-brand-500/5 pointer-events-none" />
        </div>
      ) : (
        <div
          onClick={() => inputRef.current?.click()}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          className={`
            relative cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition-all duration-200
            ${dragging
              ? 'border-brand-400 bg-brand-500/10 scale-[1.02]'
              : 'border-slate-700 hover:border-brand-500/60 hover:bg-surface-800/50'
            }
          `}
        >
          <div className={`inline-flex items-center justify-center w-12 h-12 rounded-xl mb-3 transition-colors ${dragging ? 'bg-brand-500/20' : 'bg-surface-700'}`}>
            {icon || <UploadIcon className={`w-6 h-6 ${dragging ? 'text-brand-400' : 'text-slate-400'}`} />}
          </div>
          <p className="text-sm font-medium text-slate-300 mb-1">
            {dragging ? 'Drop it!' : 'Drop file or click to browse'}
          </p>
          <p className="text-xs text-slate-500">{hint}</p>
          <input
            ref={inputRef}
            type="file"
            accept={accept}
            className="hidden"
            onChange={(e) => onFile(e.target.files?.[0] || null)}
          />
        </div>
      )}
    </div>
  )
}
