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

export default function UploadZone({
  label,
  accept,
  hint,
  file,
  onFile,
  onFileSelect,
  icon,
  badgeText,
  id,
}) {
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState(null)
  const inputRef = useRef(null)

  // Resolve callback consistently whether caller passes onFileSelect or onFile
  const handleFileChange = onFileSelect || onFile

  const dispatchFile = (selectedFile) => {
    setError(null)
    if (typeof handleFileChange === 'function') {
      handleFileChange(selectedFile)
    } else {
      console.error(
        `[UploadZone] Missing valid file handler for "${label}". Expected 'onFileSelect' or 'onFile' callback function.`
      )
      setError('Configuration error: No valid file handler attached.')
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    const dropped = e.dataTransfer.files?.[0] || null
    if (dropped) {
      dispatchFile(dropped)
    }
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    setDragging(true)
  }

  const handleDragLeave = () => setDragging(false)

  const handleRemove = () => {
    if (inputRef.current) inputRef.current.value = ''
    dispatchFile(null)
  }

  const formatSize = (bytes) => {
    if (!bytes && bytes !== 0) return ''
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const zoneId = id || `upload-zone-${(label || 'file').toLowerCase().replace(/[^a-z0-9]/g, '-')}`

  return (
    <div className="w-full group" id={zoneId}>
      <div className="flex items-center justify-between mb-2.5">
        <p className="section-label">{label}</p>
        {badgeText && (
          <span className="font-mono text-micro text-theme-text-muted uppercase">
            {badgeText}
          </span>
        )}
      </div>

      {error && (
        <div className="mb-2 p-2 rounded bg-theme-error/10 border border-theme-error/30 text-theme-error font-mono text-micro">
          [ERR] {error}
        </div>
      )}

      {file ? (
        <div className="relative flex items-center gap-3.5 p-4 rounded-xl bg-theme-panel-subtle border border-theme-border animate-scale-in">
          {/* Blueprint corner marks */}
          <div className="corner-marks" />

          <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-theme-evidence/10 border border-theme-evidence/20 flex items-center justify-center">
            <FileIcon className="w-5 h-5 text-theme-evidence" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-theme-text truncate">{file.name}</p>
            <p className="text-micro text-theme-text-muted mt-0.5 font-mono">{formatSize(file.size)}</p>
          </div>
          <button
            onClick={handleRemove}
            type="button"
            className="flex-shrink-0 w-7 h-7 rounded-md flex items-center justify-center text-theme-text-muted hover:text-theme-error hover:bg-theme-error/10 transition-all duration-200"
            aria-label={`Remove ${label}`}
          >
            <XIcon className="w-3.5 h-3.5" />
          </button>
        </div>
      ) : (
        <div
          onClick={() => inputRef.current?.click()}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          className={`
            relative cursor-pointer rounded-xl border-2 border-dashed p-7 text-center transition-all duration-200
            ${dragging
              ? 'border-theme-border-active bg-theme-evidence/5 scale-[1.01]'
              : 'border-theme-border hover:border-theme-border-active hover:bg-theme-panel-subtle'
            }
          `}
        >
          {/* Subtle crosshair in center when dragging */}
          {dragging && (
            <div className="absolute inset-0 pointer-events-none flex items-center justify-center opacity-30">
              <div className="w-px h-8 bg-theme-evidence" />
              <div className="h-px w-8 bg-theme-evidence absolute" />
            </div>
          )}

          <div className={`inline-flex items-center justify-center w-11 h-11 rounded-lg mb-3 transition-all duration-200 ${
            dragging ? 'bg-theme-evidence/15 border border-theme-evidence/30' : 'bg-theme-chip border border-theme-border'
          }`}>
            {icon || <UploadIcon className={`w-5 h-5 transition-colors duration-200 ${dragging ? 'text-theme-evidence' : 'text-theme-text-secondary'}`} />}
          </div>
          <p className={`text-sm font-medium mb-1 transition-colors ${dragging ? 'text-theme-evidence' : 'text-theme-text'}`}>
            {dragging ? 'Release to upload specification' : 'Drop specification or click to browse'}
          </p>
          <p className="text-micro font-mono text-theme-text-muted uppercase tracking-wider">{hint}</p>
          <input
            ref={inputRef}
            id={id ? `${id}-input` : undefined}
            type="file"
            accept={accept}
            className="hidden"
            onChange={(e) => dispatchFile(e.target.files?.[0] || null)}
          />
        </div>
      )}
    </div>
  )
}
