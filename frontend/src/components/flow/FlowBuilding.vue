<template>
  <div class="flow-building">
    <button class="flow-back" title="Back to home" @click="emit('back')">
      <span class="flow-back-arrow">←</span>
      <span>Back</span>
    </button>
    <div class="pipeline-box" :class="{ settled: done }">
      <!-- Zone 1: progress bar -->
      <div class="progress-track">
        <div class="progress-fill" :style="{ width: progress + '%' }"></div>
      </div>

      <div class="pipeline-body">
        <!-- Zone 2: narration list -->
        <ul class="narration">
          <li
            v-for="(ph, i) in PHASES"
            :key="ph"
            class="phase"
            :class="phaseState(i)"
          >
            <span class="phase-mark">
              <span v-if="i < activePhase" class="check">✓</span>
              <span v-else-if="i === activePhase" class="dot"></span>
              <span v-else class="ring"></span>
            </span>
            <span class="phase-label">{{ ph }}</span>
          </li>
        </ul>

        <!-- Zone 3: animated assembling node-graph -->
        <div ref="canvasEl" class="graph-canvas">
          <svg ref="svgEl" class="graph-svg"></svg>
          <div v-if="done" class="graph-settled-tag">graph ready</div>
        </div>
      </div>

      <!-- Error state: surface the failure with a retry (mirrors MainView). -->
      <Transition name="reveal">
        <div v-if="error" class="complete-row build-error-row">
          <span class="build-error-text">{{ error }}</span>
          <button class="view-reactions" @click="retry">
            Retry
            <span class="arrow">→</span>
          </button>
        </div>
      </Transition>

      <!-- Completion action: single deliberate gate -->
      <Transition name="reveal">
        <div v-if="done && !error" class="complete-row">
          <button class="view-reactions" @click="emitViewReactions">
            View reactions
            <span class="arrow">→</span>
          </button>
        </div>
      </Transition>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import * as d3 from 'd3'
import { createAvatar } from '@dicebear/core'
import { avataaars, initials } from '@dicebear/collection'
import { getPendingUpload } from '../../store/pendingUpload'
import { generateOntology, buildGraph, getTaskStatus, getProject, getGraphData } from '../../api/graph'
import { createSimulation, prepareSimulation, getPrepareStatus, startSimulation } from '../../api/simulation'

const props = defineProps({
  query: { type: String, default: '' }
})
const emit = defineEmits(['viewReactions', 'back'])

const PHASES = [
  'Searching sources',
  'Constructing graph',
  'Matching entities',
  'Pulling personas',
  'Preparing simulation'
]

const progress = ref(0)
const activePhase = ref(0)
const done = ref(false)
const error = ref('')

// Live simulation id, set once the pipeline creates the simulation. Handed up
// to the results overlay via the viewReactions event.
let simulationId = null
let cancelled = false

const canvasEl = ref(null)
const svgEl = ref(null)

// ── Real graph data, ingested from the backend ──────────────────────────────
// Populated by ingestGraphData() once getGraphData() returns. Each node carries
// a synthetic `reveal` phase so it spawns into the canvas progressively as the
// narration advances (the "assembling" feel). Node types use GraphPanel's
// vocabulary so nodeKind() + avatarUrl() render identically to the main app.
let NODES = []   // [{ id, label, type, reveal }]
let EDGES = []   // [{ s, t, reveal }]
const PERSONAS = []  // real personas come later (the sim run); kept empty here

// Map a backend graph payload ({ nodes:[{uuid,name,labels}], edges:[{source_node_uuid,target_node_uuid}] })
// into the reveal-phased node/edge model the canvas animates. Spread nodes across
// phases 1→4 by index so they don't all pop in at once.
const ingestGraphData = (gd) => {
  const rawNodes = (gd && gd.nodes) || []
  const rawEdges = (gd && gd.edges) || []
  if (!rawNodes.length) return
  const per = Math.max(1, Math.ceil(rawNodes.length / 4))
  NODES = rawNodes.map((n, i) => ({
    id: n.uuid,
    label: n.name || 'entity',
    type: (n.labels || []).find(l => l !== 'Entity') || 'Entity',
    reveal: Math.min(4, 1 + Math.floor(i / per))
  }))
  const ids = new Set(NODES.map(n => n.id))
  EDGES = rawEdges
    .filter(e => ids.has(e.source_node_uuid) && ids.has(e.target_node_uuid))
    .map(e => ({ s: e.source_node_uuid, t: e.target_node_uuid, reveal: 2 }))
  // Re-reveal from scratch so the freshly-loaded real nodes appear up to the
  // current phase.
  lastRevealedPhase = -1
  revealUpTo(Math.min(activePhase.value, PHASES.length - 1))
}

// ── Node visual kind + avatar — ported from GraphPanel.vue ──────────────────
// People get DiceBear avataaars faces; orgs get initials badges; locations get
// a map-pin glyph; everything else is a coloured dot. Exact same logic as the
// main app's graph so nodes look identical.
const PERSON_TYPES = new Set([
  'Person', 'Student', 'Professor', 'Journalist', 'Celebrity', 'Executive',
  'Official', 'Lawyer', 'Doctor', 'CEO', 'Employee', 'Politician', 'Activist',
  'Expert', 'Resident', 'Citizen', 'Worker', 'Teacher', 'Nurse', 'Farmer'
])
const ORG_TYPES = new Set([
  'Organization', 'University', 'Company', 'GovernmentAgency', 'MediaOutlet',
  'Hospital', 'School', 'NGO', 'Agency', 'Institution', 'Party', 'Union',
  'Department', 'Committee', 'Council', 'Ministry'
])
const LOCATION_TYPES = new Set(['Location', 'City', 'Province', 'Region', 'District', 'Suburb', 'Place'])

const PERSON_KEYWORDS = [
  'person', 'individual', 'citizen', 'resident', 'caregiver', 'patient',
  'parent', 'voter', 'commuter', 'student', 'teacher', 'doctor', 'nurse',
  'farmer', 'lawyer', 'activist', 'journalist', 'professor', 'advocate'
]
const LOCATION_KEYWORDS = [
  'location', 'city', 'province', 'region', 'district', 'suburb', 'township',
  'place', 'area', 'neighborhood', 'neighbourhood', 'zone', 'site', 'venue'
]

const matchesKeyword = (lower, keywords) => keywords.some(k => lower.includes(k))

const nodeKind = (type) => {
  if (!type || type === 'Entity') return 'other'
  if (PERSON_TYPES.has(type)) return 'person'
  if (ORG_TYPES.has(type)) return 'org'
  if (LOCATION_TYPES.has(type)) return 'location'
  const lower = type.toLowerCase()
  if (matchesKeyword(lower, LOCATION_KEYWORDS)) return 'location'
  if (matchesKeyword(lower, PERSON_KEYWORDS)) return 'person'
  return 'org'
}
const hasAvatar = (type) => {
  const k = nodeKind(type)
  return k === 'person' || k === 'org'
}

// Deterministic DiceBear avatar — same logic + cache as GraphPanel.
const _avatarCache = new Map()
const avatarUrl = (node) => {
  const kind = nodeKind(node.type)
  const seed = kind === 'org'
    ? (node.label || node.id || 'Org')
    : (node.id || node.label || 'unknown')
  const cacheKey = `${kind}:${seed}`
  let uri = _avatarCache.get(cacheKey)
  if (!uri) {
    const collection = kind === 'org' ? initials : avataaars
    const svg = createAvatar(collection, { seed, radius: 50 }).toString()
    uri = `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
    _avatarCache.set(cacheKey, uri)
  }
  return uri
}

// Entity-type colour palette — same as GraphPanel's entityTypes computed.
const ENTITY_COLORS = [
  '#1E9E5A', '#004E89', '#7B2D8E', '#1A936F', '#C5283D', '#E9724C',
  '#3498db', '#9b59b6', '#27ae60', '#f39c12'
]
const _colorCache = new Map()
let _colorIdx = 0
const typeColor = (type) => {
  if (!_colorCache.has(type)) {
    _colorCache.set(type, ENTITY_COLORS[_colorIdx % ENTITY_COLORS.length])
    _colorIdx++
  }
  return _colorCache.get(type)
}

const NODE_R = 14
const nodeRadius = (n) => (n.type === 'persona' ? 5 : NODE_R)

// ── d3 persistent simulation ────────────────────────────────────────────────
let simulation = null
let svgSel = null
let gRoot = null
let linkLayer = null
let nodeLayer = null
let personaLayer = null
let simNodes = []   // objects d3 mutates with x/y
let simLinks = []
let simPersonas = []
const nodeById = new Map()
let lastRevealedPhase = -1
let rafId = null
let resizeObs = null

const initSim = () => {
  const el = canvasEl.value
  if (!el) return
  const w = el.clientWidth
  const h = el.clientHeight

  svgSel = d3.select(svgEl.value)
    .attr('width', w)
    .attr('height', h)
    .attr('viewBox', `0 0 ${w} ${h}`)
  svgSel.selectAll('*').remove()

  gRoot = svgSel.append('g')
  linkLayer = gRoot.append('g').attr('class', 'links')
  personaLayer = gRoot.append('g').attr('class', 'personas')
  nodeLayer = gRoot.append('g').attr('class', 'nodes')

  // clipPath defs — one shared circle clip so avatar images render as round
  // avatars. Same approach as GraphPanel.
  const defs = svgSel.append('defs')
  defs.append('clipPath')
    .attr('id', 'flow-avatar-clip')
    .append('circle')
    .attr('r', NODE_R)
    .attr('cx', 0)
    .attr('cy', 0)

  // Pre-seed positions near centre so new nodes spawn from the middle and get
  // pushed outward by the force — this is what makes it read as "assembling".
  const cx = w / 2, cy = h / 2
  NODES.forEach(n => { n.x = cx; n.y = cy })
  PERSONAS.forEach(p => { p.x = cx; p.y = cy })

  simulation = d3.forceSimulation(simNodes)
    .force('link', d3.forceLink(simLinks).id(d => d.id).distance(d => d.target && d.target.type === 'persona' ? 22 : 78).strength(d => d.target && d.target.type === 'persona' ? 0.9 : 0.5))
    .force('charge', d3.forceManyBody().strength(d => d.type === 'persona' ? -30 : -220))
    .force('collide', d3.forceCollide().radius(d => nodeRadius(d) + 6))
    .force('center', d3.forceCenter(w / 2, h / 2).strength(0.06))
    .force('x', d3.forceX(w / 2).strength(0.03))
    .force('y', d3.forceY(h / 2).strength(0.03))
    .alpha(1)
    .alphaDecay(0.02)

  simulation.on('tick', drawTick)
}

// Add any nodes/edges whose reveal phase <= phase, that aren't already in the sim.
const revealUpTo = (phase) => {
  if (phase <= lastRevealedPhase) return
  lastRevealedPhase = phase
  const cx = canvasEl.value.clientWidth / 2
  const cy = canvasEl.value.clientHeight / 2

  // nodes
  for (const n of NODES) {
    if (n.reveal <= phase && !nodeById.has(n.id)) {
      const simNode = { ...n, x: cx, y: cy }
      simNodes.push(simNode)
      nodeById.set(n.id, simNode)
    }
  }
  // edges (only between already-present nodes)
  for (const e of EDGES) {
    if (e.reveal <= phase && !simLinks.some(l => l.__key === `${e.s}->${e.t}`)) {
      const a = nodeById.get(e.s), b = nodeById.get(e.t)
      if (a && b) simLinks.push({ source: e.s, target: e.t, __key: `${e.s}->${e.t}` })
    }
  }
  // persona dots
  for (const p of PERSONAS) {
    if (p.reveal <= phase && !simPersonas.some(sp => sp.id === p.id)) {
      const parent = nodeById.get(p.parent)
      const sp = { ...p, type: 'persona', x: parent ? parent.x : cx, y: parent ? parent.y : cy }
      simPersonas.push(sp)
      // link persona to parent with a short spring so it orbits
      simLinks.push({ source: p.id, target: p.parent, __key: `persona-${p.id}`, __persona: true })
      // persona must also be a sim node so forceLink resolves it
      if (!simNodes.some(n => n.id === p.id)) simNodes.push(sp)
      nodeById.set(p.id, sp)
    }
  }

  // (Re)bind data to the simulation
  simulation.nodes(simNodes)
  simulation.force('link').links(simLinks)
  simulation.alpha(0.8).restart()

  // SVG data-join: append new elements, fade them in.
  joinLinks()
  joinNodes()
  joinPersonas()
}

const joinLinks = () => {
  const sel = linkLayer.selectAll('line').data(simLinks, d => d.__key)
  sel.exit().remove()
  const enter = sel.enter().append('line')
    .attr('stroke', d => d.__persona ? '#BFE6D2' : '#C0C0C0')
    .attr('stroke-width', d => d.__persona ? 1 : 1.5)
    .attr('stroke-dasharray', d => d.__persona ? '2 3' : null)
    .attr('opacity', 0)
  enter.transition().duration(500).attr('opacity', 1)
}

const joinNodes = () => {
  const sel = nodeLayer.selectAll('g.node').data(simNodes.filter(n => n.type !== 'persona'), d => d.id)
  sel.exit().remove()
  const enter = sel.enter().append('g')
    .attr('class', 'node')
    .attr('opacity', 0)
    .attr('transform', d => `translate(${d.x},${d.y}) scale(0.2)`)

  // A node has an identity mark (avatar image or location pin) for any kind
  // except the plain-dot fallback — same as GraphPanel.
  const hasMark = (d) => nodeKind(d.type) !== 'other'

  // Outer ring — coloured ring on white for marked nodes; coloured fill for dots.
  enter.append('circle')
    .attr('class', 'node-ring')
    .attr('r', d => hasMark(d) ? NODE_R : 10)
    .attr('fill', d => hasMark(d) ? '#fff' : typeColor(d.type))
    .attr('stroke', d => hasMark(d) ? typeColor(d.type) : '#fff')
    .attr('stroke-width', 2.5)

  // Avatar image for person (face) and org (initials) nodes, clipped to ring.
  enter.filter(d => hasAvatar(d.type))
    .append('image')
    .attr('class', 'node-avatar')
    .attr('href', d => avatarUrl(d))
    .attr('x', -NODE_R)
    .attr('y', -NODE_R)
    .attr('width', NODE_R * 2)
    .attr('height', NODE_R * 2)
    .attr('clip-path', 'url(#flow-avatar-clip)')
    .attr('preserveAspectRatio', 'xMidYMid slice')
    .style('pointer-events', 'none')

  // Map-pin glyph for location nodes.
  enter.filter(d => nodeKind(d.type) === 'location')
    .append('path')
    .attr('class', 'node-pin')
    .attr('d', 'M0,-9 C-5,-9 -8,-5.5 -8,-1.5 C-8,3.5 0,9 0,9 C0,9 8,3.5 8,-1.5 C8,-5.5 5,-9 0,-9 Z')
    .attr('fill', d => typeColor(d.type))
    .attr('stroke', '#fff')
    .attr('stroke-width', 1.2)
    .style('pointer-events', 'none')

  enter.filter(d => nodeKind(d.type) === 'location')
    .append('circle')
    .attr('class', 'node-pin-dot')
    .attr('r', 2.4)
    .attr('cy', -2)
    .attr('fill', '#fff')
    .style('pointer-events', 'none')

  // Node labels — same style as GraphPanel.
  enter.append('text')
    .text(d => d.label.length > 8 ? d.label.slice(0, 8) + '…' : d.label)
    .attr('x', d => hasMark(d) ? 18 : 14)
    .attr('y', 4)
    .attr('font-size', '11px')
    .attr('font-weight', '500')
    .attr('font-family', "system-ui, sans-serif")
    .attr('fill', '#333')
    .style('pointer-events', 'none')

  enter.transition().duration(550).ease(d3.easeCubicOut)
    .attr('opacity', 1)
    .attr('transform', d => `translate(${d.x},${d.y}) scale(1)`)
}

const joinPersonas = () => {
  const sel = personaLayer.selectAll('circle.pdot').data(simPersonas, d => d.id)
  sel.exit().remove()
  const enter = sel.enter().append('circle')
    .attr('class', 'pdot')
    .attr('r', 0)
    .attr('fill', '#1E9E5A')
    .attr('stroke', '#fff')
    .attr('stroke-width', 1.5)
    .attr('opacity', 0)
  enter.transition().duration(500).delay(120)
    .attr('r', 5)
    .attr('opacity', 1)
}

const drawTick = () => {
  // links
  linkLayer.selectAll('line')
    .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
    .attr('x2', d => d.target.x).attr('y2', d => d.target.y)
  // nodes
  nodeLayer.selectAll('g.node')
    .attr('transform', d => `translate(${d.x},${d.y})`)
  // persona dots
  personaLayer.selectAll('circle.pdot')
    .attr('cx', d => d.x).attr('cy', d => d.y)
}

const phaseState = (i) => {
  if (i < activePhase.value) return 'done'
  if (i === activePhase.value) return 'active'
  return 'pending'
}

// ── Real build pipeline ─────────────────────────────────────────────────────
// Mirrors the existing app's flow (Home → MainView → SimulationView → Step3):
// generateOntology → buildGraph (poll) → createSimulation → prepareSimulation
// (poll) → startSimulation. Each backend stage maps onto one narration phase,
// and the real graph fills the canvas at the "matching entities" phase.
const sleep = (ms) => new Promise(r => setTimeout(r, ms))

const setPhase = (i) => {
  if (i > activePhase.value) {
    activePhase.value = i
    revealUpTo(Math.min(i, PHASES.length - 1))
  }
}

const fail = (msg) => { if (!cancelled) error.value = msg || 'Something went wrong' }

const runPipeline = async () => {
  error.value = ''
  const pending = getPendingUpload()
  const requirement = pending.simulationRequirement || ''
  const mode = pending.mode || 'policy'
  const modeIsManual = !!pending.modeIsManual
  const hasFiles = !!(pending.files && pending.files.length)
  if (!requirement.trim() && !hasFiles) {
    fail('No simulation input found. Go back and describe a scenario.')
    return
  }

  try {
    // ── Phase 0: Searching sources — generate the ontology from the seed ──
    setPhase(0)
    progress.value = 5
    const formData = new FormData()
    ;(pending.files || []).forEach(f => formData.append('files', f))
    formData.append('simulation_requirement', requirement)
    const ont = await generateOntology(formData)
    if (cancelled) return
    if (!ont.success) { fail(ont.error || 'Ontology generation failed'); return }
    const projectId = ont.data.project_id
    progress.value = 15

    // ── Phase 1: Constructing graph — kick off the build and poll the task ──
    setPhase(1)
    const build = await buildGraph({ project_id: projectId })
    if (cancelled) return
    if (!build.success) { fail(build.error || 'Graph build failed to start'); return }
    const taskId = build.data.task_id

    let graphId = null
    while (!cancelled) {
      await sleep(2000)
      let task = null
      try { const r = await getTaskStatus(taskId); task = r.success ? r.data : null } catch (_) { continue }
      if (!task) continue
      progress.value = 15 + Math.min(100, task.progress || 0) * 0.45  // 15 → 60
      if (task.status === 'completed') break
      if (task.status === 'failed') { fail(task.error || 'Graph build failed'); return }
    }
    if (cancelled) return

    // ── Phase 2: Matching entities — load the real graph into the canvas ──
    setPhase(2)
    progress.value = 60
    try {
      const proj = await getProject(projectId)
      if (proj.success && proj.data.graph_id) {
        graphId = proj.data.graph_id
        const g = await getGraphData(graphId)
        if (g.success) ingestGraphData(g.data)
      }
    } catch (_) { /* graph visual is best-effort; the run can still proceed */ }
    if (cancelled) return

    // ── Phase 3: Pulling personas — create + prepare the simulation ──
    setPhase(3)
    progress.value = 64
    const created = await createSimulation({ project_id: projectId, graph_id: graphId || undefined })
    if (cancelled) return
    if (!created.success || !created.data?.simulation_id) {
      fail(created.error || 'Could not create simulation'); return
    }
    simulationId = created.data.simulation_id

    const preparePayload = {
      simulation_id: simulationId,
      use_llm_for_profiles: true,
      parallel_profile_count: 5,
      mode_is_manual: modeIsManual,
    }
    if (modeIsManual && mode) preparePayload.mode = mode
    if (pending.customAgentsEnabled && pending.customAgents?.length) {
      preparePayload.custom_agents = pending.customAgents
      if (pending.customAgentsOnly) preparePayload.custom_agents_only = true
    }
    const prep = await prepareSimulation(preparePayload)
    if (cancelled) return
    if (!prep.success) { fail(prep.error || 'Preparation failed'); return }

    if (!prep.data?.already_prepared) {
      const prepareTaskId = prep.data?.task_id
      while (!cancelled) {
        await sleep(2500)
        let st = null
        try {
          const r = await getPrepareStatus({ task_id: prepareTaskId, simulation_id: simulationId })
          st = r.success ? r.data : null
        } catch (_) { continue }
        if (!st) continue
        progress.value = 64 + Math.min(100, st.progress || 0) * 0.26  // 64 → 90
        if (st.status === 'completed' || st.status === 'ready' || st.already_prepared) break
        if (st.status === 'failed') { fail(st.error || 'Preparation failed'); return }
      }
    }
    if (cancelled) return

    // ── Phase 4: Preparing simulation — start the run ──
    setPhase(4)
    progress.value = 92
    const started = await startSimulation({
      simulation_id: simulationId,
      platform: 'opinion_space',
      preset: 'balanced',
      enable_graph_memory_update: true,
    })
    if (cancelled) return
    if (!started.success) { fail(started.error || 'Could not start simulation'); return }

    // ── Settled ──
    progress.value = 100
    activePhase.value = PHASES.length
    revealUpTo(PHASES.length - 1)
    done.value = true
  } catch (e) {
    fail(e.message || 'Build pipeline error')
  }
}

const emitViewReactions = () => emit('viewReactions', simulationId)

const retry = () => {
  error.value = ''
  progress.value = 0
  activePhase.value = 0
  runPipeline()
}

const handleResize = () => {
  if (!canvasEl.value || !svgSel) return
  const w = canvasEl.value.clientWidth
  const h = canvasEl.value.clientHeight
  svgSel.attr('width', w).attr('height', h).attr('viewBox', `0 0 ${w} ${h}`)
  simulation?.force('center', d3.forceCenter(w / 2, h / 2).strength(0.06))
  simulation?.alpha(0.5).restart()
}

onMounted(() => {
  nextTick(() => {
    initSim()
    // Always reveal phase 0 immediately so the graph isn't empty on first paint.
    revealUpTo(0)
    // tiny breath before the build kicks off
    setTimeout(runPipeline, 350)
    resizeObs = new ResizeObserver(handleResize)
    if (canvasEl.value) resizeObs.observe(canvasEl.value)
  })
})

onUnmounted(() => {
  cancelled = true
  if (rafId) cancelAnimationFrame(rafId)
  if (resizeObs) resizeObs.disconnect()
  if (simulation) simulation.stop()
})
</script>

<style scoped>
.flow-building {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
  background: rgba(245, 245, 245, 0.8);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

/* Back / cancel — top-left of the build overlay */
.flow-back {
  position: absolute;
  top: 18px;
  left: 18px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: 1px solid #E5E7EB;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  color: #555;
  cursor: pointer;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 600;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.flow-back:hover { border-color: #1E9E5A; color: #1E9E5A; background: #F0FAF4; }
.flow-back-arrow { font-size: 14px; line-height: 1; }

/* Pipeline box — matches app panel styling: 8px radius, #E5E7EB border, #FFF bg */
.pipeline-box {
  width: 100%;
  max-width: 980px;
  height: min(680px, 86vh);
  background: #FFF;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: box-shadow 0.6s ease, border-color 0.6s ease;
  animation: pop-in 0.5s cubic-bezier(0.22, 1, 0.36, 1);
}
@keyframes pop-in {
  from { transform: scale(0.95) translateY(8px); opacity: 0; }
  to   { transform: scale(1) translateY(0); opacity: 1; }
}
/* Settled — matches .step-complete: #F0F9F4 bg tint + #C8E6D2 border */
.pipeline-box.settled {
  border-color: #C8E6D2;
  box-shadow: 0 0 0 1px #C8E6D2, 0 8px 32px rgba(30, 158, 90, 0.12);
}

/* Zone 1: progress bar — matches .progress-bar (8px, #E5E7EB, #1E9E5A, 4px radius) */
.progress-track {
  height: 8px;
  background: #E5E7EB;
  flex-shrink: 0;
}
.progress-fill {
  height: 100%;
  background: #1E9E5A;
  border-radius: 0 4px 4px 0;
  transition: width 0.3s ease;
}

.pipeline-body {
  flex: 1;
  display: grid;
  grid-template-columns: 230px 1fr;
  min-height: 0;
}

/* Zone 2: narration — matches .step-status panel (#F9FAFB, #E5E7EB, 8px) */
.narration {
  list-style: none;
  margin: 0;
  padding: 24px 20px;
  border-right: 1px solid #E5E7EB;
  background: #F9FAFB;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.phase {
  display: flex;
  align-items: center;
  gap: 12px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  color: #9CA3AF;
  transition: color 0.3s ease;
}
.phase.active { color: #1F2937; font-weight: 600; }
.phase.done { color: #1E9E5A; }
.phase.done .phase-label { text-decoration: line-through; text-decoration-color: rgba(30, 158, 90, 0.3); }

/* Phase marks — matches .phase-status (24px circle, #E5E7EB idle, #1E9E5A active/done) */
.phase-mark {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: 50%;
  font-size: 12px;
}
.check {
  color: #FFF;
  font-size: 12px;
  font-weight: 700;
  width: 24px; height: 24px;
  border-radius: 50%;
  background: #1E9E5A;
  display: flex; align-items: center; justify-content: center;
}
.ring {
  width: 24px; height: 24px; border-radius: 50%;
  background: #E5E7EB;
  color: #9CA3AF;
}
.dot {
  width: 24px; height: 24px; border-radius: 50%;
  background: #1E9E5A;
  display: flex; align-items: center; justify-content: center;
  animation: pulse 1.6s ease-out infinite;
}
.dot::after {
  content: '';
  width: 8px; height: 8px; border-radius: 50%;
  background: #FFF;
}
@keyframes pulse {
  0%   { box-shadow: 0 0 0 0 rgba(30, 158, 90, 0.5); }
  70%  { box-shadow: 0 0 0 8px rgba(30, 158, 90, 0); }
  100% { box-shadow: 0 0 0 0 rgba(30, 158, 90, 0); }
}

/* Zone 3: graph canvas — dotted bg matching GraphPanel (#FAFAFA) */
.graph-canvas {
  position: relative;
  min-height: 0;
  overflow: hidden;
  background-color: #FAFAFA;
  background-image: radial-gradient(#D0D0D0 1.5px, transparent 1.5px);
  background-size: 24px 24px;
}
.graph-svg { width: 100%; height: 100%; display: block; }

.graph-settled-tag {
  position: absolute;
  bottom: 16px;
  left: 50%;
  transform: translateX(-50%);
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: #1E9E5A;
  background: #F0F9F4;
  border: 1px solid #C8E6D2;
  padding: 5px 12px;
  border-radius: 999px;
}

/* Completion — matches .action-btn.primary */
.complete-row {
  flex-shrink: 0;
  padding: 16px 20px 20px;
  display: flex;
  justify-content: center;
}
.view-reactions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  border: none;
  border-radius: 8px;
  background: #1E9E5A;
  color: #FFF;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}
.view-reactions:hover { background: #178F4D; }
.view-reactions .arrow { font-size: 14px; transition: transform 0.15s; }
.view-reactions:hover .arrow { transform: translateX(3px); }

.reveal-enter-active { transition: opacity 0.5s ease, transform 0.5s ease; }
.reveal-enter-from { opacity: 0; transform: translateY(8px); }

/* Error row — readable failure message + retry, neutral red (not the accent). */
.build-error-row { flex-direction: column; gap: 12px; }
.build-error-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  color: #C0392B;
  text-align: center;
  max-width: 560px;
}

@media (max-width: 760px) {
  .pipeline-body { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }
  .narration { border-right: none; border-bottom: 1px solid #E5E7EB; flex-direction: row; flex-wrap: wrap; gap: 14px; padding: 16px; }
}
</style>
