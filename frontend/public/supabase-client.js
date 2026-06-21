/* Shared Supabase client for the standalone marketing pages (landing.html,
   auth.html). These are plain static HTML — not part of the Vite build — so we
   load supabase-js from a CDN (same pattern as DiceBear on the landing page).

   IMPORTANT: this MUST mirror frontend/src/lib/supabase.js exactly — same
   project URL, same publishable key, same auth options (default storageKey).
   That way a session written here lands in the same localStorage entry
   (`sb-<project-ref>-auth-token`) the Vue SPA reads in useAuth.initAuth(), so
   signing in on auth.html carries straight into the app with no extra hop.

   Config (URL + publishable key) is NOT hardcoded here — it's imported from
   ./supabase-config.js, which is generated at dev/build time from the
   VITE_SUPABASE_* env vars (see scripts/gen-public-config.js) and is gitignored.
   That keeps real keys out of this open-source repo; each deployer supplies
   their own (Vercel env vars in prod, frontend/.env locally). */
import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm'
import { SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY } from './supabase-config.js'

export { SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY }

export const supabase = createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
    flowType: 'pkce'
  }
})

// Where OAuth / magic-link / email-confirm flows return to. We always bounce
// through the SPA's /auth/callback route (it settles the session, then routes
// to `next`). `next` is an in-app path like "/?seed=...&mode=policy".
export function callbackUrl(next) {
  const base = `${window.location.origin}/auth/callback`
  return next ? `${base}?next=${encodeURIComponent(next)}` : base
}
