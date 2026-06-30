<template>
  <div class="app-shell">
    <!-- Persistent left sidebar — brand, tab switch, Personas/Sims, Recents.
         Full-height app-shell rail shared by both views. -->
    <aside class="sidebar">
      <div class="sidebar-brand" @click="router.push('/')">
        <span class="brand-mark">c</span>
        <span class="brand-word"><span class="brand-strong">crowds</span></span>
      </div>

      <!-- Primary view switch -->
      <nav class="side-section">
        <button
          class="side-item"
          :class="{ active: activeView === 'simple' }"
          @click="activeView = 'simple'"
        >
          <span class="side-icon">✳</span>
          <span class="side-label">Sim</span>
        </button>
        <button
          class="side-item"
          :class="{ active: activeView === 'panel' }"
          @click="activeView = 'panel'"
        >
          <span class="side-icon">◇</span>
          <span class="side-label">Panel Pitch</span>
        </button>
      </nav>

      <!-- Drawer launchers -->
      <nav class="side-section">
        <button
          class="side-item"
          :class="{ active: personaDrawerOpen }"
          @click="personaDrawerOpen = !personaDrawerOpen"
        >
          <span class="side-icon">👥</span>
          <span class="side-label">Personas</span>
          <span v-if="customAgents.length" class="side-badge">{{ customAgents.length }}</span>
        </button>
      </nav>

      <!-- Previous — tab-aware: sims on the Sim tab, panels on Panel Pitch -->
      <div v-if="activeView === 'simple'" class="side-recents">
        <div class="side-recents-head">Previous sims</div>
        <div v-if="recentsLoading" class="side-recents-empty">Loading…</div>
        <div v-else-if="!recents.length" class="side-recents-empty">No previous sims yet.</div>
        <button
          v-for="sim in recents"
          :key="sim.simulation_id"
          class="side-recent"
          :title="sim.simulation_requirement || 'Unnamed simulation'"
          @click="openSim(sim)"
        >{{ sim.simulation_requirement || 'Unnamed simulation' }}</button>
      </div>

      <div v-else class="side-recents">
        <div class="side-recents-head">Previous panels</div>
        <div v-if="panelsLoading" class="side-recents-empty">Loading…</div>
        <div v-else-if="!panels.length" class="side-recents-empty">No previous panels yet.</div>
        <button
          v-for="p in panels"
          :key="p.session_id"
          class="side-recent"
          :title="p.pitch || '(no pitch)'"
          @click="openPanel(p)"
        >{{ p.pitch || '(no pitch)' }}</button>
      </div>
    </aside>

    <!-- Main column — tab content scrolls here, beside the fixed sidebar -->
    <main class="app-main">
      <div class="main-inner">

      <!-- Simple view — a clean, Claude-style centered prompt box. Personas
           live in a collapsible burger drawer on the left, grouped into
           categories. Closed by default so the prompt is the focus; reuses the
           existing segment/persona picker state and startSimulation flow. -->
      <div v-if="activeView === 'simple'" class="simple-view" :class="{ 'drawer-open': personaDrawerOpen }">
        <!-- Scrim — click-away to close on small screens -->
        <div v-if="personaDrawerOpen" class="persona-scrim" @click="personaDrawerOpen = false"></div>

        <!-- Persona drawer — personas grouped by category -->
        <aside class="persona-drawer" :class="{ open: personaDrawerOpen }">
          <header class="drawer-head">
            <h2>Personas</h2>
            <button class="drawer-close" @click="personaDrawerOpen = false" aria-label="Close">×</button>
          </header>

          <input
            v-model="castSearch"
            class="drawer-search"
            type="text"
            placeholder="Search personas…"
          />

          <div class="drawer-body">
            <div v-if="segmentsLoading || libraryLoading" class="drawer-empty">Loading…</div>
            <div v-else-if="!personaGroups.length" class="drawer-empty">No personas available.</div>

            <!-- One accordion section per category. Each lists its segments;
                 a segment row seats every persona in that segment with one
                 click, and expands to reveal individual personas. -->
            <section
              v-for="grp in personaGroups"
              :key="grp.id"
              class="drawer-group"
            >
              <button class="group-header" @click="toggleGroup(grp.id)" :aria-expanded="openGroups.has(grp.id)">
                <span class="group-caret" :class="{ open: openGroups.has(grp.id) }">▸</span>
                <span class="group-name">{{ grp.label }}</span>
                <span class="group-count">{{ grp.total }}</span>
              </button>

              <div v-show="openGroups.has(grp.id)" class="group-segments">
                <div v-for="seg in grp.segments" :key="seg.id" class="seg-block">
                  <button
                    class="seg-row"
                    :class="{ on: segmentState(seg) === 'full', partial: segmentState(seg) === 'partial' }"
                    :disabled="seg.count === 0"
                    :title="seg.description"
                    @click="toggleSegment(seg)"
                  >
                    <span class="seg-check">
                      <svg v-if="segmentState(seg) !== 'none'" viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="3.5">
                        <polyline points="20 6 9 17 4 12"></polyline>
                      </svg>
                    </span>
                    <span class="seg-label">{{ seg.label }}</span>
                    <span class="seg-count">{{ pickedInSegment(seg) }}/{{ seg.count }}</span>
                    <span
                      class="seg-expand"
                      :class="{ open: openSegments.has(seg.id) }"
                      @click.stop="toggleSegmentExpand(seg)"
                      :title="openSegments.has(seg.id) ? 'Hide people' : 'Show people'"
                    >▾</span>
                  </button>

                  <!-- Individual personas within this segment -->
                  <div v-show="openSegments.has(seg.id)" class="seg-people">
                    <button
                      v-for="p in personasInSegment(seg)"
                      :key="personaIdOf(p)"
                      type="button"
                      class="person-row"
                      :class="{ on: pickedIds.has(personaIdOf(p)) }"
                      :title="p.persona || ''"
                      @click="onPersonaClick(p, 0, $event)"
                    >
                      <span class="person-avatar">{{ (p.name || '?').slice(0, 1).toUpperCase() }}</span>
                      <span class="person-body">
                        <span class="person-name">{{ p.name || 'Unnamed' }}</span>
                        <span class="person-arch">{{ (p.actor_archetype || 'unknown').replace(/_/g, ' ') }}</span>
                      </span>
                    </button>
                    <div v-if="!personasInSegment(seg).length" class="seg-people-empty">No personas in this group.</div>
                  </div>
                </div>
              </div>
            </section>
          </div>

          <footer class="drawer-foot">
            <button class="drawer-clear" :disabled="!pickedIds.size" @click="clearPicked">Clear</button>
            <button class="drawer-add" :disabled="!pickedIds.size" @click="addPickedToRoster">
              Add {{ pickedIds.size }} to roster
            </button>
          </footer>
        </aside>

        <!-- Center — one prompt box, Claude-style. Vertically centered, with a
             greeting headline; mode toggle and send button live inside the box. -->
        <div class="simple-center">
          <div class="simple-ask">
            <h1 class="simple-greeting">{{ pitchCopy.modeHint }}</h1>
            <div class="simple-prompt">
              <textarea
                v-model="formData.simulationRequirement"
                class="simple-prompt-input"
                :placeholder="pitchCopy.seedPlaceholder"
                :disabled="loading || seedLoading"
                @keydown.enter.exact.prevent="startSimulation"
              ></textarea>
              <div class="simple-prompt-bar">
                <div class="simple-modes">
                  <button class="simple-mode" :class="{ active: mode === 'policy' }" :disabled="loading || seedLoading" @click="selectMode('policy')">Policy</button>
                  <button class="simple-mode" :class="{ active: mode === 'product' }" :disabled="loading || seedLoading" @click="selectMode('product')">Product</button>
                  <!-- Ground in web research — searches SA news for the typed query
                       and rewrites it into a structured briefing, in place. -->
                  <button
                    class="simple-ground"
                    :class="{ active: seedSources.length > 0 }"
                    :disabled="!formData.simulationRequirement.trim() || seedLoading || loading"
                    @click="handleGenerateSeed"
                    :title="!formData.simulationRequirement.trim() ? 'Type your query first' : 'Search the web and expand into a briefing'"
                  >
                    <span v-if="seedLoading">🔍 Researching…</span>
                    <span v-else-if="seedSources.length">✓ Grounded</span>
                    <span v-else>🌐 Ground in web research</span>
                  </button>
                </div>
                <button class="simple-send" @click="startSimulation" :disabled="!canSubmit || loading" :title="loading ? 'Initializing…' : 'Start Engine'">
                  <span v-if="loading">…</span>
                  <span v-else>↑</span>
                </button>
              </div>
            </div>

            <!-- Web-research feedback: error or source list, below the box -->
            <div v-if="seedError" class="simple-ground-error">{{ seedError }}</div>
            <div v-else-if="seedSources.length" class="simple-ground-sources">
              Grounded in {{ seedSources.length }} source{{ seedSources.length !== 1 ? 's' : '' }}:
              <a v-for="src in seedSources" :key="src.url" :href="src.url" target="_blank">{{ src.title || src.url }}</a>
            </div>

            <!-- Cast step — who's in the sim. Two choices: an auto-generated
                 SA population (default) or a hand-picked roster. -->
            <div class="cast-step">
              <div class="cast-step-label">Who's in the sim?</div>
              <div class="cast-choices">
                <button
                  class="cast-choice"
                  :class="{ active: castMode === 'auto' }"
                  :disabled="loading || seedLoading"
                  @click="selectCastMode('auto')"
                >
                  <span class="cast-choice-title">Auto-generate a population</span>
                  <span class="cast-choice-sub">A synthetic SA population built from your seed</span>
                </button>
                <button
                  class="cast-choice"
                  :class="{ active: castMode === 'custom' }"
                  :disabled="loading || seedLoading"
                  @click="selectCastMode('custom')"
                >
                  <span class="cast-choice-title">Pick specific personas</span>
                  <span class="cast-choice-sub">Choose people from the persona library</span>
                </button>
              </div>

              <!-- Custom roster detail: chosen personas + only/augment toggle -->
              <div v-if="castMode === 'custom'" class="cast-custom">
                <div class="cast-custom-head">
                  <span v-if="customAgents.length">
                    {{ customAgents.length }} persona{{ customAgents.length !== 1 ? 's' : '' }} chosen
                  </span>
                  <span v-else class="cast-custom-empty">No personas chosen yet</span>
                  <button class="simple-roster-link" @click="personaDrawerOpen = true">
                    {{ customAgents.length ? 'edit' : 'choose personas' }}
                  </button>
                </div>

                <div v-if="customAgents.length" class="cast-chips">
                  <span v-for="a in customAgents" :key="a.name" class="cast-chip">
                    {{ a.name }}
                    <button class="cast-chip-x" title="Remove" @click="removeFromRoster(a)">×</button>
                  </span>
                </div>

                <div v-if="customAgents.length" class="cast-scope">
                  <button
                    class="cast-scope-opt"
                    :class="{ active: customAgentsOnly }"
                    @click="customAgentsOnly = true"
                  >Use only these</button>
                  <button
                    class="cast-scope-opt"
                    :class="{ active: !customAgentsOnly }"
                    @click="customAgentsOnly = false"
                  >Add to auto-population</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="activeView === 'panel'" class="panel-pitch-view">
        <PanelPitchPanel :key="panelKey" />
      </div>

      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import PanelPitchPanel from '../components/PanelPitchPanel.vue'
import { generateSeedFromWeb, listPersonas, getPersona } from '../api/research'
import { listSegments, listSessions } from '../api/panel'
import { getSimulationHistory } from '../api/simulation'


const router = useRouter()

const activeView = ref('simple')

// Previous sims — listed in the sidebar on the Sim tab; click to open one.
const recents = ref([])
const recentsLoading = ref(false)
const loadRecents = async () => {
  recentsLoading.value = true
  try {
    const res = await getSimulationHistory(20)
    recents.value = res.data || []
  } catch (e) {
    console.error('Failed to load recent sims:', e)
  } finally {
    recentsLoading.value = false
  }
}
const openSim = (sim) => {
  router.push({ name: 'Simulation', params: { simulationId: sim.simulation_id } })
}

// Previous panels — listed in the sidebar on the Panel Pitch tab. Clicking one
// points PanelPitchPanel's restore key at that session and remounts it (the
// panel reads localStorage['panelPitch.activeSession'] on mount).
const PANEL_ACTIVE_KEY = 'panelPitch.activeSession'
const panels = ref([])
const panelsLoading = ref(false)
const panelKey = ref(0)
const loadPanels = async () => {
  panelsLoading.value = true
  try {
    const res = await listSessions()
    panels.value = res.data.sessions || []
  } catch (e) {
    console.error('Failed to load previous panels:', e)
  } finally {
    panelsLoading.value = false
  }
}
const openPanel = (p) => {
  localStorage.setItem(PANEL_ACTIVE_KEY, p.session_id)
  panelKey.value++   // force PanelPitchPanel to remount and restore this session
}

const onAddToRoster = (personas) => {
  const existing = new Set(customAgents.value.map(a => (a.name || '').toLowerCase()))
  const fresh = personas.filter(p => p && p.name && !existing.has(p.name.toLowerCase()))
  if (fresh.length === 0) return
  customAgents.value = [...customAgents.value, ...fresh]
  customAgentsEnabled.value = true
  // Adding anyone implies a custom cast; keep the inline step in sync.
  if (castMode.value !== 'custom') {
    castMode.value = 'custom'
    customAgentsOnly.value = true
  }
}

// Left-column persona picker — choose the sim cast from the library directly.
const libraryPersonas = ref([])
const libraryLoading = ref(false)
const pickedIds = ref(new Set())
const personaIdOf = (p) => p.id ?? p.persona_id ?? p.name

// Panel segments — same definitions the Panel Pitch tab uses, server-side.
// Server returns `members: [persona_id, …]` for each segment so the picker
// can bulk-pick without re-implementing predicates. Library persona IDs
// are stable hex hashes; cache personas use the filename hash.
const panelSegments = ref([])
const segmentsLoading = ref(false)
const loadSegments = async () => {
  if (panelSegments.value.length || segmentsLoading.value) return
  segmentsLoading.value = true
  try {
    const res = await listSegments()
    const data = res.data || res
    panelSegments.value = data.segments || data?.data?.segments || []
  } catch (e) {
    console.error('Failed to load panel segments:', e)
  } finally {
    segmentsLoading.value = false
  }
}

// Drawer search box. Kept separate from the global `pickedIds` so typing in
// the search box doesn't blow away the selection.
const castSearch = ref('')

const filteredLibrary = computed(() => {
  const q = castSearch.value.trim().toLowerCase()
  return libraryPersonas.value.filter((p) => {
    if (!q) return true
    return (
      (p.name || '').toLowerCase().includes(q) ||
      (p.occupation || '').toLowerCase().includes(q) ||
      (p.actor_archetype || '').toLowerCase().includes(q)
    )
  })
})

// Shift-range anchor — the last index that received a click. Declared BEFORE
// the watch below (and rangePickTo) that reference it; in <script setup> a
// const is in the temporal dead zone until this line, so a use above here
// throws "Cannot access before initialization" and breaks the whole component.
const lastClickedIdx = ref(-1)

// Drop the shift-range anchor whenever the visible slice changes, so a
// stale anchor can't leap across a re-filtered grid.
watch(filteredLibrary, () => { lastClickedIdx.value = -1 })

const loadLibrary = async () => {
  if (libraryPersonas.value.length || libraryLoading.value) return
  libraryLoading.value = true
  try {
    const res = await listPersonas()
    libraryPersonas.value = (res.personas || []).map(p => ({
      ...p,
      actor_archetype: p.actor_archetype || p.archetype,
    }))
  } catch (e) {
    console.error('Failed to load persona library:', e)
  } finally {
    libraryLoading.value = false
  }
}

const togglePicked = (p) => {
  const id = personaIdOf(p)
  const next = new Set(pickedIds.value)
  next.has(id) ? next.delete(id) : next.add(id)
  pickedIds.value = next
}

// (Plain-click toggle, Ctrl/Cmd-add, and Shift-range are all handled by the
// single onPersonaClick handler below — no separate addPicked/rangePickTo.)

// Segment helpers — driven by the server's panel_service.SEGMENTS list
// (label / description / count / members). A segment is `full` when every
// member is in pickedIds, `partial` when at least one is, else `none`.
// Click toggles: full → remove all members, otherwise → add all.
const pickedInSegment = (seg) => {
  if (!seg || !seg.members) return 0
  let n = 0
  for (const m of seg.members) if (pickedIds.value.has(m)) n++
  return n
}
const segmentState = (seg) => {
  if (!seg || !seg.members || seg.members.length === 0) return 'none'
  const picked = pickedInSegment(seg)
  if (picked === 0) return 'none'
  if (picked === seg.members.length) return 'full'
  return 'partial'
}
const toggleSegment = (seg) => {
  if (!seg || !seg.members || seg.members.length === 0) return
  const state = segmentState(seg)
  const next = new Set(pickedIds.value)
  if (state === 'full') {
    for (const m of seg.members) next.delete(m)
  } else {
    for (const m of seg.members) next.add(m)
  }
  pickedIds.value = next
}

// ── Persona drawer (burger nav) — personas organised into categories ───────
// The burger drawer groups the flat panel segments into a handful of
// human-readable categories. The mapping lives on the client (the segment
// ids are stable); any segment we don't explicitly place falls into "Other"
// so a new backend segment still shows up instead of vanishing.
const personaDrawerOpen = ref(false)
const openGroups = ref(new Set())     // expanded category sections
const openSegments = ref(new Set())   // segments expanded to show people

const GROUP_DEFS = [
  { id: 'everyone', label: 'Everyone', segs: ['everyone'] },
  { id: 'employment', label: 'Work & income', segs: ['employed', 'unemployed', 'youth', 'small_business', 'informal_traders', 'grant_recipients'] },
  { id: 'education', label: 'Education', segs: ['learners', 'guardians', 'gogo_guardians', 'educators'] },
  { id: 'fees', label: 'School fees', segs: ['fee_paying', 'no_fee_school'] },
]

// Build the ordered category list from whatever segments the server actually
// returned. Empty categories are dropped; unplaced segments collect in "Other".
const personaGroups = computed(() => {
  const byId = {}
  for (const seg of panelSegments.value) byId[seg.id] = seg
  const placed = new Set()
  const groups = []
  for (const def of GROUP_DEFS) {
    const segments = def.segs.map(id => byId[id]).filter(Boolean)
    segments.forEach(s => placed.add(s.id))
    if (segments.length) {
      groups.push({ ...def, segments, total: segments.reduce((n, s) => n + (s.count || 0), 0) })
    }
  }
  const leftovers = panelSegments.value.filter(s => !placed.has(s.id))
  if (leftovers.length) {
    groups.push({ id: 'other', label: 'Other', segments: leftovers, total: leftovers.reduce((n, s) => n + (s.count || 0), 0) })
  }
  return groups
})

const toggleGroup = (id) => {
  const next = new Set(openGroups.value)
  next.has(id) ? next.delete(id) : next.add(id)
  openGroups.value = next
}

const toggleSegmentExpand = (seg) => {
  const next = new Set(openSegments.value)
  next.has(seg.id) ? next.delete(seg.id) : next.add(seg.id)
  openSegments.value = next
}

// Resolve a segment's member ids to full persona records, honouring the
// current search box so the people list stays in sync with the filter.
const personasInSegment = (seg) => {
  if (!seg || !seg.members) return []
  const members = new Set(seg.members)
  return filteredLibrary.value.filter(p => members.has(personaIdOf(p)))
}

// Open the first category by default so the drawer isn't a wall of collapsed
// rows the first time it's opened.
watch(personaDrawerOpen, (open) => {
  if (open && openGroups.value.size === 0 && personaGroups.value.length) {
    openGroups.value = new Set([personaGroups.value[0].id])
  }
})

// Persona-grid multi-select. Mirrors the file-manager pattern:
//   plain click   → toggle (add if not picked, remove if picked)
//   Cmd/Ctrl+click → add without toggling off (a "select more" gesture)
//   Shift+click   → range select from the last clicked persona through the
//                   current one across the *visible* (filtered) grid
// (lastClickedIdx is declared above, before the watch that resets it.)
const onPersonaClick = (p, idx, ev) => {
  // Defensive: $event should always be the MouseEvent here, but fall back
  // to a plain toggle if it ever isn't (e.g. a programmatic invocation).
  const shift = !!(ev && ev.shiftKey)
  const accel = !!(ev && (ev.metaKey || ev.ctrlKey))
  if (shift && lastClickedIdx.value >= 0 && lastClickedIdx.value < filteredLibrary.value.length) {
    const [from, to] = [Math.min(lastClickedIdx.value, idx), Math.max(lastClickedIdx.value, idx)]
    const next = new Set(pickedIds.value)
    for (let i = from; i <= to; i++) next.add(personaIdOf(filteredLibrary.value[i]))
    pickedIds.value = next
    lastClickedIdx.value = idx
    return
  }
  if (accel) {
    const id = personaIdOf(p)
    const next = new Set(pickedIds.value)
    next.add(id)
    pickedIds.value = next
    lastClickedIdx.value = idx
    return
  }
  // Plain click — toggle the persona and move the anchor for any follow-up
  // shift-click range.
  togglePicked(p)
  lastClickedIdx.value = idx
}

const clearPicked = () => {
  pickedIds.value = new Set()
}

const addPickedToRoster = async () => {
  const existingNames = new Set(customAgents.value.map(a => (a.name || '').toLowerCase()))
  const added = []
  for (const id of pickedIds.value) {
    const meta = libraryPersonas.value.find(p => personaIdOf(p) === id)
    if (!meta || existingNames.has((meta.name || '').toLowerCase())) continue
    let full = meta
    try {
      const res = await getPersona(id)
      if (res.success && res.persona) {
        full = { ...res.persona, actor_archetype: res.persona.actor_archetype || res.persona.archetype }
      }
    } catch (e) {
      console.warn('Falling back to metadata for persona', id, e)
    }
    added.push(full)
  }
  if (added.length) onAddToRoster(added)   // reuse the existing roster merge
  pickedIds.value = new Set()
}

const formData = ref({ simulationRequirement: '' })
const files = ref([])
const loading = ref(false)

// Web seed generation
const seedLoading = ref(false)
const seedError = ref('')
const seedSources = ref([])
const customAgentsEnabled = ref(false)
const customAgents = ref([])
const customAgentsOnly = ref(false)

// ── Cast step ────────────────────────────────────────────────────────────
// In-flow choice of who's in the sim, sitting under the seed box:
//   'auto'   → synthetic SA population generated from the seed (the default).
//   'custom' → a hand-picked roster; customAgentsOnly decides whether those
//              people replace the population (default) or augment it.
// castMode drives customAgentsEnabled so startSimulation needs no extra logic.
const castMode = ref('auto')
const selectCastMode = (m) => {
  castMode.value = m
  customAgentsEnabled.value = (m === 'custom')
  if (m === 'custom') {
    customAgentsOnly.value = true          // "only these" is the default
    personaDrawerOpen.value = true         // open the picker so the user can choose
  }
}
const removeFromRoster = (agent) => {
  customAgents.value = customAgents.value.filter(a => a !== agent)
  if (!customAgents.value.length) {        // emptied the roster → back to auto
    castMode.value = 'auto'
    customAgentsEnabled.value = false
  }
}

// Simulation mode: 'policy' (citizens vs a policy) or 'product' (a SA market vs a product idea)
const mode = ref('policy')
// Whether the user actively chose the mode. Until they touch the toggle, the backend
// auto-detects mode from the seed (an untouched toggle no longer silently means policy).
const modeTouched = ref(false)
const selectMode = (m) => { mode.value = m; modeTouched.value = true }

// Mode-driven pitch + input copy. Policy strings are the originals, so the
// default view is unchanged.
const pitchCopy = computed(() => {
  if (mode.value === 'product') {
    return {
      tag: 'PRODUCT WIND TUNNEL',
      title: 'Stress-test a product idea<br />against a South African market.',
      bullet3: 'Pause and test a price, feature, or pitch change. Compare reactions.',
      modeHint: 'How would a SA market react to your product idea?',
      seedHeader: 'Product Idea',
      seedPlaceholder: 'Describe the product idea, pitch, or positioning you want to stress-test. What is it? Who is it for? What problem does it solve?'
    }
  }
  return {
    tag: 'POLICY WIND TUNNEL',
    title: 'Test events on <span class="pitch-accent">digital agents</span><br />before they happen to real people.',
    bullet3: 'Pause and test a policy announcement. Compare trajectories.',
    modeHint: 'How would the public react to your policy or announcement?',
    seedHeader: 'Seed Message',
    seedPlaceholder: 'Describe the policy, event, or scenario you want to simulate. What are you testing? Who is the audience?'
  }
})

onMounted(() => {
  // Simple view is the default and needs the picker data up front.
  loadLibrary()
  loadSegments()
  loadRecents()
})

// Load the previous-panels list the first time the Panel Pitch tab is opened.
watch(activeView, (v) => {
  if (v === 'panel' && !panels.value.length) loadPanels()
})

const canSubmit = computed(() => {
  const hasSeed = formData.value.simulationRequirement.trim() !== ''
  return hasSeed
})

const handleGenerateSeed = async () => {
  const query = formData.value.simulationRequirement.trim()
  if (!query || seedLoading.value) return
  seedLoading.value = true
  seedError.value = ''
  seedSources.value = []

  try {
    // Pass the user's natural-language query as the topic; backend infers + expands.
    const res = await generateSeedFromWeb({ topic: query, mode: mode.value })
    if (res.success && res.seed_text) {
      formData.value.simulationRequirement = res.seed_text
      seedSources.value = res.sources || []
    } else {
      seedError.value = res.error || 'Generation returned no content'
    }
  } catch (e) {
    seedError.value = e.message || 'Network or API error — check Firecrawl/Serper keys'
  } finally {
    seedLoading.value = false
  }
}

const startSimulation = async () => {
  if (!canSubmit.value || loading.value) return
  loading.value = true

  // Deep research runs later, during Step 2 (Prepare), where the graph entity
  // types are known. Just hand the document + requirement to the Process page.
  import('../store/pendingUpload.js').then(({ setPendingUpload }) => {
    setPendingUpload(
      files.value,
      formData.value.simulationRequirement,
      customAgentsEnabled.value ? customAgents.value : [],
      customAgentsEnabled.value,
      customAgentsEnabled.value && customAgentsOnly.value,
      mode.value,
      modeTouched.value
    )
    router.push({ name: 'Process', params: { projectId: 'new' } })
  })

  loading.value = false
}
</script>

<style scoped>
/* Nav brand — green "f" tile mark (matches the browser favicon) + wordmark.
   Whole lockup is clickable → home, with a subtle hover lift. */
.sidebar-brand:hover .brand-mark {
  box-shadow: 0 3px 10px rgba(30, 158, 90, 0.35);
  transform: translateY(-1px);
}
.brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  /* soft vertical depth instead of a flat fill */
  background: linear-gradient(160deg, #25b368 0%, #1E9E5A 60%, #178048 100%);
  color: #fff;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 1.15rem;
  line-height: 1;
  flex-shrink: 0;
  box-shadow: 0 2px 6px rgba(30, 158, 90, 0.28);
  transition: box-shadow 0.18s ease, transform 0.18s ease;
}
/* Tighter, two-tone wordmark so it reads as a mark, not flat text */
.brand-word {
  line-height: 1;
  letter-spacing: -0.3px;
  color: #6b6b6b;          /* "sandbox" recedes */
  font-weight: 700;
}
.brand-strong { color: #1E9E5A; }   /* "fub" carries the accent */

/* Panel Pitch view — fills the main column beside the sidebar */
.panel-pitch-view {
  margin-top: 0;
}

/* ── App shell — full-height left sidebar + scrollable main column ───────── */
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* Left sidebar — brand, view switch, Personas/Sims, Recents */
.sidebar {
  flex-shrink: 0;
  width: 256px;
  height: 100vh;
  background: #FAFAFA;
  border-right: 1px solid #E8E8E8;
  display: flex;
  flex-direction: column;
  padding: 16px 12px;
  gap: 8px;
  overflow: hidden;
}
.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px 12px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 1.15rem;
  cursor: pointer;
  user-select: none;
}

.side-section {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-bottom: 8px;
  border-bottom: 1px solid #ECECEC;
}
.side-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 12px;
  background: transparent;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.82rem;
  font-weight: 600;
  color: #555;
  text-align: left;
  transition: background 0.15s, color 0.15s;
}
.side-item:hover { background: #F0F0F0; color: #1a1a1a; }
.side-item.active { background: #F0FAF4; color: #1E9E5A; }
.side-icon { font-size: 0.95rem; line-height: 1; width: 18px; text-align: center; }
.side-label { flex: 1; }
.side-badge {
  font-size: 0.65rem;
  font-weight: 700;
  background: #1E9E5A;
  color: #fff;
  border-radius: 999px;
  padding: 1px 7px;
}

/* Recents — scrollable list of recent sims */
.side-recents {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding-top: 4px;
}
.side-recents-head {
  padding: 6px 12px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.66rem;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: #aaa;
}
.side-recents-empty {
  padding: 6px 12px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  color: #bbb;
}
.side-recent {
  display: block;
  width: 100%;
  padding: 7px 12px;
  background: transparent;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  font-size: 0.8rem;
  color: #555;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: background 0.15s, color 0.15s;
}
.side-recent:hover { background: #F0F0F0; color: #1a1a1a; }

/* Main column — scrolls independently of the sidebar */
.app-main {
  flex: 1;
  min-width: 0;
  height: 100vh;
  overflow-y: auto;
}
.main-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 40px;
}

/* ── Simple view ─────────────────────────────────────────────────────────
   A clean, centered prompt box. Personas live in a collapsible burger drawer
   on the left, grouped into categories. Closed by default, so the prompt is
   the focus. Drives the existing roster + startSimulation flow. */
.simple-view {
  position: relative;
  min-height: calc(100vh - 80px);
}

/* Scrim behind the drawer (mobile/overlay mode) */
.persona-scrim {
  position: fixed;
  inset: 0 0 0 256px;
  background: rgba(0,0,0,0.18);
  z-index: 35;
}

/* Persona drawer — slides out beside the sidebar. Closed: fully off-screen
   left (translateX(-100%) on a left:0 box). Open: nudged right to clear the
   256px sidebar so it sits beside it, not over it. */
.persona-drawer {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  width: 340px;
  max-width: 88vw;
  z-index: 40;
  background: #fff;
  border-right: 1px solid #E5E5E5;
  box-shadow: 2px 0 20px rgba(0,0,0,0.06);
  display: flex;
  flex-direction: column;
  transform: translateX(-100%);
  transition: transform 0.22s ease;
}
.persona-drawer.open { transform: translateX(256px); }
.drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px 12px;
  border-bottom: 1px solid #EEE;
}
.drawer-head h2 {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 600;
  color: #000;
}
.drawer-close {
  background: none;
  border: none;
  font-size: 1.5rem;
  line-height: 1;
  color: #999;
  cursor: pointer;
  padding: 0 4px;
}
.drawer-close:hover { color: #000; }
.drawer-search {
  margin: 12px 20px;
  border: 1px solid #DDD;
  border-radius: 8px;
  padding: 9px 12px;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  font-size: 0.85rem;
  background: #FAFAFA;
  outline: none;
}
.drawer-search:focus { border-color: #1E9E5A; background: #fff; }
.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 4px 12px 12px;
}
.drawer-empty {
  padding: 24px;
  text-align: center;
  color: #999;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem;
}

/* Category accordion */
.drawer-group { border-bottom: 1px solid #F0F0F0; }
.group-header {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 8px;
  background: none;
  border: none;
  cursor: pointer;
  text-align: left;
}
.group-header:hover { background: #FAFAFA; }
.group-caret {
  color: #1E9E5A;
  font-size: 0.7rem;
  transition: transform 0.18s;
}
.group-caret.open { transform: rotate(90deg); }
.group-name {
  flex: 1;
  font-weight: 600;
  font-size: 0.9rem;
  color: #1a1a1a;
}
.group-count {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.66rem;
  font-weight: 700;
  color: #1E9E5A;
  background: rgba(30,158,90,0.1);
  border-radius: 999px;
  padding: 2px 8px;
}
.group-segments {
  padding: 2px 0 8px 18px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* Segment row inside a category */
.seg-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 7px 8px;
  background: none;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
}
.seg-row:hover:not(:disabled) { background: #F4FBF7; }
.seg-row:disabled { opacity: 0.4; cursor: not-allowed; }
.seg-check {
  width: 17px;
  height: 17px;
  flex-shrink: 0;
  border: 1.5px solid #CCC;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: #fff;
}
.seg-row.on .seg-check { background: #1E9E5A; border-color: #1E9E5A; }
.seg-row.partial .seg-check { background: rgba(30,158,90,0.5); border-color: #1E9E5A; }
.seg-label {
  flex: 1;
  font-size: 0.84rem;
  color: #333;
}
.seg-count {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.64rem;
  color: #999;
}
.seg-expand {
  font-size: 0.7rem;
  color: #BBB;
  padding: 2px 4px;
  transition: transform 0.18s, color 0.15s;
}
.seg-expand:hover { color: #1E9E5A; }
.seg-expand.open { transform: rotate(180deg); color: #1E9E5A; }

/* Individual people under a segment */
.seg-people {
  padding: 2px 0 6px 26px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.seg-people-empty {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.68rem;
  color: #BBB;
  padding: 4px 8px;
}
.person-row {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 5px 8px;
  background: none;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
}
.person-row:hover { background: #FAFAFA; }
.person-row.on { background: #F0FAF4; border-color: rgba(30,158,90,0.4); }
.person-avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #F0FAF4;
  border: 1px solid rgba(30,158,90,0.3);
  color: #1E9E5A;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.66rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.person-body { display: flex; flex-direction: column; min-width: 0; }
.person-name {
  font-weight: 600;
  font-size: 0.78rem;
  color: #1a1a1a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.person-arch {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.58rem;
  color: #888;
}

/* Drawer footer actions */
.drawer-foot {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid #EEE;
}
.drawer-clear {
  background: transparent;
  border: 1px solid #DDD;
  border-radius: 8px;
  padding: 9px 14px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.74rem;
  color: #666;
  cursor: pointer;
}
.drawer-clear:hover:not(:disabled) { border-color: #C0392B; color: #C0392B; }
.drawer-clear:disabled { opacity: 0.4; cursor: not-allowed; }
.drawer-add {
  flex: 1;
  background: #1E9E5A;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 9px 14px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.76rem;
  font-weight: 700;
  cursor: pointer;
}
.drawer-add:hover:not(:disabled) { background: #178048; }
.drawer-add:disabled { background: #DDD; cursor: not-allowed; }

.simple-roster-link {
  background: none;
  border: none;
  color: #1E9E5A;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
  text-decoration: underline;
}

/* ── Cast step — who's in the sim (under the seed box) ───────────────────── */
.cast-step {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cast-step-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: #999;
}
.cast-choices {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.cast-choice {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  background: #fff;
  border: 1px solid #E5E5E5;
  border-radius: 12px;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s, background 0.15s;
}
.cast-choice:hover:not(:disabled) { border-color: #1E9E5A; }
.cast-choice.active { border-color: #1E9E5A; background: #F0FAF4; }
.cast-choice:disabled { opacity: 0.5; cursor: not-allowed; }
.cast-choice-title { font-weight: 600; font-size: 0.88rem; color: #1a1a1a; }
.cast-choice-sub { font-size: 0.74rem; color: #777; line-height: 1.4; }

.cast-custom {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid #E5E5E5;
  border-radius: 12px;
  background: #FAFAFA;
}
.cast-custom-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.74rem;
  color: #555;
}
.cast-custom-empty { color: #999; }
.cast-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.cast-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px 4px 12px;
  background: #fff;
  border: 1px solid #1E9E5A;
  border-radius: 999px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  color: #1E9E5A;
  font-weight: 600;
}
.cast-chip-x {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: none;
  border-radius: 50%;
  background: rgba(30, 158, 90, 0.12);
  color: #1E9E5A;
  font-size: 0.9rem;
  line-height: 1;
  cursor: pointer;
}
.cast-chip-x:hover { background: #1E9E5A; color: #fff; }

.cast-scope { display: flex; gap: 4px; }
.cast-scope-opt {
  padding: 5px 14px;
  border: 1px solid #E5E5E5;
  background: #fff;
  border-radius: 999px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  font-weight: 600;
  color: #777;
  cursor: pointer;
  transition: all 0.15s;
}
.cast-scope-opt:hover { border-color: #1E9E5A; color: #1E9E5A; }
.cast-scope-opt.active { background: #1E9E5A; border-color: #1E9E5A; color: #fff; }

/* Center — Claude-style single prompt box, page-centered. Sits in normal flow
   over the full simple-view; the drawer overlays on top rather than pushing
   it, so the prompt stays centered whether the drawer is open or closed. */
.simple-center {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 80px);
}
.simple-ask {
  width: 100%;
  max-width: 680px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  margin-top: -40px; /* nudge above true center, like Claude's home */
}
.simple-greeting {
  margin: 0;
  text-align: center;
  font-size: 1.9rem;
  font-weight: 500;
  letter-spacing: -0.5px;
  color: #1a1a1a;
}
.simple-prompt {
  border: 1px solid #DDD;
  border-radius: 16px;
  background: #fff;
  padding: 16px 16px 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.simple-prompt:focus-within {
  border-color: #1E9E5A;
  box-shadow: 0 2px 12px rgba(30, 158, 90, 0.12);
}
.simple-prompt-input {
  width: 100%;
  border: none;
  background: transparent;
  outline: none;
  resize: none;
  min-height: 56px;
  max-height: 240px;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  font-size: 1.05rem;
  line-height: 1.55;
  color: #1a1a1a;
}
.simple-prompt-input::placeholder { color: #9a9a9a; }
.simple-prompt-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
}
.simple-modes { display: flex; flex-wrap: wrap; gap: 4px; }
.simple-mode {
  padding: 5px 14px;
  border: 1px solid #E5E5E5;
  background: #fff;
  border-radius: 999px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  font-weight: 600;
  color: #777;
  cursor: pointer;
  transition: all 0.15s;
}
.simple-mode:hover:not(:disabled) { border-color: #1E9E5A; color: #1E9E5A; }
.simple-mode.active { background: #1E9E5A; border-color: #1E9E5A; color: #fff; }
.simple-mode:disabled { opacity: 0.5; cursor: not-allowed; }

/* Ground-in-web-research pill — sits beside the mode pills */
.simple-ground {
  padding: 5px 14px;
  border: 1px solid #E5E5E5;
  background: #fff;
  border-radius: 999px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  font-weight: 600;
  color: #777;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.simple-ground:hover:not(:disabled) { border-color: #1E9E5A; color: #1E9E5A; }
.simple-ground.active { background: #F0FAF4; border-color: #1E9E5A; color: #1E9E5A; }
.simple-ground:disabled { opacity: 0.5; cursor: not-allowed; }

.simple-ground-error {
  margin: 0;
  padding: 8px 12px;
  background: #FEE;
  border: 1px solid #FCC;
  border-radius: 8px;
  color: #C00;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
}
.simple-ground-sources {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  align-items: baseline;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: #888;
}
.simple-ground-sources a {
  color: #1E9E5A;
  text-decoration: none;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.simple-ground-sources a:hover { text-decoration: underline; }

.simple-send {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: #1E9E5A;
  color: #fff;
  font-size: 1.2rem;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}
.simple-send:hover:not(:disabled) { background: #178048; }
.simple-send:disabled { background: #DDD; cursor: not-allowed; }

@media (max-width: 860px) {
  .simple-ask { margin-top: 0; }
}
</style>
