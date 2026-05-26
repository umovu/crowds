<template>
  <div class="comparison-panel">
    <div class="comparison-header">
      <h3>Policy Comparison</h3>
      <p class="hint">Compare baseline simulation against an intervention fork to measure impact</p>
    </div>

    <div class="sim-selector-row">
      <div class="sim-select-group">
        <label>Baseline Simulation</label>
        <select v-model="baselineId" class="sim-select">
          <option value="">Select baseline...</option>
          <option v-for="sim in simulations" :key="sim.id" :value="sim.id">
            {{ sim.name || sim.id }}
          </option>
        </select>
      </div>
      <div class="vs-badge">VS</div>
      <div class="sim-select-group">
        <label>Intervention Simulation</label>
        <select v-model="interventionId" class="sim-select">
          <option value="">Select intervention...</option>
          <option v-for="sim in simulations" :key="sim.id" :value="sim.id">
            {{ sim.name || sim.id }}
          </option>
        </select>
      </div>
      <button
        class="compare-btn"
        :disabled="!baselineId || !interventionId || loading"
        @click="loadComparison"
      >
        {{ loading ? 'Loading...' : 'Compare' }}
      </button>
    </div>

    <div v-if="error" class="error-message">{{ error }}</div>

    <div v-if="comparisonData" class="comparison-results">
      <!-- Key Metrics -->
      <div class="metrics-grid">
        <div class="metric-card">
          <span class="metric-label">Agents Interviewed</span>
          <span class="metric-value">{{ comparisonData.baseline.agent_count }}</span>
        </div>
        <div class="metric-card">
          <span class="metric-label">Stance Changes</span>
          <span class="metric-value" :class="{ 'positive': comparisonData.changed_count > 0 }">
            {{ comparisonData.changed_count }}
          </span>
        </div>
        <div class="metric-card">
          <span class="metric-label">Avg Radicalism Shift</span>
          <span class="metric-value" :class="radicalismClass(comparisonData.avg_radicalism_delta)">
            {{ comparisonData.avg_radicalism_delta > 0 ? '+' : '' }}{{ comparisonData.avg_radicalism_delta.toFixed(2) }}
          </span>
        </div>
        <div class="metric-card">
          <span class="metric-label">Protest Risk Change</span>
          <span class="metric-value" :class="riskClass(comparisonData.protest_risk_delta)">
            {{ comparisonData.protest_risk_delta > 0 ? '+' : '' }}{{ comparisonData.protest_risk_delta.toFixed(1) }}%
          </span>
        </div>
      </div>

      <!-- Stance Distribution Comparison -->
      <div class="comparison-section">
        <h4>Stance Distribution</h4>
        <div class="stance-bars">
          <div
            v-for="stance in ['support', 'neutral', 'concerned', 'oppose', 'resist']"
            :key="stance"
            class="stance-bar-row"
          >
            <span class="stance-label">{{ stance }}</span>
            <div class="stance-bar-group">
              <div class="stance-bar-container">
                <div
                  class="stance-bar baseline"
                  :class="`stance-${stance}`"
                  :style="{ width: stancePct(comparisonData.baseline.stance_distribution, stance) + '%' }"
                ></div>
                <span class="stance-pct">
                  {{ stanceCount(comparisonData.baseline.stance_distribution, stance) }}
                </span>
              </div>
              <div class="stance-bar-container">
                <div
                  class="stance-bar intervention"
                  :class="`stance-${stance}`"
                  :style="{ width: stancePct(comparisonData.intervention.stance_distribution, stance) + '%' }"
                ></div>
                <span class="stance-pct">
                  {{ stanceCount(comparisonData.intervention.stance_distribution, stance) }}
                </span>
              </div>
            </div>
          </div>
        </div>
        <div class="legend">
          <span class="legend-item baseline">Baseline</span>
          <span class="legend-item intervention">Intervention</span>
        </div>
      </div>

      <!-- Agent Changes Table -->
      <div v-if="comparisonData.changed_agents.length > 0" class="comparison-section">
        <h4>Agents Who Changed Position</h4>
        <table class="changes-table">
          <thead>
            <tr>
              <th>Agent</th>
              <th>Archetype</th>
              <th>Baseline Stance</th>
              <th>After Intervention</th>
              <th>Radicalism</th>
              <th>Impact</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="agent in comparisonData.changed_agents" :key="agent.id">
              <td>{{ agent.name }}</td>
              <td>{{ agent.actor_archetype }}</td>
              <td>
                <span class="stance-badge" :class="`stance-${agent.baseline_stance}`">
                  {{ agent.baseline_stance }}
                </span>
              </td>
              <td>
                <span class="stance-badge" :class="`stance-${agent.intervention_stance}`">
                  {{ agent.intervention_stance }}
                </span>
              </td>
              <td>{{ agent.baseline_radicalism }} → {{ agent.intervention_radicalism }}</td>
              <td>
                <span :class="impactClass(agent.stance_delta)">
                  {{ agent.stance_delta > 0 ? '+' : '' }}{{ agent.stance_delta }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-else class="no-changes">
        No agents changed position between baseline and intervention.
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getSimulationAgents } from '../api/simulation'
import { listSimulations } from '../api/simulation'

const props = defineProps({
  currentSimulationId: {
    type: String,
    default: ''
  }
})

const simulations = ref([])
const baselineId = ref('')
const interventionId = ref('')
const loading = ref(false)
const error = ref(null)
const comparisonData = ref(null)

const loadSimulations = async () => {
  try {
    const res = await listSimulations()
    if (res.success) {
      simulations.value = res.data || []
    }
  } catch (e) {
    console.error('Failed to load simulations:', e)
  }
}

const loadComparison = async () => {
  if (!baselineId.value || !interventionId.value) return
  loading.value = true
  error.value = null
  comparisonData.value = null

  try {
    const [baseRes, intvRes] = await Promise.all([
      getSimulationAgents(baselineId.value),
      getSimulationAgents(interventionId.value),
    ])

    if (!baseRes.data?.success || !intvRes.data?.success) {
      error.value = 'Failed to load simulation data'
      return
    }

    const baseline = baseRes.data.data
    const intervention = intvRes.data.data

    comparisonData.value = computeComparison(baseline, intervention)
  } catch (e) {
    error.value = e.message || 'Comparison failed'
  } finally {
    loading.value = false
  }
}

const computeComparison = (baseline, intervention) => {
  const baseAgents = baseline.agents || []
  const intvAgents = intervention.agents || []

  // Build lookup maps
  const baseMap = {}
  baseAgents.forEach(a => { baseMap[a.id] = a })

  const changedAgents = []
  let totalRadicalismDelta = 0
  let changedCount = 0

  const stanceOrder = { resist: -2, oppose: -1, concerned: 0, neutral: 1, support: 2 }

  intvAgents.forEach(intvAgent => {
    const baseAgent = baseMap[intvAgent.id]
    if (!baseAgent) return

    const stanceDelta = (stanceOrder[intvAgent.stance] || 0) - (stanceOrder[baseAgent.stance] || 0)
    const radDelta = (intvAgent.current_radicalism || intvAgent.base_radicalism || 1) -
                     (baseAgent.current_radicalism || baseAgent.base_radicalism || 1)

    if (intvAgent.stance !== baseAgent.stance || radDelta !== 0) {
      changedAgents.push({
        id: intvAgent.id,
        name: intvAgent.name,
        actor_archetype: intvAgent.actor_archetype,
        baseline_stance: baseAgent.stance,
        intervention_stance: intvAgent.stance,
        baseline_radicalism: baseAgent.base_radicalism,
        intervention_radicalism: intvAgent.current_radicalism || intvAgent.base_radicalism,
        stance_delta: stanceDelta,
        radicalism_delta: radDelta,
      })
      totalRadicalismDelta += radDelta
      changedCount++
    }
  })

  // Sort by impact (most positive change first = moved toward support)
  changedAgents.sort((a, b) => b.stance_delta - a.stance_delta)

  // Calculate protest risk (simple heuristic: % of oppose + resist)
  const protestRisk = (agents) => {
    const total = agents.length || 1
    const risky = agents.filter(a => a.stance === 'oppose' || a.stance === 'resist').length
    return (risky / total) * 100
  }

  const baseRisk = protestRisk(baseAgents)
  const intvRisk = protestRisk(intvAgents)

  return {
    baseline: {
      agent_count: baseAgents.length,
      stance_distribution: countStances(baseAgents),
    },
    intervention: {
      agent_count: intvAgents.length,
      stance_distribution: countStances(intvAgents),
    },
    changed_count: changedCount,
    changed_agents: changedAgents,
    avg_radicalism_delta: changedCount > 0 ? totalRadicalismDelta / changedCount : 0,
    protest_risk_delta: intvRisk - baseRisk,
  }
}

const countStances = (agents) => {
  const dist = {}
  agents.forEach(a => {
    dist[a.stance] = (dist[a.stance] || 0) + 1
  })
  return dist
}

const stancePct = (distribution, stance) => {
  const total = Object.values(distribution).reduce((a, b) => a + b, 0) || 1
  return ((distribution[stance] || 0) / total) * 100
}

const stanceCount = (distribution, stance) => {
  return distribution[stance] || 0
}

const radicalismClass = (delta) => {
  if (delta < 0) return 'positive'
  if (delta > 0) return 'negative'
  return 'neutral'
}

const riskClass = (delta) => {
  if (delta < 0) return 'positive'
  if (delta > 0) return 'negative'
  return 'neutral'
}

const impactClass = (delta) => {
  if (delta > 0) return 'positive'
  if (delta < 0) return 'negative'
  return 'neutral'
}

onMounted(() => {
  loadSimulations()
  if (props.currentSimulationId) {
    baselineId.value = props.currentSimulationId
  }
})
</script>

<style scoped>
.comparison-panel {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
}

.comparison-header {
  margin-bottom: 20px;
}

.comparison-header h3 {
  margin: 0 0 8px 0;
}

.hint {
  color: #888;
  font-size: 13px;
  margin: 0;
}

.sim-selector-row {
  display: flex;
  align-items: flex-end;
  gap: 16px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.sim-select-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  min-width: 200px;
}

.sim-select-group label {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
}

.sim-select {
  padding: 10px 12px;
  border: 1px solid #d0d0d0;
  border-radius: 8px;
  font-size: 14px;
  font-family: inherit;
}

.vs-badge {
  font-weight: 700;
  color: #888;
  padding-bottom: 10px;
}

.compare-btn {
  padding: 10px 24px;
  background: #2196f3;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
}

.compare-btn:hover:not(:disabled) {
  background: #1976d2;
}

.compare-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.metric-card {
  background: #f8f9fa;
  padding: 16px;
  border-radius: 10px;
  text-align: center;
}

.metric-label {
  display: block;
  font-size: 12px;
  color: #666;
  margin-bottom: 8px;
}

.metric-value {
  display: block;
  font-size: 24px;
  font-weight: 700;
  color: #333;
}

.metric-value.positive { color: #2e7d32; }
.metric-value.negative { color: #c62828; }
.metric-value.neutral { color: #666; }

.comparison-section {
  margin-bottom: 24px;
}

.comparison-section h4 {
  margin: 0 0 16px 0;
  font-size: 15px;
}

.stance-bars {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.stance-bar-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.stance-label {
  width: 90px;
  font-size: 13px;
  font-weight: 600;
  text-transform: capitalize;
  color: #555;
}

.stance-bar-group {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stance-bar-container {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 24px;
}

.stance-bar {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
  min-width: 4px;
}

.stance-bar.baseline { opacity: 0.7; }

.stance-pct {
  font-size: 12px;
  color: #666;
  min-width: 30px;
}

.legend {
  display: flex;
  gap: 16px;
  margin-top: 12px;
  justify-content: center;
}

.legend-item {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 12px;
}

.legend-item.baseline { background: #e0e0e0; }
.legend-item.intervention { background: #2196f3; color: white; }

.changes-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.changes-table th {
  text-align: left;
  padding: 10px;
  border-bottom: 2px solid #e0e0e0;
  font-weight: 600;
  color: #555;
}

.changes-table td {
  padding: 10px;
  border-bottom: 1px solid #f0f0f0;
}

.changes-table tr:hover {
  background: #f8f9fa;
}

.no-changes {
  text-align: center;
  color: #888;
  padding: 40px;
}

.error-message {
  background: #ffebee;
  color: #c62828;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 16px;
}

.positive { color: #2e7d32; font-weight: 600; }
.negative { color: #c62828; font-weight: 600; }
.neutral { color: #666; }

.stance-badge {
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.stance-support { background: #e8f5e9; color: #2e7d32; }
.stance-neutral { background: #f5f5f5; color: #666; }
.stance-concerned { background: #fff3e0; color: #e65100; }
.stance-oppose { background: #ffebee; color: #c62828; }
.stance-resist { background: #fce4ec; color: #ad1457; }
</style>
