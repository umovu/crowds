<template>
  <div class="interview-panel">
    <!-- Agent Selector Sidebar -->
    <div class="agent-sidebar">
      <div class="sidebar-header">
        <h3>Stakeholders</h3>
        <div class="filter-controls">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search agents..."
            class="search-input"
          />
          <select v-model="archetypeFilter" class="filter-select">
            <option value="">All Archetypes</option>
            <option v-for="arch in uniqueArchetypes" :key="arch" :value="arch">
              {{ arch }}
            </option>
          </select>
        </div>
      </div>
      <div class="agent-list">
        <div
          v-for="agent in filteredAgents"
          :key="agent.id"
          class="agent-item"
          :class="{ active: selectedAgent?.id === agent.id }"
          @click="selectAgent(agent)"
        >
          <div class="agent-item-header">
            <img :src="getAvatarUrl(agent.name, 32)" :alt="agent.name" class="agent-item-avatar" />
            <span class="agent-item-name">{{ agent.name }}</span>
            <span
              class="stance-badge"
              :class="`stance-${agent.stance}`"
            >
              {{ agent.stance }}
            </span>
          </div>
          <div class="agent-item-meta">
            <span class="archetype-tag">{{ agent.actor_archetype || 'unknown' }}</span>
            <span v-if="agent.is_institutional" class="institutional-badge">institutional</span>
          </div>
          <div class="agent-item-topics">
            {{ (agent.interested_topics || []).slice(0, 3).join(', ') }}
          </div>
        </div>
      </div>
    </div>

    <!-- Interview Area -->
    <div class="interview-area">
      <div v-if="!selectedAgent" class="no-selection">
        <div class="no-selection-icon">🎙</div>
        <p>Select a stakeholder to interview</p>
        <p class="hint">Ask questions to understand their position and test persuasion strategies</p>
      </div>

      <template v-else>
        <!-- Agent Header -->
        <div class="selected-agent-header">
          <img :src="getAvatarUrl(selectedAgent.name, 56)" :alt="selectedAgent.name" class="selected-agent-avatar" />
          <div class="agent-title">
            <h2>{{ selectedAgent.name }}</h2>
            <span class="occupation">{{ selectedAgent.occupation }}</span>
          </div>
          <div class="agent-badges">
            <span class="archetype-badge">{{ selectedAgent.actor_archetype }}</span>
            <span
              class="stance-badge large"
              :class="`stance-${selectedAgent.stance}`"
            >
              {{ selectedAgent.stance }}
            </span>
            <span class="radicalism-badge">
              Radicalism: {{ selectedAgent.base_radicalism }}/5
            </span>
          </div>
        </div>

        <!-- Simulation Opinions -->
        <div v-if="selectedAgent.opinions && selectedAgent.opinions.length > 0" class="simulation-opinions">
          <h4>Simulation Posts ({{ selectedAgent.opinions.length }})</h4>
          <div class="opinions-list">
            <div
              v-for="(opinion, idx) in selectedAgent.opinions"
              :key="idx"
              class="opinion-card"
            >
              <div class="opinion-header">
                <span class="opinion-round">Round {{ opinion.round }}</span>
                <span class="opinion-time">{{ formatTime(opinion.timestamp) }}</span>
              </div>
              <div class="opinion-content">{{ opinion.content }}</div>
              <div v-if="opinion.topics && opinion.topics.length > 0" class="opinion-topics">
                <span v-for="topic in opinion.topics" :key="topic" class="topic-tag">{{ topic }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Interview History -->
        <div v-if="interviewHistory.length > 0" class="interview-history">
          <h4>Previous Interviews</h4>
          <div
            v-for="(entry, idx) in interviewHistory"
            :key="idx"
            class="history-entry"
          >
            <div class="history-question">
              <span class="label">Q:</span> {{ entry.question }}
            </div>
            <div class="history-response">
              <span class="label">A:</span> {{ entry.response }}
            </div>
            <div v-if="entry.stance_changed" class="stance-change-notice">
              Stance changed: {{ entry.stance_before }} → {{ entry.stance_after }}
            </div>
          </div>
        </div>

        <!-- Policy Context Input -->
        <div class="policy-context-input">
          <h4>Policy Context</h4>
          <p class="hint">Describe the specific policy you're testing (e.g., "SANDF deployment in civilian areas for crime reduction")</p>
          <div class="context-input-group">
            <textarea
              v-model="policyContext"
              placeholder="Enter the policy being discussed... e.g., 'SANDF deployment in Cape Town suburbs'"
              class="context-textarea"
              :disabled="interviewing"
              rows="2"
            ></textarea>
          </div>
        </div>

        <!-- Structured Questions -->
        <div class="structured-questions">
          <h4>Structured Questions</h4>
          <div class="question-buttons">
            <button
              v-for="q in structuredQuestions"
              :key="q.type"
              class="question-btn"
              :disabled="interviewing"
              @click="askStructured(q.type)"
            >
              {{ q.label }}
            </button>
          </div>
        </div>

        <!-- Free Text Question -->
        <div class="free-text-question">
          <h4>Custom Question</h4>
          <div class="question-input-group">
            <textarea
              v-model="customQuestion"
              placeholder="Ask a specific question about the policy... e.g., 'Would you accept SANDF deployment if police were also deployed?'"
              class="question-textarea"
              :disabled="interviewing"
              rows="3"
            ></textarea>
            <button
              class="ask-btn"
              :disabled="!customQuestion.trim() || interviewing"
              @click="askCustom"
            >
              {{ interviewing ? 'Asking...' : 'Ask' }}
            </button>
          </div>
        </div>

        <!-- Intervention Section -->
        <div class="intervention-section">
          <h4>Test Intervention</h4>
          <p class="hint">
            Simulate what happens if a policy maker tells this stakeholder something.
            e.g., "We will offer a taxi operator subsidy of R500/month."
          </p>
          <div class="intervention-input-group">
            <textarea
              v-model="interventionText"
              placeholder="Enter intervention text..."
              class="intervention-textarea"
              :disabled="intervening"
              rows="3"
            ></textarea>
            <button
              class="intervene-btn"
              :disabled="!interventionText.trim() || intervening"
              @click="applyIntervention"
            >
              {{ intervening ? 'Applying...' : 'Test Intervention' }}
            </button>
          </div>
        </div>

        <!-- Current Response -->
        <div v-if="currentResponse" class="response-panel">
          <h4>Response</h4>
          <div class="response-content">{{ currentResponse.response }}</div>
          <div class="response-meta">
            <div class="meta-row">
              <span class="meta-label">Stance:</span>
              <span
                class="stance-badge"
                :class="`stance-${currentResponse.stance_after}`"
              >
                {{ currentResponse.stance_after }}
              </span>
              <span v-if="currentResponse.stance_changed" class="change-arrow">
                ← was {{ currentResponse.stance_before }}
              </span>
            </div>
            <div v-if="currentResponse.radicalism_after !== undefined" class="meta-row">
              <span class="meta-label">Radicalism:</span>
              <span>{{ currentResponse.radicalism_after }}/5</span>
              <span v-if="currentResponse.radicalism_changed" class="change-arrow">
                ← was {{ currentResponse.radicalism_before }}
              </span>
            </div>
            <div v-if="currentResponse.mobilization_after !== undefined" class="meta-row">
              <span class="meta-label">Mobilization:</span>
              <span>{{ mobilizationLabel(currentResponse.mobilization_after) }}</span>
              <span v-if="currentResponse.mobilization_after !== currentResponse.mobilization_before" class="change-arrow">
                ← was {{ mobilizationLabel(currentResponse.mobilization_before) }}
              </span>
            </div>
          </div>
        </div>

        <!-- Error Display -->
        <div v-if="error" class="error-message">
          {{ error }}
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import {
  getSimulationAgents,
  interviewAgent,
  interveneWithAgent
} from '../api/simulation'

const props = defineProps({
  simulationId: {
    type: String,
    required: true
  }
})

// State
const agents = ref([])
const selectedAgent = ref(null)
const searchQuery = ref('')
const archetypeFilter = ref('')
const customQuestion = ref('')
const policyContext = ref('')
const interventionText = ref('')
const currentResponse = ref(null)
const interviewHistory = ref([])
const interviewing = ref(false)
const intervening = ref(false)
const error = ref(null)
const loading = ref(false)

// Avatar utility — deterministic DiceBear avatars from agent name
const getAvatarUrl = (name, size = 40) => {
  const seed = encodeURIComponent(name || 'agent')
  return `https://api.dicebear.com/7.x/avataaars/svg?seed=${seed}&size=${size}&backgroundColor=b6e3f4%2Cc0e8d5%2Cfde68a%2Cffd6a5&backgroundType=solid`
}

// Format timestamp for display
const formatTime = (timestamp) => {
  if (!timestamp) return ''
  try {
    const date = new Date(timestamp)
    return date.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ''
  }
}

// Structured question definitions
const structuredQuestions = [
  { type: 'biggest_concern', label: 'Biggest Concern?' },
  { type: 'what_would_change', label: 'What Would Change Your Mind?' },
  { type: 'willing_to_negotiate', label: 'Willing to Negotiate?' },
  { type: 'mobilization_intent', label: 'Planning Action?' },
  { type: 'message_to_government', label: 'Message to Government?' },
]

// Load agents on mount
const loadAgents = async () => {
  loading.value = true
  error.value = null
  try {
    const res = await getSimulationAgents(props.simulationId)
    if (res.success) {
      agents.value = res.data.agents || []
    } else {
      error.value = res.error || 'Failed to load agents'
    }
  } catch (e) {
    error.value = e.message || 'Network error'
  } finally {
    loading.value = false
  }
}

// Computed
const uniqueArchetypes = computed(() => {
  const arches = new Set()
  agents.value.forEach(a => {
    if (a.actor_archetype) arches.add(a.actor_archetype)
  })
  return Array.from(arches).sort()
})

const filteredAgents = computed(() => {
  let result = agents.value
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter(a =>
      (a.name || '').toLowerCase().includes(q) ||
      (a.occupation || '').toLowerCase().includes(q) ||
      (a.group_affiliation || '').toLowerCase().includes(q)
    )
  }
  if (archetypeFilter.value) {
    result = result.filter(a => a.actor_archetype === archetypeFilter.value)
  }
  return result
})

// Methods
const selectAgent = (agent) => {
  selectedAgent.value = agent
  currentResponse.value = null
  error.value = null
  customQuestion.value = ''
  interventionText.value = ''
  interviewHistory.value = []
}

const askStructured = async (questionType) => {
  if (!selectedAgent.value) return
  interviewing.value = true
  error.value = null
  currentResponse.value = null

  try {
    const res = await interviewAgent(props.simulationId, selectedAgent.value.id, {
      question_type: questionType,
      policy_context: policyContext.value || 'recent government policy announcement'
    })
    if (res.success) {
      currentResponse.value = res.data
      interviewHistory.value.push({
        question: structuredQuestions.find(q => q.type === questionType)?.label || questionType,
        response: res.data.response,
        stance_before: res.data.stance_before,
        stance_after: res.data.stance_after,
        stance_changed: res.data.stance_changed,
      })
      // Update local agent stance if changed
      if (res.data.stance_changed) {
        selectedAgent.value.stance = res.data.stance_after
      }
    } else {
      error.value = res.error || 'Interview failed'
    }
  } catch (e) {
    error.value = e.message || 'Network error'
  } finally {
    interviewing.value = false
  }
}

const askCustom = async () => {
  if (!selectedAgent.value || !customQuestion.value.trim()) return
  interviewing.value = true
  error.value = null
  currentResponse.value = null

  try {
    const res = await interviewAgent(props.simulationId, selectedAgent.value.id, {
      question: customQuestion.value.trim(),
      policy_context: policyContext.value || 'recent government policy announcement'
    })
    if (res.success) {
      currentResponse.value = res.data
      interviewHistory.value.push({
        question: customQuestion.value.trim(),
        response: res.data.response,
        stance_before: res.data.stance_before,
        stance_after: res.data.stance_after,
        stance_changed: res.data.stance_changed,
      })
      if (res.data.stance_changed) {
        selectedAgent.value.stance = res.data.stance_after
      }
      customQuestion.value = ''
    } else {
      error.value = res.error || 'Interview failed'
    }
  } catch (e) {
    error.value = e.message || 'Network error'
  } finally {
    interviewing.value = false
  }
}

const applyIntervention = async () => {
  if (!selectedAgent.value || !interventionText.value.trim()) return
  intervening.value = true
  error.value = null
  currentResponse.value = null

  try {
    const res = await interveneWithAgent(props.simulationId, selectedAgent.value.id, {
      intervention_text: interventionText.value.trim()
    })
    if (res.success) {
      currentResponse.value = res.data
      interviewHistory.value.push({
        question: `Intervention: ${interventionText.value.trim()}`,
        response: res.data.response,
        stance_before: res.data.stance_before,
        stance_after: res.data.stance_after,
        stance_changed: res.data.stance_changed,
      })
      if (res.data.stance_changed) {
        selectedAgent.value.stance = res.data.stance_after
      }
      interventionText.value = ''
    } else {
      error.value = res.error || 'Intervention failed'
    }
  } catch (e) {
    error.value = e.message || 'Network error'
  } finally {
    intervening.value = false
  }
}

const mobilizationLabel = (level) => {
  const labels = ['None', 'Discussing', 'Organizing', 'Acting']
  return labels[level] || 'Unknown'
}

// Watch for simulationId changes
watch(() => props.simulationId, (newId) => {
  if (newId) {
    agents.value = []
    selectedAgent.value = null
    currentResponse.value = null
    interviewHistory.value = []
    loadAgents()
  }
}, { immediate: true })
</script>

<style scoped>
.interview-panel {
  display: flex;
  height: 100%;
  min-height: 600px;
  gap: 0;
  background: #f5f5f5;
}

/* Sidebar */
.agent-sidebar {
  width: 320px;
  background: #fff;
  border-right: 1px solid #e0e0e0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid #e0e0e0;
}

.sidebar-header h3 {
  margin: 0 0 12px 0;
  font-size: 16px;
  font-weight: 600;
}

.filter-controls {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.search-input,
.filter-select {
  padding: 8px 12px;
  border: 1px solid #d0d0d0;
  border-radius: 6px;
  font-size: 13px;
  font-family: inherit;
}

.agent-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.agent-item {
  padding: 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
  margin-bottom: 4px;
}

.agent-item:hover {
  background: #f0f0f0;
}

.agent-item.active {
  background: #e3f2fd;
  border-left: 3px solid #2196f3;
}

.agent-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.agent-item-name {
  font-weight: 600;
  font-size: 14px;
}

.agent-item-meta {
  display: flex;
  gap: 6px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}

.agent-item-topics {
  font-size: 11px;
  color: #888;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Interview Area */
.interview-area {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
  background: #fafafa;
}

.no-selection {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #888;
}

.no-selection-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.hint {
  font-size: 13px;
  color: #999;
  margin-top: 8px;
}

/* Selected Agent Header */
.selected-agent-header {
  background: #fff;
  padding: 20px;
  border-radius: 12px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.agent-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}

.agent-title h2 {
  margin: 0;
  font-size: 22px;
}

.occupation {
  color: #666;
  font-size: 14px;
}

.agent-badges {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* Badges */
.stance-badge {
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.stance-badge.large {
  font-size: 13px;
  padding: 4px 14px;
}

.stance-support { background: #e8f5e9; color: #2e7d32; }
.stance-neutral { background: #f5f5f5; color: #666; }
.stance-concerned { background: #fff3e0; color: #e65100; }
.stance-oppose { background: #ffebee; color: #c62828; }
.stance-resist { background: #fce4ec; color: #ad1457; }

.archetype-badge {
  background: #e3f2fd;
  color: #1565c0;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
}

.archetype-tag {
  background: #e3f2fd;
  color: #1565c0;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
}

.institutional-badge {
  background: #f3e5f5;
  color: #6a1b9a;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
}

.radicalism-badge {
  background: #fff8e1;
  color: #f57f17;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
}

/* Interview History */
.interview-history {
  background: #fff;
  padding: 20px;
  border-radius: 12px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.interview-history h4 {
  margin: 0 0 16px 0;
  font-size: 15px;
}

.history-entry {
  padding: 12px;
  background: #f8f9fa;
  border-radius: 8px;
  margin-bottom: 10px;
}

.history-question {
  font-weight: 600;
  margin-bottom: 6px;
  color: #333;
}

.history-response {
  color: #555;
  line-height: 1.5;
}

.stance-change-notice {
  margin-top: 8px;
  padding: 6px 10px;
  background: #e8f5e9;
  color: #2e7d32;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}

/* Structured Questions */
.structured-questions,
.free-text-question,
.intervention-section {
  background: #fff;
  padding: 20px;
  border-radius: 12px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.structured-questions h4,
.free-text-question h4,
.intervention-section h4 {
  margin: 0 0 16px 0;
  font-size: 15px;
}

.question-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.question-btn {
  padding: 10px 18px;
  background: #f0f0f0;
  border: 1px solid #d0d0d0;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-family: inherit;
  transition: all 0.15s;
}

.question-btn:hover:not(:disabled) {
  background: #e3f2fd;
  border-color: #2196f3;
}

.question-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Input Groups */
.question-input-group,
.intervention-input-group,
.context-input-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.question-textarea,
.intervention-textarea,
.context-textarea {
  padding: 12px;
  border: 1px solid #d0d0d0;
  border-radius: 8px;
  font-family: inherit;
  font-size: 14px;
  resize: vertical;
}

.question-textarea:focus,
.intervention-textarea:focus,
.context-textarea:focus {
  outline: none;
  border-color: #2196f3;
}

/* Policy Context Input */
.policy-context-input {
  margin-bottom: 20px;
  padding: 16px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
}

.policy-context-input h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
  color: #333;
}

.policy-context-input .hint {
  margin-bottom: 10px;
}

.ask-btn,
.intervene-btn {
  padding: 12px 24px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  align-self: flex-start;
}

.ask-btn {
  background: #2196f3;
  color: white;
}

.ask-btn:hover:not(:disabled) {
  background: #1976d2;
}

.intervene-btn {
  background: #ff9800;
  color: white;
}

.intervene-btn:hover:not(:disabled) {
  background: #f57c00;
}

.ask-btn:disabled,
.intervene-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Response Panel */
.response-panel {
  background: #fff;
  padding: 20px;
  border-radius: 12px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  border-left: 4px solid #4caf50;
}

.response-panel h4 {
  margin: 0 0 12px 0;
  font-size: 15px;
  color: #2e7d32;
}

.response-content {
  line-height: 1.7;
  color: #333;
  margin-bottom: 16px;
  font-size: 15px;
}

.response-meta {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.meta-label {
  font-weight: 600;
  color: #666;
  min-width: 100px;
}

.change-arrow {
  color: #888;
  font-size: 12px;
  font-style: italic;
}

/* Error */
.error-message {
  background: #ffebee;
  color: #c62828;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 20px;
}

.label {
  font-weight: 600;
  color: #666;
  margin-right: 6px;
}

/* Avatar styles */
.agent-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.agent-item-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
}

.selected-agent-header {
  display: flex;
  align-items: center;
  gap: 16px;
}

.selected-agent-avatar {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
  border: 2px solid #e0e0e0;
}

/* Simulation Opinions */
.simulation-opinions {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #e0e0e0;
}

.simulation-opinions h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: #333;
}

.opinions-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.opinion-card {
  background: #fafafa;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 12px;
}

.opinion-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 12px;
  color: #666;
}

.opinion-round {
  font-weight: 600;
  color: #1e9e5a;
}

.opinion-time {
  color: #999;
}

.opinion-content {
  font-size: 14px;
  line-height: 1.5;
  color: #333;
  margin-bottom: 8px;
}

.opinion-topics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.opinion-topics .topic-tag {
  font-size: 11px;
  padding: 2px 8px;
  background: #e8f5e9;
  color: #1e9e5a;
  border-radius: 10px;
}
</style>
