// frontend/src/App.jsx version 2.0.0

import { useState, useRef, useCallback, useEffect } from 'react'

const ACCEPTED = [
  '.docx', '.doc', '.odt', '.rtf',
  '.pptx', '.ppt', '.odp',
  '.xlsx', '.xls', '.ods',
  '.html', '.htm', '.txt', '.csv',
  '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.svg',
].join(',')

const formatSize = (bytes) => {
  if (bytes < 1024) return `${bytes} o`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`
  return `${(bytes / 1024 / 1024).toFixed(1)} Mo`
}

export default function App() {
  const [theme, setTheme] = useState(() => {
    const savedTheme = window.localStorage.getItem('theme')
    if (savedTheme === 'light' || savedTheme === 'dark') return savedTheme
    return 'light'
  })
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState('idle') // idle | loading | done | error
  const [pdfBlob, setPdfBlob] = useState(null)
  const [pdfFilename, setPdfFilename] = useState('')
  const [errorMsg, setErrorMsg] = useState('')
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    window.localStorage.setItem('theme', theme)
  }, [theme])

  const reset = () => {
    setFile(null)
    setStatus('idle')
    setPdfBlob(null)
    setPdfFilename('')
    setErrorMsg('')
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleFile = (f) => {
    if (!f) return
    reset()
    setFile(f)
  }

  const handleInputChange = (e) => handleFile(e.target.files?.[0])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files?.[0]
    if (f) handleFile(f)
  }, [])

  const handleDragOver = (e) => { e.preventDefault(); setDragging(true) }
  const handleDragLeave = () => setDragging(false)
  const handleDropzoneKeyDown = (e) => {
    if (file) return
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      inputRef.current?.click()
    }
  }

  const convert = async () => {
    if (!file) return
    setStatus('loading')
    setPdfBlob(null)
    setErrorMsg('')

    const formData = new FormData()
    formData.append('file', file)

    try {
      const api = import.meta.env.VITE_API_URL || ''
      const res = await fetch(`${api}/convert`, { method: 'POST', body: formData })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Erreur inconnue' }))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }
      const blob = await res.blob()
      const disposition = res.headers.get('content-disposition') || ''
      const match = disposition.match(/filename="?([^"]+)"?/)
      const name = match?.[1] || file.name.replace(/\.[^.]+$/, '') + '.pdf'
      setPdfBlob(blob)
      setPdfFilename(name)
      setStatus('done')
    } catch (err) {
      setErrorMsg(err.message)
      setStatus('error')
    }
  }

  const download = () => {
    if (!pdfBlob) return
    const url = URL.createObjectURL(pdfBlob)
    const a = document.createElement('a')
    a.href = url
    a.download = pdfFilename
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div style={styles.root}>
      <header style={styles.header}>
        <div style={styles.headerLeft}>
          <span style={styles.logo}>doc<span style={styles.logoAccent}>→</span>pdf</span>
          <span style={styles.tagline}>Conversion locale & confidentielle</span>
        </div>
        <button
          type="button"
          style={styles.themeSwitch}
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          role="switch"
          aria-checked={theme === 'dark'}
          aria-label={`Passer en mode ${theme === 'dark' ? 'clair' : 'sombre'}`}
          title={`Mode ${theme === 'dark' ? 'clair' : 'sombre'}`}
        >
          <span
            style={{
              ...styles.themeThumb,
              ...(theme === 'light' ? styles.themeThumbLight : {}),
            }}
          />
          <span
            style={{
              ...styles.themeLabel,
              ...(theme === 'light' ? styles.themeLabelLight : {}),
            }}
          >
            {theme === 'dark' ? 'Dark' : 'Light'}
          </span>
        </button>
      </header>

      <main style={styles.main}>
        <div style={styles.card}>

          {/* Drop zone */}
          <div
            style={{
              ...styles.dropzone,
              ...(dragging ? styles.dropzoneDragging : {}),
              ...(file ? styles.dropzoneActive : {}),
            }}
            role="button"
            tabIndex={file ? -1 : 0}
            aria-label={file ? `Fichier sélectionné : ${file.name}` : 'Déposer un fichier ou appuyer sur Entrée pour parcourir'}
            onClick={() => !file && inputRef.current?.click()}
            onKeyDown={handleDropzoneKeyDown}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
          >
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPTED}
              onChange={handleInputChange}
              style={{ display: 'none' }}
            />

            {!file ? (
              <div style={styles.dropContent}>
                <UploadIcon />
                <p style={styles.dropLabel}>Déposer un fichier ici</p>
                <p style={styles.dropSub}>ou <span style={styles.link} onClick={(e) => { e.stopPropagation(); inputRef.current?.click() }}>parcourir</span></p>
                <p style={styles.dropFormats}>docx · pdf · pptx · xlsx · odt · html · txt · images…</p>
              </div>
            ) : (
              <div style={styles.fileInfo}>
                <FileIcon ext={file.name.split('.').pop()} />
                <div style={styles.fileMeta}>
                  <span style={styles.fileName}>{file.name}</span>
                  <span style={styles.fileSize}>{formatSize(file.size)}</span>
                </div>
                <button
                  style={styles.clearBtn}
                  onClick={(e) => { e.stopPropagation(); reset() }}
                  title="Retirer le fichier"
                >✕</button>
              </div>
            )}
          </div>

          {/* Convert button */}
          {file && status !== 'done' && (
            <button
              style={{
                ...styles.convertBtn,
                ...(status === 'loading' ? styles.convertBtnLoading : {}),
              }}
              onClick={convert}
              disabled={status === 'loading'}
            >
              {status === 'loading' ? (
                <span style={styles.loaderRow}>
                  <Spinner /> Conversion en cours…
                </span>
              ) : (
                'Convertir en PDF'
              )}
            </button>
          )}

          {/* Error */}
          {status === 'error' && (
            <div style={styles.errorBox}>
              <span style={styles.errorIcon}>⚠</span>
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Done */}
          {status === 'done' && (
            <div style={styles.doneBox}>
              <div style={styles.doneTop}>
                <span style={styles.doneIcon}>✓</span>
                <span style={styles.doneName}>{pdfFilename}</span>
              </div>
              <div style={styles.doneActions}>
                <button style={styles.downloadBtn} onClick={download}>
                  Télécharger le PDF
                </button>
                <button style={styles.newBtn} onClick={reset}>
                  Nouveau fichier
                </button>
              </div>
            </div>
          )}
        </div>
      </main>

      <footer style={styles.footer}>
        Traitement 100% local — aucun document transmis à un service tiers
      </footer>
    </div>
  )
}

// ─── Icons ────────────────────────────────────────────────────────────────────

function UploadIcon() {
  return (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.4, marginBottom: 12 }}>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  )
}

function FileIcon({ ext }) {
  return (
    <div style={styles.fileIconBox}>
      <span style={styles.fileIconExt}>.{ext}</span>
    </div>
  )
}

function Spinner() {
  return (
    <span style={styles.spinner} />
  )
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = {
  root: {
    minHeight: '100vh',
    display: 'flex',
    flexDirection: 'column',
    background: 'var(--bg)',
  },
  header: {
    padding: '24px 32px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 20,
    borderBottom: '1px solid var(--border)',
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'baseline',
    gap: 16,
  },
  logo: {
    fontFamily: 'var(--font-mono)',
    fontSize: 18,
    fontWeight: 500,
    letterSpacing: '-0.02em',
    color: 'var(--text)',
  },
  logoAccent: {
    color: 'var(--text-muted)',
  },
  tagline: {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    color: 'var(--text-muted)',
    letterSpacing: '0.05em',
  },
  themeSwitch: {
    height: 30,
    minWidth: 92,
    padding: '3px 10px 3px 3px',
    borderRadius: 999,
    border: '1px solid var(--border)',
    background: 'var(--surface)',
    color: 'var(--text-dim)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    position: 'relative',
    transition: 'border-color 0.15s, background 0.15s',
  },
  themeThumb: {
    position: 'absolute',
    left: 3,
    width: 22,
    height: 22,
    borderRadius: '50%',
    background: 'var(--text)',
    transform: 'translateX(0)',
    transition: 'transform 0.2s ease',
    flexShrink: 0,
  },
  themeThumbLight: {
    transform: 'translateX(57px)',
  },
  themeLabel: {
    fontFamily: 'var(--font-mono)',
    fontSize: 10,
    letterSpacing: '0.04em',
    textTransform: 'uppercase',
  },
  themeLabelLight: {
    marginRight: 'auto',
    marginLeft: 10,
  },
  main: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '40px 24px',
  },
  card: {
    width: '100%',
    maxWidth: 480,
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
  },
  dropzone: {
    border: '1px dashed var(--border-hover)',
    borderRadius: var_radius(),
    padding: '40px 32px',
    cursor: 'pointer',
    transition: 'border-color 0.15s, background 0.15s',
    background: 'transparent',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  dropzoneDragging: {
    borderColor: 'var(--text-dim)',
    background: 'var(--accent-dim)',
  },
  dropzoneActive: {
    cursor: 'default',
    borderStyle: 'solid',
    borderColor: 'var(--border)',
    padding: '20px 24px',
  },
  dropContent: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    textAlign: 'center',
    gap: 4,
  },
  dropLabel: {
    fontWeight: 400,
    color: 'var(--text-dim)',
    fontSize: 14,
  },
  dropSub: {
    fontSize: 13,
    color: 'var(--text-muted)',
  },
  link: {
    color: 'var(--text-dim)',
    textDecoration: 'underline',
    cursor: 'pointer',
  },
  dropFormats: {
    fontFamily: 'var(--font-mono)',
    fontSize: 10,
    color: 'var(--text-muted)',
    marginTop: 8,
    letterSpacing: '0.04em',
  },
  fileInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: 14,
    width: '100%',
  },
  fileIconBox: {
    width: 42,
    height: 42,
    borderRadius: 4,
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  fileIconExt: {
    fontFamily: 'var(--font-mono)',
    fontSize: 9,
    color: 'var(--text-muted)',
    textTransform: 'uppercase',
  },
  fileMeta: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
    minWidth: 0,
  },
  fileName: {
    fontSize: 13,
    fontWeight: 500,
    color: 'var(--text)',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  fileSize: {
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    color: 'var(--text-muted)',
  },
  clearBtn: {
    background: 'none',
    border: 'none',
    color: 'var(--text-muted)',
    fontSize: 14,
    cursor: 'pointer',
    padding: '4px 8px',
    borderRadius: 4,
    lineHeight: 1,
    flexShrink: 0,
    transition: 'color 0.1s',
  },
  convertBtn: {
    width: '100%',
    padding: '13px 24px',
    background: 'var(--text)',
    color: 'var(--bg)',
    borderRadius: var_radius(),
    fontSize: 14,
    fontWeight: 500,
    letterSpacing: '0.01em',
    transition: 'opacity 0.15s',
    cursor: 'pointer',
  },
  convertBtnLoading: {
    opacity: 0.7,
    cursor: 'not-allowed',
  },
  loaderRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
  },
  spinner: {
    display: 'inline-block',
    width: 14,
    height: 14,
    borderRadius: '50%',
    border: '2px solid var(--border)',
    borderTopColor: 'var(--text)',
    animation: 'spin 0.7s linear infinite',
  },
  errorBox: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 10,
    padding: '14px 16px',
    background: 'rgba(248, 113, 113, 0.06)',
    border: '1px solid rgba(248, 113, 113, 0.2)',
    borderRadius: var_radius(),
    fontSize: 13,
    color: 'var(--error)',
    lineHeight: 1.5,
  },
  errorIcon: {
    flexShrink: 0,
    marginTop: 1,
  },
  doneBox: {
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    padding: '20px',
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: var_radius(),
  },
  doneTop: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
  },
  doneIcon: {
    color: 'var(--success)',
    fontSize: 16,
    flexShrink: 0,
  },
  doneName: {
    fontFamily: 'var(--font-mono)',
    fontSize: 12,
    color: 'var(--text-dim)',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  doneActions: {
    display: 'flex',
    gap: 10,
  },
  downloadBtn: {
    flex: 1,
    padding: '11px 16px',
    background: 'var(--text)',
    color: 'var(--bg)',
    borderRadius: var_radius(),
    fontSize: 13,
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'opacity 0.15s',
  },
  newBtn: {
    padding: '11px 16px',
    background: 'transparent',
    color: 'var(--text-dim)',
    borderRadius: var_radius(),
    fontSize: 13,
    border: '1px solid var(--border)',
    cursor: 'pointer',
    transition: 'border-color 0.15s',
    whiteSpace: 'nowrap',
  },
  footer: {
    padding: '16px 32px',
    borderTop: '1px solid var(--border)',
    fontFamily: 'var(--font-mono)',
    fontSize: 10,
    color: 'var(--text-muted)',
    letterSpacing: '0.04em',
    textAlign: 'center',
  },
}

function var_radius() { return 'var(--radius)' }
