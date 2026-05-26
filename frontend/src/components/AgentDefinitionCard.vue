<template>
  <div class="agent-card" :class="{ 'expanded': expanded }">
    <div class="card-main" @click="toggleExpand">
      <div class="card-identity">
        <div class="avatar">{{ initials }}</div>
        <div class="identity-info">
          <div class="name-row">
            <span class="agent-name">{{ agent.name }}</span>
            <span v-if="agent.occupation" class="agent-occupation">{{ agent.occupation }}</span>
          </div>
          <div class="meta-row">
            <span v-if="agent.gender" class="meta-tag">{{ agent.gender }}</span>
            <span v-if="agent.age" class="meta-tag">{{ agent.age }} yrs</span>
            <span v-if="agent.mbti" class="meta-tag">{{ agent.mbti }}</span>
            <span v-if="stanceLabel" class="meta-tag stance" :class="stanceClass">{{ stanceLabel }}</span>
            <span v-if="agent._source === 'seed_document'" class="meta-tag source-doc">from doc</span>
            <span v-if="agent.is_core_focus" class="meta-tag core-focus">★ Core Focus</span>
            <span v-if="isCustom" class="meta-tag custom-agent">◆ Custom</span>
          </div>
        </div>
      </div>
      <div class="card-actions">
        <button class="action-icon" @click.stop="$emit('toggle-core-focus', agent)" :title="agent.is_core_focus ? 'Remove Core Focus' : 'Set as Core Focus'">★</button>
        <button class="action-icon" @click.stop="$emit('edit', agent)" title="Edit">✎</button>
        <button class="action-icon delete" @click.stop="$emit('remove', agent)" title="Remove">×</button>
        <span class="expand-icon" :class="{ rotated: expanded }">▼</span>
      </div>
    </div>

    <div v-if="expanded" class="card-detail">
      <div class="detail-section">
        <p class="detail-persona">{{ agent.persona }}</p>
        <p v-if="agent.background_story" class="detail-story">{{ agent.background_story }}</p>
      </div>

      <div class="detail-stats">
        <div v-if="hasEmotions" class="stat-group">
          <span class="stat-label">Emotions</span>
          <div class="emotion-bars">
            <div v-for="(val, key) in visibleEmotions" :key="key" class="emotion-bar">
              <span class="bar-label">{{ key }}</span>
              <div class="bar-track">
                <div class="bar-fill" :style="{ width: (val / 10 * 100) + '%', background: emotionColor(key) }"></div>
              </div>
              <span class="bar-val">{{ val }}</span>
            </div>
          </div>
        </div>

        <div v-if="hasAttitudes" class="stat-group">
          <span class="stat-label">Attitudes</span>
          <div class="attitude-bars">
            <div v-for="(att, idx) in agent.attitudes.slice(0, 4)" :key="idx" class="attitude-bar">
              <span class="bar-label">{{ att.topic }}</span>
              <div class="bar-track">
                <div class="bar-fill" :class="attitudeClass(att.rating)" :style="{ width: (att.rating / 10 * 100) + '%' }"></div>
              </div>
              <span class="bar-val">{{ att.rating }}</span>
            </div>
          </div>
        </div>

        <div v-if="hasRelationships" class="stat-group">
          <span class="stat-label">Relationships</span>
          <div class="rel-chips">
            <span v-for="(rel, idx) in allRelationships.slice(0, 6)" :key="idx" class="rel-chip">
              {{ rel.name }} <span class="rel-strength">{{ rel.strength }}</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  agent: { type: Object, required: true }
})

defineEmits(['edit', 'remove'])

const expanded = ref(false)

function toggleExpand() {
  expanded.value = !expanded.value
}

const initials = computed(() => {
  const name = props.agent.name || '?'
  const parts = name.split(' ').filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
  return name.substring(0, 2).toUpperCase()
})

const stanceLabel = computed(() => {
  const atts = props.agent.attitudes || []
  if (!atts.length) return null
  const avg = atts.reduce((s, a) => s + (a.rating || 5), 0) / atts.length
  if (avg >= 7.5) return 'Supportive'
  if (avg <= 3.5) return 'Opposing'
  return 'Neutral'
})

const stanceClass = computed(() => {
  const label = stanceLabel.value
  if (label === 'Supportive') return 'stance-support'
  if (label === 'Opposing') return 'stance-oppose'
  return 'stance-neutral'
})

const hasEmotions = computed(() => {
  const e = props.agent.emotions || {}
  return Object.values(e).some(v => v > 0)
})

const visibleEmotions = computed(() => {
  const e = props.agent.emotions || {}
  return Object.fromEntries(Object.entries(e).filter(([, v]) => v > 0))
})

const hasAttitudes = computed(() => {
  return (props.agent.attitudes || []).length > 0
})

const hasRelationships = computed(() => {
  return allRelationships.value.length > 0
})

const allRelationships = computed(() => {
  const rels = props.agent.relationships || {}
  const result = []
  for (const type of ['family', 'friends', 'colleagues']) {
    for (const r of (rels[type] || [])) {
      result.push({ ...r, type })
    }
  }
  return result
})

const isCustom = computed(() => {
  const src = props.agent.source_entity_type || ''
  return src.startsWith('custom')
})

function emotionColor(key) {
  const map = {
    sadness: '#5B8DB8',
    joy: '#F4A261',
    fear: '#8B5CF6',
    disgust: '#84A98C',
    anger: '#E63946',
    surprise: '#F4D35E',
  }
  return map[key] || '#999'
}

function attitudeClass(rating) {
  if (rating >= 7) return 'att-support'
  if (rating <= 3) return 'att-oppose'
  return 'att-neutral'
}
</script>

<style scoped>
.agent-card {
  background: #fff;
  border: 1px solid #EAEAEA;
  transition: all 0.2s;
}

.agent-card:hover {
  border-color: #CCC;
}

.card-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  gap: 12px;
}

.card-identity {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.avatar {
  width: 36px;
  height: 36px;
  background: #000;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  font-weight: 700;
  flex-shrink: 0;
}

.identity-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.agent-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: #000;
}

.agent-occupation {
  font-size: 0.75rem;
  color: #999;
}

.meta-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.meta-tag {
  font-size: 0.7rem;
  padding: 2px 6px;
  background: #F5F5F5;
  color: #666;
  border: 1px solid #EEE;
}

.meta-tag.stance {
  font-weight: 600;
}

.stance-support { background: #E8F5E9; color: #2E7D32; border-color: #C8E6C9; }
.stance-oppose { background: #FFEBEE; color: #C62828; border-color: #FFCDD2; }
.stance-neutral { background: #F5F5F5; color: #666; border-color: #EEE; }
.source-doc { background: #E3F2FD; color: #1565C0; border-color: #BBDEFB; }
.core-focus { background: #FFF3E0; color: #E65100; border-color: #FFE0B2; }
.custom-agent { background: #E8F5E9; color: #2E7D32; border-color: #C8E6C9; }

.card-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.action-icon {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: #999;
  font-size: 0.85rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 2px;
  transition: all 0.2s;
}

.action-icon:hover {
  background: #F5F5F5;
  color: #000;
}

.action-icon.delete:hover {
  background: #FFEBEE;
  color: #C62828;
}

.action-icon[title*="Core Focus"]:hover,
.action-icon[title*="Core Focus"].active {
  color: #E65100;
}

.expand-icon {
  font-size: 0.65rem;
  color: #CCC;
  margin-left: 4px;
  transition: transform 0.2s;
}

.expand-icon.rotated {
  transform: rotate(180deg);
}

/* Detail */
.card-detail {
  padding: 0 16px 16px;
  border-top: 1px solid #F5F5F5;
  animation: slideDown 0.2s ease;
}

@keyframes slideDown {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.detail-section {
  padding: 12px 0;
}

.detail-persona {
  font-size: 0.85rem;
  line-height: 1.6;
  color: #333;
  margin: 0;
}

.detail-story {
  font-size: 0.8rem;
  line-height: 1.5;
  color: #666;
  margin: 8px 0 0;
}

.detail-stats {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stat-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stat-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: #999;
}

/* Bars */
.emotion-bars,
.attitude-bars {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.emotion-bar,
.attitude-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.bar-label {
  font-size: 0.75rem;
  color: #666;
  width: 80px;
  text-transform: capitalize;
  flex-shrink: 0;
}

.bar-track {
  flex: 1;
  height: 6px;
  background: #F0F0F0;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  transition: width 0.3s;
}

.bar-val {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: #999;
  width: 24px;
  text-align: right;
}

.att-support { background: #2E7D32; }
.att-oppose { background: #C62828; }
.att-neutral { background: #999; }

/* Rel chips */
.rel-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.rel-chip {
  font-size: 0.75rem;
  padding: 3px 8px;
  background: #FAFAFA;
  border: 1px solid #EEE;
  color: #666;
}

.rel-strength {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: #999;
  margin-left: 4px;
}
</style>
