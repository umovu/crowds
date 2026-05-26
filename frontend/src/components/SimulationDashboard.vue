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
import { ref, computed, onMounted, watch } from 'vue'
import { getOverview, getSentimentTimeline, getArchetypeActivity, getEventSummary, getTopicCascade, getAgentSummary, getNonParticipation } from '../api/analysis'
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

const loadData = async () => {
  if (!props.simulationId) return
  
  loading.value = true
  error.value = null

  try {
    // Load overview first
    const overviewRes = await getOverview(props.simulationId)
    if (overviewRes.data?.success) {
      overview.value = overviewRes.data.data
      sentimentTimeline.value = overview.value.sentiment_timeline || []
      eventSummary.value = overview.value.event_summary || []
      topicCascade.value = overview.value.topic_cascade || []
    }

    // Load other data in parallel
    const [activityRes, eventsRes, topicsRes, agentsRes, nonPartRes] = await Promise.all([
      getArchetypeActivity(props.simulationId),
      getEventSummary(props.simulationId),
      getTopicCascade(props.simulationId),
      getAgentSummary(props.simulationId),
      getNonParticipation(props.simulationId),
    ])

    if (activityRes.data?.success) {
      archetypeActivity.value = activityRes.data.data
    }
    if (eventsRes.data?.success) {
      eventSummary.value = eventsRes.data.data
    }
    if (topicsRes.data?.success) {
      topicCascade.value = topicsRes.data.data
    }
    if (agentsRes.data?.success) {
      agentSummary.value = agentsRes.data.data
    }
    if (nonPartRes.data?.success) {
      nonParticipationData.value = nonPartRes.data.data
    }
  } catch (err) {
    error.value = err.message || 'Failed to load analytics'
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
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #F0F0F0;
}

.agent-name {
  font-weight: 700;
  font-size: 14px;
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
</style>
