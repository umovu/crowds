<template>
  <div class="chart-container">
    <h3 class="chart-title">Non-Participation Analysis</h3>

    <div v-if="!data || data.total_non_participation_actions === 0" class="no-data">
      No non-participation actions recorded during this simulation.
    </div>

    <div v-else class="analysis-content">
      <!-- Summary Cards -->
      <div class="summary-row">
        <div class="summary-card">
          <span class="summary-value">{{ data.total_non_participation_actions }}</span>
          <span class="summary-label">Total Silent Actions</span>
        </div>
        <div class="summary-card">
          <span class="summary-value">{{ reasonCount }}</span>
          <span class="summary-label">Reason Categories</span>
        </div>
        <div class="summary-card">
          <span class="summary-value">{{ archetypeCount }}</span>
          <span class="summary-label">Archetypes Silent</span>
        </div>
      </div>

      <!-- Reason Distribution -->
      <div class="section">
        <h4 class="section-title">Why Agents Stayed Silent</h4>
        <div class="bar-chart">
          <div
            v-for="(count, reason) in sortedByReason"
            :key="reason"
            class="bar-row"
          >
            <span class="bar-label">{{ reasonLabel(reason) }}</span>
            <div class="bar-track">
              <div
                class="bar-fill"
                :style="{
                  width: (count / maxReasonCount * 100) + '%',
                  background: reasonColor(reason)
                }"
              ></div>
            </div>
            <span class="bar-count">{{ count }}</span>
          </div>
        </div>
      </div>

      <!-- Archetype Distribution -->
      <div class="section">
        <h4 class="section-title">Silent by Archetype</h4>
        <div class="bar-chart">
          <div
            v-for="(count, archetype) in sortedByArchetype"
            :key="archetype"
            class="bar-row"
          >
            <span class="bar-label archetype-label">{{ archetype }}</span>
            <div class="bar-track">
              <div
                class="bar-fill archetype-fill"
                :style="{
                  width: (count / maxArchetypeCount * 100) + '%'
                }"
              ></div>
            </div>
            <span class="bar-count">{{ count }}</span>
          </div>
        </div>
      </div>

      <!-- Round Timeline -->
      <div v-if="data.by_round && data.by_round.length > 0" class="section">
        <h4 class="section-title">Silence by Round</h4>
        <div class="round-chart">
          <div
            v-for="roundData in data.by_round.slice(0, 20)"
            :key="roundData.round"
            class="round-bar"
          >
            <div
              class="round-fill"
              :style="{ height: (roundData.count / maxRoundCount * 100) + '%' }"
              :title="`Round ${roundData.round}: ${roundData.count} silent`"
            ></div>
            <span class="round-label">R{{ roundData.round }}</span>
          </div>
        </div>
      </div>

      <!-- Sample Quotes -->
      <div v-if="data.sample_quotes && data.sample_quotes.length > 0" class="section">
        <h4 class="section-title">Sample Agent Thoughts</h4>
        <div class="quotes-list">
          <div
            v-for="(quote, idx) in data.sample_quotes"
            :key="idx"
            class="quote-card"
          >
            <div class="quote-header">
              <span class="quote-name">{{ quote.name }}</span>
              <span class="quote-archetype">{{ quote.archetype }}</span>
              <span class="quote-action-type">{{ quote.action_type }}</span>
            </div>
            <div class="quote-category">
              <span class="category-badge" :class="'cat-' + quote.reason_category">
                {{ reasonLabel(quote.reason_category) }}
              </span>
            </div>
            <div v-if="quote.reason" class="quote-reason">
              <span class="quote-label">Reason:</span>
              <span class="quote-text">{{ quote.reason }}</span>
            </div>
            <div v-if="quote.internal_thought" class="quote-thought">
              <span class="quote-label">Internal Thought:</span>
              <span class="quote-text italic">{{ quote.internal_thought }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: {
    type: Object,
    default: () => null
  }
})

const reasonCount = computed(() => props.data?.by_reason ? Object.keys(props.data.by_reason).length : 0)
const archetypeCount = computed(() => props.data?.by_archetype ? Object.keys(props.data.by_archetype).length : 0)

const sortedByReason = computed(() => {
  if (!props.data?.by_reason) return []
  return Object.entries(props.data.by_reason)
    .sort(([, a], [, b]) => b - a)
})

const sortedByArchetype = computed(() => {
  if (!props.data?.by_archetype) return []
  return Object.entries(props.data.by_archetype)
    .sort(([, a], [, b]) => b - a)
})

const maxReasonCount = computed(() => {
  if (!props.data?.by_reason) return 1
  return Math.max(...Object.values(props.data.by_reason), 1)
})

const maxArchetypeCount = computed(() => {
  if (!props.data?.by_archetype) return 1
  return Math.max(...Object.values(props.data.by_archetype), 1)
})

const maxRoundCount = computed(() => {
  if (!props.data?.by_round) return 1
  return Math.max(...props.data.by_round.map(r => r.count), 1)
})

const REASON_LABELS = {
  distrust: 'Distrust / Manipulation',
  time_constraints: 'Time / Busy',
  apathy: 'Apathy / Not Interested',
  cynicism: 'Cynicism / Nothing Changes',
  exclusion: 'Exclusion / Unheard',
  observational: 'Observational / Watching',
  fear: 'Fear / Risk / Unsafe',
  other: 'Other',
}

const REASON_COLORS = {
  distrust: '#E63946',
  time_constraints: '#457B9D',
  apathy: '#8D99AE',
  cynicism: '#6D597A',
  exclusion: '#F4A261',
  observational: '#2A9D8F',
  fear: '#E76F51',
  other: '#999',
}

function reasonLabel(key) {
  return REASON_LABELS[key] || key
}

function reasonColor(key) {
  return REASON_COLORS[key] || '#999'
}
</script>

<style scoped>
.chart-container {
  background: #FFF;
  border: 1px solid #EAEAEA;
  border-radius: 8px;
  padding: 20px;
}

.chart-title {
  font-family: 'JetBrains Mono', monospace;
  font-size: 14px;
  font-weight: 700;
  margin: 0 0 16px 0;
}

.no-data {
  padding: 40px;
  text-align: center;
  color: #999;
  font-size: 14px;
}

.analysis-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Summary Cards */
.summary-row {
  display: flex;
  gap: 16px;
}

.summary-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px;
  background: #FAFAFA;
  border: 1px solid #EAEAEA;
  border-radius: 6px;
}

.summary-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1.5rem;
  font-weight: 700;
  color: #333;
}

.summary-label {
  font-size: 0.75rem;
  color: #999;
  margin-top: 4px;
}

/* Sections */
.section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-title {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: #999;
  margin: 0;
}

/* Bar Chart */
.bar-chart {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bar-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.bar-label {
  font-size: 0.8rem;
  color: #666;
  width: 140px;
  flex-shrink: 0;
  text-transform: capitalize;
}

.archetype-label {
  width: 160px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
}

.bar-track {
  flex: 1;
  height: 14px;
  background: #F0F0F0;
  border-radius: 2px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s ease;
}

.archetype-fill {
  background: #555;
}

.bar-count {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #999;
  width: 40px;
  text-align: right;
}

/* Round Chart */
.round-chart {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  height: 100px;
  padding: 8px 0;
}

.round-bar {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  height: 100%;
  gap: 4px;
}

.round-fill {
  width: 100%;
  background: #B8B8B8;
  border-radius: 2px 2px 0 0;
  transition: height 0.3s ease;
  min-height: 4px;
}

.round-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  color: #BBB;
}

/* Quotes */
.quotes-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.quote-card {
  background: #FAFAFA;
  border: 1px solid #EAEAEA;
  border-radius: 6px;
  padding: 12px 16px;
}

.quote-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.quote-name {
  font-size: 0.85rem;
  font-weight: 600;
  color: #000;
}

.quote-archetype {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  padding: 2px 6px;
  background: #F0F0F0;
  color: #666;
  border-radius: 3px;
}

.quote-action-type {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: #999;
  margin-left: auto;
}

.quote-category {
  margin-bottom: 8px;
}

.category-badge {
  font-size: 0.7rem;
  padding: 2px 8px;
  border-radius: 3px;
  text-transform: capitalize;
}

.cat-distrust { background: #FFEBEE; color: #C62828; }
.cat-time_constraints { background: #E3F2FD; color: #1565C0; }
.cat-apathy { background: #F5F5F5; color: #666; }
.cat-cynicism { background: #F3E5F5; color: #6A1B9A; }
.cat-exclusion { background: #FFF3E0; color: #E65100; }
.cat-observational { background: #E8F5E9; color: #2E7D32; }
.cat-fear { background: #FBE9E7; color: #BF360C; }
.cat-other { background: #F5F5F5; color: #999; }

.quote-reason,
.quote-thought {
  display: flex;
  gap: 8px;
  font-size: 0.8rem;
  margin-top: 6px;
}

.quote-label {
  font-weight: 600;
  color: #999;
  flex-shrink: 0;
  width: 120px;
}

.quote-text {
  color: #555;
  line-height: 1.4;
}

.quote-text.italic {
  font-style: italic;
  color: #666;
}
</style>