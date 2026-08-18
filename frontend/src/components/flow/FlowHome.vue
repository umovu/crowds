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
          <!-- fit asks which of six named groups lands the offer — there's no
               crowd to pick, and the size is fixed: six × two seats. -->
          <template v-if="isFit">
            <div class="pp-field-label">Which fits best?</div>
            <p class="pp-fit-note">Six buyer groups, two seats each — a fixed 12-person cast. The ranking IS the answer.</p>
          </template>
          <template v-else>
            <div class="pp-field-label">Who's in the room?</div>
            <input v-model="crowdSearch" class="crowd-search" type="text" placeholder="Search groups…">
            <div class="pp-segments">
              <button
                v-for="seg in filteredSegments"
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
          </template>

          <div class="pp-control-row">
            <span class="pp-control-label">Panel size</span>
            <div class="pp-size-btns">
              <button
                v-for="opt in sizeOptions"
                :key="opt"
                class="pp-size-btn"
                :class="{ active: effectiveSize === opt }"
                :disabled="isFit"
                @click="panelSize = opt"
              >{{ opt }}</button>
            </div>
          </div>
        </div>
        <div class="crowd-modal-foot">
          <span class="crowd-foot-summary">{{ crowdSummary }} · {{ effectiveSize }} people</span>
          <button class="crowd-done-btn" @click="applyAudience">Done</button>
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
                  v-if="lens !== 'ab'"
                  ref="panelInput"
                  v-model="panelPitch"
                  class="simple-prompt-input"
                  :placeholder="promptPlaceholder"
                  @focus="panelFocused = true"
                  @blur="panelFocused = false"
                  @input="onComposerInput"
                ></textarea>
                <div v-else class="ab-box" @focus="panelFocused = true" @blur="panelFocused = false">
                  <textarea
                    ref="abAInput"
                    v-model="abA"
                    class="ab-box-input"
                    placeholder="Version A — the first way of saying it."
                    @input="onComposerInput"
                  ></textarea>
                  <textarea
                    ref="abBInput"
                    v-model="abB"
                    class="ab-box-input"
                    placeholder="Version B — change one thing, not everything."
                    @input="onComposerInput"
                  ></textarea>
                </div>
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

                  <button v-if="lens !== 'fit'" ref="tourCrowd" class="crowd-btn" @click="openAudiencePicker">
                    <span class="crowd-btn-icon">◇</span>
                    <span>Select crowds</span>
                    <span class="crowd-btn-summary">{{ crowdSummary }}</span>
                  </button>
                  <button v-else ref="tourCrowd" class="crowd-btn" disabled title="Fit ranks every buyer group — there's no one crowd to pick.">
                    <span class="crowd-btn-icon">◇</span>
                    <span>All six buyer groups</span>
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

              <!-- The four lenses: pick a job and the same sentence re-runs
                   under that lens. No form ever opens — structure lives behind
                   the input, the user only types and optionally corrects. -->
              <div v-if="!posterBrief" class="ptr-section">
                <div class="ptr-grid">
                  <div
                    v-for="c in LENS_CARDS"
                    :key="c.id"
                    class="ptr-card"
                    :class="{ active: lens === c.id }"
                  >
                    <button class="ptr-card-main" @click="selectLens(c.id)">
                      <span class="ptr-card-label">{{ c.label }}</span>
                      <span class="ptr-card-blurb">{{ c.blurb }}</span>
                      <span v-if="studyLoading && lens === c.id" class="ptr-card-busy">reading…</span>
                    </button>
                    <button class="ptr-card-eg" title="Fill the sentence with this example" @click="useExample(c.id)">
                      “{{ c.example }}”
                    </button>
                  </div>
                </div>
              </div>

              <!-- Confirmation chips: what the machine read. Tap to correct,
                   or just run — approving is the default. Required gate: the
                   safety net that replaces the old four-field form. -->
              <div v-if="study && !studyLoading" class="study-block">
                <div class="study-reading">
                  <button class="study-chip" title="Edit the sentence — re-reads everything" @click="editFromSentence">
                    <span class="study-chip-label">Testing</span>
                    <span class="study-chip-value">{{ study.what }}</span>
                    <span class="study-chip-mark">✎</span>
                  </button>
                  <button
                    v-if="lens !== 'fit'"
                    class="study-chip"
                    title="Pick the audience"
                    @click="openAudiencePicker"
                  >
                    <span class="study-chip-label">Audience</span>
                    <span class="study-chip-value">{{ audienceLabel }}</span>
                    <span class="study-chip-conf" :class="study.audience.confidence">{{ confBadge }}</span>
                  </button>
                  <button v-else class="study-chip is-static" title="Fit ranks every buyer group — there's no one crowd to pick.">
                    <span class="study-chip-label">Audience</span>
                    <span class="study-chip-value">All six buyer groups</span>
                  </button>
                  <button class="study-chip" title="Toggle what the panel is asked" @click="probesOpen = !probesOpen">
                    <span class="study-chip-label">Probing</span>
                    <span class="study-chip-value">{{ probesLabel }}</span>
                    <span class="study-chip-mark" :class="{ open: probesOpen }">▾</span>
                  </button>
                  <button v-if="study.mode === 'product'" class="study-chip" title="Set the price — the affordability step needs it" @click="startPriceEdit">
                    <span class="study-chip-label">Price</span>
                    <span class="study-chip-value" :class="{ 'is-missing': !study.price }">{{ study.price || 'not set' }}</span>
                  </button>
                  <button class="study-chip" title="Switch the lens — re-reads your sentence under it" @click="cycleLens">
                    <span class="study-chip-label">Mode</span>
                    <span class="study-chip-value">{{ study.mode }} · {{ lensLabel }}</span>
                  </button>
                </div>
                <p class="study-note" :class="{ warn: study.audience.confidence === 'thin-data' }">
                  <template v-if="study.audience.confidence === 'thin-data'">Audience is guessed (auto-chosen default) — tap to check it.</template>
                  <template v-else>Audience routed from your sentence.</template>
                </p>

                <div v-if="editingPrice" class="price-edit">
                  <input
                    ref="priceEditor"
                    v-model="priceInput"
                    class="price-edit-input"
                    placeholder="e.g. R50/month"
                    @keyup.enter="commitPrice"
                    @blur="commitPrice"
                  />
                </div>

                <!-- Probes: the sub-questions the panel is asked, toggleable. -->
                <Transition name="probe-pop">
                <div v-if="probesOpen" class="probe-pop">
                  <div v-for="p in study.probes" :key="p.id" class="probe-row">
                    <label class="probe-toggle">
                      <input
                        type="checkbox"
                        :checked="p.active"
                        :disabled="p.base"
                        @change="toggleProbe(p)"
                      />
                      <span>
                        <span class="probe-question">{{ p.question }}</span>
                        <span class="probe-meta">{{ p.base ? 'always asked' : p.confidence }}</span>
                      </span>
                    </label>
                  </div>
                  <div class="probe-add">
                    <input
                      v-model="newProbe"
                      class="probe-add-input"
                      placeholder="Add your own question…"
                      @keyup.enter="addProbe"
                    />
                    <button class="probe-add-btn" @click="addProbe">Add</button>
                  </div>
                </div>
                </Transition>
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
              <p class="pp-hint">
                <template v-if="study">Mode ({{ study.mode }}) is detected automatically from your sentence — the chips above are your chance to correct the reading.</template>
                <template v-else>At the end we read your sentence back as a checkable summary — approve it or correct a chip, then run. Panel is the fast read; the full simulation is an additional, deeper run.</template>
              </p>
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
import { createSession, listSessions, listSegments, readStudy, uploadPoster } from '../../api/panel'
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
  emit('open', {
    mode: 'sim',
    simulationId: s.simulation_id,
    query: s.simulation_requirement || '',
    // Status + project handles let the flow view route a half-built sim back
    // into the build box (resume) instead of opening a blank results room.
    status: s.status,
    projectId: s.project_id,
    graphId: s.graph_id,
  })
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

// ── The study flow: one sentence, picked lens, editable confirmation chips ──
// The four lenses are the old mode cards, but tapping one never opens a form —
// it re-reads the SAME sentence under that lens. The sentence stays the user's
// only input; structure (audience, probes, mode, price) is derived and shown
// back as chips they may correct or approve and run.
const LENS_CARDS = [
  { id: 'land', label: 'How does this land?', blurb: 'The honest first read on what you’re putting out.', example: 'A startup launching a mobile app that lets South Africans invest from R50 a month with no monthly fees, aimed at young professionals in cities who have never invested before.' },
  { id: 'breaks', label: 'What breaks it?', blurb: 'Blockers only. Same run, sharper question.', example: 'Government announces a national permit verification drive: employers must confirm every worker’s papers within 90 days.' },
  { id: 'fit', label: 'Which segment fits best?', blurb: 'Same offer, six buyer groups. See who it lands with.', example: 'A mobile app that lets South Africans invest from R50 a month with no monthly fees.' },
  { id: 'ab', label: 'A/B two versions', blurb: 'Two ways of saying it, one room, side by side.', example: 'A: Start investing from R50 a month — no monthly fees.  B: R50 puts you in the market.', exampleA: 'Start investing from R50 a month — no monthly fees.', exampleB: 'R50 puts you in the market. Stop watching from the side.' },
]

const lens = ref(null)
const abA = ref('')
const abB = ref('')
const lensLabel = computed(() => LENS_CARDS.find(c => c.id === lens.value)?.label || '')

// The confirmed study spec (what the /read endpoint derived). Chips render from
// it and every correction writes straight back into it — the two never drift.
const study = ref(null)
const studyLoading = ref(false)
const probesOpen = ref(false)
const editingPrice = ref(false)
const priceInput = ref('')
const newProbe = ref('')
const crowdSearch = ref('')
const priceEditor = ref(null)
const abAInput = ref(null)
let readTimer = null
let audienceManuallySet = false

// The one sentence to read right now (A/B keeps its two lines separate).
function currentPitch() {
  if (lens.value === 'ab') {
    return [abA.value, abB.value].map(s => s.trim()).filter(Boolean).join('\n\n')
  }
  return composedPitch()
}

function scheduleRead() {
  clearTimeout(readTimer)
  readTimer = setTimeout(runRead, 350)
}

async function runRead() {
  clearTimeout(readTimer)
  if (studyLoading.value) return
  const text = currentPitch()
  if (!text.trim() || !lens.value) return
  studyLoading.value = true
  try {
    const res = await readStudy({ pitch: text, lens: lens.value })
    const spec = res && res.data
    if (spec && spec.what) {
      study.value = spec
      // A crowd the user picked before reading wins over the inferred reading.
      if (audienceManuallySet) {
        study.value.audience.segments = selectedSegments.value.filter(s => s !== 'everyone')
        study.value.audience.confidence = 'strong-data'
        audienceManuallySet = false
      }
    }
  } catch (e) {
    study.value = null
  } finally {
    studyLoading.value = false
  }
}

// Running always goes through the read first — the chips ARE the confirm step,
// and running is the approval.
async function ensureStudy() {
  if (study.value) return study.value
  if (!lens.value) lens.value = 'land'
  await runRead()
  return study.value
}

function onComposerInput() {
  autosizePrompt()
  study.value = null
  probesOpen.value = false
  if (lens.value) scheduleRead()
}

function selectLens(id) {
  // Carry the sentence across the single-composer / A/B switch.
  if (lens.value === 'ab' && id !== 'ab') {
    if (!panelPitch.value.trim() && abA.value.trim()) panelPitch.value = abA.value
  } else if (id === 'ab' && lens.value !== 'ab') {
    if (!abA.value.trim()) abA.value = panelPitch.value
  }
  lens.value = id
  study.value = null
  probesOpen.value = false
  if (id !== 'ab') nextTick(() => panelInput.value?.focus())
  scheduleRead()
}

function useExample(id) {
  const card = LENS_CARDS.find(c => c.id === id)
  if (!card) return
  if (id === 'ab') {
    abA.value = card.exampleA || ''
    abB.value = card.exampleB || ''
  } else {
    panelPitch.value = card.example || ''
  }
  lens.value = id
  study.value = null
  runRead().then(() => {
    if (id !== 'ab') panelInput.value?.focus()
  })
}

function cycleLens() {
  const order = ['land', 'breaks', 'fit', 'ab']
  selectLens(order[(order.indexOf(lens.value) + 1) % order.length])
}

function editFromSentence() {
  study.value = null
  nextTick(() => {
    if (lens.value === 'ab') abAInput.value?.focus()
    else panelInput.value?.focus()
  })
}

// ── Audience picker: the audience chip's editor ────────────────────────────
const filteredSegments = computed(() => {
  const q = crowdSearch.value.trim().toLowerCase()
  if (!q) return segments.value
  return segments.value.filter(s =>
    (s.label || '').toLowerCase().includes(q) ||
    (s.description || '').toLowerCase().includes(q))
})

function openAudiencePicker() {
  if (lens.value === 'fit') return
  const cur = study.value?.audience?.segments || []
  selectedSegments.value = cur.length ? [...cur] : ['everyone']
  crowdSearch.value = ''
  crowdPickerOpen.value = true
}

function applyAudience() {
  const picked = selectedSegments.value.filter(s => s !== 'everyone')
  if (study.value && lens.value !== 'fit') {
    study.value.audience.segments = picked
    study.value.audience.confidence = 'strong-data'
  } else {
    audienceManuallySet = picked.length > 0
  }
  crowdPickerOpen.value = false
}

// ── Chips: labels + editors ───────────────────────────────────────────────
const audienceLabel = computed(() => {
  const segs = study.value?.audience?.segments || []
  if (!segs.length) return 'the default South African mix'
  return segmentsText(segs)
})
const confBadge = computed(() =>
  study.value?.audience?.confidence === 'strong-data' ? 'from sentence' : 'guessed')
const probesLabel = computed(() => {
  const active = (study.value?.probes || []).filter(p => p.active)
  const themed = active.filter(p => !p.base).map(p => p.label)
  return themed.length ? themed.join(' + ') : (active[0]?.label || 'First reaction')
})

function segmentsText(ids) {
  return (ids || []).map(id => segments.value.find(s => s.id === id)?.label || id).join(' + ')
}

function toggleProbe(p) {
  p.active = !p.active
}

function addProbe() {
  const t = newProbe.value.trim()
  if (!t || !study.value) return
  study.value.probes.push({
    id: 'custom_' + Date.now(),
    label: 'Your probe',
    question: t,
    base: false,
    confidence: 'strong-data',
    active: true,
  })
  newProbe.value = ''
}

function startPriceEdit() {
  if (study.value.mode !== 'product') return
  priceInput.value = study.value.price || ''
  editingPrice.value = true
  nextTick(() => priceEditor.value?.focus())
}

function commitPrice() {
  if (!editingPrice.value) return
  editingPrice.value = false
  const v = priceInput.value.trim()
  study.value.price = v || null
}

// ── Build the slot scaffold from the approved spec ────────────────────────
// The runnable seed itself is assembled server-side by pointers.assemble_seed,
// so this client half never repeats (and can't drift from) that template.

// Required-slot values + the confirmed probes, in the exact scaffold shape
// backend/app/services/pointers.py validates (mirror of the old slot forms).
function buildSlots(spec) {
  const l = spec.lens
  const segs = spec.audience.segments || []
  const slots = { probes: spec.probes }
  if (l === 'land' || l === 'breaks') {
    slots.announcement = spec.what || ''
    if (segs.length) slots.audience = segmentsText(segs)
    if (spec.worry) slots.worry = spec.worry
  } else if (l === 'fit') {
    slots.offer = spec.what || ''
    if (spec.price) slots.price = spec.price
  } else {
    slots.version_a = abA.value || ''
    slots.version_b = abB.value || ''
    if (spec.worry) slots.decision = spec.worry
  }
  return slots
}

function tryExample() {
  useExample('land')
  dismissWelcome()
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
// fit ranks six buyer groups — fan-out breadth is not a user setting.
const isFit = computed(() => lens.value === 'fit')
const effectiveSize = computed(() => (isFit.value ? 12 : panelSize.value))
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

// A poster on its own is enough to run — the question is optional. A/B needs
// both versions; every other lens just needs the one sentence.
const canSubmit = computed(() => {
  if (posterBrief.value) return true
  if (lens.value === 'ab') return Boolean(abA.value.trim() && abB.value.trim())
  return Boolean(panelPitch.value.trim() || posterBrief.value)
})

// With a poster attached the box is for the founder's question, not the pitch.
const promptPlaceholder = computed(() => posterBrief.value
  ? "Ask the room something about your poster. e.g. Would you trust this? What would stop you? Leave it blank to just get their reactions."
  : "What do you want to test? Describe a policy or announcement, or a product and its price — the way you'd explain it to someone. e.g. A R99/month prepaid solar lantern subscription for township households, paid via airtime."
)

// Crowd picker (segments + size live behind a modal, off the home view). The
// summary reads the confirmed study spec once the chips are up, else the raw
// picker selection — never both, so they can't drift.
const crowdPickerOpen = ref(false)
const crowdSummary = computed(() => {
  if (isFit.value) return 'All six buyer groups'
  const src = (study.value && lens.value !== 'fit')
    ? (study.value.audience.segments || [])
    : selectedSegments.value
  const sel = src && src.length ? src : ['everyone']
  if (sel.length === 1 && sel[0] === 'everyone') return 'Everyone'
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
// Panel: fast read. Runs through the study spec the user just saw as chips —
// the read IS the confirm step. Mode, audience, price and probes all come from
// that approved spec, never from hidden re-inference.
const submitPanel = async () => {
  if (panelSubmitting.value) return
  const spec = await ensureStudy()
  if (!spec) return
  panelSubmitting.value = true
  try {
    const slots = buildSlots(spec)
    const body = {
      n: effectiveSize.value,
      pointer: spec.lens,
      slots,
      mode: spec.mode,
    }
    // The server assembles the seed from the slots (pointers.assemble_seed is
    // the one implementation of that template). ab is the exception: each
    // version is already a whole pitch, so A rides in as the explicit pitch.
    if (spec.lens === 'ab') body.pitch = slots.version_a
    else if (!LENS_CARDS.some(c => c.id === spec.lens)) body.pitch = composedPitch()
    // The confirmed audience wins; fit ranks all six by design, so no segments.
    if (spec.lens !== 'fit') {
      const segs = spec.audience.segments || []
      if (segs.length) body.segments = segs
    }
    const res = await createSession(body)
    const sessionId = res.data?.session_id
    if (!sessionId) throw new Error('No session id returned')
    // The assembled seed is what the room saw — take it back from the server,
    // never rebuild it here.
    const q = res.data?.pitch || spec.what
    emit('submit', {
      query: q,
      mode: 'panel',
      segments: spec.lens === 'fit' ? null : (spec.audience.segments || []),
      size: effectiveSize.value,
      sessionId,
      pointer: spec.lens,
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

// Direct sim: the deeper, additional run off the same approved sentence. No
// mode toggle — modeIsManual stays false so the backend auto-detects
// policy/product at /prepare (the detected mode is preserved by the prompt).
const submitDirectSim = async () => {
  if (panelSubmitting.value) return
  const spec = await ensureStudy()
  const q = spec ? (spec.what || composedPitch()) : composedPitch()
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
.app-shell {
  display: flex; height: 100vh; overflow: hidden;
  background: var(--paper); color: var(--ink);
  font-family: var(--font-body); font-size: var(--fs-base);
}
.sidebar {
  flex-shrink: 0; width: var(--sidebar-w); height: 100vh;
  background: var(--paper); border-right: 1px solid var(--hairline);
  display: flex; flex-direction: column;
  padding: 22px 16px; gap: 10px; overflow: hidden;
}
.sidebar-brand {
  display: flex; align-items: center; gap: 10px;
  padding: 2px 10px 18px;
  font-family: var(--font-body);
  font-weight: 700; font-size: var(--fs-lg); cursor: pointer; user-select: none;
}
.brand-mark {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: 8px;
  background: linear-gradient(160deg, #25b368 0%, var(--accent) 60%, var(--accent-strong) 100%);
  color: var(--card); font-family: var(--font-body);
  font-weight: 800; font-size: 1.15rem; line-height: 1; flex-shrink: 0;
  box-shadow: 0 2px 6px var(--accent-soft);
}
.brand-word { line-height: 1; letter-spacing: var(--tracking-tight); color: var(--ink); font-weight: 700; }
.brand-strong { color: var(--accent); }
.side-section {
  display: flex; flex-direction: column; gap: 2px;
  padding-bottom: 8px; border-bottom: 1px solid var(--hairline-soft);
}
.side-item {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 9px 10px; background: transparent; border: none;
  border-radius: var(--r-sm); cursor: pointer;
  font-family: var(--font-body); font-size: var(--fs-sm);
  font-weight: 500; color: var(--ink-soft); text-align: left;
  transition: background 0.15s, color 0.15s;
}
.side-item:hover { background: var(--hairline-soft); color: var(--ink); }
.side-item.active { background: var(--accent-pill); color: var(--accent-text); font-weight: 600; }
.side-icon { font-size: 0.95rem; line-height: 1; width: 18px; text-align: center; }
.side-label { flex: 1; }
.side-recents { flex: 1; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 1px; padding-top: 4px; }
.side-recents-head {
  flex: none; padding: 6px 10px; font-family: var(--font-body); font-size: var(--fs-2xs);
  font-weight: 500; letter-spacing: var(--tracking-label);
  text-transform: uppercase; color: var(--muted-soft);
}
.side-recents-empty { flex: none; padding: 6px 10px; font-family: var(--font-body); font-size: var(--fs-xs); color: var(--muted-soft); }
.flow-recent {
  display: block; width: 100%; flex: none; padding: 7px 10px;
  background: transparent; border: none; border-radius: var(--r-sm); cursor: pointer;
  font-family: var(--font-body);
  font-size: var(--fs-sm); color: var(--ink-soft); text-align: left;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: background 0.15s, color 0.15s;
}
.flow-recent:hover { background: var(--hairline-soft); color: var(--ink); }

/* Main column */
.app-main { flex: 1; min-width: 0; height: 100vh; overflow-y: auto; }
.main-inner { max-width: calc(var(--column-w) + 80px); margin: 0 auto; padding: 40px; }
.simple-view { position: relative; min-height: calc(100vh - 80px); }
.simple-center { display: flex; align-items: center; justify-content: center; min-height: calc(100vh - 80px); }
.simple-ask {
  width: 100%; max-width: var(--column-w);
  display: flex; flex-direction: column; gap: 22px;
  margin-top: -40px;
}
.simple-greeting {
  margin: 0 auto; text-align: center; max-width: 26ch;
  font-family: var(--font-body);
  font-size: var(--fs-display); font-weight: 400;
  line-height: var(--lh-tight); letter-spacing: var(--tracking-tight);
  color: var(--ink); text-wrap: balance;
}
.simple-prompt {
  border: 1px solid var(--hairline); border-radius: var(--r-xl); background: var(--card);
  padding: 18px 18px 14px; box-shadow: var(--shadow-card);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.simple-prompt.focused {
  border-color: var(--accent);
  box-shadow: var(--shadow-card), 0 0 0 3px var(--accent-ring);
}
.simple-prompt-input {
  width: 100%; border: none; background: transparent; outline: none; resize: none;
  min-height: 84px; max-height: 240px; overflow-y: auto;
  font-family: var(--font-body);
  font-size: var(--fs-md); line-height: var(--lh-body); color: var(--ink);
}
.simple-prompt-input::placeholder { color: var(--muted-soft); }
.simple-prompt-bar { display: flex; align-items: center; gap: 8px; margin-top: 12px; }

/* ── Select-crowds button (opens the picker modal) ────────────────────────── */
.crowd-btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 7px 14px; border: 1px solid var(--hairline); background: var(--card);
  border-radius: var(--r-pill); cursor: pointer;
  font-family: var(--font-body); font-size: var(--fs-xs);
  font-weight: 500; color: var(--ink-soft);
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.crowd-btn:hover { border-color: var(--accent); color: var(--accent-text); background: var(--accent-pill); }
.crowd-btn-icon { font-size: var(--fs-sm); line-height: 1; color: var(--muted); }
.crowd-btn-summary {
  color: var(--accent-text); background: var(--accent-soft);
  padding: 1px 8px; border-radius: var(--r-pill); font-size: var(--fs-2xs);
  max-width: 14ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
/* The whole pill is the <label>, so the raw input is hidden. */
.poster-file { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
.crowd-btn.busy { opacity: 0.6; cursor: default; }
.poster-note {
  margin: 10px 0 0; font-family: var(--font-body);
  font-size: 0.72rem; color: var(--muted);
}
.poster-note.error { color: var(--danger); }

/* ── Reading a poster: thumbnail + spinner + moving bar + clock ───────────── */
.poster-loading {
  margin-top: 10px; padding: 12px 14px;
  display: flex; gap: 14px; align-items: center;
  border: 1px solid var(--hairline); border-radius: 12px; background: var(--card-sunk);
  font-family: var(--font-body);
}
.poster-thumb {
  width: 46px; height: 60px; object-fit: cover; flex: none;
  border-radius: 6px; border: 1px solid var(--hairline);
}
.poster-loading-body { flex: 1; min-width: 0; }
.poster-loading-top { display: flex; align-items: center; gap: 9px; }
.poster-loading-title { font-size: 0.78rem; font-weight: 600; color: var(--ink-soft); }
.poster-loading-clock { margin-left: auto; font-size: 0.72rem; color: var(--muted); }
.poster-loading-stage { margin-top: 7px; font-size: 0.72rem; color: var(--muted); }

.poster-spinner {
  width: 13px; height: 13px; flex: none;
  border: 2px solid var(--accent-soft);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: poster-spin 0.75s linear infinite;
}
@keyframes poster-spin { to { transform: rotate(360deg); } }

/* Indeterminate bar — the call returns all at once, so it sweeps rather than
   pretending to measure real progress. */
.poster-bar {
  margin-top: 9px; height: 3px; border-radius: 999px;
  background: var(--hairline-soft); overflow: hidden;
}
.poster-bar-fill {
  display: block; width: 38%; height: 100%; border-radius: 999px;
  background: var(--accent);
  animation: poster-sweep 1.5s ease-in-out infinite;
}
@keyframes poster-sweep {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(265%); }
}

.poster-chip {
  width: 18px; height: 24px; object-fit: cover; flex: none;
  border-radius: 4px; border: 1px solid var(--hairline);
}

/* ── Attached poster: the brief lives out of the way, collapsed ───────────── */
.poster-card {
  margin-top: 10px; padding: 10px 14px;
  border: 1px solid var(--hairline); border-radius: 12px; background: var(--card-sunk);
  font-family: var(--font-body); font-size: 0.74rem;
}
.poster-card-head { display: flex; align-items: center; gap: 10px; }
.poster-card-icon { color: var(--accent); }
.poster-card-name {
  font-weight: 600; color: var(--ink-soft);
  max-width: 22ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.poster-card-tag {
  color: var(--accent); background: var(--accent-soft);
  padding: 1px 8px; border-radius: 8px; font-size: 0.68rem;
}
.poster-card-link {
  margin-left: auto; border: none; background: none; cursor: pointer;
  font-family: inherit; font-size: 0.72rem; color: var(--muted);
  text-decoration: underline; text-underline-offset: 2px;
}
.poster-card-link:hover { color: var(--accent); }
.poster-card-x {
  border: none; background: none; cursor: pointer;
  font-size: 1.05rem; line-height: 1; color: var(--muted); padding: 0 2px;
}
.poster-card-x:hover { color: var(--danger); }
.poster-card-brief {
  margin: 10px 0 0; padding-top: 10px; border-top: 1px solid var(--hairline-soft);
  max-height: 260px; overflow-y: auto;
  white-space: pre-wrap; font-size: 0.72rem; line-height: 1.6; color: var(--ink-soft);
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
  background: var(--card); border-radius: 16px; padding: 28px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
}
.ob-card-kicker {
  font-family: var(--font-body); font-size: 11px; font-weight: 700;
  letter-spacing: 0.6px; text-transform: uppercase; color: var(--accent);
}
.ob-card-title { margin: 6px 0 16px; font-size: 20px; font-weight: 700; color: var(--ink); line-height: 1.3; }
.ob-list { margin: 0 0 22px; padding-left: 20px; display: flex; flex-direction: column; gap: 10px; }
.ob-list li { font-size: 14px; line-height: 1.55; color: var(--ink-soft); }
.ob-list b { color: var(--ink); }
.ob-card-actions { display: flex; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
.ob-btn {
  padding: 9px 16px; border-radius: 9px; font-size: 13px; font-weight: 700;
  cursor: pointer; border: 1px solid transparent; transition: background .15s, border-color .15s;
}
.ob-btn.ghost { background: var(--card); border-color: var(--hairline); color: var(--ink-soft); }
.ob-btn.ghost:hover { background: var(--hairline-soft); }
.ob-btn.primary { background: var(--accent); color: var(--card); }
.ob-btn.primary:hover { background: var(--accent-strong); }

.ob-examples { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin: 14px 2px 0; }
.ob-examples-label {
  font-family: var(--font-body); font-size: 11px; font-weight: 700;
  color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px;
}
.ob-example {
  padding: 6px 12px; border-radius: 999px; border: 1px solid var(--hairline); background: var(--card);
  font-size: 12.5px; color: var(--ink-soft); cursor: pointer; transition: border-color .15s, background .15s;
}
.ob-example:hover { border-color: var(--accent); background: var(--accent-pill); color: var(--accent-strong); }

.tour-overlay { position: fixed; inset: 0; z-index: 200; }
.tour-spot {
  position: fixed; border-radius: 10px; pointer-events: none;
  box-shadow: 0 0 0 9999px rgba(15, 23, 42, 0.55);
  outline: 2px solid var(--accent); transition: left .2s, top .2s, width .2s, height .2s;
}
.tour-tip {
  position: fixed; background: var(--card); border-radius: 12px; padding: 16px;
  box-shadow: 0 14px 40px rgba(0, 0, 0, 0.28);
}
.tour-tip-step {
  font-family: var(--font-body); font-size: 10.5px; font-weight: 700;
  color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;
}
.tour-tip-title { font-size: 15px; font-weight: 700; color: var(--ink); margin-bottom: 6px; }
.tour-tip-body { font-size: 13px; line-height: 1.55; color: var(--ink-soft); margin-bottom: 14px; }
.tour-tip-actions { display: flex; justify-content: space-between; gap: 8px; }

.crowd-backdrop {
  position: fixed; inset: 0; z-index: 50;
  background: rgba(0, 0, 0, 0.32);
  display: flex; align-items: center; justify-content: center; padding: 24px;
}
.crowd-modal {
  width: 100%; max-width: 680px; max-height: 84vh;
  display: flex; flex-direction: column;
  background: var(--card); border-radius: 16px; overflow: hidden;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.22);
}
.crowd-modal-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 18px 22px; border-bottom: 1px solid var(--hairline-soft);
}
.crowd-modal-title { font-size: 1.05rem; font-weight: 600; color: var(--ink); }
.crowd-modal-close {
  border: none; background: transparent; cursor: pointer;
  font-size: 1rem; color: var(--muted); line-height: 1; padding: 4px;
}
.crowd-modal-close:hover { color: var(--ink); }
.crowd-modal-body { padding: 20px 22px; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; }
.pp-control-row { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.crowd-modal-foot {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 14px 22px; border-top: 1px solid var(--hairline-soft);
}
.crowd-foot-summary { font-family: var(--font-body); font-size: 0.72rem; color: var(--muted); }
.crowd-done-btn {
  background: var(--accent); color: var(--card); border: none; border-radius: 999px;
  padding: 9px 24px; font-family: var(--font-body);
  font-weight: 700; font-size: 0.8rem; letter-spacing: 0.4px;
  cursor: pointer; transition: background 0.15s;
}
.crowd-done-btn:hover { background: var(--accent-strong); }

/* ── Panel pitch fields — copied from PanelPitchPanel ─────────────────────── */
.pp-field-group { display: flex; flex-direction: column; gap: 10px; }
.pp-field-label {
  font-family: var(--font-body);
  font-size: 0.72rem; font-weight: 700;
  letter-spacing: 0.5px; text-transform: uppercase; color: var(--muted);
}
.pp-segments {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  grid-auto-rows: 1fr; gap: 10px;
}
.pp-segment {
  display: flex; flex-direction: column; gap: 4px;
  height: 100%; min-height: 118px;
  padding: 12px 14px; border: 1px solid var(--hairline); border-radius: 12px;
  background: var(--card); cursor: pointer; text-align: left;
  transition: border-color 0.15s, background 0.15s;
}
.pp-segment:hover { border-color: var(--accent); }
.pp-segment.selected { border-color: var(--accent); background: var(--accent-pill); }
.pp-segment-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.pp-segment-label {
  font-weight: 600; font-size: 0.88rem; color: var(--ink);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.pp-segment-count {
  font-family: var(--font-body); font-size: 0.7rem; font-weight: 700;
  color: var(--accent); background: var(--accent-soft);
  padding: 1px 7px; border-radius: 8px;
}
.pp-segment-desc {
  font-size: 0.73rem; color: var(--muted); line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical;
  overflow: hidden;
}

.pp-controls {
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
}
.pp-control-label {
  font-family: var(--font-body); font-size: 0.72rem;
  color: var(--muted); letter-spacing: 0.5px; text-transform: uppercase;
}
.pp-size-btns { display: flex; gap: 4px; }
.pp-size-btn {
  padding: 5px 14px; border: 1px solid var(--hairline); background: var(--card);
  border-radius: 999px; font-family: var(--font-body);
  font-size: 0.72rem; font-weight: 600; color: var(--muted); cursor: pointer;
  transition: all 0.15s;
}
.pp-size-btn:hover { border-color: var(--accent); color: var(--accent); }
.pp-size-btn:disabled { opacity: 0.45; cursor: not-allowed; background: var(--hairline-soft); }
.pp-size-btn:disabled:hover { border-color: var(--hairline); color: var(--muted); }
.pp-size-btn.active { background: var(--accent); border-color: var(--accent); color: var(--card); }
.pp-fit-note { margin: 0 0 14px; font-size: 0.78rem; line-height: 1.5; color: var(--ink-soft); }
/* Run-speed dropdown — lives in the seed-box bar next to Select crowds */
.speed-dd { position: relative; }
.speed-caret { font-size: 0.6rem; color: var(--muted); transition: transform 0.15s; }
.speed-caret.open { transform: rotate(180deg); }
.speed-menu {
  position: absolute; top: calc(100% + 6px); left: 0; z-index: 30;
  min-width: 240px; background: var(--card); border: 1px solid var(--hairline);
  border-radius: 12px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12);
  padding: 6px; display: flex; flex-direction: column; gap: 2px;
}
.speed-item {
  display: flex; flex-direction: column; gap: 2px; align-items: flex-start;
  padding: 8px 10px; border: none; background: transparent; border-radius: 8px;
  cursor: pointer; text-align: left; transition: background 0.12s;
}
.speed-item:hover { background: var(--hairline-soft); }
.speed-item.active { background: var(--accent-pill); }
.speed-item-top { display: flex; align-items: baseline; gap: 8px; }
.speed-item-name {
  font-family: var(--font-body); font-size: 0.78rem; font-weight: 700; color: var(--ink-soft);
}
.speed-item.active .speed-item-name { color: var(--accent); }
.speed-item-rounds { font-family: var(--font-body); font-size: 0.66rem; color: var(--muted); }
.speed-item-hint { font-size: 0.7rem; color: var(--muted); line-height: 1.35; }

.speed-pop-enter-active, .speed-pop-leave-active { transition: opacity 0.14s ease, transform 0.14s ease; }
.speed-pop-enter-from, .speed-pop-leave-to { opacity: 0; transform: translateY(-4px); }

.pp-actions { margin-left: auto; display: flex; align-items: center; gap: 10px; }
.pp-assemble-btn {
  display: flex; align-items: center; gap: 12px;
  background: var(--accent); color: var(--card); border: none; border-radius: var(--r-pill);
  padding: 12px 26px; font-family: var(--font-body);
  font-weight: 600; font-size: var(--fs-sm); letter-spacing: 0;
  cursor: pointer; transition: background 0.15s;
}
.pp-assemble-btn:hover:not(:disabled) { background: var(--accent-strong); }
.pp-assemble-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* Direct sim — secondary action (the deeper, additional run) */
.pp-sim-btn {
  background: var(--card); color: var(--accent-text); border: 1px solid var(--hairline);
  border-radius: var(--r-pill); padding: 11px 20px;
  font-family: var(--font-body);
  font-weight: 500; font-size: var(--fs-sm); letter-spacing: 0;
  cursor: pointer; transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.pp-sim-btn:hover:not(:disabled) { border-color: var(--accent); }
.pp-sim-btn:hover:not(:disabled) { background: var(--accent-pill); }
.pp-sim-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.pp-hint {
  margin: 4px 0 0; text-align: center;
  font-family: var(--font-body); font-size: var(--fs-xs);
  color: var(--muted-soft); line-height: var(--lh-body);
}

/* ── Mobile burger + off-canvas sidebar ──────────────────────────────────── */
.burger-btn {
  display: none;
  position: fixed; top: 12px; left: 12px; z-index: 96;
  width: 40px; height: 40px; border-radius: 10px;
  background: var(--card); border: 1px solid var(--hairline); cursor: pointer;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  align-items: center; justify-content: center;
}
.burger-lines { display: flex; flex-direction: column; gap: 4px; width: 18px; }
.burger-lines i {
  display: block; height: 2px; border-radius: 2px; background: var(--ink-soft);
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
    background: var(--paper);
  }
  .sidebar.open { transform: translateX(0); }
  /* clear the fixed burger button, which sits at top-left */
  .sidebar-brand { padding-top: 2px; padding-left: 46px; }
  .app-main { width: 100%; }
  .main-inner { padding: 68px 16px 24px; }
  .simple-greeting { font-size: 26px; }
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
  font-family: var(--font-body);
  font-size: 0.62rem; font-weight: 700;
  color: var(--accent); background: var(--accent-soft);
  border-radius: 999px; padding: 1px 7px;
}

/* Profile button — bottom of sidebar */
.side-foot {
  margin-top: auto;
  padding: 12px 0 4px;
  border-top: 1px solid var(--hairline-soft);
}
.profile-item {
  display: flex; align-items: center; gap: 10px;
  width: 100%; padding: 9px 12px;
  background: transparent; border: none; border-radius: 8px;
  cursor: pointer; text-align: left; font: inherit; color: inherit;
  transition: background 0.15s;
}
.profile-item:hover { background: var(--hairline-soft); }
.profile-avatar {
  width: 30px; height: 30px; border-radius: 50%;
  background: linear-gradient(160deg, #25b368 0%, var(--accent) 60%, var(--accent-strong) 100%);
  color: var(--card);
  font-family: var(--font-body);
  font-weight: 700; font-size: 0.78rem;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.profile-body { display: flex; flex-direction: column; min-width: 0; flex: 1; gap: 1px; }
.profile-name {
  font-size: 0.82rem; font-weight: 600; color: var(--ink);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2;
}
.profile-sub {
  font-family: var(--font-body);
  font-size: 0.6rem; color: var(--muted);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.2;
}
.profile-chevron { color: var(--muted-soft); font-size: 0.7rem; flex-shrink: 0; }

/* ── Personas tab ─────────────────────────────────────────────────────── */
.persona-view { display: flex; flex-direction: column; gap: 20px; }
.persona-view .page-head {
  display: flex; align-items: baseline; justify-content: space-between;
}
.persona-view .page-title { font-size: 1.6rem; font-weight: 600; letter-spacing: -0.5px; color: var(--ink); }
.persona-view .page-sub { font-family: var(--font-body); font-size: 0.74rem; color: var(--muted); letter-spacing: 0.4px; }

.persona-filters { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.persona-search {
  flex: 1; min-width: 200px;
  border: 1px solid var(--hairline); border-radius: 8px;
  padding: 9px 14px;
  font-family: var(--font-body);
  font-size: 0.84rem; color: var(--ink);
  background: var(--paper); outline: none;
  transition: border-color 0.15s, background 0.15s;
}
.persona-search:focus { border-color: var(--accent); background: var(--card); }
.persona-filter-chip {
  padding: 6px 14px; border: 1px solid var(--hairline); background: var(--card);
  border-radius: 999px;
  font-family: var(--font-body);
  font-size: 0.7rem; font-weight: 600; color: var(--muted);
  cursor: pointer; transition: all 0.15s;
}
.persona-filter-chip:hover { border-color: var(--accent); color: var(--accent); }
.persona-filter-chip.active { background: var(--accent); border-color: var(--accent); color: var(--card); }
.chip-count { opacity: 0.6; font-size: 0.62rem; margin-left: 2px; }

.persona-loading {
  padding: 40px; text-align: center;
  font-family: var(--font-body); font-size: 0.82rem; color: var(--muted);
}

.persona-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px;
}
.persona-card {
  background: var(--card); border: 1px solid var(--hairline); border-radius: 12px;
  padding: 16px 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  display: flex; gap: 14px; cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
}
.persona-card:hover {
  border-color: var(--accent); box-shadow: 0 4px 14px rgba(0,0,0,0.06); transform: translateY(-1px);
}
.persona-card-avatar {
  width: 40px; height: 40px; border-radius: 50%;
  background: var(--accent-pill); border: 1px solid var(--accent-soft);
  color: var(--accent);
  font-family: var(--font-body);
  font-size: 0.82rem; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.persona-card-info { display: flex; flex-direction: column; gap: 3px; min-width: 0; flex: 1; }
.persona-card-name {
  font-size: 0.88rem; font-weight: 600; color: var(--ink);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.persona-card-arch {
  font-family: var(--font-body);
  font-size: 0.64rem; color: var(--accent); font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.3px;
}
.persona-card-occ {
  font-size: 0.74rem; color: var(--ink-soft);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.persona-card-meta {
  font-family: var(--font-body);
  font-size: 0.6rem; color: var(--muted-soft); margin-top: 2px;
}

@media (max-width: 860px) {
  .persona-grid { grid-template-columns: 1fr; }
}

/* ── The four lenses: pick one, the sentence re-runs under it ─────────────── */
.ptr-section { margin-top: 14px; }
.ptr-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
}
.ptr-card {
  display: flex; flex-direction: column; text-align: left;
  padding: 0; border: 1px solid var(--hairline); border-radius: 12px;
  background: var(--card); overflow: hidden;
  transition: border-color .15s, box-shadow .15s;
}
.ptr-card.active { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-ring); }
.ptr-card-main {
  border: none; background: none; cursor: pointer; padding: 12px 14px 6px;
  display: flex; flex-direction: column; gap: 4px; text-align: left;
}
.ptr-card-main:hover .ptr-card-label { color: var(--accent); }
.ptr-card-label { font-size: 0.9rem; font-weight: 700; color: var(--ink); }
.ptr-card-blurb { font-size: 0.74rem; color: var(--muted); line-height: 1.35; }
.ptr-card-eg {
  border: none; background: var(--paper); cursor: pointer;
  padding: 6px 14px; text-align: left;
  font-size: 0.68rem; line-height: 1.35; color: var(--muted);
  border-top: 1px solid var(--hairline-soft); font-style: italic;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ptr-card-eg:hover { color: var(--accent); background: var(--accent-pill); }
.ptr-card-busy { font-size: 0.68rem; color: var(--accent); font-family: var(--font-body); }

/* A/B needs two lines — the only exception to the one-sentence rule. */
.ab-box { display: flex; flex-direction: column; gap: 10px; }
.ab-box-input {
  width: 100%; border: 1px solid var(--hairline); border-radius: 10px; background: var(--card-sunk);
  padding: 10px 12px; resize: none; min-height: 52px; max-height: 140px;
  font-family: var(--font-body);
  font-size: 1rem; line-height: 1.5; color: var(--ink); outline: none;
}
.ab-box-input:focus { border-color: var(--accent); background: var(--card); }
.ab-box-input::placeholder { color: var(--muted-soft); }

/* ── Confirmation chips: the machine's reading, yours to correct ──────────── */
.study-block { margin-top: 12px; }
.study-reading { display: flex; flex-wrap: wrap; gap: 8px; }
.study-chip {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 7px 12px; border: 1px solid var(--hairline); border-radius: 999px;
  background: var(--card); cursor: pointer; max-width: 100%;
  transition: border-color .15s, box-shadow .15s;
}
.study-chip:hover { border-color: var(--accent); }
.study-chip.is-static { cursor: default; }
.study-chip.is-static:hover { border-color: var(--hairline); }
.study-chip-label {
  font-family: var(--font-body); font-size: 0.64rem;
  font-weight: 700; letter-spacing: 0.4px; text-transform: uppercase;
  color: var(--accent); flex: none;
}
.study-chip-value {
  font-size: 0.78rem; font-weight: 600; color: var(--ink);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 40ch;
}
.study-chip-value.is-missing { color: var(--danger); font-style: italic; }
.study-chip-conf {
  font-family: var(--font-body); font-size: 0.6rem; font-weight: 600;
  padding: 1px 7px; border-radius: 8px; flex: none;
}
.study-chip-conf.strong-data { color: var(--accent); background: var(--accent-soft); }
.study-chip-conf.thin-data { color: var(--warn-text); background: var(--warn-soft); }
.study-chip-mark { color: var(--muted); font-size: 0.72rem; flex: none; }
.study-chip-mark.open { color: var(--accent); }

.study-note { margin: 8px 0 0; font-size: 0.72rem; color: var(--warn-text); }
.study-note.warn { color: var(--warn-text); }

/* Price inline editor — appears under the chips when tapped. */
.price-edit { margin-top: 8px; }
.price-edit-input {
  width: 190px; border: 1px solid var(--accent); border-radius: 8px;
  padding: 6px 10px; font-size: 0.8rem; color: var(--ink); outline: none;
  font-family: var(--font-body);
  box-shadow: 0 0 0 2px var(--accent-ring);
}
.price-edit-input::placeholder { color: var(--muted-soft); }

/* ── Probes popover: toggle, add your own ─────────────────────────────────── */
.probe-pop {
  margin-top: 8px; padding: 10px 12px;
  border: 1px solid var(--hairline); border-radius: 12px; background: var(--card-sunk);
}
.probe-toggle {
  display: flex; align-items: flex-start; gap: 9px; cursor: pointer;
  padding: 5px 0;
}
.probe-toggle input { margin-top: 2px; accent-color: var(--accent); }
.probe-question { font-size: 0.8rem; color: var(--ink); line-height: 1.4; }
.probe-meta {
  font-family: var(--font-body); font-size: 0.6rem;
  color: var(--muted); margin-left: 8px;
}
.probe-add { display: flex; gap: 8px; margin-top: 8px; }
.probe-add-input {
  flex: 1; border: 1px solid var(--hairline); border-radius: 8px;
  padding: 6px 10px; font-size: 0.78rem; color: var(--ink); outline: none;
}
.probe-add-input:focus { border-color: var(--accent); }
.probe-add-btn {
  border: 1px solid var(--accent); background: var(--accent); color: var(--card);
  border-radius: 8px; padding: 0 14px; cursor: pointer;
  font-family: var(--font-body); font-size: 0.72rem; font-weight: 600;
}
.probe-add-btn:hover { background: var(--accent-strong); }
.probe-pop-enter-active { transition: opacity .16s ease, transform .16s ease; }
.probe-pop-leave-active { transition: opacity .12s ease; }
.probe-pop-enter-from { opacity: 0; transform: translateY(-4px); }
.probe-pop-leave-to { opacity: 0; }

/* Audience picker search */
.crowd-search {
  width: 100%; border: 1px solid var(--hairline); border-radius: 8px;
  padding: 7px 10px; font-size: 0.8rem; color: var(--ink); outline: none;
  margin-bottom: 10px; box-sizing: border-box;
}
.crowd-search:focus { border-color: var(--accent); }
.crowd-search::placeholder { color: var(--muted-soft); }
</style>
