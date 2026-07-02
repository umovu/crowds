import axios from 'axios'
import { supabase } from '../lib/supabase'

// Create axios instance
const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 300000, // 5 minute timeout (ontology generation may require longer time)
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor — attach the Supabase access token (JWT) so the Flask
// backend can verify the caller. supabase-js auto-refreshes the token, so
// getSession() always returns a fresh one.
service.interceptors.request.use(
  async config => {
    let { data } = await supabase.auth.getSession()
    let session = data.session
    // Refresh proactively when the access token is expired / near expiry, so a
    // stale token after a page refresh doesn't fire a doomed request that trips
    // the 401 sign-out below.
    if (session?.expires_at && session.expires_at * 1000 < Date.now() + 10000) {
      try {
        const r = await supabase.auth.refreshSession()
        if (r.data?.session) session = r.data.session
      } catch (_) { /* keep the stale token; the 401 path will retry once */ }
    }
    if (session?.access_token) {
      config.headers.Authorization = `Bearer ${session.access_token}`
    }
    return config
  },
  error => {
    console.error('Request error:', error)
    return Promise.reject(error)
  }
)

// Response interceptor (fault-tolerant retry mechanism)
service.interceptors.response.use(
  response => {
    const res = response.data

    // If the returned status code is not success, throw error
    if (!res.success && res.success !== undefined) {
      console.error('API Error:', res.error || res.message || 'Unknown error')
      return Promise.reject(new Error(res.error || res.message || 'Error'))
    }

    return res
  },
  async error => {
    console.error('Response error:', error)

    // Handle timeout
    if (error.code === 'ECONNABORTED' && error.message.includes('timeout')) {
      console.error('Request timeout')
    }

    // Handle network error
    if (error.message === 'Network Error') {
      console.error('Network error - please check your connection')
    }

    // Tag the HTTP status (when present) so retry logic can tell a transient
    // failure (network / 5xx) from a permanent one (4xx — won't self-heal).
    if (error.response && error.response.status != null) {
      error.httpStatus = error.response.status
    }

    // 402 from the backend = the action needs a paid plan. Flag it and broadcast
    // an app-wide event so the UI can prompt an upgrade instead of erroring out.
    if (error.httpStatus === 402 || error.response?.data?.code === 'upgrade_required') {
      error.upgradeRequired = true
      error.upgradeMessage = error.response?.data?.error || 'Upgrade required'
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('billing:upgrade-required', {
          detail: { message: error.upgradeMessage }
        }))
      }
      return Promise.reject(error)
    }

    // 401 = token missing/expired/invalid. Before nuking the session (which
    // would drop the user's whole view on a mere token blip after a refresh),
    // try refreshing the session once and replaying the request. Only if that
    // refresh genuinely fails do we sign out and send them to the auth page.
    if (error.httpStatus === 401) {
      const original = error.config
      if (original && !original._retried401) {
        original._retried401 = true
        try {
          const { data } = await supabase.auth.refreshSession()
          const token = data?.session?.access_token
          if (token) {
            original.headers = original.headers || {}
            original.headers.Authorization = `Bearer ${token}`
            return service(original)   // replay once with the fresh token
          }
        } catch (_) { /* fall through to sign-out */ }
      }
      supabase.auth.signOut().finally(() => {
        const next = encodeURIComponent(window.location.pathname + window.location.search)
        if (!window.location.pathname.startsWith('/auth.html')) {
          window.location.assign(`/auth.html?next=${next}`)
        }
      })
    }

    return Promise.reject(error)
  }
)

// A failure is worth retrying only if it could plausibly succeed on a retry:
// network errors, timeouts, and 5xx. A 4xx (e.g. 404 "data not found") will
// return the same result every time — retrying just makes the user wait.
const isRetryable = (error) => {
  const status = error && error.httpStatus
  if (status != null) {
    return status >= 500  // 5xx transient; 4xx permanent
  }
  // No HTTP status → network error / timeout / aborted: retryable.
  return true
}

// Request function with retry
export const requestWithRetry = async (requestFn, maxRetries = 3, delay = 1000) => {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await requestFn()
    } catch (error) {
      // Don't waste retries on permanent failures — surface them immediately.
      if (!isRetryable(error) || i === maxRetries - 1) throw error

      console.warn(`Request failed, retrying (${i + 1}/${maxRetries})...`)
      await new Promise(resolve => setTimeout(resolve, delay * Math.pow(2, i)))
    }
  }
}

export default service
