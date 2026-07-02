<template>
  <div class="app-shell">
    <!-- ── Sidebar — exact copy of Home.vue ─────────────────────────────── -->
    <aside class="sidebar">
      <div class="sidebar-brand">
        <span class="brand-mark">c</span>
        <span class="brand-word"><span class="brand-strong">crowds</span></span>
      </div>
      <nav class="side-section">
        <button class="side-item" :class="{ active: !isPanel }">
          <span class="side-icon">✳</span>
          <span class="side-label">Sim</span>
        </button>
        <button class="side-item" :class="{ active: isPanel }">
          <span class="side-icon">◇</span>
          <span class="side-label">Panel Pitch</span>
        </button>
      </nav>
      <div class="side-recents">
        <div class="side-recents-head">{{ isPanel ? 'Previous panels' : 'Previous sims' }}</div>
        <div class="side-recents-empty">{{ query.slice(0, 40) }}{{ query.length > 40 ? '…' : '' }}</div>
      </div>
    </aside>

    <!-- ── Main column ──────────────────────────────────────────────────── -->
    <main class="app-main">
      <!-- App header — exact copy of SimulationRunView -->
      <header class="app-header">
        <div class="header-left">
          <button class="flow-back" title="Back to home" @click="emit('back')">
            <span class="flow-back-arrow">←</span>
            <span>Back</span>
          </button>
          <div class="brand">
            <span class="brand-mark">c</span>
            <span class="brand-word"><span class="brand-strong">crowds</span></span>
          </div>
        </div>
        <div class="header-right">
          <div class="workflow-step">
            <span class="step-name">Reactions</span>
          </div>
          <div class="step-divider"></div>
          <span class="status-indicator" :class="statusClass">
            <span class="dot"></span>
            {{ statusLabel }}
          </span>

          <!-- Live run controls (sim mode only, while the run is alive) -->
          <template v-if="!isPanel && feedLive">
            <div class="step-divider"></div>
            <button class="run-ctrl" :disabled="controlBusy" @click="togglePause">
              {{ paused ? '▶ Resume' : '❚❚ Pause' }}
            </button>
            <button class="run-ctrl danger" :disabled="controlBusy" @click="stopRun">
              ■ Stop
            </button>
          </template>
        </div>
      </header>

      <!-- ── Simulation panel ──────────────────────────────────────────── -->
      <div class="simulation-panel">

        <!-- ── Results body — shared layout for both modes ──────────────── -->
        <!-- Sim and panel now read the same way: a scenario banner, the stance
             spectrum, a summary, then mode-specific detail (sim = a live
             reaction feed; panel = room replies). -->
        <div class="main-content-area" ref="scrollContainer">
          <!-- Scenario banner -->
          <div class="spectrum-pitched">
            <span class="spectrum-pitched-label">{{ isPanel ? 'PITCHED:' : 'SCENARIO:' }}</span> {{ query }}
          </div>

          <!-- Typing indicator while the room is live -->
          <div v-if="feedLive" class="spectrum-typing">
            <div class="chat-typing-indicator">
              <span class="typing-dot"></span>
              <span class="typing-dot"></span>
              <span class="typing-dot"></span>
              <span class="typing-text">{{ isPanel ? 'Panel is reacting…' : 'The room is reacting…' }}</span>
            </div>
          </div>

          <!-- Summary of what agents feel -->
          <div class="spectrum-summary">
            <div class="spectrum-summary-head">
              <span>Summary</span>
              <button
                v-if="!isPanel && simulationId"
                class="report-dl-btn"
                :disabled="reportBusy || feedLive"
                :title="feedLive ? 'Available once the run finishes' : 'Generate and download the full insight report (.md)'"
                @click="downloadReport"
              >
                <span v-if="reportBusy" class="btn-spinner"></span>
                {{ reportBusy ? (reportMsg || 'Generating…') : '⤓ Download report' }}
              </button>
            </div>
            <p v-if="!reportBusy && reportMsg" class="report-dl-msg">{{ reportMsg }}</p>
            <div class="spectrum-summary-body">
              <p>{{ summaryText }}</p>
            </div>
          </div>

          <!-- ── Live reaction feed (sim mode) — clean single column ─────── -->
          <div v-if="!isPanel && feed.length" class="sim-feed">
            <div class="sim-feed-head">
              <span>Reactions</span>
              <span class="sim-feed-count">{{ feed.length }} events</span>
            </div>
            <TransitionGroup name="reaction-item" tag="div" class="sim-feed-list">
              <div
                v-for="action in feed"
                :key="action.uid"
                class="reaction-card"
                @click="openChat(action.agent_id)"
              >
                <img :src="avatarFor(action.agent_id, action.agent_name)" :alt="action.agent_name" class="reaction-avatar" />
                <div class="reaction-body">
                  <div class="reaction-meta">
                    <span class="reaction-name">{{ action.agent_name }}</span>
                    <span class="reaction-badge" :class="action.round === 1 ? 'badge-post' : 'badge-comment'">{{ action.action_type }}</span>
                    <span v-if="action.round > 1" class="reaction-round">round {{ action.round }}</span>
                    <span v-if="action.stance_changed" class="reaction-shift">
                      {{ stanceLabel(action.stance_before) }} → {{ stanceLabel(action.stance_after) }}
                    </span>
                    <span class="reaction-chat-hint">💬</span>
                  </div>
                  <p class="reaction-text">{{ action.content }}</p>
                </div>
              </div>
            </TransitionGroup>
          </div>

          <!-- ── Panel reactions (panel mode) — avatars clustered by stance ── -->
          <!-- Personas group into deterministic stance buckets; clicking a face
               opens an anchored popover with their reaction, and "Ask a
               follow-up" hands off to the existing chat slide-out. -->
          <div v-if="isPanel && panelReactions.length" class="sim-feed">
            <div class="sim-feed-head">
              <span>Reactions</span>
              <span class="sim-feed-count">{{ panelReactions.length }} personas</span>
            </div>
            <div class="pp-clusters">
              <div v-for="c in reactionClusters" :key="c.key" class="pp-cluster">
                <div class="pp-cluster-head">
                  <span class="pp-cluster-name">{{ c.label }}</span>
                  <span class="pp-cluster-count">{{ c.members.length }}</span>
                </div>
                <div class="pp-cluster-avatars">
                  <button
                    v-for="a in c.members"
                    :key="a.id"
                    class="pp-av-btn"
                    :class="{ active: popAgentId === a.id }"
                    :title="a.name"
                    @mouseenter="showReactionPop(a, $event)"
                    @mouseleave="scheduleClosePop"
                    @click="interviewFromAvatar(a)"
                  >
                    <img :src="a.avatarUrl" :alt="a.name" />
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Opinion popover — appears on hover; click the avatar to interview -->
          <div
            v-if="popAgent"
            class="pp-pop"
            :style="popStyle"
            @mouseenter="cancelClosePop"
            @mouseleave="scheduleClosePop"
          >
            <div class="pp-pop-head">
              <img :src="popAgent.avatarUrl" :alt="popAgent.name" />
              <div class="pp-pop-id">
                <span class="pp-pop-name">{{ popAgent.name }}</span>
                <span v-if="popAgent.archetype" class="pp-pop-role">{{ popAgent.archetype.replace(/_/g, ' ') }}</span>
              </div>
            </div>
            <div v-if="popAgent.stance_changed" class="pp-pop-tags">
              <span class="reaction-shift">{{ stanceLabel(popAgent.stance_before) }} → {{ stanceLabel(popAgent.stance_after) }}</span>
            </div>
            <p class="pp-pop-text">{{ popAgent.currentReaction }}</p>
            <div class="pp-pop-hint">Click to read full reaction →</div>
          </div>

          <!-- Room broadcast replies -->
          <div v-if="roomReplies.length" class="room-replies">
            <div class="room-replies-head">The room responded</div>
            <div
              v-for="r in roomReplies"
              :key="r.id"
              class="room-reply"
              @click="openChat(r.agentId)"
            >
              <img :src="r.avatarUrl" :alt="r.name" class="room-reply-avatar" />
              <div class="room-reply-body">
                <span class="room-reply-name">{{ r.name }}</span>
                <span class="room-reply-text">{{ r.text }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Bottom broadcast bar — speak to the room -->
        <div class="room-bar">
          <input
            v-model="roomDraft"
            class="room-bar-input"
            placeholder="Ask the room…"
            @keydown.enter.exact.prevent="broadcast"
          />
          <button class="room-bar-send" :disabled="!roomDraft.trim() || roomReplying" @click="broadcast">
            <span v-if="roomReplying" class="btn-spinner"></span>
            <span v-else>↑</span>
          </button>
        </div>
      </div>
    </main>

    <!-- Chat panel — right-side slide-out overlay -->
    <Transition name="scrim">
      <div v-if="showChat" class="chat-scrim" @click="closeChat"></div>
    </Transition>
    <Transition name="slide-right">
      <aside v-if="showChat" class="chat-side-panel">
        <div class="chat-panel-header">
          <div class="chat-panel-title">
            <span class="panel-icon">💬</span>
            <span>Chat with {{ selectedAgentName }}</span>
            <span v-if="selectedAgentArchetype" class="archetype-badge">{{ selectedAgentArchetype }}</span>
          </div>
          <button class="chat-close-btn" @click="closeChat">×</button>
        </div>

        <!-- Who you're talking to + the reaction they already gave, so the
             follow-up has context. -->
        <div v-if="selectedAgent" class="chat-agent-card">
          <img :src="selectedAgent.avatarUrl" :alt="selectedAgent.name" class="chat-agent-avatar" />
          <div class="chat-agent-meta">
            <span class="chat-agent-name">{{ selectedAgent.name }}</span>
            <span v-if="selectedAgentArchetype" class="chat-agent-arch">{{ selectedAgentArchetype }}</span>
          </div>
          <span v-if="selectedAgent.stance_after" class="chat-agent-stance">{{ stanceLabel(selectedAgent.stance_after) }}</span>
        </div>
        <div v-if="selectedAgent && selectedAgent.currentReaction" class="chat-agent-reaction">
          <span class="chat-agent-reaction-label">Their reaction</span>
          <p class="chat-agent-reaction-text">{{ selectedAgent.currentReaction }}</p>
        </div>

        <div class="chat-messages-container">
          <div class="chat-messages-list">
            <div v-if="chatMessages.length === 0" class="chat-empty-state">
              <p>Ask {{ selectedAgentName }} a follow-up</p>
              <p class="hint">Their reaction is shown above</p>
            </div>
            <div
              v-for="(msg, i) in chatMessages"
              :key="i"
              class="chat-message"
              :class="msg.role"
            >
              <div class="message-bubble">{{ msg.content }}</div>
              <div class="message-time">{{ msg.time }}</div>
            </div>
            <div v-if="chatLoading" class="chat-typing-indicator">
              <span class="typing-dot"></span>
              <span class="typing-dot"></span>
              <span class="typing-dot"></span>
              <span class="typing-text">{{ selectedAgentName }} is typing...</span>
            </div>
          </div>
        </div>

        <div class="chat-input-container">
          <input
            v-model="chatInput"
            @keyup.enter="sendChatMessage"
            :disabled="chatLoading"
            placeholder="Type your message..."
            class="chat-input-field"
          />
          <button
            class="chat-send-btn"
            @click="sendChatMessage"
            :disabled="chatLoading || !chatInput.trim()"
          >
            <span v-if="!chatLoading">Send</span>
            <span v-else class="btn-spinner"></span>
          </button>
        </div>
      </aside>
    </Transition>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { createAvatar } from '@dicebear/core'
import { avataaars } from '@dicebear/collection'
import {
  getSimulationProfilesRealtime,
  getRunStatus,
  getRunStatusDetail,
  getSimulationActions,
  interviewAgent,
  broadcastIntervention,
  pauseSimulation,
  resumeSimulation,
  stopSimulation
} from '../../api/simulation'
import { getSession, pitchSession, askAgent, listRounds } from '../../api/panel'
import { generateReport, getReportStatus, getReport } from '../../api/report'

const props = defineProps({
  query: { type: String, default: '' },
  mode: { type: String, default: 'sim' },  // 'sim' | 'panel'
  simulationId: { type: String, default: null },
  sessionId: { type: String, default: null }
})
const emit = defineEmits(['back'])

const isPanel = computed(() => props.mode === 'panel')

// ── Report download (sim mode) ──────────────────────────────────────────────
// Generate the full insight report on the backend, poll until it's written,
// then download the markdown. No-op for panels (no graph/sim to report on).
const reportBusy = ref(false)
const reportMsg = ref('')

const _sleep = (ms) => new Promise(r => setTimeout(r, ms))

const _saveMarkdown = (text, name) => {
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

const downloadReport = async () => {
  if (reportBusy.value || !props.simulationId) return
  reportBusy.value = true
  reportMsg.value = 'Generating report…'
  try {
    const gen = await generateReport({ simulation_id: props.simulationId })
    const d = gen?.data?.data || gen?.data || {}
    let reportId = d.report_id
    const taskId = d.task_id

    // Poll until the task completes (≈3 min cap), unless it was already done.
    if (d.status !== 'completed' && !d.already_generated) {
      const deadline = Date.now() + 3 * 60 * 1000
      while (Date.now() < deadline) {
        await _sleep(3000)
        const st = await getReportStatus({ task_id: taskId, simulation_id: props.simulationId })
        const s = st?.data?.data || st?.data || {}
        if (s.progress != null) reportMsg.value = `Generating report… ${s.progress}%`
        if (s.status === 'completed') { reportId = s.report_id || s.result?.report_id || reportId; break }
        if (s.status === 'failed') throw new Error(s.error || s.message || 'Report generation failed')
      }
    }
    if (!reportId) throw new Error('Report timed out — try again in a moment.')

    const rep = await getReport(reportId)
    const md = (rep?.data?.data || rep?.data || {}).markdown_content
    if (!md) throw new Error('Report was empty.')
    _saveMarkdown(md, `${reportId}.md`)
    reportMsg.value = ''
  } catch (e) {
    reportMsg.value = e?.message || 'Could not generate the report.'
  } finally {
    reportBusy.value = false
  }
}

// ── DiceBear avatar helper ──────────────────────────────────────────────────
const _avatarCache = new Map()
const getAvatarUrl = (name) => {
  const seed = name || 'unknown'
  if (_avatarCache.has(seed)) return _avatarCache.get(seed)
  const svg = createAvatar(avataaars, {
    seed, radius: 50,
    backgroundColor: ['b6e3f4', 'c0e8d5', 'fde68a', 'ffd6a5'],
    backgroundType: ['solid']
  }).toString()
  const uri = `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
  _avatarCache.set(seed, uri)
  return uri
}

// Avatar for a feed row — prefer the roster agent's avatar (so the feed and the
// spectrum show the same face), falling back to a name-seeded one.
const avatarFor = (id, name) => {
  const a = agents.value.find(x => x.id === id)
  return a?.avatarUrl || getAvatarUrl(name)
}

// ── Normalised agent roster ─────────────────────────────────────────────────
// One shape for both modes: sim mode fills this from the simulation profiles,
// panel mode from the assembled session roster. Each agent carries its current
// stance + latest reaction so the spectrum, popovers and chat all read from here.
const agents = ref([])

const normalizeAgent = (a) => ({
  id: a.id ?? a.agent_id,
  name: a.name || a.agent_name || `Agent ${a.id ?? a.agent_id}`,
  archetype: a.actor_archetype || a.archetype || a.occupation || '',
  avatarUrl: getAvatarUrl(a.name || a.agent_name || String(a.id ?? a.agent_id)),
  stance_after: a.stance || a.stance_after || 'neutral',
  stance_before: a.stance || a.stance_before || 'neutral',
  stance_changed: false,
  currentReaction: a.currentReaction || ''
})

// ── Stance spectrum definitions ─────────────────────────────────────────────
const STANCES = [
  { key: 'support', label: 'Won over', color: '#1E9E5A' },
  { key: 'neutral', label: 'Curious', color: '#9CA3AF' },
  { key: 'concerned', label: 'Unconvinced', color: '#F59E0B' },
  { key: 'oppose', label: 'Resistant', color: '#C0392B' },
]

const agentsByStance = (stance) => panelAgents.value.filter(a => a.stance_after === stance)

// The roster the summary counts read off (live for both modes).
const panelAgents = computed(() => agents.value)

// Panel reaction cards: only personas that actually returned reaction text.
// (Stance can be set without a response, so guard on currentReaction to avoid
// rendering blank cards.)
const panelReactions = computed(() =>
  panelAgents.value.filter(a => (a.currentReaction || '').trim())
)

// How many personas changed their mind so far (drives the "experience" read).
const shiftedCount = computed(() => panelAgents.value.filter(a => a.stance_changed).length)

// ── Reaction map: cluster personas into stance columns (deterministic) ───────
// Buckets follow the STANCES spread (won over → resistant); any stray stance
// falls into its own column. No LLM, no scoring — holds with the model off.
const reactionClusters = computed(() => {
  const byStance = {}
  for (const a of panelReactions.value) {
    const key = a.stance_after || 'neutral'
    ;(byStance[key] || (byStance[key] = [])).push(a)
  }
  const extra = Object.keys(byStance).filter(k => !STANCES.some(s => s.key === k))
  const ordered = [
    ...STANCES.map(s => ({ key: s.key, label: s.label })),
    ...extra.map(k => ({ key: k, label: stanceLabel(k) })),
  ]
  return ordered.filter(o => byStance[o.key]?.length).map(o => ({ ...o, members: byStance[o.key] }))
})

// Opinion popover: appears on hover (read-only); clicking the avatar opens the
// interview side panel instead. A short close delay lets the cursor travel from
// the avatar onto the popover without it vanishing.
const popAgentId = ref(null)
const popStyle = ref({})
let _popCloseTimer = null
const popAgent = computed(() => agents.value.find(a => a.id === popAgentId.value) || null)
const showReactionPop = (a, ev) => {
  if (_popCloseTimer) { clearTimeout(_popCloseTimer); _popCloseTimer = null }
  popAgentId.value = a.id
  const rect = ev.currentTarget.getBoundingClientRect()
  const W = 360, GAP = 10, MARGIN = 16
  let left = rect.left + rect.width / 2 - W / 2
  left = Math.max(12, Math.min(left, window.innerWidth - W - 12))
  // Place below by default; flip above when there's more room up top.
  const spaceBelow = window.innerHeight - rect.bottom - GAP - MARGIN
  const spaceAbove = rect.top - GAP - MARGIN
  const style = { left: left + 'px' }
  if (spaceBelow >= 220 || spaceBelow >= spaceAbove) {
    style.top = (rect.bottom + GAP) + 'px'
  } else {
    style.bottom = (window.innerHeight - rect.top + GAP) + 'px'
  }
  popStyle.value = style
}
const cancelClosePop = () => { if (_popCloseTimer) { clearTimeout(_popCloseTimer); _popCloseTimer = null } }
const scheduleClosePop = () => { _popCloseTimer = setTimeout(() => { popAgentId.value = null }, 140) }
const interviewFromAvatar = (a) => { cancelClosePop(); popAgentId.value = null; openChat(a.id) }

// Summary text — a short summary report of where the room sits, grounded in the
// live roster: the prevailing mood, the actual breakdown, and how many have
// moved as the scenario plays out. No LLM — pure real counts.
const summaryText = computed(() => {
  const total = panelAgents.value.length
  if (!total) return 'No reactions yet — the room is still forming its view.'
  const subject = isPanel.value ? 'pitch' : 'scenario'
  const support = agentsByStance('support').length
  const concerned = agentsByStance('concerned').length
  const oppose = agentsByStance('oppose').length
  const neutral = agentsByStance('neutral').length

  let mood
  if (support > total / 2) mood = `The room leans positive — most are won over or warming to the ${subject}.`
  else if (oppose > total / 2) mood = `The room leans resistant — the ${subject} is not landing with this group as it stands.`
  else if (concerned > total / 3) mood = `The room is cautious — a large share is unconvinced, with specific conditions before they would engage.`
  else if (neutral >= total / 2) mood = `The room is curious but undecided — open to hearing more about the ${subject}, but nobody is committed yet.`
  else mood = 'The room is mixed — opinions are spread with no clear majority.'

  // A one-line breakdown of the real split, in plain language.
  const parts = []
  if (support) parts.push(`${support} won over`)
  if (neutral) parts.push(`${neutral} curious`)
  if (concerned) parts.push(`${concerned} unconvinced`)
  if (oppose) parts.push(`${oppose} resistant`)
  const breakdown = `Of ${total} personas: ${parts.join(', ')}.`

  // How the room has actually moved so far.
  const moved = shiftedCount.value
  const shift = moved > 0
    ? ` ${moved === 1 ? 'One persona has' : moved + ' personas have'} changed their mind so far.`
    : ''

  return `${mood} ${breakdown}${shift}`
})

// ── Feed — timeline actions ─────────────────────────────────────────────────
const feed = ref([])
const feedLive = ref(true)
const scrollContainer = ref(null)

// ── Live run controls (sim mode): pause / resume / stop ─────────────────────
const paused = ref(false)
const controlBusy = ref(false)

const statusClass = computed(() => {
  if (!feedLive.value) return 'completed'
  return paused.value ? 'paused' : 'processing'
})
const statusLabel = computed(() => {
  if (!feedLive.value) return 'Settled'
  return paused.value ? 'Paused' : 'Simulating'
})

const togglePause = async () => {
  if (controlBusy.value || !props.simulationId) return
  controlBusy.value = true
  try {
    if (paused.value) {
      await resumeSimulation(props.simulationId)
      paused.value = false
    } else {
      await pauseSimulation(props.simulationId)
      paused.value = true
    }
  } catch (e) {
    console.warn('Pause/resume failed:', e)
  } finally {
    controlBusy.value = false
  }
}

const stopRun = async () => {
  if (controlBusy.value || !props.simulationId) return
  controlBusy.value = true
  try {
    await stopSimulation({ simulation_id: props.simulationId })
    paused.value = false
    feedLive.value = false
    stopSimPolling()
  } catch (e) {
    console.warn('Stop failed:', e)
  } finally {
    controlBusy.value = false
  }
}

const STANCE_LABELS = {
  support: 'won over', neutral: 'curious', concerned: 'unconvinced',
  oppose: 'resistant', resist: 'hostile'
}
const stanceLabel = (s) => STANCE_LABELS[s] || s

// Opinion-feed action labels — only expressed/responded opinions land in the feed.
const ACTION_LABELS = { EXPRESS_OPINION: 'EXPRESS', RESPOND_TO_OPINION: 'RESPOND' }

const scrollToBottom = () => {
  nextTick(() => {
    if (scrollContainer.value) scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
  })
}

// ── Sim mode: real-time profiles + action timeline ──────────────────────────
const seenActionIds = new Set()
let actionTimer = null
let statusTimer = null

const loadSimAgents = async () => {
  if (!props.simulationId) return
  try {
    const res = await getSimulationProfilesRealtime(props.simulationId, 'opinion_space')
    if (res.success && res.data) {
      const profiles = Array.isArray(res.data) ? res.data : (res.data.profiles || [])
      agents.value = profiles.map(normalizeAgent)
    }
  } catch (e) {
    console.warn('Failed to load sim agent profiles:', e)
  }
}

// Push one opinion action onto the feed (deduped). Shared by the live poll and
// the persisted-history loader (used when revisiting a finished sim).
const pushActionToFeed = (action) => {
  const label = ACTION_LABELS[action.action_type]
  const content = action.action_args?.content
  if (!label || !content) return   // opinion timeline only
  const uid = action.id || `${action.timestamp}-${action.agent_id}-${action.action_type}`
  if (seenActionIds.has(uid)) return
  seenActionIds.add(uid)
  feed.value.push({
    uid,
    agent_id: action.agent_id,
    agent_name: action.agent_name,
    action_type: label,
    content,
    round: action.round_num || 1,
    stance_before: action.stance_before || null,
    stance_after: action.stance_after || null,
    stance_changed: !!action.stance_changed
  })
  // Keep the live roster in sync so the stance spectrum reflects the latest
  // round as reactions stream in (the spectrum reads off agents.value).
  if (action.stance_after) {
    const ag = agents.value.find(a => a.id === action.agent_id)
    if (ag) {
      if (action.stance_after !== ag.stance_after) ag.stance_before = ag.stance_after
      ag.stance_after = action.stance_after
      if (action.stance_changed) ag.stance_changed = true
      ag.currentReaction = content
    }
  }
}

const pollSimActions = async () => {
  if (!props.simulationId) return
  try {
    const res = await getRunStatusDetail(props.simulationId)
    if (res.success && res.data) {
      ;(res.data.all_actions || []).forEach(pushActionToFeed)
      scrollToBottom()
    }
  } catch (e) {
    console.warn('Failed to poll sim actions:', e)
  }
}

// Load the persisted action history — used when revisiting a sim whose run is
// no longer live (the realtime detail endpoint only has the in-memory tail).
const loadSimActionHistory = async () => {
  if (!props.simulationId) return
  try {
    const res = await getSimulationActions(props.simulationId, { platform: 'opinion_space', limit: 1000 })
    const actions = res.data?.actions || (Array.isArray(res.data) ? res.data : [])
    actions.forEach(pushActionToFeed)
    scrollToBottom()
  } catch (e) {
    console.warn('Failed to load sim action history:', e)
  }
}

const pollSimStatus = async () => {
  if (!props.simulationId) return
  try {
    const res = await getRunStatus(props.simulationId)
    if (res.success && res.data) {
      const d = res.data
      const completed = d.runner_status === 'completed' || d.runner_status === 'stopped' || d.simulation_completed === true
      if (completed) {
        feedLive.value = false
        stopSimPolling()
      }
    }
  } catch (e) {
    console.warn('Failed to poll sim status:', e)
  }
}

const startSimPolling = () => {
  actionTimer = setInterval(pollSimActions, 3000)
  statusTimer = setInterval(pollSimStatus, 2000)
}
const stopSimPolling = () => {
  if (actionTimer) { clearInterval(actionTimer); actionTimer = null }
  if (statusTimer) { clearInterval(statusTimer); statusTimer = null }
}

const startSim = async () => {
  feedLive.value = true
  await loadSimAgents()
  await pollSimActions()
  // Revisiting a finished run: the realtime tail is empty, so pull the history.
  if (feed.value.length === 0) await loadSimActionHistory()
  // Stop the "live" treatment + polling if the run is already done.
  await pollSimStatus()
  if (feedLive.value) startSimPolling()
}

// ── Panel mode: assembled session roster + a single pitch round ─────────────
const loadPanel = async () => {
  if (!props.sessionId) return
  feedLive.value = true
  try {
    const detail = await getSession(props.sessionId)
    if (detail.data?.agents) {
      agents.value = detail.data.agents.map(normalizeAgent)
      // Restore any saved follow-up interviews (persisted on disk per agent), so
      // they don't disappear across reopen/refresh. The pitch reaction itself is
      // shown separately, so skip those entries.
      for (const a of detail.data.agents) {
        const mem = a.chat_state?.interview_memory || []
        const thread = []
        for (const m of mem) {
          if (m.source === 'pitch_round') continue
          if (m.question) thread.push({ role: 'user', content: m.question, time: '' })
          if (m.response) thread.push({ role: 'assistant', content: m.response, time: '' })
        }
        if (thread.length) interviewThreads[a.id] = thread
      }
    }
    // Revisiting a saved panel? Load its latest pitch round instead of running a
    // new one. Only pitch when the session has no rounds yet (a fresh assemble).
    let results = null
    try {
      const rRes = await listRounds(props.sessionId, true)
      const rounds = rRes.data?.rounds || []
      if (rounds.length) {
        const last = rounds[rounds.length - 1]
        results = (last.result || {}).results || []
      }
    } catch (_) { /* fall through to a fresh pitch */ }
    if (!results) {
      const res = await pitchSession(props.sessionId, { concurrency: 6 })
      results = res.data?.results || []
    }
    const byId = {}
    for (const r of results) byId[r.agent_id] = r
    agents.value = agents.value.map(a => {
      const r = byId[a.id]
      if (!r) return a
      return {
        ...a,
        stance_before: r.stance_before || a.stance_before,
        stance_after: r.stance_after || r.stance_before || a.stance_after,
        stance_changed: !!r.stance_changed,
        currentReaction: r.response || a.currentReaction
      }
    })
  } catch (e) {
    console.warn('Failed to load / pitch panel:', e)
  } finally {
    feedLive.value = false
  }
}

// ── Chat panel — slide-out, matches Step3Simulation ─────────────────────────
const showChat = ref(false)
const chatAgentId = ref(null)
const chatInput = ref('')
const chatLoading = ref(false)

// Per-agent follow-up threads, keyed by agent id. Kept here so a thread survives
// closing/reopening the panel, and seeded on mount from the agent's saved
// interview memory on disk (panel mode) so interviews don't disappear.
const interviewThreads = reactive({})
const ensureThread = (id) => (interviewThreads[id] || (interviewThreads[id] = []))
const chatMessages = computed(() =>
  (chatAgentId.value != null && interviewThreads[chatAgentId.value]) || []
)

const selectedAgent = computed(() => agents.value.find(a => a.id === chatAgentId.value))
const selectedAgentName = computed(() => selectedAgent.value?.name || 'Agent')
const selectedAgentArchetype = computed(() => {
  const a = selectedAgent.value?.archetype
  return a ? a.replace(/_/g, ' ') : ''
})

const openChat = (agentId) => {
  chatAgentId.value = agentId
  // Sim timeline: surface this agent's latest opinion as "their reaction" so the
  // side panel has the same context the panel-pitch spectrum gives.
  if (!isPanel.value) {
    const a = agents.value.find(x => x.id === agentId)
    const last = [...feed.value].reverse().find(f => f.agent_id === agentId)
    if (a && last) a.currentReaction = last.content
  }
  showChat.value = true
}
const closeChat = () => {
  showChat.value = false
  chatAgentId.value = null
}

const now = () => new Date().toLocaleTimeString()

const sendChatMessage = async () => {
  const text = chatInput.value.trim()
  if (!text || chatLoading.value || chatAgentId.value == null) return
  const agentId = chatAgentId.value
  const thread = ensureThread(agentId)
  chatInput.value = ''
  // The backend persists each Q&A to the agent's interview memory on disk, so
  // these survive a reopen (and a session restore).
  thread.push({ role: 'user', content: text, time: now() })
  chatLoading.value = true
  try {
    let reply = ''
    if (isPanel.value) {
      const res = await askAgent(props.sessionId, agentId, text)
      reply = res.data?.response || ''
    } else {
      const res = await interviewAgent(props.simulationId, agentId, { question: text })
      reply = res.data?.response || res.data?.result?.response || ''
    }
    thread.push({ role: 'assistant', content: reply || '(no response)', time: now() })
  } catch (e) {
    thread.push({ role: 'assistant', content: '(failed: ' + e.message + ')', time: now() })
  } finally {
    chatLoading.value = false
  }
}

// ── Room broadcast bar ──────────────────────────────────────────────────────
const roomDraft = ref('')
const roomReplies = ref([])
const roomReplying = ref(false)

const broadcast = async () => {
  const q = roomDraft.value.trim()
  if (!q || roomReplying.value) return
  roomDraft.value = ''
  roomReplying.value = true
  roomReplies.value = []
  try {
    if (isPanel.value) {
      // Ask the room — a sample of the panel answers, shown as room replies.
      const sample = agents.value.slice(0, 6)
      await Promise.all(sample.map(async (a) => {
        try {
          const res = await askAgent(props.sessionId, a.id, q)
          roomReplies.value.push({
            id: `${a.id}-reply-${Date.now()}`,
            agentId: a.id,
            name: a.name,
            avatarUrl: a.avatarUrl,
            text: res.data?.response || ''
          })
        } catch (_) { /* skip individual failures */ }
      }))
    } else {
      // Sim mode: post to the opinion space as the founder; the running room
      // reacts next round and those reactions surface in the timeline feed.
      await broadcastIntervention(props.simulationId, { intervention_text: q })
    }
  } finally {
    roomReplying.value = false
  }
}

// Escape closes chat
const onKeydown = (e) => { if (e.key === 'Escape' && showChat.value) closeChat() }

onMounted(() => {
  if (isPanel.value) loadPanel()
  else startSim()
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  stopSimPolling()
})
</script>

<style scoped>
/* ── App shell — exact copy of Home.vue ───────────────────────────────────── */
.app-shell { position: absolute; inset: 0; z-index: 20; display: flex; height: 100vh; overflow: hidden; background: #FFF; }
.sidebar {
  flex-shrink: 0; width: 256px; height: 100vh;
  background: #FAFAFA; border-right: 1px solid #E8E8E8;
  display: flex; flex-direction: column;
  padding: 16px 12px; gap: 8px; overflow: hidden;
}
.sidebar-brand {
  display: flex; align-items: center; gap: 10px;
  padding: 6px 8px 12px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800; font-size: 1.15rem;
  cursor: pointer; user-select: none;
}
.brand-mark {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: 8px;
  background: linear-gradient(160deg, #25b368 0%, #1E9E5A 60%, #178048 100%);
  color: #fff; font-family: 'JetBrains Mono', monospace;
  font-weight: 800; font-size: 1.15rem; line-height: 1; flex-shrink: 0;
  box-shadow: 0 2px 6px rgba(30, 158, 90, 0.28);
}
.brand-word { line-height: 1; letter-spacing: -0.3px; color: #6b6b6b; font-weight: 700; }
.brand-strong { color: #1E9E5A; }
.side-section {
  display: flex; flex-direction: column; gap: 2px;
  padding-bottom: 8px; border-bottom: 1px solid #ECECEC;
}
.side-item {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 9px 12px; background: transparent; border: none;
  border-radius: 8px; cursor: pointer;
  font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;
  font-weight: 600; color: #555; text-align: left;
  transition: background 0.15s, color 0.15s;
}
.side-item:hover { background: #F0F0F0; color: #1a1a1a; }
.side-item.active { background: #F0FAF4; color: #1E9E5A; }
.side-icon { font-size: 0.95rem; line-height: 1; width: 18px; text-align: center; }
.side-label { flex: 1; }
.side-recents { flex: 1; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 1px; padding-top: 4px; }
.side-recents-head { padding: 6px 12px; font-family: 'JetBrains Mono', monospace; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; color: #aaa; }
.side-recents-empty { padding: 6px 12px; font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #bbb; }

/* Main column */
.app-main { flex: 1; min-width: 0; height: 100vh; overflow: hidden; display: flex; flex-direction: column; }

/* ── App header — exact copy ──────────────────────────────────────────────── */
.app-header {
  height: 60px; border-bottom: 1px solid #EAEAEA;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px; background: #FFF; z-index: 100; flex-shrink: 0;
}
.header-left { display: flex; align-items: center; gap: 14px; }
.flow-back {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px; border: 1px solid #E5E7EB; border-radius: 999px;
  background: #FFF; color: #555; cursor: pointer;
  font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 600;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.flow-back:hover { border-color: #1E9E5A; color: #1E9E5A; background: #F0FAF4; }
.flow-back-arrow { font-size: 14px; line-height: 1; }
.brand { display: flex; align-items: center; gap: 9px; font-family: 'JetBrains Mono', monospace; font-weight: 800; font-size: 18px; cursor: pointer; user-select: none; }
.brand-mark { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; border-radius: 7px; background: linear-gradient(160deg, #25b368 0%, #1E9E5A 60%, #178048 100%); color: #fff; font-size: 17px; line-height: 1; flex-shrink: 0; box-shadow: 0 2px 6px rgba(30, 158, 90, 0.28); }
.brand-word { line-height: 1; letter-spacing: -0.3px; color: #6b6b6b; font-weight: 700; }
.brand-strong { color: #1E9E5A; }
.header-right { display: flex; align-items: center; gap: 16px; }
.workflow-step { display: flex; align-items: center; gap: 8px; font-size: 14px; }
.step-name { font-weight: 700; color: #000; }
.step-divider { width: 1px; height: 14px; background-color: #E0E0E0; }
.status-indicator { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #666; font-weight: 500; }
.status-indicator .dot { width: 8px; height: 8px; border-radius: 50%; background: #CCC; }
.status-indicator.processing .dot { background: #FF5722; animation: pulse 1s infinite; }
.status-indicator.completed .dot { background: #4CAF50; }
.status-indicator.paused .dot { background: #F59E0B; }
@keyframes pulse { 50% { opacity: 0.5; } }

/* Live run controls — pause / resume / stop */
.run-ctrl {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 5px 12px; border: 1px solid #E5E7EB; border-radius: 999px;
  background: #FFF; color: #555; cursor: pointer;
  font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 600;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.run-ctrl:hover:not(:disabled) { border-color: #1E9E5A; color: #1E9E5A; background: #F0FAF4; }
.run-ctrl.danger:hover:not(:disabled) { border-color: #C0392B; color: #C0392B; background: #FDF2F1; }
.run-ctrl:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── Simulation panel — exact copy of Step3Simulation ─────────────────────── */
.simulation-panel {
  flex: 1; display: flex; flex-direction: column;
  background: #FFFFFF;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  overflow: hidden;
}

/* Control bar */
.control-bar {
  background: #FFF; padding: 12px 24px;
  display: flex; justify-content: space-between; align-items: center;
  border-bottom: 1px solid #EAEAEA; z-index: 10; height: 64px; flex-shrink: 0;
}
.status-group { display: flex; gap: 12px; }
.platform-status {
  display: flex; flex-direction: column; gap: 4px;
  padding: 6px 12px; border-radius: 4px;
  background: #FAFAFA; border: 1px solid #EAEAEA;
  opacity: 0.7; transition: all 0.3s; min-width: 140px; position: relative;
}
.platform-status.active { opacity: 1; border-color: #333; background: #FFF; }
.platform-status.completed { opacity: 1; border-color: #1A936F; background: #F2FAF6; }
.platform-header { display: flex; align-items: center; gap: 8px; margin-bottom: 2px; }
.platform-name { font-size: 11px; font-weight: 700; color: #000; text-transform: uppercase; letter-spacing: 0.05em; }
.platform-status.opinion-space .platform-icon { color: #000; }
.platform-stats { display: flex; gap: 10px; }
.stat { display: flex; align-items: baseline; gap: 3px; }
.stat-label { font-size: 8px; color: #999; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
.stat-value { font-size: 11px; font-weight: 600; color: #333; }
.stat-total { font-size: 9px; color: #999; font-weight: 400; }
.mono { font-family: 'JetBrains Mono', monospace; }
.status-badge { margin-left: auto; color: #1A936F; display: flex; align-items: center; }
.action-controls { display: flex; gap: 10px; }

/* Action buttons */
.action-btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 10px 20px; font-size: 13px; font-weight: 600;
  border: none; border-radius: 4px; cursor: pointer;
  transition: all 0.2s ease; text-transform: uppercase; letter-spacing: 0.05em;
  background: #f0f0f0; color: #333;
}
.action-btn:hover { background: #e0e0e0; }
.action-btn.primary { background: #000; color: #FFF; }
.action-btn.primary:hover:not(:disabled) { background: #333; }
.action-btn:disabled { opacity: 0.3; cursor: not-allowed; }

/* ── Chat panel — right-side slide-out overlay ────────────────────────────── */
.chat-scrim {
  position: absolute; inset: 0; z-index: 40;
  background: rgba(0, 0, 0, 0.15); cursor: pointer;
}
.chat-side-panel {
  position: absolute; top: 0; right: 0; bottom: 0; z-index: 50;
  width: 400px; max-width: 90vw;
  background: #FFF; border-left: 1px solid #EAEAEA;
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.08);
  display: flex; flex-direction: column;
}
.chat-panel-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 20px; border-bottom: 1px solid #F0F0F0; flex-shrink: 0;
}
.chat-panel-title { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 15px; color: #333; }
.panel-icon { font-size: 18px; }
.archetype-badge { font-size: 11px; font-weight: 500; padding: 2px 8px; background: #F0F0F0; color: #666; border-radius: 10px; text-transform: lowercase; }
.chat-close-btn { background: none; border: none; font-size: 24px; color: #999; cursor: pointer; padding: 0; line-height: 1; }
.chat-close-btn:hover { color: #333; }

/* Agent context card — who you're talking to, shown above the follow-up thread */
.chat-agent-card {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 20px; border-bottom: 1px solid #F0F0F0;
  background: #FFF; flex-shrink: 0;
}
.chat-agent-avatar { width: 44px; height: 44px; border-radius: 50%; border: 2px solid #E5E7EB; background: #FFF; flex-shrink: 0; }
.chat-agent-meta { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.chat-agent-name { font-size: 15px; font-weight: 700; color: #1F2937; }
.chat-agent-arch { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #9CA3AF; text-transform: lowercase; }
.chat-agent-stance {
  font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 700;
  text-transform: uppercase; color: #1E9E5A;
  background: rgba(30, 158, 90, 0.1); border: 1px solid rgba(30, 158, 90, 0.3);
  padding: 3px 10px; border-radius: 999px; flex-shrink: 0;
}
/* The reaction they already gave — full text, readable */
.chat-agent-reaction {
  padding: 14px 20px; border-bottom: 1px solid #F0F0F0; background: #F9FAFB;
  flex-shrink: 0; height: auto; max-height: 85vh; overflow-y: auto;
}
.chat-agent-reaction-label {
  display: block; font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 700;
  letter-spacing: 0.5px; text-transform: uppercase; color: #9CA3AF; margin-bottom: 6px;
}
.chat-agent-reaction-text { margin: 0; font-size: 14px; line-height: 1.55; color: #374151; max-width: 60ch; }

.chat-messages-container { flex: 1; overflow-y: auto; background: #F9F9F9; border-radius: 0; padding: 16px; }
.chat-messages-list { display: flex; flex-direction: column; gap: 10px; }
.chat-empty-state { text-align: center; padding: 40px 20px; color: #888; }
.chat-empty-state p { margin: 4px 0; }
.chat-empty-state .hint { font-size: 12px; color: #AAA; }
.chat-message { display: flex; flex-direction: column; max-width: 80%; }
.chat-message.user { align-self: flex-end; align-items: flex-end; }
.chat-message.assistant { align-self: flex-start; align-items: flex-start; }
.message-bubble { padding: 10px 14px; border-radius: 14px; font-size: 14px; line-height: 1.4; }
.chat-message.user .message-bubble { background: #4CAF50; color: white; border-bottom-right-radius: 4px; }
.chat-message.assistant .message-bubble { background: white; color: #333; border: 1px solid #E0E0E0; border-bottom-left-radius: 4px; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05); }
.message-time { font-size: 10px; color: #AAA; margin-top: 4px; }
.chat-typing-indicator { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: white; border-radius: 12px; border: 1px solid #E0E0E0; width: fit-content; }
.typing-dot { width: 6px; height: 6px; background: #AAA; border-radius: 50%; animation: typingBounce 1.4s infinite ease-in-out; }
.typing-dot:nth-child(1) { animation-delay: 0s; }
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes typingBounce { 0%, 60%, 100% { transform: translateY(0); } 30% { transform: translateY(-6px); } }
.typing-text { font-size: 12px; color: #888; margin-left: 4px; }
.chat-input-container { display: flex; gap: 10px; padding: 16px 20px; border-top: 1px solid #F0F0F0; flex-shrink: 0; }
.chat-input-field { flex: 1; padding: 12px 16px; font-size: 14px; border: 1px solid #DDD; border-radius: 24px; outline: none; transition: border-color 0.2s; }
.chat-input-field:focus { border-color: #4CAF50; }
.chat-send-btn { padding: 10px 24px; background: #4CAF50; color: white; border: none; border-radius: 24px; font-size: 14px; font-weight: 600; cursor: pointer; transition: background 0.2s; min-width: 80px; }
.chat-send-btn:hover:not(:disabled) { background: #43A047; }
.chat-send-btn:disabled { background: #CCC; cursor: not-allowed; }
.btn-spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid white; border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Right-side slide + scrim transitions */
.slide-right-enter-active, .slide-right-leave-active { transition: transform 0.35s cubic-bezier(0.22, 1, 0.36, 1); }
.slide-right-enter-from, .slide-right-leave-to { transform: translateX(100%); }
.scrim-enter-active, .scrim-leave-active { transition: opacity 0.3s ease; }
.scrim-enter-from, .scrim-leave-to { opacity: 0; }

.main-content-area { flex: 1; overflow-y: auto; }

/* ── Live reaction feed (sim mode) — clean single column ───────────────────── */
.sim-feed {
  margin: 16px 24px;
  background: #FFF; border: 1px solid #E5E7EB; border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  overflow: hidden;
}
.sim-feed-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 20px; border-bottom: 1px solid #E5E7EB; background: #F9FAFB;
  font-size: 14px; font-weight: 600; color: #1F2937;
}
.sim-feed-count { font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 400; color: #9CA3AF; }
.sim-feed-list { display: flex; flex-direction: column; }

.reaction-card {
  display: flex; gap: 12px; align-items: flex-start;
  padding: 14px 20px; border-bottom: 1px solid #F0F0F0;
  cursor: pointer; transition: background 0.15s;
}
.reaction-card:last-child { border-bottom: none; }
.reaction-card:hover { background: #F9FAFB; }
.reaction-avatar { width: 36px; height: 36px; border-radius: 50%; border: 2px solid #E5E7EB; background: #FFF; flex-shrink: 0; }
.reaction-body { flex: 1; min-width: 0; }
.reaction-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 4px; }
.reaction-name { font-size: 13px; font-weight: 700; color: #1F2937; }
.reaction-badge { font-size: 9px; padding: 2px 6px; border-radius: 4px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; border: 1px solid transparent; }
.badge-post { background: #F0F0F0; color: #333; border-color: #E0E0E0; }
.badge-comment { background: #F0F0F0; color: #666; border-color: #E0E0E0; }
.reaction-round { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #9CA3AF; }
.reaction-shift {
  font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 700;
  color: #1E9E5A; background: rgba(30, 158, 90, 0.1);
  border: 1px solid rgba(30, 158, 90, 0.3); padding: 1px 6px; border-radius: 999px;
}
.reaction-chat-hint { margin-left: auto; font-size: 13px; opacity: 0; transition: opacity 0.15s; }
.reaction-card:hover .reaction-chat-hint { opacity: 1; }
.reaction-text { margin: 0; font-size: 14px; line-height: 1.55; color: #374151; }

/* Reaction feed transitions */
.reaction-item-enter-active { transition: all 0.4s ease; }
.reaction-item-enter-from { opacity: 0; transform: translateY(12px); }

/* ── Reaction map — avatars clustered into stance columns ──────────────────── */
.pp-clusters { display: flex; flex-wrap: wrap; padding: 16px 20px 20px; }
.pp-cluster { flex: 1; min-width: 190px; padding: 0 18px; border-right: 1px dashed #E5E7EB; }
.pp-cluster:last-child { border-right: none; }
.pp-cluster:first-child { padding-left: 0; }
.pp-cluster-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 14px; }
.pp-cluster-name { font-size: 14px; font-weight: 700; color: #111; }
.pp-cluster-count {
  font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 700;
  color: #1E9E5A; background: rgba(30, 158, 90, 0.1); padding: 1px 8px; border-radius: 999px;
}
.pp-cluster-avatars { display: flex; flex-wrap: wrap; gap: 8px; }
.pp-av-btn { padding: 0; border: none; background: none; cursor: pointer; border-radius: 50%; line-height: 0; transition: transform 0.12s; }
.pp-av-btn:hover, .pp-av-btn.active { transform: translateY(-3px); }
.pp-av-btn img {
  width: 46px; height: 46px; border-radius: 50%;
  border: 2px solid #E5E7EB; background: #fff; transition: border-color 0.12s, box-shadow 0.12s;
}
.pp-av-btn:hover img, .pp-av-btn.active img { border-color: #1E9E5A; box-shadow: 0 0 0 3px rgba(30, 158, 90, 0.1); }

/* Persona popover */
.pp-pop {
  position: fixed; z-index: 61; width: 360px; max-width: 92vw;
  background: #fff; border: 1px solid #E0E0E0; border-radius: 16px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18); padding: 0 18px 18px;
}
.pp-pop-head {
  display: flex; gap: 12px; align-items: center;
  position: sticky; top: 0; background: #fff; z-index: 1;
  padding: 16px 0 10px;
}
.pp-pop-head img { width: 46px; height: 46px; border-radius: 50%; border: 2px solid #1E9E5A; flex-shrink: 0; }
.pp-pop-id { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.pp-pop-name { font-weight: 700; font-size: 14px; color: #111; }
.pp-pop-role { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #9CA3AF; text-transform: lowercase; }
.pp-pop-tags { margin-bottom: 10px; }
.pp-pop-text {
  margin: 0 0 12px; font-size: 13.5px; line-height: 1.6; color: #333;
  display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical;
  overflow: hidden;
}
.pp-pop-hint {
  font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 700;
  color: #1E9E5A; letter-spacing: 0.3px;
}

/* ── Scenario banner ──────────────────────────────────────────────────────── */
.spectrum-pitched {
  margin: 16px 24px 0;
  padding: 10px 14px;
  background: #FAFAFA; border: 1px solid #EEE; border-radius: 12px;
  font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #555; line-height: 1.5;
}
.spectrum-pitched-label { color: #1E9E5A; font-weight: 700; margin-right: 6px; }

.spectrum-typing { padding: 16px 24px; }

/* ── Summary box ──────────────────────────────────────────────────────────── */
.spectrum-summary {
  margin: 16px 24px;
  background: #FFF;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  overflow: hidden;
}
.spectrum-summary-head {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 14px 20px;
  border-bottom: 1px solid #E5E7EB;
  background: #F9FAFB;
  font-size: 14px; font-weight: 600; color: #1F2937;
}
.report-dl-btn {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 7px 14px; border: none; border-radius: 8px; cursor: pointer;
  background: #1E9E5A; color: #fff; font-weight: 700; font-size: 12.5px;
  font-family: 'JetBrains Mono', monospace; transition: background .15s;
}
.report-dl-btn:hover:not(:disabled) { background: #178048; }
.report-dl-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.report-dl-btn .btn-spinner { border-color: #fff; border-top-color: transparent; }
.report-dl-msg { margin: 8px 20px 0; font-size: 12.5px; color: #C0392B; }
.spectrum-summary-body {
  padding: 16px 20px;
}
.spectrum-summary-body p {
  margin: 0;
  font-size: 14px; line-height: 1.6; color: #374151;
}
/* ── Room replies ─────────────────────────────────────────────────────────── */
.room-replies { margin: 0 24px 16px; display: flex; flex-direction: column; gap: 8px; }
.room-replies-head {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.5px; color: #9CA3AF;
}
.room-reply {
  display: flex; gap: 10px; align-items: flex-start;
  padding: 12px 16px; background: #FFF; border: 1px solid #E5E7EB;
  border-radius: 8px; cursor: pointer; transition: border-color 0.15s;
  animation: card-in 0.4s ease;
}
@keyframes card-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.room-reply:hover { border-color: #1E9E5A; }
.room-reply-avatar { width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0; }
.room-reply-body { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.room-reply-name { font-size: 13px; font-weight: 600; color: #1F2937; }
.room-reply-text { font-size: 13px; line-height: 1.45; color: #374151; }

/* ── Bottom room bar ──────────────────────────────────────────────────────── */
.room-bar {
  display: flex; gap: 10px; align-items: center;
  padding: 12px 24px; background: #FFF;
  border-top: 1px solid #EAEAEA; flex-shrink: 0;
}
.room-bar-input {
  flex: 1; padding: 12px 18px;
  font-size: 14px; border: 1px solid #E5E7EB;
  border-radius: 999px; outline: none; background: #FAFAFA;
  font-family: inherit; transition: border-color 0.2s, background 0.2s;
}
.room-bar-input:focus { border-color: #1E9E5A; background: #FFF; }
.room-bar-send {
  width: 40px; height: 40px; border: none; border-radius: 50%;
  background: #1E9E5A; color: #FFF; font-size: 1.1rem; font-weight: 700;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; transition: background 0.15s;
}
.room-bar-send:hover:not(:disabled) { background: #178048; }
.room-bar-send:disabled { background: #DDD; cursor: not-allowed; }

@media (max-width: 640px) {
  .chat-side-panel { max-height: 100vh; max-width: 100vw; border-radius: 0; }
}
</style>
