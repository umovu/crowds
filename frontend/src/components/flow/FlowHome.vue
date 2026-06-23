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
          :class="{ active: activeTab === 'sim' }"
          @click="activeTab = 'sim'"
        >
          <span class="side-icon">✳</span>
          <span class="side-label">Sim</span>
        </button>
        <button
          class="side-item"
          :class="{ active: activeTab === 'panel' }"
          @click="activeTab = 'panel'"
        >
          <span class="side-icon">◇</span>
          <span class="side-label">Panel Pitch</span>
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

      <!-- Recents — tab-aware -->
      <div v-if="activeTab !== 'personas'" class="side-recents">
        <div class="side-recents-head">{{ activeTab === 'sim' ? 'Previous sims' : 'Previous panels' }}</div>

        <template v-if="activeTab === 'sim'">
          <div v-if="simsLoading" class="side-recents-empty">Loading…</div>
          <div v-else-if="!sims.length" class="side-recents-empty">No previous sims yet.</div>
          <button
            v-for="s in sims"
            :key="s.simulation_id"
            class="flow-recent"
            :title="s.simulation_requirement || 'Untitled simulation'"
            @click="openSim(s)"
          >{{ (s.simulation_requirement || 'Untitled simulation').slice(0, 46) }}</button>
        </template>

        <template v-else>
          <div v-if="panelsLoading" class="side-recents-empty">Loading…</div>
          <div v-else-if="!panels.length" class="side-recents-empty">No previous panels yet.</div>
          <button
            v-for="p in panels"
            :key="p.session_id"
            class="flow-recent"
            :title="p.pitch || '(no pitch)'"
            @click="openPanel(p)"
          >{{ (p.pitch || '(no pitch)').slice(0, 46) }}</button>
        </template>
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

        <!-- ════ SIM + PANEL TABS (centered) ════ -->
        <div v-else class="simple-view">
          <div class="simple-center">

            <!-- ════ SIM TAB ════ -->
            <div v-if="activeTab === 'sim'" class="simple-ask">
              <h1 class="simple-greeting">How would the public react to your policy or announcement?</h1>
              <div class="simple-prompt" :class="{ focused: focused }">
                <textarea
                  ref="simInput"
                  v-model="simQuery"
                  class="simple-prompt-input"
                  placeholder="Describe the policy, event, or scenario you want to simulate. What are you testing? Who is the audience?"
                  @focus="focused = true"
                  @blur="focused = false"
                  @keydown.enter.exact.prevent="submitSim"
                ></textarea>
                <div class="simple-prompt-bar">
                  <div class="simple-modes">
                    <button class="simple-mode" :class="{ active: simMode === 'policy' }" @click="pickSimMode('policy')">Policy</button>
                    <button class="simple-mode" :class="{ active: simMode === 'product' }" @click="pickSimMode('product')">Product</button>
                  </div>
                  <button class="simple-send" @click="submitSim" :disabled="!simQuery.trim()" title="Start Engine">
                    <span>↑</span>
                  </button>
                </div>
              </div>
            </div>

            <!-- ════ PANEL PITCH TAB ════ -->
            <div v-else-if="activeTab === 'panel'" class="simple-ask">
              <h1 class="simple-greeting">Pitch it straight to the people it's for.</h1>

              <div class="simple-prompt" :class="{ focused: panelFocused }">
                <textarea
                  ref="panelInput"
                  v-model="panelPitch"
                  class="simple-prompt-input"
                  placeholder="Describe the product and the price. e.g. A R99/month prepaid solar lantern subscription for township households, paid via airtime."
                  @focus="panelFocused = true"
                  @blur="panelFocused = false"
                ></textarea>
                <div class="simple-prompt-bar">
                  <div class="simple-modes">
                    <button class="simple-mode" :class="{ active: panelMode === 'product' }" @click="panelMode = 'product'">Product</button>
                    <button class="simple-mode" :class="{ active: panelMode === 'policy' }" @click="panelMode = 'policy'">Policy</button>
                  </div>
                </div>
              </div>

              <div class="pp-field-group">
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
              </div>

              <div class="pp-controls">
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

          </div>
        </div>

      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { setPendingUpload } from '../../store/pendingUpload'
import { createSession, listSessions } from '../../api/panel'
import { getSimulationHistory } from '../../api/simulation'
import { listPersonas } from '../../api/research'
import { useBilling } from '../../composables/useBilling'
import ProfileModal from './ProfileModal.vue'

const emit = defineEmits(['submit', 'open'])

const route = useRoute()
const router = useRouter()

const activeTab = ref('sim')

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

// ── Sim state ───────────────────────────────────────────────────────────────
const simQuery = ref('')
const simMode = ref('policy')
const simModeTouched = ref(false)
const focused = ref(false)
const simInput = ref(null)

const submitSim = () => {
  const q = simQuery.value.trim()
  if (!q) return
  setPendingUpload([], q, [], false, false, simMode.value, simModeTouched.value)
  emit('submit', { query: q, mode: 'sim', simMode: simMode.value })
}

const pickSimMode = (m) => { simMode.value = m; simModeTouched.value = true }

// ── Panel pitch state ───────────────────────────────────────────────────────
const panelPitch = ref('')
const panelMode = ref('product')
const panelFocused = ref(false)
const panelInput = ref(null)
const panelSize = ref(12)
const sizeOptions = [8, 12, 20]
const selectedSegments = ref(['everyone'])

const segments = [
  { id: 'everyone', label: 'Everyone', count: 48, description: 'Full mixed population' },
  { id: 'employed', label: 'Employed', count: 18, description: 'Formal and informal employment' },
  { id: 'unemployed', label: 'Unemployed', count: 12, description: 'Seeking work' },
  { id: 'youth', label: 'Youth', count: 14, description: 'Aged 18–25' },
  { id: 'small_business', label: 'Small business', count: 9, description: 'Spaza, tuck shops, traders' },
  { id: 'informal_traders', label: 'Informal traders', count: 7, description: 'Street vendors, market sellers' },
  { id: 'grant_recipients', label: 'Grant recipients', count: 11, description: 'SASSA grant holders' },
  { id: 'learners', label: 'Learners', count: 10, description: 'School learners' },
  { id: 'guardians', label: 'Guardians', count: 8, description: 'Parents and caregivers' },
]

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
const submitPanel = async () => {
  const q = panelPitch.value.trim()
  if (!q || panelSubmitting.value) return
  panelSubmitting.value = true
  try {
    const res = await createSession({
      pitch: q,
      mode: panelMode.value,
      n: panelSize.value,
      segments: selectedSegments.value
    })
    const sessionId = res.data?.session_id
    if (!sessionId) throw new Error('No session id returned')
    emit('submit', {
      query: q,
      mode: 'panel',
      panelMode: panelMode.value,
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

// Focus the active tab's input. Load personas when switching to that tab.
watch(activeTab, (tab) => {
  nextTick(() => {
    if (tab === 'sim') simInput.value?.focus()
    else if (tab === 'panel') panelInput.value?.focus()
  })
  if (tab === 'personas' && !personas.value.length && !personasLoading.value) {
    loadPersonas()
  }
})

onMounted(() => {
  refreshBilling()  // load real plan for the sidebar badge
  // Seed handoff from the marketing landing page: /?seed=...&mode=policy|product.
  // Pre-fill the sim prompt so the visitor lands mid-thought, then strip the
  // params from the URL so a refresh doesn't re-seed.
  const seed = typeof route.query.seed === 'string' ? route.query.seed : ''
  const seedMode = route.query.mode
  if (seedMode === 'policy' || seedMode === 'product') pickSimMode(seedMode)
  if (seed) {
    activeTab.value = 'sim'
    simQuery.value = seed
  }
  if (seed || seedMode) {
    router.replace({ query: {} })
  }

  simInput.value?.focus()
  loadSims()
  loadPanels()
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
.simple-prompt-bar { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 8px; }
.simple-modes { display: flex; flex-wrap: wrap; gap: 4px; }
.simple-mode {
  padding: 5px 14px; border: 1px solid #E5E5E5; background: #fff;
  border-radius: 999px; font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem; font-weight: 600; color: #777; cursor: pointer;
  transition: all 0.15s;
}
.simple-mode:hover { border-color: #1E9E5A; color: #1E9E5A; }
.simple-mode.active { background: #1E9E5A; border-color: #1E9E5A; color: #fff; }
.simple-send {
  width: 36px; height: 36px; border-radius: 50%; border: none;
  background: #1E9E5A; color: #fff; font-size: 1.2rem; font-weight: 700;
  line-height: 1; cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: background 0.15s;
}
.simple-send:hover:not(:disabled) { background: #178048; }
.simple-send:disabled { background: #DDD; cursor: not-allowed; }

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
.pp-assemble-btn {
  margin-left: auto; display: flex; align-items: center; gap: 12px;
  background: #1E9E5A; color: #fff; border: none; border-radius: 999px;
  padding: 11px 24px; font-family: 'JetBrains Mono', monospace;
  font-weight: 700; font-size: 0.85rem; letter-spacing: 0.5px;
  cursor: pointer; transition: background 0.15s;
}
.pp-assemble-btn:hover:not(:disabled) { background: #178048; }
.pp-assemble-btn:disabled { opacity: 0.4; cursor: not-allowed; }

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
