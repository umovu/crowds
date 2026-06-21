<template>
  <!-- Panel-style agent picker: searchable, archetype-filterable card grid.
       Reused by the sim's chat tab so choosing who to talk to matches the
       Panel Pitch "who's in the room" UX instead of a cramped dropdown. -->
  <div class="agent-picker">
    <div class="ap-controls">
      <input
        v-model="search"
        class="ap-search"
        type="text"
        placeholder="Search agents by name, occupation…"
      />
      <select v-model="archetypeFilter" class="ap-filter">
        <option value="">All groups ({{ agents.length }})</option>
        <option v-for="a in archetypes" :key="a.key" :value="a.key">
          {{ pretty(a.key) }} ({{ a.count }})
        </option>
      </select>
    </div>

    <div v-if="filtered.length === 0" class="ap-empty">No agents match.</div>

    <div class="ap-grid">
      <button
        v-for="agent in filtered"
        :key="agentId(agent)"
        class="ap-card"
        :class="{ selected: isSelected(agent) }"
        :title="agent.persona || agent.background_story || ''"
        @click="select(agent)"
      >
        <img :src="avatar(agent)" :alt="name(agent)" class="ap-avatar" />
        <div class="ap-body">
          <div class="ap-name">{{ name(agent) }}</div>
          <div class="ap-meta">
            <span class="ap-arch">{{ pretty(agent.actor_archetype || 'unknown') }}</span>
            <span v-if="agent.province" class="ap-province">{{ agent.province }}</span>
          </div>
          <div class="ap-tags">
            <span v-if="agent.stance" class="ap-stance" :class="'stance-' + agent.stance">{{ stanceLabel(agent.stance) }}</span>
            <span v-if="agent.budget_tier" class="ap-tier" :class="'tier-' + agent.budget_tier">{{ agent.budget_tier }}</span>
            <span v-if="agent.is_institutional" class="ap-inst">institutional</span>
          </div>
        </div>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { createAvatar } from '@dicebear/core'
import { initials } from '@dicebear/collection'

const props = defineProps({
  agents: { type: Array, default: () => [] },
  selected: { type: Object, default: null },
  // 'policy' shows raw stance words; 'product' maps them to the reaction ladder.
  mode: { type: String, default: 'policy' },
  // Multi-select for roster-building (Console). Selected ids passed in as a Set.
  multiSelect: { type: Boolean, default: false },
  selectedIds: { type: Object, default: () => new Set() },
})
const emit = defineEmits(['select', 'toggle'])

const search = ref('')
const archetypeFilter = ref('')

const agentId = (a) => a.id ?? a.agent_id ?? a.name
const name = (a) => a.name || `Agent ${agentId(a)}`
const pretty = (s) => (s || '').replace(/_/g, ' ')

const PRODUCT_STANCE_LABELS = {
  support: 'won over', neutral: 'curious', concerned: 'unconvinced',
  oppose: 'resistant', resist: 'hostile',
}
const stanceLabel = (s) => (props.mode === 'product' ? (PRODUCT_STANCE_LABELS[s] || s) : s)

const avatar = (a) => createAvatar(initials, { seed: name(a), size: 36 }).toDataUri()

const archetypes = computed(() => {
  const counts = {}
  for (const a of props.agents) {
    const k = a.actor_archetype || 'unknown'
    counts[k] = (counts[k] || 0) + 1
  }
  return Object.entries(counts)
    .map(([key, count]) => ({ key, count }))
    .sort((a, b) => b.count - a.count)
})

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  return props.agents.filter((a) => {
    if (archetypeFilter.value && (a.actor_archetype || 'unknown') !== archetypeFilter.value) return false
    if (!q) return true
    return (
      name(a).toLowerCase().includes(q) ||
      (a.occupation || '').toLowerCase().includes(q) ||
      (a.actor_archetype || '').toLowerCase().includes(q)
    )
  })
})

const isSelected = (a) => props.multiSelect
  ? props.selectedIds.has(agentId(a))
  : (props.selected && agentId(props.selected) === agentId(a))
const select = (a) => emit(props.multiSelect ? 'toggle' : 'select', a)
</script>

<style scoped>
.agent-picker { display: flex; flex-direction: column; gap: 12px; }
.ap-controls { display: flex; gap: 8px; }
.ap-search {
  flex: 1;
  border: 1px solid #DDD;
  padding: 8px 12px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  outline: none;
  background: #FAFAFA;
}
.ap-search:focus { border-color: #1E9E5A; }
.ap-filter {
  border: 1px solid #DDD;
  padding: 8px 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem;
  background: #fff;
  cursor: pointer;
  outline: none;
}
.ap-empty {
  padding: 24px;
  text-align: center;
  color: #999;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
}
.ap-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
  padding-right: 4px;
}
.ap-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #E5E5E5;
  background: #fff;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s, background 0.15s;
}
.ap-card:hover { border-color: #1E9E5A; }
.ap-card.selected { border-color: #1E9E5A; background: #F0FAF4; }
.ap-avatar { width: 36px; height: 36px; border-radius: 50%; flex-shrink: 0; }
.ap-body { min-width: 0; flex: 1; }
.ap-name {
  font-weight: 700;
  font-size: 0.85rem;
  color: #000;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ap-meta { display: flex; gap: 6px; margin-top: 2px; }
.ap-arch { font-family: 'JetBrains Mono', monospace; font-size: 0.66rem; color: #666; }
.ap-province { font-family: 'JetBrains Mono', monospace; font-size: 0.66rem; color: #999; }
.ap-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.ap-stance, .ap-tier, .ap-inst {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.58rem;
  font-weight: 700;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  padding: 1px 6px;
  border-radius: 2px;
}
.ap-stance { background: #F4F4F4; color: #555; border: 1px solid #E0E0E0; }
.stance-support { background: rgba(30,158,90,0.12); color: #1E9E5A; border-color: rgba(30,158,90,0.4); }
.stance-oppose, .stance-resist { background: #FDEDEB; color: #C0392B; border-color: #E6B0AA; }
.ap-tier { }
.tier-tight { background: #FDEDEB; color: #C0392B; border: 1px solid #E6B0AA; }
.tier-moderate { background: #F4F4F4; color: #666; border: 1px solid #DDD; }
.tier-loose { background: rgba(30,158,90,0.1); color: #1E9E5A; border: 1px solid rgba(30,158,90,0.4); }
.ap-inst { background: #EEF; color: #557; border: 1px solid #CCD; }
</style>
