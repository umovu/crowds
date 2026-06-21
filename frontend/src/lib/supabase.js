import { createClient } from '@supabase/supabase-js'

// Supabase client — uses the publishable key (safe to ship to the browser).
// Configure VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY in frontend/.env.
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY

if (!supabaseUrl || !supabaseKey) {
  console.error(
    'Supabase env vars missing. Set VITE_SUPABASE_URL and ' +
    'VITE_SUPABASE_PUBLISHABLE_KEY in frontend/.env'
  )
}

export const supabase = createClient(supabaseUrl, supabaseKey, {
  auth: {
    // SPA: persist the session in localStorage and auto-refresh tokens.
    persistSession: true,
    autoRefreshToken: true,
    // Parse the OAuth/magic-link tokens out of the URL on redirect back.
    detectSessionInUrl: true,
    flowType: 'pkce'
  }
})
