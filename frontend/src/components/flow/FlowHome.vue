<template>
  <div class="app-shell">
    <!-- Mobile burger (hidden on desktop) -->
    <button class="burger-btn" :aria-expanded="sidebarOpen" aria-label="Menu" @click="sidebarOpen = !sidebarOpen">
      <span class="burger-lines" :class="{ open: sidebarOpen }"><i></i><i></i><i></i></span>
    </button>
    <div v-if="sidebarOpen" class="sidebar-backdrop" @click="sidebarOpen = false"></div>

    <!-- Sidebar -->
    <aside class="sidebar" :class="{ open: sidebarOpen }">
      <div class="sidebar-brand">
        <span class="brand-word">crowds</span>
      </div>
      <nav class="side-section">
        <button
          class="side-item"
          :class="{ active: activeTab === 'panel' }"
          @click="activeTab = 'panel'"
        >
          <span class="side-label">New test</span>
        </button>
        <button
          class="side-item"
          :class="{ active: activeTab === 'personas' }"
          @click="activeTab = 'personas'"
        >
          <span class="side-label">Personas</span>
          <span v-if="personaCount" class="side-badge">{{ personaCount }}</span>
        </button>
        <button class="side-item" @click="openHelp">
          <span class="side-label">How it works</span>
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
        <button class="profile-item" @click="profileModalOpen = true; sidebarOpen = false">
          <span class="profile-avatar">{{ avatarInitials }}</span>
          <span class="profile-body">
            <span class="profile-name">{{ displayName }}</span>
            <span class="profile-sub">{{ isPaid ? 'Beta plan' : 'Free plan' }}</span>
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

    <!-- ════ Onboarding: first-visit welcome card ════ -->
    <div v-if="showWelcome" class="ob-backdrop" @click.self="dismissWelcome">
      <div class="ob-card">
        <div class="ob-card-kicker">Welcome to crowds</div>
        <div class="ob-card-title">See how South Africa reacts — before it's real.</div>
        <ol class="ob-list">
          <li><b>Describe</b> what you want to test — a policy, an announcement, or a product and its price.</li>
          <li><b>Pick your crowd</b>, or leave the default South African mix.</li>
          <li><b>Run it</b> — read each person's honest reaction, then ask the room follow-ups.</li>
        </ol>
        <div class="ob-card-actions">
          <button class="ob-btn ghost" @click="dismissWelcome">Got it</button>
          <button class="ob-btn ghost" @click="tryExample">Try an example</button>
          <button class="ob-btn primary" @click="startTour">Take a tour →</button>
        </div>
      </div>
    </div>

    <!-- ════ Onboarding: guided tour spotlight ════ -->
    <div v-if="tourStep" class="tour-overlay">
      <div class="tour-spot" :style="tourSpotStyle"></div>
      <div class="tour-tip" :style="tourTipStyle">
        <div class="tour-tip-step">Step {{ tourStep }} of {{ tourSteps.length }}</div>
        <div class="tour-tip-title">{{ currentTourStep.title }}</div>
        <div class="tour-tip-body">{{ currentTourStep.body }}</div>
        <div class="tour-tip-actions">
          <button class="ob-btn ghost" @click="endTour">Skip</button>
          <button class="ob-btn primary" @click="nextTourStep">{{ tourStep >= tourSteps.length ? 'Done' : 'Next ›' }}</button>
        </div>
      </div>
    </div>

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
              :title="seg.label + ' — ' + seg.description"
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

              <div ref="tourPrompt" class="simple-prompt" :class="{ focused: panelFocused }">
                <textarea
                  ref="panelInput"
                  v-model="panelPitch"
                  class="simple-prompt-input"
                  :placeholder="promptPlaceholder"
                  @focus="panelFocused = true"
                  @blur="panelFocused = false"
                  @input="autosizePrompt"
                ></textarea>
                <div class="simple-prompt-bar">
                  <!-- Poster upload: one vision call reads the image into a
                       text brief, which becomes the pitch above. The cast only
                       ever sees text. -->
                  <label class="crowd-btn" :class="{ busy: posterBusy }">
                    <input
                      type="file"
                      class="poster-file"
                      accept="image/png,image/jpeg,image/webp"
                      :disabled="posterBusy"
                      @change="onPosterPick"
                    />
                    <span class="crowd-btn-icon">▣</span>
                    <span>{{ posterBusy ? 'Reading poster…' : 'Upload poster' }}</span>
                    <span v-if="posterName" class="crowd-btn-summary">{{ posterName }}</span>
                  </label>

                  <button ref="tourCrowd" class="crowd-btn" @click="crowdPickerOpen = true">
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

              <!-- Reading takes 30-60s. Show a thumbnail, a moving bar, the
                   stage it is on, and a counting clock, so the wait never looks
                   like nothing happening. -->
              <div v-if="posterBusy" class="poster-loading">
                <img v-if="posterPreview" :src="posterPreview" class="poster-thumb" alt="" />
                <div class="poster-loading-body">
                  <div class="poster-loading-top">
                    <span class="poster-spinner"></span>
                    <span class="poster-loading-title">Reading your poster</span>
                    <span class="poster-loading-clock">{{ posterElapsed }}s</span>
                  </div>
                  <div class="poster-bar"><span class="poster-bar-fill"></span></div>
                  <div class="poster-loading-stage">{{ posterStage }}</div>
                </div>
              </div>

              <p v-else-if="posterError" class="poster-note error">{{ posterError }}</p>

              <!-- Poster attached. The brief lives here, out of the way, so the
                   box above stays free for the founder's own question. -->
              <div v-if="posterBrief" class="poster-card">
                <div class="poster-card-head">
                  <img v-if="posterPreview" :src="posterPreview" class="poster-chip" alt="" />
                  <span v-else class="poster-card-icon">▣</span>
                  <span class="poster-card-name">{{ posterName }}</span>
                  <span class="poster-card-tag">read into text</span>
                  <button class="poster-card-link" @click="briefOpen = !briefOpen">
                    {{ briefOpen ? 'Hide what it says' : 'See what it says' }}
                  </button>
                  <button class="poster-card-x" title="Remove poster" @click="clearPoster">×</button>
                </div>
                <pre v-if="briefOpen" class="poster-card-brief">{{ posterBrief }}</pre>
              </div>

              <!-- First-timer examples: click to prefill the prompt -->
              <div v-if="!panelPitch.trim() && !posterBrief" class="ob-examples">
                <span class="ob-examples-label">Try:</span>
                <button
                  v-for="(ex, i) in EXAMPLES"
                  :key="i"
                  class="ob-example"
                  @click="useExample(ex)"
                >⊕ {{ ex.label }}</button>
              </div>

              <div class="pp-controls">
                <div class="pp-actions">
                  <button
                    ref="tourSim"
                    class="pp-sim-btn"
                    :disabled="!canSubmit || panelSubmitting"
                    title="Run a full simulation — the deeper, slower process: a population reacts and the reaction spreads over rounds."
                    @click="submitDirectSim"
                  >Run full simulation</button>
                  <button
                    ref="tourRun"
                    class="pp-assemble-btn"
                    :disabled="!canSubmit || panelSubmitting"
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
import { createSession, listSessions, listSegments, uploadPoster } from '../../api/panel'
import { getSimulationHistory } from '../../api/simulation'
import { listPersonas } from '../../api/research'
import { useBilling } from '../../composables/useBilling'
import { useAuth } from '../../composables/useAuth'
import { useToast } from '../../composables/useToast'
import ProfileModal from './ProfileModal.vue'

const emit = defineEmits(['submit', 'open'])

const route = useRoute()
const router = useRouter()

const activeTab = ref('panel')

// ── Mobile sidebar (burger) ────────────────────────────────────────────────
const sidebarOpen = ref(false)
// Selecting anything in the sidebar closes it on mobile.
watch(activeTab, () => { sidebarOpen.value = false })

// ── Auth user → sidebar profile ────────────────────────────────────────────
const { user } = useAuth()
const toast = useToast()
const displayName = computed(() => {
  const m = user.value?.user_metadata || {}
  const name = [m.first_name, m.surname].filter(Boolean).join(' ')
  return m.display_name || name || m.full_name || user.value?.email || 'Your account'
})
const avatarInitials = computed(() => {
  const m = user.value?.user_metadata || {}
  const a = (m.first_name || '').trim()
  const b = (m.surname || '').trim()
  if (a || b) return ((a[0] || '') + (b[0] || '')).toUpperCase()
  const dn = (m.display_name || m.full_name || '').trim()
  if (dn) return dn.split(/\s+/).map(p => p[0]).join('').slice(0, 2).toUpperCase()
  return (user.value?.email || 'me').slice(0, 2).toUpperCase()
})

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

// ── Onboarding: welcome card + example prompts + guided tour ─────────────────
const ONBOARD_KEY = 'crowds_onboarded_v1'
const showWelcome = ref(false)
const tourStep = ref(0)               // 0 = off; 1..N = active step
const tourTargetRect = ref(null)
const tourPrompt = ref(null)
const tourCrowd = ref(null)
const tourRun = ref(null)
const tourSim = ref(null)

// Example pitches — click to prefill so a first-timer sees a good input at once.
const EXAMPLES = [
  { label: 'R50/mo investing app', text: 'A startup launching a mobile app that lets South Africans invest from R50 a month with no monthly fees, aimed at working people in cities who have never invested before.' },
  { label: 'Migration policy', text: 'After the anti-immigrant marches, government announces a national permit verification drive: employers must confirm every worker\'s papers within 90 days, and undocumented workers are offered a route to regularise instead of deportation. We want to know how residents, employers and migrants react, and which part of the message causes the most anger.' },
  { label: 'A rumour spreading', text: 'A voice note spreads on WhatsApp claiming a local clinic is turning South Africans away to treat foreign nationals first. The health department has denied it. We want to see who believes it, who passes it on, and whether the denial changes anything.' },
]
function useExample(ex) {
  panelPitch.value = ex.text
  nextTick(() => panelInput.value && panelInput.value.focus())
}

// The tour walks the four things a first-timer needs to find, in order.
const tourSteps = computed(() => [
  { el: tourPrompt, title: 'Describe what to test', body: 'Type a policy, an announcement, or a product and its price — the way you’d explain it to a person.' },
  { el: tourCrowd,  title: 'Pick your crowd',       body: 'Choose who’s in the room, or leave the default South African mix.' },
  { el: speedDdEl,  title: 'Set the depth',         body: 'Panel is the fast read; higher depth runs more rounds for a richer result.' },
  { el: tourRun,    title: 'Run it',                body: 'Assemble the panel to get each person’s honest reaction — then hover to read, click to interview, and ask the room follow-ups.' },
  { el: tourSim,    title: 'Go deeper: full simulation', body: 'The panel is one honest read. A full simulation runs a larger crowd over several rounds, so reactions spread and shift — you see how opinion moves, not just first impressions. Slower, and uses a trial run.' },
])
const currentTourStep = computed(() => tourSteps.value[tourStep.value - 1] || {})

function updateTourRect() {
  const node = currentTourStep.value.el && currentTourStep.value.el.value
  tourTargetRect.value = node ? node.getBoundingClientRect() : null
}
function startTour() {
  showWelcome.value = false
  activeTab.value = 'panel'
  tourStep.value = 1
  nextTick(updateTourRect)
}
function nextTourStep() {
  if (tourStep.value >= tourSteps.value.length) { endTour(); return }
  tourStep.value += 1
  nextTick(updateTourRect)
}
function endTour() {
  tourStep.value = 0
  tourTargetRect.value = null
  localStorage.setItem(ONBOARD_KEY, '1')
}
function dismissWelcome() {
  showWelcome.value = false
  localStorage.setItem(ONBOARD_KEY, '1')
}
function tryExample() {
  useExample(EXAMPLES[0])
  dismissWelcome()
}
function openHelp() { showWelcome.value = true }

const tourSpotStyle = computed(() => {
  const r = tourTargetRect.value
  if (!r) return { display: 'none' }
  const pad = 8
  return {
    left: (r.left - pad) + 'px', top: (r.top - pad) + 'px',
    width: (r.width + pad * 2) + 'px', height: (r.height + pad * 2) + 'px',
  }
})
const tourTipStyle = computed(() => {
  const r = tourTargetRect.value
  if (!r) return { left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }
  const W = 300, GAP = 16, EST_H = 200
  const left = Math.min(Math.max(16, r.left), window.innerWidth - W - 16)
  let top = r.bottom + GAP
  if (top + EST_H > window.innerHeight) top = r.top - EST_H - GAP
  // Keep the whole tip — including the Next/Done button — on screen.
  top = Math.max(16, Math.min(top, window.innerHeight - EST_H - 16))
  return { left: left + 'px', top: top + 'px', width: W + 'px' }
})

onMounted(() => {
  if (!localStorage.getItem(ONBOARD_KEY)) showWelcome.value = true
  window.addEventListener('resize', updateTourRect)
})
onUnmounted(() => {
  window.removeEventListener('resize', updateTourRect)
  stopPosterProgress()
})

// ── New-test state (one input, drives both panel and direct sim) ─────────────
const panelPitch = ref('')
const panelFocused = ref(false)
const panelInput = ref(null)
const panelSize = ref(12)
const sizeOptions = [8, 12, 20]
const selectedSegments = ref(['everyone'])

// ── Poster upload → pitch text ──────────────────────────────────────────────
// The vision model reads the image ONCE into a brief, and the brief lands in
// the box above as ordinary editable text. Personas never see the image.
const posterBusy = ref(false)
const posterName = ref('')
const posterError = ref('')
const posterBrief = ref('')
const posterId = ref('')
const briefOpen = ref(false)
const posterPreview = ref('')
const posterElapsed = ref(0)

// Stage captions, shown on a timer. They describe what the read involves, so a
// long wait reads as progress rather than a hang. They are not a real progress
// signal — the call is one round trip and returns all at once.
const POSTER_STAGES = [
  'Uploading the image…',
  'Looking at the layout…',
  'Transcribing every word, including the small print…',
  'Working out what it claims and what it asks…',
  'Almost there — writing the brief…',
]
const posterStageIndex = ref(0)
const posterStage = computed(() => POSTER_STAGES[posterStageIndex.value])
let posterTimer = null

function startPosterProgress () {
  posterElapsed.value = 0
  posterStageIndex.value = 0
  clearInterval(posterTimer)
  posterTimer = setInterval(() => {
    posterElapsed.value += 1
    // Advance a stage roughly every 12 seconds, holding on the last one.
    const next = Math.floor(posterElapsed.value / 12)
    posterStageIndex.value = Math.min(next, POSTER_STAGES.length - 1)
  }, 1000)
}

function stopPosterProgress () {
  clearInterval(posterTimer)
  posterTimer = null
}

// A long question can outgrow the box. Grow it to fit, up to the CSS
// max-height, then let it scroll.
function autosizePrompt () {
  const el = panelInput.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${el.scrollHeight}px`
}

async function onPosterPick (event) {
  const file = event.target.files?.[0]
  event.target.value = ''          // let the same file be picked again
  if (!file) return

  posterBusy.value = true
  posterError.value = ''
  clearPoster()
  posterPreview.value = URL.createObjectURL(file)
  startPosterProgress()
  try {
    const res = await uploadPoster(file)
    // The brief is held aside, NOT dropped in the box — the box stays free for
    // the founder's own question about the poster.
    posterBrief.value = res.data.brief || ''
    posterId.value = res.data.poster_id || ''
    posterName.value = file.name
    await nextTick()
    panelInput.value?.focus()
  } catch (e) {
    posterError.value = e.message || 'Could not read that poster'
  } finally {
    posterBusy.value = false
    stopPosterProgress()
  }
}

function clearPoster () {
  posterBrief.value = ''
  posterId.value = ''
  posterName.value = ''
  briefOpen.value = false
  if (posterPreview.value) URL.revokeObjectURL(posterPreview.value)
  posterPreview.value = ''
}

// What actually goes to the panel: the poster brief first (what the cast is
// looking at), then the founder's question. The cast only ever sees text.
const composedPitch = () => {
  const question = panelPitch.value.trim()
  if (!posterBrief.value) return question
  const parts = ['THE POSTER', posterBrief.value]
  if (question) parts.push('WHAT THE FOUNDER WANTS TO KNOW', question)
  return parts.join('\n\n')
}

// A poster on its own is enough to run — the question is optional.
const canSubmit = computed(() =>
  Boolean(panelPitch.value.trim() || posterBrief.value)
)

// With a poster attached the box is for the founder's question, not the pitch.
const promptPlaceholder = computed(() => posterBrief.value
  ? "Ask the room something about your poster. e.g. Would you trust this? What would stop you? Leave it blank to just get their reactions."
  : "What do you want to test? Describe a policy or announcement, or a product and its price — the way you'd explain it to someone. e.g. A R99/month prepaid solar lantern subscription for township households, paid via airtime."
)

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
  const q = composedPitch()
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
    // The user pressed run and paid attention. Silence here read as "nothing
    // happened" — the button just stopped spinning.
    if (!e?.upgradeRequired) {
      toast.error(e?.message || 'Could not set up the panel.',
                  { retry: submitPanel, code: e?.response?.data?.code })
    }
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
  const q = composedPitch()
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
  min-height: 56px; max-height: 240px; overflow-y: auto;
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
  max-width: 14ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
/* The whole pill is the <label>, so the raw input is hidden. */
.poster-file { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
.crowd-btn.busy { opacity: 0.6; cursor: default; }
.poster-note {
  margin: 10px 0 0; font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem; color: #777;
}
.poster-note.error { color: #99372A; }

/* ── Reading a poster: thumbnail + spinner + moving bar + clock ───────────── */
.poster-loading {
  margin-top: 10px; padding: 12px 14px;
  display: flex; gap: 14px; align-items: center;
  border: 1px solid #E5E5E5; border-radius: 12px; background: #FAFCFB;
  font-family: 'JetBrains Mono', monospace;
}
.poster-thumb {
  width: 46px; height: 60px; object-fit: cover; flex: none;
  border-radius: 6px; border: 1px solid #E5E5E5;
}
.poster-loading-body { flex: 1; min-width: 0; }
.poster-loading-top { display: flex; align-items: center; gap: 9px; }
.poster-loading-title { font-size: 0.78rem; font-weight: 600; color: #333; }
.poster-loading-clock { margin-left: auto; font-size: 0.72rem; color: #999; }
.poster-loading-stage { margin-top: 7px; font-size: 0.72rem; color: #777; }

.poster-spinner {
  width: 13px; height: 13px; flex: none;
  border: 2px solid rgba(30, 158, 90, 0.25);
  border-top-color: #1E9E5A;
  border-radius: 50%;
  animation: poster-spin 0.75s linear infinite;
}
@keyframes poster-spin { to { transform: rotate(360deg); } }

/* Indeterminate bar — the call returns all at once, so it sweeps rather than
   pretending to measure real progress. */
.poster-bar {
  margin-top: 9px; height: 3px; border-radius: 999px;
  background: #EDEFEE; overflow: hidden;
}
.poster-bar-fill {
  display: block; width: 38%; height: 100%; border-radius: 999px;
  background: #1E9E5A;
  animation: poster-sweep 1.5s ease-in-out infinite;
}
@keyframes poster-sweep {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(265%); }
}

.poster-chip {
  width: 18px; height: 24px; object-fit: cover; flex: none;
  border-radius: 4px; border: 1px solid #E5E5E5;
}

/* ── Attached poster: the brief lives out of the way, collapsed ───────────── */
.poster-card {
  margin-top: 10px; padding: 10px 14px;
  border: 1px solid #E5E5E5; border-radius: 12px; background: #FAFCFB;
  font-family: 'JetBrains Mono', monospace; font-size: 0.74rem;
}
.poster-card-head { display: flex; align-items: center; gap: 10px; }
.poster-card-icon { color: #1E9E5A; }
.poster-card-name {
  font-weight: 600; color: #333;
  max-width: 22ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.poster-card-tag {
  color: #1E9E5A; background: rgba(30, 158, 90, 0.1);
  padding: 1px 8px; border-radius: 8px; font-size: 0.68rem;
}
.poster-card-link {
  margin-left: auto; border: none; background: none; cursor: pointer;
  font-family: inherit; font-size: 0.72rem; color: #777;
  text-decoration: underline; text-underline-offset: 2px;
}
.poster-card-link:hover { color: #1E9E5A; }
.poster-card-x {
  border: none; background: none; cursor: pointer;
  font-size: 1.05rem; line-height: 1; color: #999; padding: 0 2px;
}
.poster-card-x:hover { color: #99372A; }
.poster-card-brief {
  margin: 10px 0 0; padding-top: 10px; border-top: 1px solid #EDEFEE;
  max-height: 260px; overflow-y: auto;
  white-space: pre-wrap; font-size: 0.72rem; line-height: 1.6; color: #555;
}

/* ── Crowd picker modal ───────────────────────────────────────────────────── */
/* ── Onboarding: welcome card, example chips, guided tour ─────────────────── */
.ob-backdrop {
  position: fixed; inset: 0; z-index: 120;
  background: rgba(15, 23, 42, 0.42);
  display: flex; align-items: center; justify-content: center; padding: 24px;
}
.ob-card {
  width: 100%; max-width: 460px;
  background: #fff; border-radius: 16px; padding: 28px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
}
.ob-card-kicker {
  font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 700;
  letter-spacing: 0.6px; text-transform: uppercase; color: #1E9E5A;
}
.ob-card-title { margin: 6px 0 16px; font-size: 20px; font-weight: 700; color: #111827; line-height: 1.3; }
.ob-list { margin: 0 0 22px; padding-left: 20px; display: flex; flex-direction: column; gap: 10px; }
.ob-list li { font-size: 14px; line-height: 1.55; color: #374151; }
.ob-list b { color: #111827; }
.ob-card-actions { display: flex; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
.ob-btn {
  padding: 9px 16px; border-radius: 9px; font-size: 13px; font-weight: 700;
  cursor: pointer; border: 1px solid transparent; transition: background .15s, border-color .15s;
}
.ob-btn.ghost { background: #fff; border-color: #E5E7EB; color: #374151; }
.ob-btn.ghost:hover { background: #F3F4F6; }
.ob-btn.primary { background: #1E9E5A; color: #fff; }
.ob-btn.primary:hover { background: #178048; }

.ob-examples { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin: 14px 2px 0; }
.ob-examples-label {
  font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 700;
  color: #9CA3AF; text-transform: uppercase; letter-spacing: 0.4px;
}
.ob-example {
  padding: 6px 12px; border-radius: 999px; border: 1px solid #E5E7EB; background: #fff;
  font-size: 12.5px; color: #374151; cursor: pointer; transition: border-color .15s, background .15s;
}
.ob-example:hover { border-color: #1E9E5A; background: #F0FBF4; color: #178048; }

.tour-overlay { position: fixed; inset: 0; z-index: 200; }
.tour-spot {
  position: fixed; border-radius: 10px; pointer-events: none;
  box-shadow: 0 0 0 9999px rgba(15, 23, 42, 0.55);
  outline: 2px solid #1E9E5A; transition: left .2s, top .2s, width .2s, height .2s;
}
.tour-tip {
  position: fixed; background: #fff; border-radius: 12px; padding: 16px;
  box-shadow: 0 14px 40px rgba(0, 0, 0, 0.28);
}
.tour-tip-step {
  font-family: 'JetBrains Mono', monospace; font-size: 10.5px; font-weight: 700;
  color: #9CA3AF; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;
}
.tour-tip-title { font-size: 15px; font-weight: 700; color: #111827; margin-bottom: 6px; }
.tour-tip-body { font-size: 13px; line-height: 1.55; color: #4B5563; margin-bottom: 14px; }
.tour-tip-actions { display: flex; justify-content: space-between; gap: 8px; }

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
  display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  grid-auto-rows: 1fr; gap: 10px;
}
.pp-segment {
  display: flex; flex-direction: column; gap: 4px;
  height: 100%; min-height: 118px;
  padding: 12px 14px; border: 1px solid #E5E5E5; border-radius: 12px;
  background: #fff; cursor: pointer; text-align: left;
  transition: border-color 0.15s, background 0.15s;
}
.pp-segment:hover { border-color: #1E9E5A; }
.pp-segment.selected { border-color: #1E9E5A; background: #F0FAF4; }
.pp-segment-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.pp-segment-label {
  font-weight: 600; font-size: 0.88rem; color: #000;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.pp-segment-count {
  font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; font-weight: 700;
  color: #1E9E5A; background: rgba(30, 158, 90, 0.1);
  padding: 1px 7px; border-radius: 8px;
}
.pp-segment-desc {
  font-size: 0.73rem; color: #777; line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical;
  overflow: hidden;
}

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

/* ── Mobile burger + off-canvas sidebar ──────────────────────────────────── */
.burger-btn {
  display: none;
  position: fixed; top: 12px; left: 12px; z-index: 96;
  width: 40px; height: 40px; border-radius: 10px;
  background: #fff; border: 1px solid #E5E5E5; cursor: pointer;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  align-items: center; justify-content: center;
}
.burger-lines { display: flex; flex-direction: column; gap: 4px; width: 18px; }
.burger-lines i {
  display: block; height: 2px; border-radius: 2px; background: #444;
  transition: transform 0.18s, opacity 0.18s;
}
.burger-lines.open i:nth-child(1) { transform: translateY(6px) rotate(45deg); }
.burger-lines.open i:nth-child(2) { opacity: 0; }
.burger-lines.open i:nth-child(3) { transform: translateY(-6px) rotate(-45deg); }
.sidebar-backdrop {
  display: none;
  position: fixed; inset: 0; z-index: 94;
  background: rgba(15, 23, 42, 0.35);
}

@media (max-width: 860px) {
  .burger-btn { display: flex; }
  .sidebar-backdrop { display: block; }
  .sidebar {
    position: fixed; top: 0; left: 0; bottom: 0; z-index: 95;
    width: min(280px, 84vw);
    /* 100dvh, not 100vh — vh overshoots past the browser chrome on mobile
       and pushes the profile footer off screen. */
    height: 100dvh;
    transform: translateX(-100%);
    transition: transform 0.2s ease;
    box-shadow: 0 0 40px rgba(0, 0, 0, 0.18);
  }
  /* Profile stays pinned at the bottom; only the recents list scrolls. */
  .side-foot {
    flex-shrink: 0;
    padding-bottom: calc(4px + env(safe-area-inset-bottom));
    background: #FAFAFA;
  }
  .sidebar.open { transform: translateX(0); }
  .sidebar-brand { padding-top: 2px; }
  .app-main { width: 100%; }
  .main-inner { padding: 68px 16px 24px; }
  .simple-greeting { font-size: 1.4rem; }
  .simple-center { min-height: calc(100vh - 120px); }
  .simple-prompt-bar { flex-wrap: wrap; }
  .pp-actions { margin-left: 0; width: 100%; flex-wrap: wrap; }
  .pp-actions button { flex: 1; justify-content: center; }
  .simple-ask { margin-top: 0; }
  .pp-segments { grid-template-columns: 1fr; }
  .persona-grid { grid-template-columns: 1fr !important; }
  .persona-view .page-head { flex-direction: column; gap: 4px; }
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
  .persona-grid { grid-template-columns: 1fr; }
}
</style>
