import { useEffect, useState } from 'react'

export default function ThemeToggle() {
  const [theme, setTheme] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('ideavalidator_theme')
      if (saved === 'dark' || saved === 'light') return saved
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    }
    return 'dark'
  })

  useEffect(() => {
    const root = document.documentElement
    const meta = document.getElementById('meta-theme-color')
    if (theme === 'dark') {
      root.classList.add('dark')
      root.setAttribute('data-theme', 'dark')
      if (meta) meta.setAttribute('content', '#10283F')
    } else {
      root.classList.remove('dark')
      root.setAttribute('data-theme', 'light')
      if (meta) meta.setAttribute('content', '#F4F5F2')
    }
    try {
      localStorage.setItem('ideavalidator_theme', theme)
    } catch (_) {}
  }, [theme])

  const toggleTheme = () => {
    setTheme(prev => (prev === 'dark' ? 'light' : 'dark'))
  }

  const isDark = theme === 'dark'

  return (
    <button
      onClick={toggleTheme}
      type="button"
      id="theme-toggle-btn"
      role="switch"
      aria-checked={isDark}
      aria-label={isDark ? 'Switch to Light Mode (Blueprint Paper)' : 'Switch to Dark Mode (Blueprint Night)'}
      title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
      className="group relative flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-theme-border bg-theme-panel hover:border-theme-border-active transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-theme-evidence/40"
    >
      {/* Icon Switcher */}
      <div className="relative w-4 h-4 flex items-center justify-center">
        {/* Sun Icon (Light Mode) */}
        <svg
          className={`w-4 h-4 text-theme-annotation transition-all duration-300 absolute ${
            isDark ? 'opacity-0 rotate-90 scale-50 pointer-events-none' : 'opacity-100 rotate-0 scale-100'
          }`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="4" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32l1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
        </svg>

        {/* Moon Icon (Dark Mode) */}
        <svg
          className={`w-4 h-4 text-theme-evidence transition-all duration-300 absolute ${
            isDark ? 'opacity-100 rotate-0 scale-100' : 'opacity-0 -rotate-90 scale-50 pointer-events-none'
          }`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
        </svg>
      </div>

      <span className="font-mono text-micro font-medium text-theme-text-secondary group-hover:text-theme-text uppercase tracking-wider">
        {isDark ? 'NIGHT' : 'PAPER'}
      </span>
    </button>
  )
}
