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

          <!-- Replay the first-time coach marks at any point. -->
          <template v-if="hasReactions">
            <div class="step-divider"></div>
            <button class="run-ctrl" title="Show the tips again" @click="replayCoach">
              ? How to use
            </button>
          </template>

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
      <!-- Hidden (not destroyed) while a chat is open: the chat is a full page
           of its own, but the live feed keeps running behind it. -->
      <div v-show="!showChat" class="simulation-panel">

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
            <div v-if="showCoach && !isPanel && simulationId" class="coach-mark coach-mark--flush">
              <span class="coach-dot">⤓</span>
              <span>Once the run settles, download the full write-up here.</span>
            </div>
            <!-- Degraded round: say so before any number is read. Every count
                 below is of the people who answered, so the reader has to know
                 the room was short before they trust the shape of it. -->
            <p v-if="roomHealth" class="room-health">{{ roomHealth }}</p>
            <div class="spectrum-summary-body">
              <!-- One summary only: the counts read is a live placeholder while
                   the run is in flight; once the LLM synthesis lands it replaces it.
                   Pointer views (fit / ab) answer with their own, so their
                   deterministic room read is suppressed. -->
              <p v-if="!llmSummary && !isPointerView">{{ summaryText }}</p>
              <p v-else-if="!llmSummary && isPointerView" class="summary-read muted">
                {{ isAbView ? 'Run both versions to compare the room.' : 'The segment ranking appears below.' }}
              </p>
              <p v-else class="summary-read">{{ llmSummary }}</p>
            </div>
          </div>

          <!-- ── Live reaction feed (sim mode) — clean single column ─────── -->
          <div v-if="!isPanel && feed.length" class="sim-feed">
            <div class="sim-feed-head">
              <span>Reactions</span>
              <span class="sim-feed-count">{{ feed.length }} events</span>
            </div>
            <div v-if="showCoach" class="coach-mark">
              <span class="coach-dot">👆</span>
              <span>Click any reaction to open a private chat with that person.</span>
              <button class="coach-got" @click="dismissCoach">Got it</button>
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

          <!-- ── Panel: `fit` ranked segments (instead of the room) ────────── -->
          <!-- The pick is the answer: an ordered list, most-won-over first. Each
               row shows that segment's stance split and its members' own words.
               Real data only — the ranking order came from the backend. -->
          <div v-if="isPanel && isFitView && fitRanking.length" class="sim-feed">
            <div class="sim-feed-head">
              <span>Ranked fit</span>
              <span class="sim-feed-count">{{ fitRanking.length }} segments</span>
            </div>
            <div class="fit-ranking">
              <div v-for="(seg, i) in fitRanking" :key="seg.segment_id" class="fit-card" :class="{ top: i === 0 }">
                <div class="fit-card-head">
                  <span class="fit-rank">#{{ i + 1 }}</span>
                  <span class="fit-card-label">{{ seg.label }}</span>
                  <div class="fit-card-split">
                    <span v-for="(count, st) in seg.stance_split" :key="st" class="fit-stance" :class="`stance-${st}`">
                      {{ stanceLabel(st) }} {{ count }}
                    </span>
                  </div>
                </div>
                <div v-for="m in seg.members" :key="m.agent_id" class="fit-member" @click="openChat(m.agent_id)">
                  <img :src="getAvatarUrl(m.agent_name)" :alt="m.agent_name" class="fit-member-avatar" />
                  <div class="fit-member-body">
                    <span class="fit-member-name">
                      {{ m.agent_name }}
                      <span class="fit-member-stance" :class="`stance-${m.stance_after}`">{{ stanceLabel(m.stance_after) }}</span>
                    </span>
                    <p class="fit-member-text">{{ m.response }}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- ── Panel: `ab` two versions of the same cast, side by side ────── -->
          <div v-if="isPanel && isAbView && abVersions.length" class="sim-feed">
            <div class="sim-feed-head">
              <span>A/B comparison</span>
              <span class="sim-feed-count">one room, two versions</span>
            </div>
            <div v-if="abMoved.length" class="ab-moved">
              <span class="ab-moved-label">Who moved between versions:</span>
              <span v-for="m in abMoved" :key="m.id" class="ab-moved-item">
                {{ m.name }} — <span :class="`stance-${m.from}`">{{ stanceLabel(m.from) }}</span> → <span :class="`stance-${m.to}`">{{ stanceLabel(m.to) }}</span>
              </span>
            </div>
            <div class="ab-columns">
              <div v-for="v in abVersions" :key="v.key" class="ab-column" :class="`ab-${v.key}`">
                <div class="ab-col-head">
                  <span class="ab-col-title">{{ v.label }}</span>
                  <div class="ab-col-split">
                    <span v-for="(count, st) in v.stanceSplit" :key="st" class="fit-stance" :class="`stance-${st}`">
                      {{ stanceLabel(st) }} {{ count }}
                    </span>
                  </div>
                </div>
                <p class="ab-col-summary">{{ v.summary || 'No summary for this version.' }}</p>
                <div class="ab-col-pitch">{{ v.pitch }}</div>
                <div v-for="a in v.agents" :key="a.id" class="ab-person" @click="openChat(a.id)">
                  <img :src="a.avatarUrl" :alt="a.name" class="ab-person-avatar" />
                  <div class="ab-person-body">
                    <span class="ab-person-name">{{ a.name }}</span>
                    <span class="ab-person-stance" :class="`stance-${a.stance_after}`">{{ stanceLabel(a.stance_after) }}</span>
                    <p class="ab-person-text">{{ a.currentReaction }}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- ── Panel reactions (panel mode) — avatars clustered by stance ── -->
          <!-- Personas group into deterministic stance buckets; clicking a face
               opens an anchored popover with their reaction, and "Ask a
               follow-up" hands off to the existing chat slide-out. -->
          <div v-if="isPanel && !isPointerView && panelReactions.length" class="sim-feed">
            <div class="sim-feed-head">
              <span>Reactions</span>
              <span class="sim-feed-count">{{ panelReactions.length }} personas</span>
            </div>
            <div v-if="showCoach" class="coach-mark">
              <span class="coach-dot">👆</span>
              <span>Hover an agent to read their reaction — click to interview them.</span>
              <button class="coach-got" @click="dismissCoach">Got it</button>
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
            ref="popEl"
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
        <div v-if="showCoach && hasReactions" class="coach-mark coach-mark--room">
          <span class="coach-dot">💬</span>
          <span>Ask the room to follow up with everyone at once.</span>
        </div>
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

      <!-- ── Chat page — a full screen of its own, one persona at a time ── -->
      <section v-if="showChat" class="chat-page">
        <div class="chat-panel-header">
          <button class="chat-back-btn" @click="closeChat">
            <span class="flow-back-arrow">←</span>
            <span>Back to the room</span>
          </button>
          <div class="chat-panel-title">
            <span class="panel-icon">💬</span>
            <span>Chat with {{ selectedAgentName }}</span>
            <span v-if="selectedAgentArchetype" class="archetype-badge">{{ selectedAgentArchetype }}</span>
          </div>
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
        <!-- Collapsible so a long reaction doesn't push the chat off-screen. -->
        <div v-if="selectedAgent && selectedAgent.currentReaction" class="chat-agent-reaction">
          <button class="chat-agent-reaction-toggle" @click="reactionOpen = !reactionOpen">
            <span class="chat-agent-reaction-label">Their reaction</span>
            <span class="chat-agent-reaction-caret" :class="{ open: reactionOpen }">▾</span>
          </button>
          <p v-if="reactionOpen" class="chat-agent-reaction-text">{{ selectedAgent.currentReaction }}</p>
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
      </section>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
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
import { useToast } from '../../composables/useToast'
import { generateReport, getReportStatus, getReport } from '../../api/report'

const props = defineProps({
  query: { type: String, default: '' },
  mode: { type: String, default: 'sim' },  // 'sim' | 'panel'
  simulationId: { type: String, default: null },
  sessionId: { type: String, default: null },
  // Preview mode (/demo/chat): seed canned personas + replies and call no API,
  // so the results and chat screens can be looked at without running a sim.
  demo: { type: Boolean, default: false }
})
const emit = defineEmits(['back'])
const toast = useToast()

const isPanel = computed(() => props.mode === 'panel')

// ── Pointer state (panel mode) ─────────────────────────────────────────────
// `fit` renders a ranked segment list instead of the room; `ab` shows two
// versions of the same cast side by side. Everything here is real data — no
// LLM meant for presentation.
const panelPointer = ref(null)
const panelSlots = reactive({})
const fitRanking = ref([])
const abVersions = ref([])
const abMoved = ref([])
const isFitView = computed(() => isPanel.value && panelPointer.value === 'fit')
const isAbView = computed(() => isPanel.value && panelPointer.value === 'ab')
const isPointerView = computed(() => isFitView.value || isAbView.value)

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

// The roster the summary counts read off (live for both modes). Personas whose
// interview errored are excluded: every count downstream (stances, shifts, the
// dashboard) must be "of the people who actually answered", never "of the seats
// we booked". The seats are reported separately by `roomHealth` below, because
// dropping them quietly would present a shrunken room as the full one.
const panelAgents = computed(() => agents.value.filter(a => !a.failed))

// "10 of 12 answered." Null on a healthy round so the UI stays clean; only
// speaks up when there is something the user needs to discount.
const roomHealth = computed(() => {
  const seats = agents.value.length
  const answered = panelAgents.value.length
  if (!seats || answered === seats) return null
  return `${answered} of ${seats} people answered. ${seats - answered} could not be reached.`
})

// Panel reaction cards: only personas that actually returned reaction text.
// (Stance can be set without a response, so guard on currentReaction to avoid
// rendering blank cards.)
const panelReactions = computed(() =>
  panelAgents.value.filter(a => (a.currentReaction || '').trim())
)

// How many personas changed their mind so far (drives the "experience" read).
const shiftedCount = computed(() => panelAgents.value.filter(a => a.stance_changed).length)

// A short qualitative read of the room from the backend (LLM synthesis of the
// reactions — objections + what would move them). Real counts stay in
// summaryText; this only adds the "why". Empty when unavailable.
const llmSummary = ref('')

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
const popEl = ref(null)
let _popCloseTimer = null
const popAgent = computed(() => agents.value.find(a => a.id === popAgentId.value) || null)
const showReactionPop = (a, ev) => {
  if (_popCloseTimer) { clearTimeout(_popCloseTimer); _popCloseTimer = null }
  popAgentId.value = a.id
  const rect = ev.currentTarget.getBoundingClientRect()
  const W = 500, GAP = 10, MARGIN = 12
  const container = scrollContainer.value
  if (!container) { popStyle.value = { left: MARGIN + 'px', top: (rect.bottom + GAP) + 'px' }; return }
  // Position the box inside the scrolling results area so a long opinion grows
  // the box and extends the PAGE scroll (you scroll the page to read it).
  const crect = container.getBoundingClientRect()
  let left = rect.left - crect.left + container.scrollLeft + rect.width / 2 - W / 2
  left = Math.max(MARGIN, Math.min(left, container.clientWidth - W - MARGIN))
  const avatarTop = rect.top - crect.top + container.scrollTop
  const avatarBottom = rect.bottom - crect.top + container.scrollTop
  // Fit it in what you can actually SEE, not in the scroll canvas: on a short
  // window opening down would run under the bottom "Ask the room" bar. Render
  // hidden, measure, then pick the side with room; if neither has room, cap the
  // height so the box scrolls inside itself instead of being cut off.
  popStyle.value = { left: left + 'px', top: (avatarBottom + GAP) + 'px', visibility: 'hidden' }
  nextTick(() => {
    if (popAgentId.value !== a.id) return
    const h = popEl.value ? popEl.value.offsetHeight : 0
    const viewTop = container.scrollTop + MARGIN
    const viewBottom = container.scrollTop + container.clientHeight - MARGIN
    const roomBelow = viewBottom - (avatarBottom + GAP)
    const roomAbove = (avatarTop - GAP) - viewTop
    if (h <= roomBelow) {
      popStyle.value = { left: left + 'px', top: (avatarBottom + GAP) + 'px' }
    } else if (h <= roomAbove) {
      popStyle.value = { left: left + 'px', top: (avatarTop - GAP - h) + 'px' }
    } else if (roomAbove > roomBelow) {
      popStyle.value = { left: left + 'px', top: viewTop + 'px', maxHeight: roomAbove + 'px', overflowY: 'auto' }
    } else {
      popStyle.value = { left: left + 'px', top: (avatarBottom + GAP) + 'px', maxHeight: Math.max(roomBelow, 160) + 'px', overflowY: 'auto' }
    }
  })
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

// Coach marks on the results page: shown once per browser when the first
// reactions land (both modes), dismissable, and replayable any time from the
// "? How to use" button in the header. Declared after `feed` because the
// immediate watcher reads it on setup.
const COACH_KEY = 'crowds_results_coached_v1'
const showCoach = ref(false)
const hasReactions = computed(() => {
  if (!isPanel.value) return feed.value.length > 0
  if (isAbView.value) {
    return abVersions.value.some(v => v.agents.some(a => (a.currentReaction || '').trim()))
  }
  if (isFitView.value) return fitRanking.value.length > 0 || panelReactions.value.length > 0
  return panelReactions.value.length > 0
})
const dismissCoach = () => {
  showCoach.value = false
  try { localStorage.setItem(COACH_KEY, '1') } catch (_) { /* ignore */ }
}
const replayCoach = () => { showCoach.value = true }
watch(hasReactions, (has) => {
  if (has && !localStorage.getItem(COACH_KEY)) showCoach.value = true
}, { immediate: true })

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
    // Silence here is dangerous, not just untidy: the button resets and the user
    // believes the run is paused while it is still going.
    toast.error(paused.value ? 'Could not resume the run.'
                             : 'Could not pause. The run is still going.',
                { retry: togglePause })
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
    toast.error('Could not stop the run.', { retry: stopRun })
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

// ── Connection health ───────────────────────────────────────────────────────
// A poll fires every 2-3 seconds, so one failure means nothing — a blip would
// otherwise flash a scary message on a perfectly healthy run. Only after a few
// consecutive misses is the connection genuinely gone, and only then do we say
// so. Before this the feed simply stopped moving and a broken run was
// indistinguishable from a finished one.
const POLL_FAILS_BEFORE_WARNING = 3
let pollFails = 0
let offlineToastId = null

const notePollFailure = () => {
  pollFails++
  if (pollFails === POLL_FAILS_BEFORE_WARNING && offlineToastId === null) {
    offlineToastId = toast.error('Lost connection to the run. Retrying…')
  }
}

const notePollSuccess = () => {
  if (offlineToastId !== null) {
    toast.dismiss(offlineToastId)
    offlineToastId = null
    toast.info('Back online.')
  }
  pollFails = 0
}

const pollSimActions = async () => {
  if (!props.simulationId) return
  try {
    const res = await getRunStatusDetail(props.simulationId)
    if (res.success && res.data) {
      ;(res.data.all_actions || []).forEach(pushActionToFeed)
      scrollToBottom()
    }
    notePollSuccess()
  } catch (e) {
    notePollFailure()
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
    notePollSuccess()
  } catch (e) {
    notePollFailure()
  }
}

// A long run polled on fixed 2-3s intervals fires thousands of requests, which
// the hosting edge rate-limits (429 without CORS headers → the browser reports
// a bare "Network Error" and the run looks dead). So: one self-scheduling loop
// instead of two timers, a slower base cadence, no polling while the tab is
// hidden, and exponential backoff whenever calls are failing.
const POLL_BASE_MS = 6000
const POLL_MAX_MS = 60000
const STATUS_EVERY_N_TICKS = 2   // status check at half the action cadence
let pollTick = 0
let simPolling = false

const nextPollDelay = () => (
  pollFails === 0
    ? POLL_BASE_MS
    : Math.min(POLL_BASE_MS * Math.pow(2, pollFails), POLL_MAX_MS)
)

const scheduleNextPoll = () => {
  if (!simPolling) return
  actionTimer = setTimeout(simPollTick, nextPollDelay())
}

const simPollTick = async () => {
  // A hidden tab has nothing to show; keep the loop alive but spend no requests.
  if (typeof document !== 'undefined' && document.hidden) { scheduleNextPoll(); return }
  await pollSimActions()
  if (simPolling && pollTick % STATUS_EVERY_N_TICKS === 0) await pollSimStatus()
  pollTick++
  scheduleNextPoll()
}

const startSimPolling = () => {
  if (simPolling) return
  simPolling = true
  pollTick = 1   // status was just polled by startSim
  scheduleNextPoll()
}
const stopSimPolling = () => {
  simPolling = false
  if (actionTimer) { clearTimeout(actionTimer); actionTimer = null }
  // Polling stopping on purpose (run finished, view closed) must not leave a
  // "lost connection, retrying" bar on screen promising a retry that will never
  // come. Errors persist until dismissed, so this has to be explicit.
  if (offlineToastId !== null) { toast.dismiss(offlineToastId); offlineToastId = null }
  pollFails = 0
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
const applyRound = (results) => {
  const byId = {}
  for (const r of results) byId[r.agent_id] = r
  agents.value = agents.value.map(a => {
    const r = byId[a.id]
    if (!r) return a
    // A failed interview is not a quiet person. Its fallback text ("I have no
    // comment on that.") reads exactly like an opinion, and its stance_after is
    // copied from stance_before — so rendering it both invents a reaction and
    // counts that person as "did not move". Mark it and keep it out of the room.
    if (r.failed || r.error) {
      return { ...a, failed: true, currentReaction: '' }
    }
    return {
      ...a,
      failed: false,
      stance_before: r.stance_before || a.stance_before,
      stance_after: r.stance_after || r.stance_before || a.stance_after,
      stance_changed: !!r.stance_changed,
      currentReaction: r.response || a.currentReaction
    }
  })
}

// Build the A/B comparison: run (or reuse) one round per version against the
// SAME cast, then read who moved between them. Two rounds, one room.
const buildAb = async (rounds) => {
  const va = (panelSlots.version_a || '').trim()
  const vb = (panelSlots.version_b || '').trim()
  const versions = [
    { key: 'a', label: 'Version A', pitch: va || 'Version A' },
    { key: 'b', label: 'Version B', pitch: vb || 'Version B' },
  ]
  const byPitch = {}
  for (const r of rounds) byPitch[r.pitch] = r
  abVersions.value = []
  abMoved.value = []
  const perVersion = {}
  for (const v of versions) {
    let r = byPitch[v.pitch]
    if (!r) {
      const res = await pitchSession(props.sessionId, { pitch: v.pitch, concurrency: 6 })
      r = { pitch: v.pitch, result: { results: res.data?.results || [],
                                       summary_narrative: res.data?.summary_narrative || '' } }
    }
    const res = (r.result || {}).results || []
    const byId = {}
    for (const rr of res) byId[rr.agent_id] = rr
    const versionAgents = agents.value.map(a => {
      const rr = byId[a.id]
      return rr
        ? { ...a, stance_after: rr.stance_after || rr.stance_before || a.stance_after,
            currentReaction: rr.response || a.currentReaction }
        : a
    })
    const stanceSplit = {}
    for (const a of versionAgents) {
      const k = a.stance_after || 'neutral'
      stanceSplit[k] = (stanceSplit[k] || 0) + 1
    }
    perVersion[v.key] = { versionAgents, stanceSplit }
    abVersions.value.push({
      key: v.key, label: v.label, pitch: v.pitch,
      agents: versionAgents, stanceSplit,
      summary: (r.result || {}).summary_narrative || ''
    })
  }
  // Who moved between the two versions — deterministic per-agent comparison.
  const a = perVersion.a && perVersion.a.versionAgents
  const b = perVersion.b && perVersion.b.versionAgents
  if (a && b) {
    const bMap = {}
    for (const ag of b) bMap[ag.id] = ag
    const moved = []
    for (const ag of a) {
      const o = bMap[ag.id]
      if (o && o.stance_after !== ag.stance_after) {
        moved.push({ ...ag, from: ag.stance_after, to: o.stance_after })
      }
    }
    abMoved.value = moved
    llmSummary.value = moved.length
      ? `${moved.length} of ${a.length} personas reacted differently between the two versions.`
      : 'The two versions landed about the same across this room.'
  }
}

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
    panelPointer.value = detail.data?.pointer || null
    for (const k of Object.keys(panelSlots)) delete panelSlots[k]
    Object.assign(panelSlots, detail.data?.slots || {})

    // Existing rounds — a fresh assemble has none; a saved session has one+.
    let rounds = []
    try {
      const rRes = await listRounds(props.sessionId, true)
      rounds = rRes.data?.rounds || []
    } catch (_) { /* fall through to a fresh pitch */ }

    if (panelPointer.value === 'ab') {
      await buildAb(rounds)
    } else {
      const last = rounds[rounds.length - 1]
      let results = null
      if (last) {
        results = (last.result || {}).results || []
        llmSummary.value = (last.result || {}).summary_narrative || ''
        if (panelPointer.value === 'fit') fitRanking.value = (last.result || {}).by_segment || []
      }
      if (!results) {
        const res = await pitchSession(props.sessionId, { concurrency: 6 })
        results = res.data?.results || []
        llmSummary.value = res.data?.summary_narrative || ''
        if (panelPointer.value === 'fit') fitRanking.value = res.data?.by_segment || []
      }
      applyRound(results)
    }
  } catch (e) {
    // Includes the server refusing a collapsed round (503 "round_failed"), which
    // carries its own plain-English sentence — show that, not a generic one. The
    // room stays empty rather than half-drawn, which is the honest state.
    toast.error(e?.message || 'Could not load this panel.',
                { retry: loadPanel, code: e?.response?.data?.code })
  } finally {
    feedLive.value = false
  }
}

// ── Chat panel — slide-out, matches Step3Simulation ─────────────────────────
const showChat = ref(false)
const reactionOpen = ref(true)
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
  reactionOpen.value = true
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
    if (props.demo) {
      await new Promise(r => setTimeout(r, 700))
      reply = DEMO_REPLIES[demoReplyIndex++ % DEMO_REPLIES.length]
    } else if (isPanel.value) {
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
    if (props.demo) {
      await new Promise(r => setTimeout(r, 900))
      roomReplies.value = agents.value.map((a, i) => ({
        id: `${a.id}-demo-reply`, agentId: a.id, name: a.name, avatarUrl: a.avatarUrl,
        text: DEMO_REPLIES[i % DEMO_REPLIES.length]
      }))
    } else if (isPanel.value) {
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

// ── Demo fixtures (preview only) ────────────────────────────────────────────
const DEMO_AGENTS = [
  { id: 1, name: 'Nomsa Dlamini', archetype: 'retail supervisor', stance: 'concerned',
    currentReaction: "Honest reaction? Starting from R50 a month is sensible — too many people think investing needs a lump sum. What puts me off is trusting a startup I've never heard of with my money. Who backs it, is my money protected, and how fast can I get that R50 back if something urgent comes up?" },
  { id: 2, name: 'Sipho Mahlangu', archetype: 'delivery driver', stance: 'support',
    currentReaction: "R50 I can do. That's one takeaway I skip. If the app is simple and I can pull out when I need to, I'd try it this month." },
  { id: 3, name: 'Aisha Patel', archetype: 'small business owner', stance: 'neutral',
    currentReaction: "Low fees sound good, but low fees on a small amount is still small. Show me what R50 a month looks like after three years before I get excited." },
  { id: 4, name: 'Johan Venter', archetype: 'municipal clerk', stance: 'oppose',
    currentReaction: "I've been burned before. Until I see an FSCA licence number and a name I recognise on the board, this is a no from me." },
]
const DEMO_REPLIES = [
  "Fair enough. The trial account helps — I could test it without putting real money in.",
  "That answers the safety part. I'd still want to see it work for a month or two first.",
  "Okay, if I can withdraw that fast then the risk feels smaller than I thought.",
  "I hear you, but I'd want to ask my sister who works at a bank before I sign up.",
]
let demoReplyIndex = 0

const startDemo = () => {
  agents.value = DEMO_AGENTS.map(normalizeAgent)
  agents.value.forEach((a, i) => { a.currentReaction = DEMO_AGENTS[i].currentReaction })
  feed.value = DEMO_AGENTS.map((a, i) => ({
    id: 'demo-' + a.id,
    agent_id: a.id,
    agent_name: a.name,
    action_type: i === 0 ? 'post' : 'comment',
    round: i === 0 ? 1 : 2,
    content: a.currentReaction,
    stance_changed: false,
  }))
  feedLive.value = false
}

onMounted(() => {
  if (props.demo) startDemo()
  else if (isPanel.value) loadPanel()
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

/* Mobile: the results sidebar is decorative (recents label only) — hide it;
   the header's Back button is the way home. */
@media (max-width: 860px) {
  .sidebar { display: none; }
  .app-header { padding: 0 12px; flex-wrap: wrap; height: auto; min-height: 56px; row-gap: 4px; }
  .app-header .brand { display: none; }
  .header-right { gap: 10px; flex-wrap: wrap; }
}

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

/* ── Chat page — takes over the main column, one persona at a time ───────── */
.chat-page {
  flex: 1; min-height: 0;
  display: flex; flex-direction: column;
  background: #FFF;
}
.chat-panel-header {
  display: flex; align-items: center; gap: 16px;
  padding: 16px 20px; border-bottom: 1px solid #F0F0F0; flex-shrink: 0;
}
.chat-back-btn {
  display: flex; align-items: center; gap: 6px;
  background: none; border: 1px solid #E5E7EB; border-radius: 8px;
  padding: 6px 12px; font-size: 13px; color: #555; cursor: pointer;
}
.chat-back-btn:hover { border-color: #1E9E5A; color: #1E9E5A; }
.chat-panel-title { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 15px; color: #333; }
.panel-icon { font-size: 18px; }
.archetype-badge { font-size: 11px; font-weight: 500; padding: 2px 8px; background: #F0F0F0; color: #666; border-radius: 10px; text-transform: lowercase; }

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
.chat-agent-reaction { padding: 14px 20px; border-bottom: 1px solid #F0F0F0; background: #F9FAFB; flex-shrink: 0; }
.chat-agent-reaction-toggle {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  width: 100%; padding: 0; background: none; border: none; cursor: pointer; text-align: left;
}
.chat-agent-reaction-label {
  display: block; font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 700;
  letter-spacing: 0.5px; text-transform: uppercase; color: #9CA3AF;
}
.chat-agent-reaction-caret { font-size: 11px; color: #9CA3AF; transition: transform 0.15s ease; }
.chat-agent-reaction-caret.open { transform: rotate(180deg); }
.chat-agent-reaction-text { margin: 6px 0 0; font-size: 14px; line-height: 1.55; color: #374151; }

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
/* Chat page: keep everything in one readable centre column, like the room. */
.chat-page .chat-agent-card,
.chat-page .chat-agent-reaction,
.chat-page .chat-messages-list,
.chat-page .chat-input-container { max-width: 780px; margin-left: auto; margin-right: auto; width: 100%; }
.chat-page .chat-message { max-width: 70%; }

.main-content-area {
  flex: 1; overflow-y: scroll; position: relative;
  /* Force a visible scrollbar (override the browser's auto-hiding overlay bar). */
  scrollbar-width: thin; scrollbar-color: #B8C0C8 transparent;
}
.main-content-area::-webkit-scrollbar { width: 10px; }
.main-content-area::-webkit-scrollbar-track { background: transparent; }
.main-content-area::-webkit-scrollbar-thumb { background: #B8C0C8; border-radius: 5px; border: 2px solid transparent; background-clip: content-box; }
.main-content-area::-webkit-scrollbar-thumb:hover { background: #98A2AC; background-clip: content-box; }

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
  position: absolute; z-index: 61; width: 500px; max-width: calc(100% - 24px);
  background: #fff; border: 1px solid #E0E0E0; border-radius: 16px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18); padding: 18px;
  /* Lives in the scrolling results area: grows to the full opinion (no inner
     scrollbar); JS opens it down, or up when scrolled to the bottom. */
}
.pp-pop-head { display: flex; gap: 12px; align-items: center; margin-bottom: 10px; }
.pp-pop-head img { width: 46px; height: 46px; border-radius: 50%; border: 2px solid #1E9E5A; flex-shrink: 0; }
.pp-pop-id { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.pp-pop-name { font-weight: 700; font-size: 14px; color: #111; }
.pp-pop-role { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #9CA3AF; text-transform: lowercase; }
.pp-pop-tags { margin-bottom: 10px; }
/* Full reaction fills the box; the box itself scrolls (see .pp-pop) when the
   text is longer than the space below the avatar. */
.pp-pop-text { margin: 0; font-size: 14px; line-height: 1.6; color: #333; }

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

/* Degraded-round notice. Amber, not red: the round is usable, just short. */
.room-health {
  margin: 8px 20px 0;
  padding: 6px 10px;
  border-left: 3px solid #F59E0B;
  background: #FFFBEB;
  font-size: 12.5px;
  color: #92400E;
}
.spectrum-summary-body {
  padding: 16px 20px;
}
.spectrum-summary-body p {
  margin: 0;
  font-size: 14px; line-height: 1.6; color: #374151;
}
/* The LLM qualitative read sits under the deterministic counts, set apart. */
.summary-read {
  margin-top: 12px !important; padding-top: 12px;
  border-top: 1px solid #EEF0F2; color: #4B5563 !important;
}

/* First-time coach marks (results page) */
.coach-mark {
  display: flex; align-items: center; gap: 10px;
  margin: 0 24px 12px; padding: 10px 14px;
  background: #F0FBF4; border: 1px solid #BFE9CF; border-radius: 10px;
  font-size: 13px; color: #178048;
}
.coach-mark--room { margin: 0 24px 8px; }
.coach-mark--flush { margin: 8px 0 0; }
.coach-dot { font-size: 15px; line-height: 1; }
.coach-got {
  margin-left: auto; padding: 5px 12px; border: none; border-radius: 7px; cursor: pointer;
  background: #1E9E5A; color: #fff; font-size: 12px; font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}
.coach-got:hover { background: #178048; }
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

/* ── Scoped stance flavours (FlowResults owns these) ──────────────────────── */
.stance-support { background: rgba(30,158,90,0.12); color: #178048; }
.stance-neutral { background: #F3F4F6; color: #6B7280; }
.stance-concerned { background: #FFF4E5; color: #C2700A; }
.stance-oppose, .stance-resist { background: #FDEDEB; color: #C0392B; }

/* ── fit: ranked segment list ─────────────────────────────────────────────── */
.fit-ranking { display: flex; flex-direction: column; gap: 14px; }
.fit-card {
  border: 1px solid #E5E7EB; border-radius: 14px; padding: 14px 16px;
  background: #FFF; box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
.fit-card.top {
  border-color: #1E9E5A; background: #F7FCF9;
  box-shadow: 0 3px 14px rgba(30,158,90,0.14);
}
.fit-card-head {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin-bottom: 10px;
}
.fit-rank {
  font-family: 'JetBrains Mono', monospace; font-weight: 800; font-size: 0.8rem;
  color: #1E9E5A; background: rgba(30,158,90,0.1);
  border-radius: 8px; padding: 2px 8px;
}
.fit-card-label { font-size: 1rem; font-weight: 700; color: #111827; }
.fit-card-split { display: flex; gap: 6px; flex-wrap: wrap; margin-left: auto; }
.fit-stance {
  font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; font-weight: 700;
  border-radius: 999px; padding: 2px 9px;
}
.fit-member {
  display: flex; gap: 10px; padding: 8px 6px; border-radius: 10px;
  cursor: pointer; transition: background 0.12s;
}
.fit-member:hover { background: #F0FAF4; }
.fit-member-avatar { width: 32px; height: 32px; border-radius: 50%; flex: none; }
.fit-member-body { min-width: 0; }
.fit-member-name { font-size: 0.8rem; font-weight: 600; color: #333; }
.fit-member-stance {
  font-family: 'JetBrains Mono', monospace; font-size: 0.62rem; font-weight: 700;
  border-radius: 999px; padding: 1px 7px; margin-left: 6px; vertical-align: middle;
}
.fit-member-text {
  margin: 3px 0 0; font-size: 0.8rem; line-height: 1.5; color: #4B5563;
  white-space: pre-wrap;
}

/* ── ab: two versions of one room, side by side ───────────────────────────── */
.ab-moved {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 10px 14px; border: 1px solid #E5E7EB; border-radius: 12px;
  background: #FBFDFC; margin-bottom: 14px;
}
.ab-moved-label {
  font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; font-weight: 700;
  color: #9AA0A6; text-transform: uppercase; letter-spacing: 0.4px;
}
.ab-moved-item { font-size: 0.78rem; color: #374151; }
.ab-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.ab-column {
  border: 1px solid #E5E7EB; border-radius: 14px; padding: 14px 16px;
  background: #FFF;
}
.ab-column.ab-a { border-left: 3px solid #1E9E5A; }
.ab-column.ab-b { border-left: 3px solid #3B82F6; }
.ab-col-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.ab-col-title { font-size: 0.95rem; font-weight: 700; color: #111827; }
.ab-col-split { display: flex; gap: 5px; flex-wrap: wrap; margin-left: auto; }
.ab-col-summary {
  margin: 0 0 8px; font-size: 0.8rem; line-height: 1.5; color: #374151;
  background: #F7F8FA; border-radius: 8px; padding: 8px 10px;
}
.ab-col-pitch {
  font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #9AA0A6;
  border-bottom: 1px dashed #E5E7EB; padding-bottom: 8px; margin-bottom: 8px;
  white-space: pre-wrap;
}
.ab-person {
  display: flex; gap: 9px; padding: 7px 4px; border-radius: 9px; cursor: pointer;
  transition: background 0.12s;
}
.ab-person:hover { background: #F5F8FB; }
.ab-person-avatar { width: 30px; height: 30px; border-radius: 50%; flex: none; }
.ab-person-body { min-width: 0; }
.ab-person-name { font-size: 0.78rem; font-weight: 600; color: #333; }
.ab-person-stance {
  font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; font-weight: 700;
  border-radius: 999px; padding: 1px 7px; margin-left: 6px; vertical-align: middle;
}
.ab-person-text {
  margin: 3px 0 0; font-size: 0.78rem; line-height: 1.5; color: #4B5563;
  white-space: pre-wrap;
}

@media (max-width: 720px) { .ab-columns { grid-template-columns: 1fr; } }
</style>
