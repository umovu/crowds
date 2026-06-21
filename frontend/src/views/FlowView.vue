<template>
  <div class="flow-shell">
    <!-- Base layer: home, always present on the same page. Overlays appear on
         top of it — nothing navigates away. -->
    <FlowHome :class="{ 'base-dimmed': state !== 'home' }" @submit="onSubmit" @open="onOpen" />

    <!-- Overlay: the build box pops up over the dimmed home (sim only). -->
    <Transition name="popup">
      <FlowBuilding
        v-if="state === 'building'"
        :query="query"
        @view-reactions="goResults"
        @back="goBack"
      />
    </Transition>

    <!-- Overlay: results rises in over everything. -->
    <Transition name="rise">
      <FlowResults
        v-if="state === 'results'"
        :query="query"
        :mode="mode"
        :simulation-id="simulationId"
        :session-id="sessionId"
        @back="goBack"
      />
    </Transition>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import FlowHome from '../components/flow/FlowHome.vue'
import FlowBuilding from '../components/flow/FlowBuilding.vue'
import FlowResults from '../components/flow/FlowResults.vue'

// One app shell, one state machine. `state` is the only thing that changes.
const state = ref('home')       // 'home' | 'building' | 'results'
const query = ref('')
const mode = ref('sim')         // 'sim' | 'panel'

// Real backend handles, carried into the results overlay. Sim mode fills in
// simulationId once the build pipeline has created+started the simulation;
// panel mode fills in sessionId at submit (the assembled panel session).
const simulationId = ref(null)
const sessionId = ref(null)

// ── Real flow ───────────────────────────────────────────────────────────────
const onSubmit = (payload) => {
  query.value = payload.query
  mode.value = payload.mode
  if (payload.mode === 'panel') {
    // Panel pitch skips the graph build — the session is already assembled, go
    // straight to reactions with the real session id.
    sessionId.value = payload.sessionId || null
    state.value = 'results'
  } else {
    simulationId.value = null
    state.value = 'building'
  }
}

// The build overlay hands back the live simulation id once the pipeline has
// created + started the simulation; carry it into the results overlay.
const goResults = (simId) => {
  if (simId) simulationId.value = simId
  state.value = 'results'
}

// ── Back navigation ──────────────────────────────────────────────────────────
// Collapse any overlay back to home. Leaving the overlay unmounts FlowBuilding /
// FlowResults, which stop their own polling in onUnmounted.
const goHome = () => {
  state.value = 'home'
}

// Browser-history integration: opening an overlay from home pushes a history
// entry, so the browser Back button (and our Back buttons, which call
// history.back()) collapse the overlay to home instead of leaving the app.
let overlayDepth = 0
let suppressPush = false
watch(state, (val, old) => {
  if (suppressPush) { suppressPush = false; return }
  if (val !== 'home' && old === 'home') {
    window.history.pushState({ flowOverlay: true }, '')
    overlayDepth++
  }
})
const goBack = () => {
  if (overlayDepth > 0) window.history.back()   // → popstate → goHome
  else goHome()
}
const onPopState = () => {
  if (state.value !== 'home') {
    suppressPush = true
    goHome()
  }
  if (overlayDepth > 0) overlayDepth--
}
onMounted(() => window.addEventListener('popstate', onPopState))
onUnmounted(() => window.removeEventListener('popstate', onPopState))

// Revisit a saved sim/panel from the sidebar — straight to results, no rebuild
// (sim) and no re-pitch (panel; FlowResults loads the saved round).
const onOpen = (payload) => {
  query.value = payload.query || ''
  mode.value = payload.mode
  if (payload.mode === 'panel') {
    sessionId.value = payload.sessionId || null
    simulationId.value = null
  } else {
    simulationId.value = payload.simulationId || null
    sessionId.value = null
  }
  state.value = 'results'
}
</script>

<style scoped>
.flow-shell {
  position: relative;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  background: #FFF;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

/* Home dims/blurs when an overlay sits on top — reinforces "same page". */
.base-dimmed {
  filter: blur(2px) brightness(0.96);
  transition: filter 0.4s ease;
  pointer-events: none;
}

/* Building overlay: backdrop + card fade in together. */
.popup-enter-active,
.popup-leave-active {
  transition: opacity 0.4s ease;
}
.popup-enter-from,
.popup-leave-to {
  opacity: 0;
}

/* Results overlay: rises in from below. */
.rise-enter-active,
.rise-leave-active {
  transition: opacity 0.45s ease, transform 0.45s ease;
}
.rise-enter-from {
  opacity: 0;
  transform: translateY(18px);
}
.rise-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

</style>
