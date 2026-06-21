<template>
  <div class="custom-agent-panel">
    <!-- Toggle -->
    <div class="panel-toggle" @click="toggleEnabled">
      <div class="toggle-switch" :class="{ active: enabled }">
        <div class="toggle-knob"></div>
      </div>
      <div class="toggle-label">
        <span class="toggle-title">Include Custom Agents</span>
        <span class="toggle-desc">Add your own agent personas to the simulation</span>
      </div>
      <span v-if="agentCount > 0" class="agent-count-badge">{{ agentCount }}</span>
    </div>

    <div v-if="enabled" class="panel-content">
      <!-- Search People -->
      <div class="search-section">
        <div class="section-header">
          <span class="section-title">Search People to Model</span>
          <span class="section-hint">Describe a real-world group</span>
        </div>
        <div class="search-row">
          <input
            v-model="peopleQuery"
            class="people-input"
            type="text"
            placeholder="e.g. Cape Town minibus taxi drivers"
            @keyup.enter="runPeopleSearch"
            :disabled="searching"
          />
          <select v-model.number="peopleCount" class="people-count" :disabled="searching">
            <option :value="3">3</option>
            <option :value="5">5</option>
            <option :value="8">8</option>
            <option :value="12">12</option>
          </select>
          <button class="search-btn" @click="runPeopleSearch" :disabled="searching || !peopleQuery.trim()">
            {{ searching ? '...' : 'Generate' }}
          </button>
        </div>
        <label class="ground-toggle">
          <input type="checkbox" v-model="groundWithWeb" :disabled="searching" />
          <span>Ground with web research (slower, more realistic, uses more tokens)</span>
        </label>
        <div v-if="searchStatus" class="parse-status" :class="searchStatus.type">
          {{ searchStatus.message }}
        </div>
      </div>

      <!-- Pick from persona library (panel-style group picker) -->
      <div class="library-section">
        <div class="section-header">
          <span class="section-title">Pick from Persona Library</span>
          <button class="library-toggle" @click="toggleLibrary">
            {{ showLibrary ? 'Hide' : `Browse ${libraryPersonas.length || ''} personas` }}
          </button>
        </div>
        <div v-if="showLibrary" class="library-body">
          <div v-if="libraryLoading" class="parse-status info">Loading library…</div>
          <template v-else>
            <AgentPicker
              :agents="libraryPersonas"
              :multiSelect="true"
              :selectedIds="librarySelected"
              @toggle="toggleLibraryPersona"
            />
            <div class="library-actions">
              <span class="library-count">{{ librarySelected.size }} selected</span>
              <button
                class="library-add-btn"
                :disabled="librarySelected.size === 0"
                @click="addLibrarySelection"
              >
                Add {{ librarySelected.size }} to roster
              </button>
            </div>
          </template>
        </div>
      </div>

      <!-- Upload Area -->
      <div class="upload-section">
        <div class="section-header">
          <span class="section-title">Agent Definition Document</span>
          <span class="section-hint">JSON or unstructured text (PDF, MD, TXT)</span>
        </div>
        <div
          class="agent-upload-zone"
          @dragover.prevent="dragOver = true"
          @dragleave.prevent="dragOver = false"
          @drop.prevent="handleDrop"
          @click="triggerAgentDocInput"
          :class="{ 'drag-over': dragOver, 'has-file': agentDocFile }"
        >
          <input ref="agentDocInput" type="file" accept=".pdf,.md,.txt,.json" @change="handleAgentDocSelect" style="display: none" />
          <div v-if="!agentDocFile" class="upload-placeholder">
            <div class="upload-icon">↑</div>
            <div class="upload-title">Upload agent research document</div>
            <div class="upload-hint">Drag & drop or click to browse</div>
          </div>
          <div v-else class="file-display">
            <span class="file-icon">📄</span>
            <span class="file-name">{{ agentDocFile.name }}</span>
            <button class="file-remove" @click.stop="removeAgentDoc">×</button>
          </div>
        </div>
        <div class="upload-helper">
          <span class="upload-helper-hint">PDF, MD, TXT, JSON. Required field: <code>name</code>.</span>
          <a
            href="/agents-example.json"
            download="agents-example.json"
            class="upload-helper-link"
            @click.stop
          >
            Download example template
          </a>
        </div>
        <div v-if="parseStatus" class="parse-status" :class="parseStatus.type">
          {{ parseStatus.message }}
        </div>
      </div>

      <!-- Pending review (after upload, before commit to roster) -->
      <Transition name="fade-slide">
        <div v-if="pendingAgents.length > 0" class="pending-section" ref="pendingScrollRef">
          <div class="pending-header">
            <div>
              <span class="pending-title">Review uploaded agents</span>
              <span class="pending-sub">{{ pendingAgents.length }} parsed — pick which to add</span>
            </div>
            <button class="pending-toggle-all" @click="toggleAllPendingSelected">
              {{ allPendingSelected() ? 'Deselect all' : 'Select all' }}
            </button>
          </div>
          <div class="pending-list">
            <div
              v-for="agent in pendingAgents"
              :key="agent._id"
              class="pending-row"
              :class="{ selected: pendingSelected.has(agent._id) }"
            >
              <label class="pending-label">
                <input
                  type="checkbox"
                  :checked="pendingSelected.has(agent._id)"
                  @change="togglePendingSelected(agent._id)"
                  class="pending-check"
                />
                <div class="pending-meta">
                  <div class="pending-name">{{ agent.name }}</div>
                  <div class="pending-tags">
                    <span class="pending-badge">
                      {{ (agent.actor_archetype || agent.archetype || 'unknown').replace(/_/g, ' ') }}
                    </span>
                    <span v-if="agent.age" class="pending-bit">{{ agent.age }}y</span>
                    <span v-if="agent.occupation" class="pending-bit">{{ agent.occupation }}</span>
                    <span v-if="!agent.background_story && !agent.bio" class="pending-warn">missing background</span>
                    <span v-if="!agent.persona && !agent.description" class="pending-warn">missing persona</span>
                  </div>
                </div>
              </label>
              <button
                class="pending-enrich"
                :disabled="enrichingIds.has(agent._id)"
                @click.stop="enrichPendingAgent(agent)"
                title="Let AI fill in missing fields based on what's already here"
              >
                <span v-if="enrichingIds.has(agent._id)">…</span>
                <span v-else>✨ Enrich</span>
              </button>
            </div>
          </div>
          <div class="pending-actions">
            <button class="pending-discard" @click="discardPendingAgents">Discard</button>
            <button class="pending-commit" @click="commitPendingAgents">
              Add {{ Array.from(pendingSelected).length }} agent{{ Array.from(pendingSelected).length !== 1 ? 's' : '' }}
            </button>
          </div>
        </div>
      </Transition>

      <!-- Manual Add -->
      <div class="manual-section">
        <div class="section-header">
          <span class="section-title">Agent Roster</span>
          <button class="add-agent-btn" @click="openAddModal">
            <span>+</span>
            <span>Add Agent</span>
          </button>
        </div>

        <div v-if="agents.length === 0" class="empty-state">
          <div class="empty-icon">◈</div>
          <p>No custom agents yet.</p>
          <p class="empty-hint">Upload a document or add agents manually.</p>
        </div>

        <div v-else class="agent-list">
          <AgentDefinitionCard
            v-for="(agent, idx) in validAgents"
            :key="(agent && agent._id) || idx"
            :agent="agent"
            @edit="openEditModal(agent, idx)"
            @remove="removeAgent(idx)"
            @toggle-core-focus="toggleCoreFocus(agent, idx)"
          />
        </div>
      </div>

      <!-- Run Mode -->
      <div class="run-mode">
        <label class="run-mode-row">
          <input type="checkbox" :checked="customOnly" @change="toggleCustomOnly" />
          <span class="run-mode-label">
            <strong>Run on custom agents only</strong>
            <span class="run-mode-hint">
              Skip the auto-generated population — the simulation runs solely on the
              {{ agentCount }} agent{{ agentCount !== 1 ? 's' : '' }} above.
            </span>
          </span>
        </label>
      </div>

      <!-- Merge Mode Note -->
      <div v-if="!customOnly" class="merge-note">
        <span class="note-icon">ℹ</span>
        <span class="note-text">
          Custom agents will be <strong>merged</strong> with auto-generated graph agents.
          Custom profiles take priority when names conflict.
        </span>
      </div>
      <div v-else class="merge-note custom-only-note">
        <span class="note-icon">◆</span>
        <span class="note-text">
          <strong>Custom-only mode.</strong> Only your custom agents will be simulated.
          With a small cast, expect little opinion propagation between agents.
        </span>
      </div>
    </div>

    <!-- Modal -->
    <AgentEditModal
      v-model="showModal"
      :agent="editingAgent"
      @save="onAgentSave"
    />
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import AgentDefinitionCard from './AgentDefinitionCard.vue'
import AgentEditModal from './AgentEditModal.vue'
import AgentPicker from './AgentPicker.vue'

import { parseAgentDocument } from '../api/simulation'
import { searchPeople, enrichAgent, listPersonas, getPersona } from '../api/research'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  enabled: { type: Boolean, default: false },
  customOnly: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'update:enabled', 'update:customOnly'])

function toggleCustomOnly() {
  emit('update:customOnly', !props.customOnly)
}

const agents = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const enabled = computed({
  get: () => props.enabled,
  set: (val) => emit('update:enabled', val)
})

const agentCount = computed(() => agents.value.length)
const validAgents = computed(() => agents.value.filter(a => a && typeof a === 'object' && a.name))

// Pick-from-library state. listPersonas returns metadata; the AgentPicker only
// needs name/archetype/province/etc. for browsing. Full profile is fetched on
// add so the roster gets the persona's complete identity.
const showLibrary = ref(false)
const libraryPersonas = ref([])
const libraryLoading = ref(false)
const librarySelected = ref(new Set())

const personaId = (p) => p.id ?? p.persona_id ?? p.name

async function toggleLibrary() {
  showLibrary.value = !showLibrary.value
  if (showLibrary.value && libraryPersonas.value.length === 0) {
    libraryLoading.value = true
    try {
      const res = await listPersonas()
      // Normalise field names the picker expects (archetype → actor_archetype).
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
}

function toggleLibraryPersona(p) {
  const id = personaId(p)
  const next = new Set(librarySelected.value)
  next.has(id) ? next.delete(id) : next.add(id)
  librarySelected.value = next
}

async function addLibrarySelection() {
  const ids = Array.from(librarySelected.value)
  const existing = new Set(agents.value.map(a => (a.name || '').toLowerCase()))
  const added = []
  for (const id of ids) {
    const meta = libraryPersonas.value.find(p => personaId(p) === id)
    if (!meta || existing.has((meta.name || '').toLowerCase())) continue
    let full = meta
    try {
      // Fetch the complete profile so the roster carries the full identity,
      // not just the browse metadata.
      const res = await getPersona(id)
      if (res.success && res.persona) full = { ...res.persona, actor_archetype: res.persona.actor_archetype || res.persona.archetype }
    } catch (e) {
      console.warn('Falling back to metadata for persona', id, e)
    }
    added.push(full)
  }
  if (added.length) {
    agents.value = [...agents.value, ...added]
    if (!enabled.value) enabled.value = true
  }
  librarySelected.value = new Set()
  showLibrary.value = false
}

const showModal = ref(false)
const editingAgent = ref(null)
const editingIndex = ref(-1)
const dragOver = ref(false)
const agentDocFile = ref(null)
const agentDocInput = ref(null)
const parseStatus = ref(null)

// Issue 1 — preview before commit. Parsed agents land here first; the user
// reviews them and commits selected ones to the roster (or discards all).
// Avoids silent commits of bad parses into the live roster.
const pendingAgents = ref([])
const pendingSelected = ref(new Set())
const pendingScrollRef = ref(null)

// Per-row enrichment: track which agents are currently being enriched so we
// can show a spinner on just that row, not the whole panel.
const enrichingIds = ref(new Set())

async function enrichPendingAgent(agent) {
  if (!agent || !agent._id || enrichingIds.value.has(agent._id)) return
  const idx = pendingAgents.value.findIndex(a => a._id === agent._id)
  if (idx === -1) return

  // Mark as enriching (Set must be reassigned for Vue reactivity)
  const startSet = new Set(enrichingIds.value)
  startSet.add(agent._id)
  enrichingIds.value = startSet

  try {
    const res = await enrichAgent({ agent })
    if (res && res.success && res.agent) {
      // Update the row in place. Backend already preserved _id and any
      // user-provided non-empty fields.
      const updated = { ...res.agent }
      const next = [...pendingAgents.value]
      next[idx] = updated
      pendingAgents.value = next
    } else {
      parseStatus.value = {
        type: 'error',
        message: (res && res.error) || 'Enrich failed.'
      }
    }
  } catch (err) {
    parseStatus.value = {
      type: 'error',
      message: err.message || 'Enrich failed.'
    }
  } finally {
    const endSet = new Set(enrichingIds.value)
    endSet.delete(agent._id)
    enrichingIds.value = endSet
  }
}

// People search
const peopleQuery = ref('')
const peopleCount = ref(5)
const groundWithWeb = ref(false)
const searching = ref(false)
const searchStatus = ref(null)

// Merge a batch of generated agents into the roster, de-duping by name.
function mergeAgents(incoming) {
  const valid = incoming.filter(a => a && typeof a === 'object' && a.name)
  const existingNames = new Set(agents.value.map(a => (a && a.name || '').toLowerCase()))
  const newAgents = valid
    .filter(a => !existingNames.has(a.name.toLowerCase()))
    .map(a => ({ ...a, _id: a._id || genId() }))
  agents.value = [...agents.value, ...newAgents]
  return newAgents.length
}

async function runPeopleSearch() {
  const group = peopleQuery.value.trim()
  if (!group || searching.value) return
  searching.value = true
  searchStatus.value = {
    type: 'loading',
    message: groundWithWeb.value
      ? 'Researching the group on the web and generating personas...'
      : 'Generating personas...'
  }
  try {
    const result = await searchPeople({
      group,
      count: peopleCount.value,
      ground_with_web: groundWithWeb.value
    })
    if (result && result.success && Array.isArray(result.agents)) {
      const added = mergeAgents(result.agents)
      const groundedNote = result.grounded ? ` (grounded on ${result.sources?.length || 0} web sources)` : ''
      searchStatus.value = {
        type: 'success',
        message: `Added ${added} persona${added !== 1 ? 's' : ''} for "${group}"${groundedNote}.`
      }
    } else {
      searchStatus.value = { type: 'error', message: result.error || 'Could not generate personas.' }
    }
  } catch (err) {
    searchStatus.value = { type: 'error', message: err.message || 'People search failed.' }
  } finally {
    searching.value = false
  }
}

function toggleEnabled() {
  enabled.value = !enabled.value
}

function triggerAgentDocInput() {
  agentDocInput.value?.click()
}

function handleAgentDocSelect(e) {
  const file = e.target.files?.[0]
  if (file) setAgentDoc(file)
}

function handleDrop(e) {
  dragOver.value = false
  const file = e.dataTransfer.files?.[0]
  if (file) setAgentDoc(file)
}

// Issue 2 — informative status. Counts what came through with vs without
// the key fields so the user can tell at a glance whether the parse was
// good. Reports a single summary line under the upload zone.
function summarizeExtraction(parsed) {
  let complete = 0
  const missing = { archetype: 0, background: 0, persona: 0 }
  for (const a of parsed) {
    const hasArch = !!(a.actor_archetype || a.archetype)
    const hasBg = !!(a.background_story || a.bio || a.background)
    const hasPersona = !!(a.persona || a.description)
    if (hasArch && hasBg && hasPersona) complete++
    if (!hasArch) missing.archetype++
    if (!hasBg) missing.background++
    if (!hasPersona) missing.persona++
  }
  const parts = []
  parts.push(`${parsed.length} extracted`)
  if (complete > 0 && complete < parsed.length) parts.push(`${complete} complete`)
  else if (complete === parsed.length) parts.push('all complete')
  const gaps = []
  if (missing.archetype) gaps.push(`${missing.archetype} missing archetype`)
  if (missing.background) gaps.push(`${missing.background} missing background`)
  if (missing.persona) gaps.push(`${missing.persona} missing persona`)
  if (gaps.length) parts.push(gaps.join(', '))
  return parts.join(' · ')
}

async function setAgentDoc(file) {
  // Issue 7 — block re-upload if a pending review is already showing. Forces
  // the user to commit or discard before the next file, avoiding ambiguous
  // state where two unreviewed batches stack.
  if (pendingAgents.value.length > 0) {
    parseStatus.value = {
      type: 'error',
      message: 'Review the pending agents below before uploading another file.'
    }
    return
  }
  agentDocFile.value = file
  parseStatus.value = { type: 'loading', message: 'Parsing agent definitions...' }

  try {
    const result = await parseAgentDocument(file)
    if (result && result.success && Array.isArray(result.data)) {
      const validAgents = result.data.filter(a => a && typeof a === 'object' && a.name)
      const existingNames = new Set(agents.value.map(a => (a && a.name || '').toLowerCase()))
      // Filter out names already in the roster so the user doesn't review
      // duplicates that would silently drop on commit.
      const fresh = validAgents.filter(a => !existingNames.has(a.name.toLowerCase()))
      const stagedAgents = fresh.map(a => ({ ...a, _id: a._id || genId() }))

      if (stagedAgents.length === 0) {
        parseStatus.value = {
          type: 'error',
          message: validAgents.length > 0
            ? `Parsed ${validAgents.length} agents but all already exist in the roster.`
            : 'No usable agents found in the document.'
        }
        return
      }

      pendingAgents.value = stagedAgents
      pendingSelected.value = new Set(stagedAgents.map(a => a._id))
      parseStatus.value = {
        type: 'success',
        message: summarizeExtraction(stagedAgents) + ' — review below.'
      }
      // Issue 7 — bring the new section into view so the user sees that
      // something happened, even on a tall page.
      nextTick(() => {
        try { pendingScrollRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }) } catch {}
      })
    } else {
      parseStatus.value = { type: 'error', message: result.error || 'Could not parse agents from document.' }
    }
  } catch (err) {
    parseStatus.value = { type: 'error', message: err.message || 'Parse failed.' }
  }
}

// Commit selected pending agents into the live roster.
function commitPendingAgents() {
  const toAdd = pendingAgents.value.filter(a => pendingSelected.value.has(a._id))
  if (toAdd.length === 0) {
    parseStatus.value = { type: 'error', message: 'Select at least one agent to add.' }
    return
  }
  agents.value = [...agents.value, ...toAdd]
  const n = toAdd.length
  parseStatus.value = {
    type: 'success',
    message: `Added ${n} agent${n !== 1 ? 's' : ''} to the roster.`
  }
  pendingAgents.value = []
  pendingSelected.value = new Set()
  removeAgentDoc()
}

function discardPendingAgents() {
  pendingAgents.value = []
  pendingSelected.value = new Set()
  parseStatus.value = null
  removeAgentDoc()
}

function togglePendingSelected(id) {
  const next = new Set(pendingSelected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  pendingSelected.value = next
}

function allPendingSelected() {
  return pendingAgents.value.length > 0 &&
         pendingAgents.value.every(a => pendingSelected.value.has(a._id))
}

function toggleAllPendingSelected() {
  if (allPendingSelected()) {
    pendingSelected.value = new Set()
  } else {
    pendingSelected.value = new Set(pendingAgents.value.map(a => a._id))
  }
}

function removeAgentDoc() {
  agentDocFile.value = null
  parseStatus.value = null
  if (agentDocInput.value) agentDocInput.value.value = ''
}

function openAddModal() {
  editingAgent.value = null
  editingIndex.value = -1
  showModal.value = true
}

function openEditModal(agent, idx) {
  editingAgent.value = agent
  editingIndex.value = idx
  showModal.value = true
}

function onAgentSave(agentData) {
  const list = [...agents.value]
  if (editingIndex.value >= 0) {
    list[editingIndex.value] = { ...agentData, _id: list[editingIndex.value]._id || genId() }
  } else {
    list.push({ ...agentData, _id: genId() })
  }
  agents.value = list
}

function removeAgent(idx) {
  const list = [...agents.value]
  list.splice(idx, 1)
  agents.value = list
}

function toggleCoreFocus(agent, idx) {
  const list = [...agents.value]
  list[idx] = { ...list[idx], is_core_focus: !list[idx].is_core_focus }
  agents.value = list
}

function genId() {
  return 'agent_' + Math.random().toString(36).substring(2, 9)
}
</script>

<style scoped>
/* Pick-from-library section */
.library-section { margin-bottom: 18px; }
.library-toggle {
  background: none;
  border: 1px solid #1E9E5A;
  color: #1E9E5A;
  padding: 4px 12px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  font-weight: 600;
  cursor: pointer;
  border-radius: 3px;
}
.library-toggle:hover { background: #F0FAF4; }
.library-body {
  margin-top: 10px;
  border: 1px solid #E5E5E5;
  padding: 12px;
  background: #fff;
}
.library-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid #F0F0F0;
}
.library-count {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #666;
}
.library-add-btn {
  background: #1E9E5A;
  color: #fff;
  border: none;
  padding: 8px 18px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem;
  font-weight: 700;
  cursor: pointer;
  border-radius: 3px;
}
.library-add-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.library-add-btn:hover:not(:disabled) { background: #178048; }

.custom-agent-panel {
  display: flex;
  flex-direction: column;
  gap: 0;
}

/* Toggle */
.panel-toggle {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  background: #FAFAFA;
  border: 1px solid #EAEAEA;
  cursor: pointer;
  transition: all 0.2s;
}

.panel-toggle:hover {
  background: #F5F5F5;
}

.toggle-switch {
  width: 36px;
  height: 20px;
  background: #E0E0E0;
  border-radius: 10px;
  position: relative;
  flex-shrink: 0;
  transition: background 0.2s;
}

.toggle-switch.active {
  background: #1E9E5A;
}

.toggle-knob {
  width: 16px;
  height: 16px;
  background: #fff;
  border-radius: 50%;
  position: absolute;
  top: 2px;
  left: 2px;
  transition: transform 0.2s;
  box-shadow: 0 1px 3px rgba(0,0,0,0.15);
}

.toggle-switch.active .toggle-knob {
  transform: translateX(16px);
}

.toggle-label {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.toggle-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: #000;
}

.toggle-desc {
  font-size: 0.75rem;
  color: #999;
}

.agent-count-badge {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  font-weight: 700;
  color: #1E9E5A;
  background: rgba(30, 158, 90, 0.08);
  padding: 4px 10px;
  border-radius: 12px;
}

/* Panel Content */
.panel-content {
  padding: 20px;
  border: 1px solid #EAEAEA;
  border-top: none;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.section-title {
  font-size: 0.8rem;
  font-weight: 600;
  color: #333;
}

.section-hint {
  font-size: 0.75rem;
  color: #999;
}

/* People search */
.search-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.search-row {
  display: flex;
  gap: 8px;
}

.people-input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #DDD;
  font-family: inherit;
  font-size: 0.85rem;
}

.people-input:focus {
  outline: none;
  border-color: #1E9E5A;
}

.people-count {
  padding: 8px;
  border: 1px solid #DDD;
  font-family: inherit;
  font-size: 0.85rem;
  background: #fff;
}

.search-btn {
  padding: 8px 16px;
  border: 1px solid #000;
  background: #000;
  color: #fff;
  font-family: inherit;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.search-btn:hover:not(:disabled) {
  background: #1E9E5A;
  border-color: #1E9E5A;
}

.search-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ground-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.75rem;
  color: #666;
  cursor: pointer;
}

.ground-toggle input {
  cursor: pointer;
}

/* Upload */
.agent-upload-zone {
  border: 1px dashed #CCC;
  padding: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  background: #FAFAFA;
  transition: all 0.2s;
}

.agent-upload-zone.drag-over {
  background: #F0F0F0;
  border-color: #1E9E5A;
}

.agent-upload-zone.has-file {
  background: #fff;
  border-style: solid;
}

.upload-placeholder {
  text-align: center;
}

.upload-icon {
  width: 32px;
  height: 32px;
  border: 1px solid #DDD;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 10px;
  color: #999;
  font-size: 0.9rem;
}

.upload-title {
  font-size: 0.85rem;
  font-weight: 500;
  margin-bottom: 4px;
}

.upload-hint {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: #999;
}

.file-display {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.file-name {
  flex: 1;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  color: #333;
}

.file-remove {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: #999;
  font-size: 1.2rem;
  cursor: pointer;
}

.file-remove:hover {
  color: #C5283D;
}

/* Helper row under the upload zone — types accepted + example download.
   Quiet enough not to compete with the drop zone; visible enough that a
   first-time user finds the template without having to ask. */
.upload-helper {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  font-size: 0.72rem;
  color: #888;
}
.upload-helper-hint code {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  background: #F4F4F4;
  padding: 1px 5px;
  color: #000;
}
.upload-helper-link {
  color: #1E9E5A;
  text-decoration: none;
  font-weight: 500;
  border-bottom: 1px dotted #1E9E5A;
}
.upload-helper-link:hover {
  color: #167a45;
  border-bottom-style: solid;
}

.parse-status {
  margin-top: 8px;
  padding: 8px 12px;
  font-size: 0.8rem;
  border-left: 3px solid;
}

.parse-status.loading {
  background: #FFF8E1;
  border-color: #FFB300;
  color: #856404;
}

.parse-status.success {
  background: #E8F5E9;
  border-color: #4CAF50;
  color: #2E7D32;
}

.parse-status.error {
  background: #FFEBEE;
  border-color: #EF5350;
  color: #C62828;
}

/* Manual section */
.manual-section {
  display: flex;
  flex-direction: column;
}

.add-agent-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid #000;
  background: #000;
  color: #fff;
  font-family: inherit;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.add-agent-btn:hover {
  background: #1E9E5A;
  border-color: #1E9E5A;
}

.empty-state {
  text-align: center;
  padding: 30px 20px;
  background: #FAFAFA;
  border: 1px dashed #E0E0E0;
}

.empty-icon {
  font-size: 1.5rem;
  color: #DDD;
  margin-bottom: 10px;
}

.empty-state p {
  font-size: 0.85rem;
  color: #999;
  margin: 0;
}

.empty-hint {
  font-size: 0.75rem;
  color: #BBB;
  margin-top: 4px;
}

.agent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
}

/* Run mode toggle */
.run-mode {
  padding: 12px;
  background: #FAFAFA;
  border: 1px solid #EAEAEA;
}
.run-mode-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  cursor: pointer;
}
.run-mode-row input {
  margin-top: 3px;
  accent-color: #1E9E5A;
  cursor: pointer;
  flex-shrink: 0;
}
.run-mode-label {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.run-mode-label strong {
  font-size: 0.85rem;
  color: #000;
}
.run-mode-hint {
  font-size: 0.75rem;
  color: #888;
  line-height: 1.4;
}
.custom-only-note {
  background: #F0FAF4;
}
.custom-only-note .note-icon {
  color: #1E9E5A;
}

/* Merge note */
.merge-note {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  background: #F5F5F5;
  font-size: 0.75rem;
  color: #666;
  line-height: 1.5;
}

.note-icon {
  color: #1E9E5A;
  font-weight: 700;
  flex-shrink: 0;
}

/* Pending review — preview before committing parsed agents to the roster.
   Tinted background + slide transition so the user sees something happened. */
.pending-section {
  margin: 6px 0 18px;
  padding: 14px 16px;
  background: #F0FAF4;
  border: 1px solid #1E9E5A;
  border-left-width: 3px;
}
.pending-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 10px;
  gap: 12px;
}
.pending-title {
  font-weight: 600;
  font-size: 0.9rem;
  color: #000;
  display: block;
}
.pending-sub {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  color: #1E9E5A;
}
.pending-toggle-all {
  background: transparent;
  border: 1px solid #BBB;
  padding: 4px 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  cursor: pointer;
  color: #555;
}
.pending-toggle-all:hover {
  border-color: #1E9E5A;
  color: #1E9E5A;
}
.pending-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 320px;
  overflow-y: auto;
}
.pending-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 10px;
  background: #fff;
  border: 1px solid #DDE7E0;
  transition: border-color 0.15s, background 0.15s;
}
.pending-row:hover {
  border-color: #1E9E5A;
}
.pending-row.selected {
  border-color: #1E9E5A;
  background: #fff;
}
.pending-row:not(.selected) {
  opacity: 0.6;
}
.pending-label {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  flex: 1;
  min-width: 0;
  cursor: pointer;
}
.pending-check {
  margin-top: 2px;
  accent-color: #1E9E5A;
  cursor: pointer;
  flex-shrink: 0;
}
.pending-enrich {
  align-self: center;
  background: transparent;
  border: 1px solid #1E9E5A;
  color: #1E9E5A;
  padding: 4px 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  font-weight: 600;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s;
}
.pending-enrich:hover:not(:disabled) {
  background: #1E9E5A;
  color: #fff;
}
.pending-enrich:disabled {
  opacity: 0.5;
  cursor: wait;
}
.pending-meta {
  flex: 1;
  min-width: 0;
}
.pending-name {
  font-weight: 600;
  font-size: 0.88rem;
  color: #000;
}
.pending-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
  align-items: center;
}
.pending-badge {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.65rem;
  background: #000;
  color: #fff;
  padding: 1px 6px;
}
.pending-bit {
  font-size: 0.72rem;
  color: #666;
}
.pending-warn {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.65rem;
  color: #C5283D;
  background: #FFF0F2;
  padding: 1px 6px;
}
.pending-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}
.pending-discard {
  background: transparent;
  border: 1px solid #BBB;
  color: #666;
  padding: 7px 14px;
  font-family: inherit;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
}
.pending-discard:hover {
  border-color: #C5283D;
  color: #C5283D;
}
.pending-commit {
  background: #000;
  color: #fff;
  border: 1px solid #000;
  padding: 7px 16px;
  font-family: inherit;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
}
.pending-commit:hover {
  background: #1E9E5A;
  border-color: #1E9E5A;
}

/* Slide-down transition for the pending review block */
.fade-slide-enter-active, .fade-slide-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}
.fade-slide-enter-from, .fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
