<template>
  <!-- The build pipeline, narrated in one box. Reproduces the v0 design:
       progress bar + phase narration + a progress-driven graph that builds up.
       Pure presentation — driven entirely by the `progress` prop (0–100) that
       the parent view polls from getTaskStatus. No backend coupling here. -->
  <div class="pl-wrap">
    <div class="pl-box" :class="{ errored, done: progress >= 100 }">
      <!-- header: the scenario being built for -->
      <div class="pl-head">
        <span class="pl-eyebrow">Building your simulated population</span>
        <p v-if="query" class="pl-query">{{ query }}</p>
      </div>

      <!-- progress bar -->
      <div class="pl-bar">
        <div class="pl-bar-fill" :style="{ width: clampedProgress + '%' }"></div>
      </div>

      <div class="pl-body">
        <!-- narration list: one phase active at a time -->
        <ol class="pl-phases">
          <li
            v-for="(ph, i) in phases"
            :key="ph.key"
            class="pl-phase"
            :class="phaseState(i)"
          >
            <span class="pl-phase-mark">
              <span v-if="phaseState(i) === 'done'">✓</span>
              <span v-else-if="phaseState(i) === 'active'" class="pl-pulse">●</span>
              <span v-else>○</span>
            </span>
            <span class="pl-phase-label">{{ ph.label }}</span>
          </li>
        </ol>

        <!-- the graph, building up as progress climbs -->
        <div class="pl-graph">
          <svg viewBox="0 0 320 280" class="pl-graph-svg" preserveAspectRatio="xMidYMid meet">
            <!-- edges first (under nodes) -->
            <line
              v-for="(e, i) in edges"
              :key="'e' + i"
              :x1="nodes[e[0]].x" :y1="nodes[e[0]].y"
              :x2="nodes[e[1]].x" :y2="nodes[e[1]].y"
              class="pl-edge"
              :style="{ opacity: edgeOpacity(i) }"
            />
            <!-- entity nodes -->
            <circle
              v-for="(n, i) in nodes"
              :key="'n' + i"
              :cx="n.x" :cy="n.y" :r="n.persona ? 7 : 5"
              class="pl-node"
              :class="{ 'pl-node-persona': n.persona }"
              :style="{ opacity: nodeOpacity(i), transform: nodeScale(i) }"
            />
          </svg>
          <p class="pl-message">{{ message || defaultMessage }}</p>
        </div>
      </div>

      <!-- completion / error footer -->
      <div class="pl-foot">
        <button
          v-if="progress >= 100 && !errored"
          class="pl-cta"
          @click="$emit('view-reactions')"
        >View reactions →</button>
        <div v-else-if="errored" class="pl-error">
          <span>{{ errorMessage || 'Something went wrong building the population.' }}</span>
          <button class="pl-retry" @click="$emit('retry')">Try again</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  // 0–100, polled from getTaskStatus by the parent view
  progress: { type: Number, default: 0 },
  // live narration message from the backend task
  message: { type: String, default: '' },
  query: { type: String, default: '' },
  errored: { type: Boolean, default: false },
  errorMessage: { type: String, default: '' },
})

defineEmits(['view-reactions', 'retry'])

const clampedProgress = computed(() => Math.max(0, Math.min(100, props.progress)))

// Phase windows (progress %): narration + graph reveal are keyed to these.
// Mirrors the real backend stages (ontology/search → graph → match → personas).
const phases = [
  { key: 'sources',  label: 'Searching sources',     start: 0  },
  { key: 'graph',    label: 'Constructing graph',     start: 15 },
  { key: 'match',    label: 'Matching entities',      start: 50 },
  { key: 'personas', label: 'Pulling personas',       start: 66 },
  { key: 'prepare',  label: 'Preparing simulation',   start: 90 },
]

const phaseState = (i) => {
  const p = clampedProgress.value
  const start = phases[i].start
  const next = i + 1 < phases.length ? phases[i + 1].start : 101
  if (p >= next) return 'done'
  if (p >= start) return 'active'
  return 'pending'
}

const defaultMessage = computed(() => {
  const active = phases.findLast?.((_, i) => phaseState(i) === 'active')
  return active ? active.label + '…' : 'Starting…'
})

// ── Representative graph (presentation only) ──────────────────────────────
// Deterministic node/edge set scattered in the viewbox. Nodes fade+scale in
// during the "graph" window; persona nodes attach during the "personas" window.
const CONSTRUCT_START = 15, CONSTRUCT_END = 48
const PERSONA_START = 66, PERSONA_END = 89

const nodes = (() => {
  const out = []
  const entityCount = 14
  for (let i = 0; i < entityCount; i++) {
    const ang = (i / entityCount) * Math.PI * 2
    const rad = 70 + (i % 3) * 28
    out.push({
      x: 160 + Math.cos(ang) * rad,
      y: 140 + Math.sin(ang) * rad * 0.82,
      persona: false,
      appearAt: i / entityCount,
    })
  }
  // persona nodes attach onto entity nodes later
  const personaCount = 8
  for (let i = 0; i < personaCount; i++) {
    const host = out[(i * 2) % entityCount]
    const off = (i % 2 === 0 ? 1 : -1) * 16
    out.push({
      x: host.x + off,
      y: host.y - 18 - (i % 3) * 4,
      persona: true,
      appearAt: i / personaCount,
    })
  }
  return out
})()

const edges = (() => {
  const out = []
  for (let i = 0; i < 14; i++) {
    out.push([i, (i + 1) % 14])
    if (i % 3 === 0) out.push([i, (i + 5) % 14])
  }
  return out
})()

const clamp01 = (v) => Math.max(0, Math.min(1, v))

const nodeOpacity = (i) => {
  const n = nodes[i]
  const p = clampedProgress.value
  if (n.persona) {
    const begin = PERSONA_START + n.appearAt * (PERSONA_END - PERSONA_START)
    return clamp01((p - begin) / 5)
  }
  const begin = CONSTRUCT_START + n.appearAt * (CONSTRUCT_END - CONSTRUCT_START)
  return clamp01((p - begin) / 4)
}
const nodeScale = (i) => {
  const o = nodeOpacity(i)
  return `scale(${0.6 + o * 0.4})`
}
const edgeOpacity = (i) => {
  const e = edges[i]
  return Math.min(nodeOpacity(e[0]), nodeOpacity(e[1])) * 0.5
}
</script>

<style scoped>
.pl-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100%;
  padding: 32px 16px;
}
.pl-box {
  width: 100%;
  max-width: 560px;
  background: #fff;
  border: 1px solid #E6E8EB;
  border-radius: 20px;
  padding: 26px 26px 20px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.05);
  transition: box-shadow 0.4s ease;
}
.pl-box.done { box-shadow: 0 8px 34px rgba(30, 158, 90, 0.18); }
.pl-box.errored { border-color: #E6B0AA; }

.pl-head { margin-bottom: 16px; }
.pl-eyebrow {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #1E9E5A;
}
.pl-query {
  margin: 6px 0 0;
  font-size: 14px;
  line-height: 1.45;
  color: #333;
}

.pl-bar {
  height: 6px;
  background: #EEF0F2;
  border-radius: 999px;
  overflow: hidden;
  margin-bottom: 20px;
}
.pl-bar-fill {
  height: 100%;
  background: #1E9E5A;
  border-radius: 999px;
  transition: width 0.5s ease;
}

.pl-body {
  display: grid;
  grid-template-columns: 168px 1fr;
  gap: 18px;
}

.pl-phases { list-style: none; margin: 0; padding: 0; }
.pl-phase {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  font-size: 13px;
  color: #9AA0A6;
  transition: color 0.3s ease;
}
.pl-phase.active { color: #1E9E5A; font-weight: 600; }
.pl-phase.done { color: #555; }
.pl-phase-mark { width: 16px; text-align: center; font-size: 12px; }
.pl-phase.done .pl-phase-mark { color: #1E9E5A; }
.pl-pulse { animation: pl-pulse 1.2s ease-in-out infinite; }
@keyframes pl-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }

.pl-graph {
  display: flex;
  flex-direction: column;
  align-items: center;
}
.pl-graph-svg { width: 100%; height: 200px; }
.pl-edge { stroke: #1E9E5A; stroke-width: 1; transition: opacity 0.4s ease; }
.pl-node {
  fill: #1E9E5A;
  transform-box: fill-box;
  transform-origin: center;
  transition: opacity 0.4s ease, transform 0.4s ease;
}
.pl-node-persona { fill: #7BC9A0; }
.pl-message {
  margin: 8px 0 0;
  font-size: 12px;
  color: #888;
  text-align: center;
  min-height: 16px;
}

.pl-foot { margin-top: 18px; min-height: 40px; display: flex; justify-content: center; }
.pl-cta {
  background: #1E9E5A;
  color: #fff;
  border: none;
  border-radius: 10px;
  padding: 11px 22px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease;
}
.pl-cta:hover { background: #178049; }
.pl-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #C0392B;
}
.pl-retry {
  background: none;
  border: 1px solid #E6B0AA;
  color: #C0392B;
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
}
</style>
