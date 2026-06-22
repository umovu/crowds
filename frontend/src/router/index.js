import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import FlowView from '../views/FlowView.vue'
import Process from '../views/MainView.vue'
import SimulationView from '../views/SimulationView.vue'
import SimulationRunView from '../views/SimulationRunView.vue'
import ReportView from '../views/ReportView.vue'
import InteractionView from '../views/InteractionView.vue'
import AuthCallbackView from '../views/AuthCallbackView.vue'
import { useAuth } from '../composables/useAuth'

const routes = [
  {
    path: '/auth/callback',
    name: 'AuthCallback',
    component: AuthCallbackView,
    meta: { public: true }
  },
  {
    // Flow is the default landing experience.
    path: '/',
    name: 'Home',
    component: FlowView
  },
  {
    // Old link/bookmark compatibility — /flow now lives at /.
    path: '/flow',
    redirect: '/'
  },
  {
    // The previous rich app (persona drawer, web-research grounding, custom
    // agents, recents, and the /process→/simulation→/report multi-page flow)
    // is kept here, fully reachable.
    path: '/classic',
    name: 'Classic',
    component: Home
  },
  {
    path: '/process/:projectId',
    name: 'Process',
    component: Process,
    props: true
  },
  {
    path: '/simulation/:simulationId',
    name: 'Simulation',
    component: SimulationView,
    props: true
  },
  {
    path: '/simulation/:simulationId/start',
    name: 'SimulationRun',
    component: SimulationRunView,
    props: true
  },
  {
    path: '/report/:reportId',
    name: 'Report',
    component: ReportView,
    props: true
  },
  {
    path: '/interaction/:reportId',
    name: 'Interaction',
    component: InteractionView,
    props: true
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Global auth guard: routes are protected by default. Only routes flagged
// `meta.public` (the OAuth/magic-link callback) are reachable while signed out.
//
// The public front door is the static marketing site (frontend/public/), served
// same-origin as this SPA:
//   - bare `/`        → landing.html (the marketing page)
//   - any deep link   → auth.html, carrying `next` so sign-in returns the
//                       visitor to where they were headed
// These are plain HTML outside the Vue router, so we hard-navigate with
// window.location and cancel the in-app navigation.
router.beforeEach(async (to) => {
  // A magic-link / OAuth code can land on a non-callback path (e.g. the root)
  // when Supabase falls back to the Site URL. Route it through the callback
  // view — which settles the session — instead of letting the guard below
  // bounce it to the login page and discard the code.
  if (to.path !== '/auth/callback' && (to.query.code || to.query.error)) {
    return { path: '/auth/callback', query: to.query }
  }

  const { initAuth, isAuthenticated } = useAuth()
  await initAuth()

  if (to.meta.public) return true

  if (!isAuthenticated.value) {
    window.location.href = to.path === '/'
      ? '/landing.html'
      : `/auth.html?next=${encodeURIComponent(to.fullPath)}`
    return false
  }
  return true
})

export default router
