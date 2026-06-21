import { ref, computed } from 'vue'
import { supabase } from '../lib/supabase'

// Shared, app-wide reactive auth state (module-level singletons).
const session = ref(null)
const user = computed(() => session.value?.user ?? null)
const isAuthenticated = computed(() => !!session.value)
const loading = ref(true)

let initialized = false

// Initialize once: hydrate the current session and subscribe to changes.
// Safe to call from main.js before mounting and from the router guard.
async function initAuth() {
  if (initialized) return
  initialized = true

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

async function signInWithGoogle() {
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo: redirectTo() }
  })
  if (error) throw error
  return data
}

async function signOut() {
  const { error } = await supabase.auth.signOut()
  if (error) throw error
}

// Current access token (JWT) for attaching to backend API calls.
async function getAccessToken() {
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
    signInWithGoogle,
    signOut,
    getAccessToken
  }
}
