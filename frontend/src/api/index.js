import axios from 'axios'

// Create axios instance
const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 300000, // 5 minute timeout (ontology generation may require longer time)
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor
service.interceptors.request.use(
  config => {
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
  error => {
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
