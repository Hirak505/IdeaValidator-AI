import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'

const AuthContext = createContext(null)

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [accessToken, setAccessToken] = useState(null)
  const [loading, setLoading] = useState(true)

  // In-flight refresh promise ref to deduplicate concurrent refresh calls
  const refreshPromiseRef = useRef(null)

  // Fetch current user details with an access token
  const fetchCurrentUser = useCallback(async (token) => {
    try {
      const res = await fetch(`${API_URL}/auth/me`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })
      if (res.ok) {
        const userData = await res.json()
        setUser(userData)
        return userData
      } else {
        setUser(null)
        return null
      }
    } catch (err) {
      setUser(null)
      return null
    }
  }, [])

  // Silent refresh via HttpOnly cookie (deduplicated)
  const refreshToken = useCallback(async () => {
    // If a refresh is already in-flight, return the existing in-flight promise
    if (refreshPromiseRef.current) {
      return refreshPromiseRef.current
    }

    const performRefresh = async () => {
      try {
        const res = await fetch(`${API_URL}/auth/refresh`, {
          method: 'POST',
          credentials: 'include',
        })
        if (res.ok) {
          const data = await res.json()
          setAccessToken(data.access_token)
          await fetchCurrentUser(data.access_token)
          return data.access_token
        } else {
          // 401 or failure indicates no active/valid refresh session -> clean anonymous state
          setAccessToken(null)
          setUser(null)
          return null
        }
      } catch (err) {
        // Network error or backend offline -> preserve clean anonymous state
        setAccessToken(null)
        setUser(null)
        return null
      } finally {
        refreshPromiseRef.current = null
      }
    }

    refreshPromiseRef.current = performRefresh()
    return refreshPromiseRef.current
  }, [fetchCurrentUser])

  // Initial session restoration on mount (runs once)
  useEffect(() => {
    let mounted = true
    const initAuth = async () => {
      try {
        await refreshToken()
      } catch (_) {
        // Unauthenticated visitor: silently fail and proceed in anonymous state
      } finally {
        if (mounted) setLoading(false)
      }
    }
    initAuth()
    return () => {
      mounted = false
    }
  }, [refreshToken])

  const login = async (email, password) => {
    const res = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ email, password }),
    })
    const data = await res.json()
    if (!res.ok) {
      throw new Error(data.detail || 'Login failed.')
    }
    setAccessToken(data.access_token)
    setUser(data.user)
    return data
  }

  const register = async (email, password, displayName) => {
    const res = await fetch(`${API_URL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        email,
        password,
        display_name: displayName || undefined,
      }),
    })
    const data = await res.json()
    if (!res.ok) {
      let msg = data.detail || 'Registration failed.'
      if (Array.isArray(data.detail)) {
        msg = data.detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
      }
      throw new Error(msg)
    }
    setAccessToken(data.access_token)
    setUser(data.user)
    return data
  }

  const logout = async () => {
    try {
      await fetch(`${API_URL}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      })
    } catch (_) {
      // Ignore network errors on logout
    } finally {
      setAccessToken(null)
      setUser(null)
    }
  }

  // Wrapper for authenticated fetch with maximum 1 refresh-and-retry cycle
  const authFetch = async (url, options = {}) => {
    const opts = { ...options, headers: { ...options.headers } }
    let token = accessToken
    if (token) {
      opts.headers['Authorization'] = `Bearer ${token}`
    }

    let res = await fetch(url, opts)

    // Only attempt refresh if this was an authenticated request (token was provided)
    // that received a 401, avoiding pointless refresh attempts on unauthenticated calls
    if (res.status === 401 && token && !url.includes('/auth/login') && !url.includes('/auth/refresh')) {
      const newToken = await refreshToken()
      if (newToken) {
        opts.headers['Authorization'] = `Bearer ${newToken}`
        // Single retry with new token
        res = await fetch(url, opts)
      } else {
        // Refresh failed: clear credentials to return cleanly to unauthenticated state
        setAccessToken(null)
        setUser(null)
      }
    }
    return res
  }

  const value = {
    user,
    accessToken,
    loading,
    login,
    register,
    logout,
    refreshToken,
    authFetch,
    isAuthenticated: !!user,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
