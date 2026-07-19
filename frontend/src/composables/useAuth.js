import { ref, computed } from 'vue'
import { supabase } from '../lib/supabase'

// Shared, app-wide reactive auth state (module-level singletons).
const session = ref(null)
const user = computed(() => session.value?.user ?? null)
const isAuthenticated = computed(() => !!session.value)
const loading = ref(true)

let initialized = false

// Local-dev mock session (VITE_AUTH_DISABLED=true in frontend/.env.local):
// the whole app behaves as if this user is signed in — no Supabase involved.
// Pairs with the backend's AUTH_DISABLED=true, which stamps requests as the
// "dev" user, so the ids line up. Dev only; .env.local never ships.
const AUTH_DISABLED = import.meta.env.VITE_AUTH_DISABLED === 'true'
const MOCK_SESSION = {
  access_token: null,
  user: {
    id: 'dev',
    email: 'dev@local',
    user_metadata: { full_name: 'Jabu Dev', name: 'Jabu Dev' },
  },
}

// Initialize once: hydrate the current session and subscribe to changes.
// Safe to call from main.js before mounting and from the router guard.
async function initAuth() {
  if (initialized) return
  initialized = true

  if (AUTH_DISABLED) {
    session.value = MOCK_SESSION
    loading.value = false
    return
  }

  const { data } = await supabase.auth.getSession()
  session.value = data.session
  loading.value = false

  // Keeps `session` in sync on sign-in, sign-out, token refresh, OAuth return.
  supabase.auth.onAuthStateChange((_event, newSession) => {
    session.value = newSession
  })
}

// Where Supabase should send the user back after OAuth / magic link.
function redirectTo() {
  return `${window.location.origin}/auth/callback`
}

async function signInWithPassword(email, password) {
  const { data, error } = await supabase.auth.signInWithPassword({ email, password })
  if (error) throw error
  return data
}

async function signUpWithPassword(email, password) {
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: { emailRedirectTo: redirectTo() }
  })
  if (error) throw error
  return data
}

async function signInWithMagicLink(email) {
  const { data, error } = await supabase.auth.signInWithOtp({
    email,
    options: { emailRedirectTo: redirectTo() }
  })
  if (error) throw error
  return data
}

async function signOut() {
  if (AUTH_DISABLED) return // mock session: nothing to sign out of
  const { error } = await supabase.auth.signOut()
  if (error) throw error
}

// Current access token (JWT) for attaching to backend API calls.
async function getAccessToken() {
  if (AUTH_DISABLED) return null // backend AUTH_DISABLED accepts tokenless requests
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
}

export function useAuth() {
  return {
    session,
    user,
    isAuthenticated,
    loading,
    initAuth,
    signInWithPassword,
    signUpWithPassword,
    signInWithMagicLink,
    signOut,
    getAccessToken
  }
}
