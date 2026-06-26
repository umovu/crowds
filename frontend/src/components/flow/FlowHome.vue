<template>
  <div class="app-shell">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-brand">
        <span class="brand-word">crowds</span>
      </div>
      <nav class="side-section">
        <button
          class="side-item"
          :class="{ active: activeTab === 'panel' }"
          @click="activeTab = 'panel'"
        >
          <span class="side-icon">◇</span>
          <span class="side-label">New test</span>
        </button>
        <button
          class="side-item"
          :class="{ active: activeTab === 'personas' }"
          @click="activeTab = 'personas'"
        >
          <span class="side-icon">👥</span>
          <span class="side-label">Personas</span>
          <span v-if="personaCount" class="side-badge">{{ personaCount }}</span>
        </button>
      </nav>

      <!-- Recents — panels + sims together (one entry point now) -->
      <div v-if="activeTab !== 'personas'" class="side-recents">
        <div class="side-recents-head">Previous panels</div>
        <div v-if="panelsLoading" class="side-recents-empty">Loading…</div>
        <div v-else-if="!panels.length" class="side-recents-empty">No previous panels yet.</div>
        <button
          v-for="p in panels"
          :key="p.session_id"
          class="flow-recent"
          :title="p.pitch || '(no pitch)'"
          @click="openPanel(p)"
        >{{ (p.pitch || '(no pitch)').slice(0, 46) }}</button>

        <div class="side-recents-head" style="margin-top: 10px">Previous sims</div>
        <div v-if="simsLoading" class="side-recents-empty">Loading…</div>
        <div v-else-if="!sims.length" class="side-recents-empty">No previous sims yet.</div>
        <button
          v-for="s in sims"
          :key="s.simulation_id"
          class="flow-recent"
          :title="s.simulation_requirement || 'Untitled simulation'"
          @click="openSim(s)"
        >{{ (s.simulation_requirement || 'Untitled simulation').slice(0, 46) }}</button>
      </div>

      <!-- Profile button — bottom of sidebar -->
      <div class="side-foot">
        <button class="profile-item" @click="profileModalOpen = true">
          <span class="profile-avatar">JS</span>
          <span class="profile-body">
            <span class="profile-name">Jabu Swartbooi</span>
            <span class="profile-sub">{{ isPaid ? 'Paid plan' : 'Free plan' }}</span>
          </span>
          <span class="profile-chevron">⋯</span>
        </button>
      </div>
    </aside>

    <!-- Profile modal (small menu + full-page expand) -->
    <ProfileModal
      v-if="profileModalOpen"
      @close="profileModalOpen = false"
      @open-sim="onModalOpenSim"
    />

    <!-- Crowd picker modal — organises the library into selectable groups -->
    <div v-if="crowdPickerOpen" class="crowd-backdrop" @click.self="crowdPickerOpen = false">
      <div class="crowd-modal">
        <div class="crowd-modal-head">
          <span class="crowd-modal-title">Select your crowd</span>
          <button class="crowd-modal-close" @click="crowdPickerOpen = false">✕</button>
        </div>
        <div class="crowd-modal-body">
          <div class="pp-field-label">Who's in the room?</div>
          <div class="pp-segments">
            <button
              v-for="seg in segments"
              :key="seg.id"
              class="pp-segment"
              :class="{ selected: selectedSegments.includes(seg.id) }"
              @click="toggleSegment(seg.id)"
            >
              <span class="pp-segment-top">
                <span class="pp-segment-label">{{ seg.label }}</span>
                <span class="pp-segment-count">{{ seg.count }}</span>
              </span>
              <span class="pp-segment-desc">{{ seg.description }}</span>
            </button>
          </div>

          <div class="pp-control-row">
            <span class="pp-control-label">Panel size</span>
            <div class="pp-size-btns">
              <button
                v-for="opt in sizeOptions"
                :key="opt"
                class="pp-size-btn"
                :class="{ active: panelSize === opt }"
                @click="panelSize = opt"
              >{{ opt }}</button>
            </div>
          </div>
        </div>
        <div class="crowd-modal-foot">
          <span class="crowd-foot-summary">{{ crowdSummary }} · {{ panelSize }} people</span>
          <button class="crowd-done-btn" @click="crowdPickerOpen = false">Done</button>
        </div>
      </div>
    </div>

    <!-- Main column -->
    <main class="app-main">
      <div class="main-inner">

        <!-- ════ PERSONAS TAB ════ -->
        <div v-if="activeTab === 'personas'" class="persona-view">
          <div class="page-head">
            <div class="page-title">Personas</div>
            <div class="page-sub">{{ personas.length }} IN LIBRARY</div>
          </div>
          <div class="persona-filters">
            <input
              v-model="personaSearch"
              class="persona-search"
              type="text"
              placeholder="Search by name, occupation, archetype…"
            >
            <button
              v-for="chip in personaFilterChips"
              :key="chip.id"
              class="persona-filter-chip"
              :class="{ active: personaFilter === chip.id }"
              @click="personaFilter = chip.id"
            >{{ chip.label }} <span class="chip-count">{{ chip.count }}</span></button>
          </div>
          <div v-if="personasLoading" class="persona-loading">Loading personas…</div>
          <div v-else-if="!filteredPersonas.length" class="persona-loading">No personas match your search.</div>
          <div v-else class="persona-grid">
            <div
              v-for="p in filteredPersonas"
              :key="p.id || p.name"
              class="persona-card"
            >
              <div class="persona-card-avatar">{{ initials(p.name) }}</div>
              <div class="persona-card-info">
                <div class="persona-card-name">{{ p.name || 'Unnamed' }}</div>
                <div class="persona-card-arch">{{ (p.archetype || p.actor_archetype || 'unknown').replace(/_/g, ' ') }}</div>
                <div class="persona-card-occ">{{ p.occupation || '—' }}</div>
                <div class="persona-card-meta">{{ p.age || '?' }} · {{ p.province || '—' }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- ════ NEW TEST (centered) ════ -->
        <div v-else class="simple-view">
          <div class="simple-center">

            <!-- ════ NEW TEST (panel + optional direct sim) ════ -->
            <div v-if="activeTab === 'panel'" class="simple-ask">
              <h1 class="simple-greeting">See how South Africa reacts — before it's real.</h1>

              <div class="simple-prompt" :class="{ focused: panelFocused }">
                <textarea
                  ref="panelInput"
                  v-model="panelPitch"
                  class="simple-prompt-input"
                  placeholder="What do you want to test? Describe a policy or announcement, or a product and its price — the way you'd explain it to someone. e.g. A R99/month prepaid solar lantern subscription for township households, paid via airtime."
                  @focus="panelFocused = true"
                  @blur="panelFocused = false"
                ></textarea>
                <div class="simple-prompt-bar">
                  <button class="crowd-btn" @click="crowdPickerOpen = true">
                    <span class="crowd-btn-icon">◇</span>
                    <span>Select crowds</span>
                    <span class="crowd-btn-summary">{{ crowdSummary }}</span>
                  </button>

                  <!-- Run speed — collapsible dropdown (sim depth/rounds) -->
                  <div ref="speedDdEl" class="speed-dd">
                    <button class="crowd-btn" @click="speedMenuOpen = !speedMenuOpen">
                      <span class="crowd-btn-icon">⚡</span>
                      <span>{{ currentPreset.label }}</span>
                      <span class="crowd-btn-summary">{{ currentPreset.rounds }}</span>
                      <span class="speed-caret" :class="{ open: speedMenuOpen }">▾</span>
                    </button>
                    <Transition name="speed-pop">
                      <div v-if="speedMenuOpen" class="speed-menu" role="listbox">
                        <button
                          v-for="opt in SIM_PRESETS"
                          :key="opt.id"
                          class="speed-item"
                          :class="{ active: simPreset === opt.id }"
                          role="option"
                          :aria-selected="simPreset === opt.id"
                          @click="selectPreset(opt.id)"
                        >
                          <span class="speed-item-top">
                            <span class="speed-item-name">{{ opt.label }}</span>
                            <span class="speed-item-rounds">{{ opt.rounds }}</span>
                          </span>
                          <span class="speed-item-hint">{{ opt.hint }}</span>
                        </button>
                      </div>
                    </Transition>
                  </div>
                </div>
              </div>

              <div class="pp-controls">
                <div class="pp-actions">
                  <button
                    class="pp-sim-btn"
                    :disabled="!panelPitch.trim() || panelSubmitting"
                    title="Run a full simulation — the deeper, slower process: a population reacts and the reaction spreads over rounds."
                    @click="submitDirectSim"
                  >Run full simulation</button>
                  <button
                    class="pp-assemble-btn"
                    :disabled="!panelPitch.trim() || panelSubmitting"
                    @click="submitPanel"
                  >
                    <span>Assemble panel</span>
                    <span>→</span>
                  </button>
                </div>
              </div>
              <p class="pp-hint">Policy or product is detected automatically. Panel is the fast read; the full simulation is an additional, deeper run.</p>
            </div>

          </div>
        </div>

      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { setPendingUpload, setSimPreset } from '../../store/pendingUpload'
import { createSession, listSessions, listSegments } from '../../api/panel'
import { getSimulationHistory } from '../../api/simulation'
import { listPersonas } from '../../api/research'
import { useBilling } from '../../composables/useBilling'
import ProfileModal from './ProfileModal.vue'

const emit = defineEmits(['submit', 'open'])

const route = useRoute()
const router = useRouter()

const activeTab = ref('panel')

// ── Profile modal ──────────────────────────────────────────────────────────
const profileModalOpen = ref(false)

// Real plan for the sidebar profile badge.
const { isPaid, refresh: refreshBilling } = useBilling()

function onModalOpenSim(sim) {
  profileModalOpen.value = false
  openSim(sim)
}

// ── Personas library ───────────────────────────────────────────────────────
const personas = ref([])
const personasLoading = ref(false)
const personaSearch = ref('')
const personaFilter = ref('all')
// One tab per archetype, derived from the loaded library (+ an "All" tab).
const personaFilterChips = computed(() => {
  const counts = {}
  for (const p of personas.value) {
    const a = (p.archetype || p.actor_archetype || '').toLowerCase()
    if (a) counts[a] = (counts[a] || 0) + 1
  }
  const chips = Object.keys(counts).sort().map(a => ({
    id: a,
    label: a.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
    count: counts[a],
  }))
  return [{ id: 'all', label: 'All', count: personas.value.length }, ...chips]
})

const personaCount = computed(() => personas.value.length)

const filteredPersonas = computed(() => {
  const q = personaSearch.value.trim().toLowerCase()
  return personas.value.filter(p => {
    if (personaFilter.value !== 'all') {
      const arch = (p.archetype || p.actor_archetype || '').toLowerCase()
      if (arch !== personaFilter.value) return false
    }
    if (!q) return true
    return (
      (p.name || '').toLowerCase().includes(q) ||
      (p.occupation || '').toLowerCase().includes(q) ||
      (p.archetype || p.actor_archetype || '').toLowerCase().includes(q)
    )
  })
})

function initials(name) {
  if (!name) return '?'
  return name.split(' ').map(p => p[0]).join('').slice(0, 2).toUpperCase()
}

const loadPersonas = async () => {
  personasLoading.value = true
  try {
    const res = await listPersonas()
    personas.value = res.personas || []
  } catch (e) {
    console.error('Failed to load personas:', e)
  } finally {
    personasLoading.value = false
  }
}

// ── Previous sims / panels — saved on disk, click to revisit ───────────────
const sims = ref([])
const simsLoading = ref(false)
const panels = ref([])
const panelsLoading = ref(false)

const loadSims = async () => {
  simsLoading.value = true
  try { sims.value = (await getSimulationHistory(20)).data || [] }
  catch (e) { console.error('Failed to load previous sims:', e) }
  finally { simsLoading.value = false }
}
const loadPanels = async () => {
  panelsLoading.value = true
  try { panels.value = (await listSessions()).data?.sessions || [] }
  catch (e) { console.error('Failed to load previous panels:', e) }
  finally { panelsLoading.value = false }
}

const openSim = (s) =>
  emit('open', { mode: 'sim', simulationId: s.simulation_id, query: s.simulation_requirement || '' })
const openPanel = (p) =>
  emit('open', { mode: 'panel', sessionId: p.session_id, query: p.pitch || '' })

// ── New-test state (one input, drives both panel and direct sim) ─────────────
const panelPitch = ref('')
const panelFocused = ref(false)
const panelInput = ref(null)
const panelSize = ref(12)
const sizeOptions = [8, 12, 20]
const selectedSegments = ref(['everyone'])

// Crowd picker (segments + size live behind a modal, off the home view).
const crowdPickerOpen = ref(false)
const crowdSummary = computed(() => {
  const sel = selectedSegments.value
  if (!sel.length || (sel.length === 1 && sel[0] === 'everyone')) return 'Everyone'
  const labelOf = (id) => (segments.value.find(s => s.id === id)?.label || id)
  if (sel.length <= 2) return sel.map(labelOf).join(' + ')
  return `${sel.length} groups`
})

// Real library segments with live counts come from /api/panel/segments on mount.
// Seeded with a fallback list (ids match backend SEGMENTS) so the picker isn't
// empty before the fetch resolves or if it fails.
const segments = ref([
  { id: 'everyone', label: 'Everyone', count: 0, description: 'Full mixed population' },
  { id: 'employed', label: 'Employed', count: 0, description: 'Formal and informal employment' },
  { id: 'unemployed', label: 'Unemployed', count: 0, description: 'Seeking work' },
  { id: 'youth', label: 'Youth', count: 0, description: 'Aged under 35' },
  { id: 'small_business', label: 'Small business', count: 0, description: 'Spaza, tuck shops, traders' },
  { id: 'informal_traders', label: 'Informal traders', count: 0, description: 'Street vendors, market sellers' },
  { id: 'grant_recipients', label: 'Grant recipients', count: 0, description: 'SASSA grant holders' },
  { id: 'learners', label: 'Learners', count: 0, description: 'School learners' },
  { id: 'guardians', label: 'Guardians', count: 0, description: 'Parents and caregivers' },
])

const loadSegments = async () => {
  try {
    const res = await listSegments()
    const real = res.data?.segments
    // Show only segments that actually have members in the library.
    if (Array.isArray(real) && real.length) {
      segments.value = real.filter(s => s.id === 'everyone' || s.count > 0)
    }
  } catch (e) {
    console.error('Failed to load segments (using fallback):', e)
  }
}

const toggleSegment = (id) => {
  if (id === 'everyone') {
    selectedSegments.value = ['everyone']
    return
  }
  let next = selectedSegments.value.filter(s => s !== 'everyone')
  next = next.includes(id) ? next.filter(s => s !== id) : [...next, id]
  selectedSegments.value = next.length ? next : ['everyone']
}

const panelSubmitting = ref(false)
// Panel: fast read. Mode (policy/product) is inferred backend-side from the pitch
// (no toggle); omit `mode` so the server detects it.
const submitPanel = async () => {
  const q = panelPitch.value.trim()
  if (!q || panelSubmitting.value) return
  panelSubmitting.value = true
  try {
    const res = await createSession({
      pitch: q,
      n: panelSize.value,
      segments: selectedSegments.value
    })
    const sessionId = res.data?.session_id
    if (!sessionId) throw new Error('No session id returned')
    emit('submit', {
      query: q,
      mode: 'panel',
      segments: selectedSegments.value,
      size: panelSize.value,
      sessionId
    })
  } catch (e) {
    console.error('Failed to assemble panel:', e)
  } finally {
    panelSubmitting.value = false
  }
}

// Run-speed presets — rounds map to backend quick/balanced/deep (6/12/24).
const SIM_PRESETS = [
  { id: 'quick',    label: 'Quick',    rounds: '6 rounds',  hint: 'Fastest, cheapest — a shallow read (6 rounds).' },
  { id: 'balanced', label: 'Balanced', rounds: '12 rounds', hint: 'Default — a solid read over 12 rounds.' },
  { id: 'deep',     label: 'Deep',     rounds: '24 rounds', hint: 'Slowest, most thorough — lets reactions spread over 24 rounds.' },
]
const simPreset = ref('balanced')
const speedMenuOpen = ref(false)
const speedDdEl = ref(null)
const currentPreset = computed(() => SIM_PRESETS.find(o => o.id === simPreset.value) || SIM_PRESETS[1])
const selectPreset = (id) => { simPreset.value = id; speedMenuOpen.value = false }
// Close the speed dropdown on any click outside it.
const onSpeedOutside = (e) => {
  if (speedMenuOpen.value && speedDdEl.value && !speedDdEl.value.contains(e.target)) {
    speedMenuOpen.value = false
  }
}

// Direct sim: the deeper, additional run off the same pitch. No mode toggle —
// modeIsManual stays false so the backend auto-detects policy/product at /prepare.
const submitDirectSim = () => {
  const q = panelPitch.value.trim()
  if (!q || panelSubmitting.value) return
  setPendingUpload([], q, [], false, false)
  setSimPreset(simPreset.value)
  emit('submit', { query: q, mode: 'sim' })
}

// Focus the input. Load personas when switching to that tab.
watch(activeTab, (tab) => {
  nextTick(() => {
    if (tab === 'panel') panelInput.value?.focus()
  })
  if (tab === 'personas' && !personas.value.length && !personasLoading.value) {
    loadPersonas()
  }
})

onMounted(() => {
  refreshBilling()  // load real plan for the sidebar badge
  // Seed handoff from the marketing landing page: /?seed=... (mode is ignored now —
  // policy/product is always inferred). Pre-fill the prompt, then strip the params
  // so a refresh doesn't re-seed.
  const seed = typeof route.query.seed === 'string' ? route.query.seed : ''
  if (seed) {
    activeTab.value = 'panel'
    panelPitch.value = seed
  }
  if (seed || route.query.mode) {
    router.replace({ query: {} })
  }

  panelInput.value?.focus()
  loadSegments()
  loadSims()
  loadPanels()
  document.addEventListener('mousedown', onSpeedOutside)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', onSpeedOutside)
})
</script>

<style scoped>
/* ── App shell — exact copy of Home.vue ──────────────────────────────────── */
.app-shell { display: flex; height: 100vh; overflow: hidden; }
.sidebar {
  flex-shrink: 0; width: 256px; height: 100vh;
  background: #FAFAFA; border-right: 1px solid #E8E8E8;
  display: flex; flex-direction: column;
  padding: 16px 12px; gap: 8px; overflow: hidden;
}
.sidebar-brand {
  display: flex; align-items: center; gap: 10px;
  padding: 6px 8px 12px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800; font-size: 1.15rem; cursor: pointer; user-select: none;
}
.brand-mark {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: 8px;
  background: linear-gradient(160deg, #25b368 0%, #1E9E5A 60%, #178048 100%);
  color: #fff; font-family: 'JetBrains Mono', monospace;
  font-weight: 800; font-size: 1.15rem; line-height: 1; flex-shrink: 0;
  box-shadow: 0 2px 6px rgba(30, 158, 90, 0.28);
}
.brand-word { line-height: 1; letter-spacing: -0.3px; color: #6b6b6b; font-weight: 700; }
.brand-strong { color: #1E9E5A; }
.side-section {
  display: flex; flex-direction: column; gap: 2px;
  padding-bottom: 8px; border-bottom: 1px solid #ECECEC;
}
.side-item {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 9px 12px; background: transparent; border: none;
  border-radius: 8px; cursor: pointer;
  font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;
  font-weight: 600; color: #555; text-align: left;
  transition: background 0.15s, color 0.15s;
}
.side-item:hover { background: #F0F0F0; color: #1a1a1a; }
.side-item.active { background: #F0FAF4; color: #1E9E5A; }
.side-icon { font-size: 0.95rem; line-height: 1; width: 18px; text-align: center; }
.side-label { flex: 1; }
.side-recents { flex: 1; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 1px; padding-top: 4px; }
.side-recents-head { padding: 6px 12px; font-family: 'JetBrains Mono', monospace; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; color: #aaa; }
.side-recents-empty { padding: 6px 12px; font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #bbb; }
.flow-recent {
  display: block; width: 100%; padding: 7px 12px;
  background: transparent; border: none; border-radius: 8px; cursor: pointer;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  font-size: 0.8rem; color: #555; text-align: left;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: background 0.15s, color 0.15s;
}
.flow-recent:hover { background: #F0F0F0; color: #1a1a1a; }

/* Main column */
.app-main { flex: 1; min-width: 0; height: 100vh; overflow-y: auto; }
.main-inner { max-width: 1200px; margin: 0 auto; padding: 40px; }
.simple-view { position: relative; min-height: calc(100vh - 80px); }
.simple-center { display: flex; align-items: center; justify-content: center; min-height: calc(100vh - 80px); }
.simple-ask {
  width: 100%; max-width: 680px;
  display: flex; flex-direction: column; gap: 24px;
  margin-top: -40px;
}
.simple-greeting {
  margin: 0; text-align: center;
  font-size: 1.9rem; font-weight: 500; letter-spacing: -0.5px; color: #1a1a1a;
}
.simple-prompt {
  border: 1px solid #DDD; border-radius: 16px; background: #fff;
  padding: 16px 16px 12px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.simple-prompt.focused { border-color: #1E9E5A; box-shadow: 0 2px 12px rgba(30, 158, 90, 0.12); }
.simple-prompt-input {
  width: 100%; border: none; background: transparent; outline: none; resize: none;
  min-height: 56px; max-height: 240px;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  font-size: 1.05rem; line-height: 1.55; color: #1a1a1a;
}
.simple-prompt-input::placeholder { color: #9a9a9a; }
.simple-prompt-bar { display: flex; align-items: center; gap: 8px; margin-top: 8px; }

/* ── Select-crowds button (opens the picker modal) ────────────────────────── */
.crowd-btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 14px; border: 1px solid #E5E5E5; background: #fff;
  border-radius: 999px; cursor: pointer;
  font-family: 'JetBrains Mono', monospace; font-size: 0.74rem;
  font-weight: 600; color: #555; transition: border-color 0.15s, color 0.15s;
}
.crowd-btn:hover { border-color: #1E9E5A; color: #1E9E5A; }
.crowd-btn-icon { font-size: 0.85rem; line-height: 1; }
.crowd-btn-summary {
  color: #1E9E5A; background: rgba(30, 158, 90, 0.1);
  padding: 1px 8px; border-radius: 8px; font-size: 0.68rem;
}

/* ── Crowd picker modal ───────────────────────────────────────────────────── */
.crowd-backdrop {
  position: fixed; inset: 0; z-index: 50;
  background: rgba(0, 0, 0, 0.32);
  display: flex; align-items: center; justify-content: center; padding: 24px;
}
.crowd-modal {
  width: 100%; max-width: 680px; max-height: 84vh;
  display: flex; flex-direction: column;
  background: #fff; border-radius: 16px; overflow: hidden;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.22);
}
.crowd-modal-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 18px 22px; border-bottom: 1px solid #ECECEC;
}
.crowd-modal-title { font-size: 1.05rem; font-weight: 600; color: #1a1a1a; }
.crowd-modal-close {
  border: none; background: transparent; cursor: pointer;
  font-size: 1rem; color: #999; line-height: 1; padding: 4px;
}
.crowd-modal-close:hover { color: #1a1a1a; }
.crowd-modal-body { padding: 20px 22px; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; }
.pp-control-row { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.crowd-modal-foot {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 14px 22px; border-top: 1px solid #ECECEC;
}
.crowd-foot-summary { font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #999; }
.crowd-done-btn {
  background: #1E9E5A; color: #fff; border: none; border-radius: 999px;
  padding: 9px 24px; font-family: 'JetBrains Mono', monospace;
  font-weight: 700; font-size: 0.8rem; letter-spacing: 0.4px;
  cursor: pointer; transition: background 0.15s;
}
.crowd-done-btn:hover { background: #178048; }

/* ── Panel pitch fields — copied from PanelPitchPanel ─────────────────────── */
.pp-field-group { display: flex; flex-direction: column; gap: 10px; }
.pp-field-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem; font-weight: 700;
  letter-spacing: 0.5px; text-transform: uppercase; color: #999;
}
.pp-segments {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 10px;
}
.pp-segment {
  display: flex; flex-direction: column; gap: 4px;
  padding: 12px 14px; border: 1px solid #E5E5E5; border-radius: 12px;
  background: #fff; cursor: pointer; text-align: left;
  transition: border-color 0.15s, background 0.15s;
}
.pp-segment:hover { border-color: #1E9E5A; }
.pp-segment.selected { border-color: #1E9E5A; background: #F0FAF4; }
.pp-segment-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.pp-segment-label { font-weight: 600; font-size: 0.88rem; color: #000; }
.pp-segment-count {
  font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; font-weight: 700;
  color: #1E9E5A; background: rgba(30, 158, 90, 0.1);
  padding: 1px 7px; border-radius: 8px;
}
.pp-segment-desc { font-size: 0.73rem; color: #777; line-height: 1.4; }

.pp-controls {
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
}
.pp-control-label {
  font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;
  color: #999; letter-spacing: 0.5px; text-transform: uppercase;
}
.pp-size-btns { display: flex; gap: 4px; }
.pp-size-btn {
  padding: 5px 14px; border: 1px solid #E5E5E5; background: #fff;
  border-radius: 999px; font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem; font-weight: 600; color: #777; cursor: pointer;
  transition: all 0.15s;
}
.pp-size-btn:hover { border-color: #1E9E5A; color: #1E9E5A; }
.pp-size-btn.active { background: #1E9E5A; border-color: #1E9E5A; color: #fff; }
/* Run-speed dropdown — lives in the seed-box bar next to Select crowds */
.speed-dd { position: relative; }
.speed-caret { font-size: 0.6rem; color: #9CA3AF; transition: transform 0.15s; }
.speed-caret.open { transform: rotate(180deg); }
.speed-menu {
  position: absolute; top: calc(100% + 6px); left: 0; z-index: 30;
  min-width: 240px; background: #fff; border: 1px solid #E5E7EB;
  border-radius: 12px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12);
  padding: 6px; display: flex; flex-direction: column; gap: 2px;
}
.speed-item {
  display: flex; flex-direction: column; gap: 2px; align-items: flex-start;
  padding: 8px 10px; border: none; background: transparent; border-radius: 8px;
  cursor: pointer; text-align: left; transition: background 0.12s;
}
.speed-item:hover { background: #F5F5F5; }
.speed-item.active { background: #F0FAF4; }
.speed-item-top { display: flex; align-items: baseline; gap: 8px; }
.speed-item-name {
  font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; font-weight: 700; color: #444;
}
.speed-item.active .speed-item-name { color: #1E9E5A; }
.speed-item-rounds { font-family: 'JetBrains Mono', monospace; font-size: 0.66rem; color: #9CA3AF; }
.speed-item-hint { font-size: 0.7rem; color: #888; line-height: 1.35; }

.speed-pop-enter-active, .speed-pop-leave-active { transition: opacity 0.14s ease, transform 0.14s ease; }
.speed-pop-enter-from, .speed-pop-leave-to { opacity: 0; transform: translateY(-4px); }

.pp-actions { margin-left: auto; display: flex; align-items: center; gap: 10px; }
.pp-assemble-btn {
  display: flex; align-items: center; gap: 12px;
  background: #1E9E5A; color: #fff; border: none; border-radius: 999px;
  padding: 11px 24px; font-family: 'JetBrains Mono', monospace;
  font-weight: 700; font-size: 0.85rem; letter-spacing: 0.5px;
  cursor: pointer; transition: background 0.15s;
}
.pp-assemble-btn:hover:not(:disabled) { background: #178048; }
.pp-assemble-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* Direct sim — secondary action (the deeper, additional run) */
.pp-sim-btn {
  background: #fff; color: #1E9E5A; border: 1px solid #1E9E5A;
  border-radius: 999px; padding: 10px 18px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700; font-size: 0.8rem; letter-spacing: 0.3px;
  cursor: pointer; transition: background 0.15s, color 0.15s;
}
.pp-sim-btn:hover:not(:disabled) { background: #F0FAF4; }
.pp-sim-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.pp-hint {
  margin: 12px 0 0; font-size: 0.76rem; color: #999; line-height: 1.5;
}

@media (max-width: 860px) {
  .simple-ask { margin-top: 0; }
  .pp-segments { grid-template-columns: 1fr; }
  .persona-grid { grid-template-columns: repeat(2, 1fr) !important; }
}

/* ── Sidebar additions ─────────────────────────────────────────────────── */
.side-badge {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.62rem; font-weight: 700;
  color: #1E9E5A; background: rgba(30,158,90,0.1);
  border-radius: 999px; padding: 1px 7px;
}

/* Profile button — bottom of sidebar */
.side-foot {
  margin-top: auto;
  padding: 12px 12px 4px;
  border-top: 1px solid #ECECEC;
}
.profile-item {
  display: flex; align-items: center; gap: 10px;
  width: 100%; padding: 9px 12px;
  background: transparent; border: none; border-radius: 8px;
  cursor: pointer; text-align: left; font: inherit; color: inherit;
  transition: background 0.15s;
}
.profile-item:hover { background: #F0F0F0; }
.profile-avatar {
  width: 30px; height: 30px; border-radius: 50%;
  background: linear-gradient(160deg, #25b368 0%, #1E9E5A 60%, #178048 100%);
  color: #fff;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700; font-size: 0.78rem;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.profile-body { display: flex; flex-direction: column; min-width: 0; flex: 1; gap: 1px; }
.profile-name {
  font-size: 0.82rem; font-weight: 600; color: #1a1a1a;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2;
}
.profile-sub {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem; color: #999;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2;
}
.profile-chevron { color: #bbb; font-size: 0.7rem; flex-shrink: 0; }

/* ── Personas tab ─────────────────────────────────────────────────────── */
.persona-view { display: flex; flex-direction: column; gap: 20px; }
.persona-view .page-head {
  display: flex; align-items: baseline; justify-content: space-between;
}
.persona-view .page-title { font-size: 1.6rem; font-weight: 600; letter-spacing: -0.5px; color: #1a1a1a; }
.persona-view .page-sub { font-family: 'JetBrains Mono', monospace; font-size: 0.74rem; color: #999; letter-spacing: 0.4px; }

.persona-filters { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.persona-search {
  flex: 1; min-width: 200px;
  border: 1px solid #DDD; border-radius: 8px;
  padding: 9px 14px;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  font-size: 0.84rem; color: #1a1a1a;
  background: #F2F2F2; outline: none;
  transition: border-color 0.15s, background 0.15s;
}
.persona-search:focus { border-color: #1E9E5A; background: #fff; }
.persona-filter-chip {
  padding: 6px 14px; border: 1px solid #DDD; background: #fff;
  border-radius: 999px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem; font-weight: 600; color: #777;
  cursor: pointer; transition: all 0.15s;
}
.persona-filter-chip:hover { border-color: #1E9E5A; color: #1E9E5A; }
.persona-filter-chip.active { background: #1E9E5A; border-color: #1E9E5A; color: #fff; }
.chip-count { opacity: 0.6; font-size: 0.62rem; margin-left: 2px; }

.persona-loading {
  padding: 40px; text-align: center;
  font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; color: #999;
}

.persona-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px;
}
.persona-card {
  background: #fff; border: 1px solid #E8E8E8; border-radius: 12px;
  padding: 16px 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  display: flex; gap: 14px; cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
}
.persona-card:hover {
  border-color: #1E9E5A; box-shadow: 0 4px 14px rgba(0,0,0,0.06); transform: translateY(-1px);
}
.persona-card-avatar {
  width: 40px; height: 40px; border-radius: 50%;
  background: #F0FAF4; border: 1px solid rgba(30,158,90,0.3);
  color: #1E9E5A;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.82rem; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.persona-card-info { display: flex; flex-direction: column; gap: 3px; min-width: 0; flex: 1; }
.persona-card-name {
  font-size: 0.88rem; font-weight: 600; color: #1a1a1a;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.persona-card-arch {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.64rem; color: #1E9E5A; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.3px;
}
.persona-card-occ {
  font-size: 0.74rem; color: #555;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.persona-card-meta {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem; color: #bbb; margin-top: 2px;
}

@media (max-width: 860px) {
  .persona-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
