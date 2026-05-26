<template>
  <div class="chart-container">
    <h3 class="chart-title">Event Impact</h3>
    <div v-if="!events.length" class="no-events">
      No events were injected during this simulation.
    </div>
    <div v-else class="event-cards">
      <div
        v-for="event in events"
        :key="event.event_id"
        class="event-card"
        :class="`severity-${event.severity}`"
      >
        <div class="event-header">
          <div class="event-meta">
            <span class="event-round">Round {{ event.round_injected }}</span>
            <span class="event-severity">{{ event.severity }}</span>
          </div>
          <h4 class="event-title">{{ event.title }}</h4>
          <span class="event-source">{{ event.source }}</span>
        </div>
        <p class="event-content">{{ event.content }}</p>
        <div class="event-footer">
          <span class="event-category">{{ event.category }}</span>
          <span class="event-rule">{{ event.rule_id }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  events: {
    type: Array,
    default: () => []
  },
  simulationId: {
    type: String,
    default: ''
  }
})
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

.no-events {
  padding: 40px;
  text-align: center;
  color: #999;
  font-size: 14px;
}

.event-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.event-card {
  border: 1px solid #EAEAEA;
  border-radius: 8px;
  padding: 16px;
  border-left: 4px solid #CCC;
  transition: box-shadow 0.2s;
}

.event-card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}

.severity-low { border-left-color: #4CAF50; }
.severity-medium { border-left-color: #FF9800; }
.severity-high { border-left-color: #F44336; }
.severity-critical { border-left-color: #9C27B0; }

.event-header {
  margin-bottom: 12px;
}

.event-meta {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.event-round {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  padding: 2px 8px;
  background: #F5F5F5;
  border-radius: 4px;
  color: #666;
}

.event-severity {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  font-weight: 600;
}

.severity-low .event-severity { background: #E8F5E9; color: #2E7D32; }
.severity-medium .event-severity { background: #FFF3E0; color: #EF6C00; }
.severity-high .event-severity { background: #FFEBEE; color: #C62828; }
.severity-critical .event-severity { background: #F3E5F5; color: #6A1B9A; }

.event-title {
  font-size: 14px;
  font-weight: 700;
  margin: 0 0 4px 0;
  line-height: 1.4;
}

.event-source {
  font-size: 12px;
  color: #999;
}

.event-content {
  font-size: 13px;
  line-height: 1.5;
  color: #555;
  margin: 0 0 12px 0;
}

.event-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid #F0F0F0;
}

.event-category {
  font-size: 11px;
  color: #666;
  text-transform: capitalize;
}

.event-rule {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #999;
}
</style>
