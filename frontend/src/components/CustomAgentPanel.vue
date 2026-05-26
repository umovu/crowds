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
        <div v-if="parseStatus" class="parse-status" :class="parseStatus.type">
          {{ parseStatus.message }}
        </div>
      </div>

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

      <!-- Merge Mode Note -->
      <div class="merge-note">
        <span class="note-icon">ℹ</span>
        <span class="note-text">
          Custom agents will be <strong>merged</strong> with auto-generated graph agents.
          Custom profiles take priority when names conflict.
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
import { ref, computed } from 'vue'
import AgentDefinitionCard from './AgentDefinitionCard.vue'
import AgentEditModal from './AgentEditModal.vue'

import { parseAgentDocument } from '../api/simulation'
import { searchPeople } from '../api/research'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  enabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'update:enabled'])

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

const showModal = ref(false)
const editingAgent = ref(null)
const editingIndex = ref(-1)
const dragOver = ref(false)
const agentDocFile = ref(null)
const agentDocInput = ref(null)
const parseStatus = ref(null)

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

async function setAgentDoc(file) {
  agentDocFile.value = file
  parseStatus.value = { type: 'loading', message: 'Parsing agent definitions...' }

  try {
    const result = await parseAgentDocument(file)
    if (result && result.success && Array.isArray(result.data)) {
      const count = result.data.length
      const validCount = result.data.filter(a => a && typeof a === 'object' && a.name).length
      console.log(`[CustomAgentPanel] Backend returned ${count} agents, ${validCount} valid`)
      // Merge parsed agents, avoiding duplicates by name (defensive: filter null/invalid)
      const validAgents = result.data.filter(a => a && typeof a === 'object' && a.name)
      const existingNames = new Set(agents.value.map(a => (a && a.name || '').toLowerCase()))
      const newAgents = validAgents.filter(a => !existingNames.has(a.name.toLowerCase()))
      agents.value = [...agents.value, ...newAgents]
      parseStatus.value = {
        type: 'success',
        message: `Extracted ${newAgents.length} agent${newAgents.length !== 1 ? 's' : ''} from document.`
      }
    } else {
      parseStatus.value = { type: 'error', message: result.error || 'Could not parse agents from document.' }
    }
  } catch (err) {
    parseStatus.value = { type: 'error', message: err.message || 'Parse failed.' }
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
</style>
