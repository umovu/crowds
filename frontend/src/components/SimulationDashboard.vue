<template>
  <div class="simulation-dashboard">
    <!-- Dashboard Header -->
    <div class="dashboard-header">
      <h2 class="dashboard-title">Simulation Analytics</h2>
      <div class="dashboard-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="tab-btn"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="dashboard-loading">
      <div class="loading-spinner"></div>
      <span>Loading analytics...</span>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="dashboard-error">
      <span class="error-icon">⚠</span>
      <span>{{ error }}</span>
    </div>

    <!-- Dashboard Content -->
    <div v-else class="dashboard-content">
      <!-- Overview Tab -->
      <div v-show="activeTab === 'overview'" class="tab-panel">
        <div class="overview-grid">
          <div class="metric-card">
            <span class="metric-label">Total Rounds</span>
            <span class="metric-value">{{ overview?.meta?.total_rounds || 0 }}</span>
          </div>
          <div class="metric-card">
            <span class="metric-label">Total Agents</span>
            <span class="metric-value">{{ overview?.meta?.total_agents || 0 }}</span>
          </div>
          <div class="metric-card">
            <span class="metric-label">Events Injected</span>
            <span class="metric-value">{{ eventSummary.length }}</span>
          </div>
          <div class="metric-card">
            <span class="metric-label">Top Topic</span>
            <span class="metric-value topic-value">{{ topTopic }}</span>
          </div>
        </div>
        <SentimentTimeline :data="sentimentTimeline" />
        <EventImpactCards :events="eventSummary" :simulationId="simulationId" />
      </div>

      <!-- Sentiment Tab -->
      <div v-show="activeTab === 'sentiment'" class="tab-panel">
        <SentimentTimeline :data="sentimentTimeline" />
        <ArchetypeHeatmap :data="archetypeActivity" />
      </div>

      <!-- Events Tab -->
      <div v-show="activeTab === 'events'" class="tab-panel">
        <EventImpactCards :events="eventSummary" :simulationId="simulationId" />
      </div>

      <!-- Non-Participation Tab -->
      <div v-show="activeTab === 'non-participation'" class="tab-panel">
        <NonParticipationPanel :data="nonParticipationData" />
      </div>

      <!-- Topics Tab -->
      <div v-show="activeTab === 'topics'" class="tab-panel">
        <TopicWordCloud :data="topicCascade" />
      </div>

      <!-- Agents Tab -->
      <div v-show="activeTab === 'agents'" class="tab-panel">
        <div class="agent-list">
          <div
            v-for="agent in agentSummary"
            :key="agent.agent_id"
            class="agent-card"
          >
            <div class="agent-header">
              <span class="agent-name">{{ agent.name }}</span>
              <span class="agent-archetype">{{ agent.archetype }}</span>
              <span v-if="agent.stance" class="agent-stance" :class="stanceClass(agent.stance)">{{ agent.stance }}</span>
            </div>

            <!-- Latest expressed opinion — read this to decide your intervention -->
            <div v-if="agent.latest_opinion" class="agent-opinion">
              <span class="opinion-quote">“{{ agent.latest_opinion }}”</span>
              <span v-if="agent.latest_opinion_round != null" class="opinion-round">round {{ agent.latest_opinion_round }}</span>
            </div>
            <div v-else class="agent-opinion agent-opinion--empty">
              No opinion expressed during the run.
            </div>

            <div class="agent-stats">
              <div class="stat">
                <span class="stat-label">Actions</span>
                <span class="stat-value">{{ agent.action_count }}</span>
              </div>
              <div class="stat">
                <span class="stat-label">Avg Impact</span>
                <span class="stat-value">{{ agent.avg_impact.toFixed(2) }}</span>
              </div>
              <div class="stat">
                <span class="stat-label">Expressed</span>
                <span class="stat-value">{{ agent.express_count }}</span>
              </div>
              <div class="stat">
                <span class="stat-label">Responded</span>
                <span class="stat-value">{{ agent.respond_count }}</span>
              </div>
            </div>

            <!-- Intervene -->
            <button
              v-if="openIntervene !== agent.agent_id"
              class="intervene-toggle"
              @click="startIntervene(agent.agent_id)"
            >
              Pose intervention →
            </button>
            <div v-else class="intervene-box">
              <textarea
                v-model="interveneText[agent.agent_id]"
                class="intervene-input"
                rows="2"
                placeholder="Tell this agent something new — e.g. a concession, a price, a guarantee — and see how their reaction shifts."
                :disabled="interveneBusy === agent.agent_id"
              ></textarea>
              <div class="intervene-actions">
                <button class="intervene-cancel" @click="cancelIntervene" :disabled="interveneBusy === agent.agent_id">Cancel</button>
                <button
                  class="intervene-send"
                  @click="sendIntervene(agent)"
                  :disabled="interveneBusy === agent.agent_id || !(interveneText[agent.agent_id] || '').trim()"
                >
                  {{ interveneBusy === agent.agent_id ? 'Posing…' : 'Send' }}
                </button>
              </div>

              <!-- Result: stance before/after + the agent's reply -->
              <div v-if="interveneResult[agent.agent_id]" class="intervene-result">
                <div class="result-stance">
                  <span class="result-label">{{ interveneResult[agent.agent_id].mode === 'product' ? 'Reaction' : 'Stance' }}</span>
                  <span class="stance-pill" :class="stanceClass(interveneResult[agent.agent_id].stance_before)">{{ interveneResult[agent.agent_id].stance_before_label || interveneResult[agent.agent_id].stance_before || '—' }}</span>
                  <span class="stance-arrow">→</span>
                  <span class="stance-pill" :class="stanceClass(interveneResult[agent.agent_id].stance_after)">{{ interveneResult[agent.agent_id].stance_after_label || interveneResult[agent.agent_id].stance_after || '—' }}</span>
                  <span v-if="interveneResult[agent.agent_id].stance_changed" class="stance-changed">shifted</span>
                  <span v-else class="stance-unchanged">no change</span>
                </div>
                <div v-if="interveneResult[agent.agent_id].response" class="result-reply">
                  “{{ interveneResult[agent.agent_id].response }}”
                </div>
              </div>
              <div v-if="interveneError[agent.agent_id]" class="intervene-err">{{ interveneError[agent.agent_id] }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Interviews Tab -->
      <div v-show="activeTab === 'interviews'" class="tab-panel">
        <AgentInterviewPanel :simulation-id="simulationId" />
      </div>

      <!-- Compare Tab -->
      <div v-show="activeTab === 'compare'" class="tab-panel">
        <PolicyComparisonPanel :current-simulation-id="simulationId" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, reactive } from 'vue'
import { getOverview, getSentimentTimeline, getArchetypeActivity, getEventSummary, getTopicCascade, getAgentSummary, getNonParticipation } from '../api/analysis'
import { interveneWithAgent } from '../api/simulation'
import SentimentTimeline from './SentimentTimeline.vue'
import ArchetypeHeatmap from './ArchetypeHeatmap.vue'
import EventImpactCards from './EventImpactCards.vue'
import TopicWordCloud from './TopicWordCloud.vue'
import AgentInterviewPanel from './AgentInterviewPanel.vue'
import PolicyComparisonPanel from './PolicyComparisonPanel.vue'
import NonParticipationPanel from './NonParticipationPanel.vue'

const props = defineProps({
  simulationId: {
    type: String,
    required: true
  }
})

const tabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'sentiment', label: 'Sentiment' },
  { id: 'events', label: 'Events' },
  { id: 'non-participation', label: 'Non-Participation' },
  { id: 'topics', label: 'Topics' },
  { id: 'agents', label: 'Agents' },
  { id: 'interviews', label: 'Interviews' },
  { id: 'compare', label: 'Compare' },
]

const activeTab = ref('overview')
const loading = ref(true)
const error = ref(null)

// Data stores
const overview = ref(null)
const sentimentTimeline = ref([])
const archetypeActivity = ref([])
const eventSummary = ref([])
const topicCascade = ref([])
const agentSummary = ref([])
const nonParticipationData = ref(null)

const topTopic = computed(() => {
  if (!topicCascade.value.length) return '-'
  return topicCascade.value[0].topic
})

// ── Post-sim intervention (Agents tab) ─────────────────────────────
// Read an agent's latest opinion, then pose an intervention and see how
// their stance shifts. Keyed by agent_id so each card is independent.
const openIntervene = ref(null)         // which agent's box is open
const interveneText = reactive({})      // agent_id -> draft text
const interveneBusy = ref(null)         // agent_id currently sending
const interveneResult = reactive({})    // agent_id -> result payload
const interveneError = reactive({})     // agent_id -> error string

const stanceClass = (stance) => {
  const s = (stance || '').toLowerCase()
  if (['support', 'supportive', 'favourable', 'favorable', 'positive'].some(k => s.includes(k))) return 'stance-support'
  if (['oppose', 'against', 'hostile', 'negative'].some(k => s.includes(k))) return 'stance-oppose'
  if (['neutral', 'undecided', 'mixed', 'concerned'].some(k => s.includes(k))) return 'stance-neutral'
  return 'stance-neutral'
}

const startIntervene = (agentId) => {
  openIntervene.value = agentId
  if (!(agentId in interveneText)) interveneText[agentId] = ''
}

const cancelIntervene = () => {
  openIntervene.value = null
}

const sendIntervene = async (agent) => {
  const agentId = agent.agent_id
  const text = (interveneText[agentId] || '').trim()
  if (!text) return
  interveneBusy.value = agentId
  delete interveneError[agentId]
  try {
    const res = await interveneWithAgent(props.simulationId, agentId, { intervention_text: text })
    if (res.success && res.data) {
      interveneResult[agentId] = res.data
      // Reflect the new stance on the card immediately
      if (res.data.stance_after) agent.stance = res.data.stance_after
    } else {
      interveneError[agentId] = res.error || 'Intervention failed.'
    }
  } catch (err) {
    interveneError[agentId] = err.message || 'Intervention failed.'
  } finally {
    interveneBusy.value = null
  }
}

const loadData = async () => {
  if (!props.simulationId) {
    loading.value = false
    error.value = 'No simulation is linked to this report yet.'
    return
  }

  loading.value = true
  error.value = null

  try {
    // The axios interceptor unwraps response.data into the top-level result,
    // so each *Res below IS the `{success, data}` body — not the raw axios
    // response. Read res.success / res.data, NOT res.data.success / res.data.data.
    const overviewRes = await getOverview(props.simulationId)
    if (overviewRes.success) {
      overview.value = overviewRes.data
      sentimentTimeline.value = overview.value.sentiment_timeline || []
      eventSummary.value = overview.value.event_summary || []
      topicCascade.value = overview.value.topic_cascade || []
    } else {
      // Defensive: a {success:false} body normally throws via the interceptor,
      // but if it ever reaches here, show a clear message instead of a blank
      // dashboard behind a cleared spinner.
      error.value = overviewRes.error || 'No analytics data is available for this simulation yet.'
      return
    }

    // Load other data in parallel
    const [activityRes, eventsRes, topicsRes, agentsRes, nonPartRes] = await Promise.all([
      getArchetypeActivity(props.simulationId),
      getEventSummary(props.simulationId),
      getTopicCascade(props.simulationId),
      getAgentSummary(props.simulationId),
      getNonParticipation(props.simulationId),
    ])

    if (activityRes.success) {
      archetypeActivity.value = activityRes.data
    }
    if (eventsRes.success) {
      eventSummary.value = eventsRes.data
    }
    if (topicsRes.success) {
      topicCascade.value = topicsRes.data
    }
    if (agentsRes.success) {
      agentSummary.value = agentsRes.data
    }
    if (nonPartRes.success) {
      nonParticipationData.value = nonPartRes.data
    }
  } catch (err) {
    // Map the common failures to actionable messages instead of a raw axios string.
    const status = err && err.httpStatus
    if (status === 404) {
      error.value = 'No analytics data found for this simulation. It may still be running, or it produced no recorded activity.'
    } else if (err && err.code === 'ECONNABORTED') {
      error.value = 'Analytics request timed out. Is the backend running?'
    } else if (err && err.message === 'Network Error') {
      error.value = 'Cannot reach the backend. Check that the server is running.'
    } else {
      error.value = (err && err.message) || 'Failed to load analytics'
    }
    console.error('Dashboard load error:', err)
  } finally {
    loading.value = false
  }
}

watch(() => props.simulationId, (newId) => {
  if (newId) loadData()
}, { immediate: true })

onMounted(() => {
  if (props.simulationId) loadData()
})
</script>

<style scoped>
.simulation-dashboard {
  padding: 24px;
  background: #FAFAFA;
  min-height: 100%;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  /* Wrap the tab row onto its own line when the title + ~8 tabs can't fit on
     one line, instead of clipping the trailing tabs off the visible edge. */
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid #EAEAEA;
}

.dashboard-title {
  font-family: 'JetBrains Mono', monospace;
  font-size: 20px;
  font-weight: 700;
  margin: 0;
}

.dashboard-tabs {
  display: flex;
  gap: 4px;
  background: #F0F0F0;
  padding: 4px;
  border-radius: 6px;
  /* When even one row of tabs is wider than the panel, scroll horizontally so
     every sub-tab stays reachable rather than being clipped. */
  max-width: 100%;
  overflow-x: auto;
}

/* Tabs must keep their size in the scroll row — never shrink so small they
   collapse or become unclickable. */
.tab-btn {
  flex: 0 0 auto;
  white-space: nowrap;
}

.tab-btn {
  border: none;
  background: transparent;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 600;
  color: #666;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  font-family: 'Space Grotesk', sans-serif;
}

.tab-btn.active {
  background: #FFF;
  color: #000;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.dashboard-loading,
.dashboard-error {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px;
  color: #666;
}

.loading-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #E0E0E0;
  border-top-color: #333;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-icon {
  font-size: 20px;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.metric-card {
  background: #FFF;
  border: 1px solid #EAEAEA;
  border-radius: 8px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.metric-label {
  font-size: 12px;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
}

.metric-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 28px;
  font-weight: 700;
  color: #000;
}

.topic-value {
  font-size: 18px;
  text-transform: capitalize;
}

.tab-panel {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.agent-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.agent-card {
  background: #FFF;
  border: 1px solid #EAEAEA;
  border-radius: 8px;
  padding: 16px;
}

.agent-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #F0F0F0;
}

.agent-name {
  font-weight: 700;
  font-size: 14px;
  margin-right: auto;
}

.agent-archetype {
  font-size: 11px;
  padding: 4px 8px;
  background: #F5F5F5;
  border-radius: 4px;
  color: #666;
  text-transform: lowercase;
}

.agent-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-label {
  font-size: 11px;
  color: #999;
}

.stat-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 16px;
  font-weight: 600;
}

/* Stance badges */
.agent-stance,
.stance-pill {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
  text-transform: lowercase;
  white-space: nowrap;
}
.stance-support { background: rgba(30, 158, 90, 0.12); color: #1E9E5A; }
.stance-oppose  { background: #FDECEA; color: #C5283D; }
.stance-neutral { background: #F5F5F5; color: #666; }

/* Latest opinion */
.agent-opinion {
  font-size: 12.5px;
  line-height: 1.5;
  color: #333;
  margin-bottom: 12px;
}
.opinion-quote { font-style: italic; }
.opinion-round {
  display: inline-block;
  margin-left: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #999;
}
.agent-opinion--empty {
  font-style: italic;
  color: #BBB;
}

/* Intervene */
.intervene-toggle {
  margin-top: 12px;
  width: 100%;
  padding: 7px 0;
  background: transparent;
  border: 1px dashed #1E9E5A;
  color: #1E9E5A;
  font-size: 12px;
  font-weight: 600;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.intervene-toggle:hover { background: rgba(30, 158, 90, 0.06); }

.intervene-box {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #F0F0F0;
}
.intervene-input {
  width: 100%;
  box-sizing: border-box;
  padding: 8px;
  border: 1px solid #DDD;
  border-radius: 6px;
  font-family: inherit;
  font-size: 12.5px;
  resize: vertical;
}
.intervene-input:focus { outline: none; border-color: #1E9E5A; }
.intervene-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
.intervene-cancel {
  padding: 6px 12px;
  background: transparent;
  border: 1px solid #DDD;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  color: #666;
}
.intervene-send {
  padding: 6px 14px;
  background: #1E9E5A;
  border: 1px solid #1E9E5A;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  cursor: pointer;
}
.intervene-send:disabled { opacity: 0.5; cursor: not-allowed; }

.intervene-result {
  margin-top: 12px;
  padding: 10px;
  background: #F7FBF8;
  border: 1px solid #E0EFE6;
  border-radius: 6px;
}
.result-stance {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 12px;
}
.result-label { color: #999; font-size: 11px; }
.stance-arrow { color: #999; }
.stance-changed {
  font-size: 10px;
  font-weight: 700;
  color: #1E9E5A;
  text-transform: uppercase;
}
.stance-unchanged {
  font-size: 10px;
  color: #999;
  text-transform: uppercase;
}
.result-reply {
  margin-top: 8px;
  font-size: 12.5px;
  font-style: italic;
  line-height: 1.5;
  color: #333;
}
.intervene-err {
  margin-top: 8px;
  font-size: 12px;
  color: #C5283D;
}
</style>
