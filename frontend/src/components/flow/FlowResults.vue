<template>
  <div class="app-shell">
    <!-- ── Sidebar — exact copy of Home.vue ─────────────────────────────── -->
    <aside class="sidebar">
      <div class="sidebar-brand">
        <span class="brand-mark">f</span>
        <span class="brand-word"><span class="brand-strong">fub</span>sandbox</span>
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
            <span class="brand-mark">f</span>
            <span class="brand-word"><span class="brand-strong">fub</span>sandbox</span>
          </div>
        </div>
        <div class="header-right">
          <div class="workflow-step">
            <span class="step-name">Reactions</span>
          </div>
          <div class="step-divider"></div>
          <span class="status-indicator" :class="feedLive ? 'processing' : 'completed'">
            <span class="dot"></span>
            {{ feedLive ? 'Simulating' : 'Settled' }}
          </span>
        </div>
      </header>

      <!-- ── Simulation panel ──────────────────────────────────────────── -->
      <div class="simulation-panel">

        <!-- ── Timeline feed (sim mode) — exact copy of Step3Simulation ─── -->
        <div v-if="!isPanel" class="main-content-area" ref="scrollContainer">
          <div class="timeline-header" v-if="feed.length > 0">
            <div class="timeline-stats">
              <span class="total-count">TOTAL EVENTS: <span class="mono">{{ feed.length }}</span></span>
              <span class="platform-breakdown">
                <span class="breakdown-item opinion-space">
                  <svg class="mini-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"></circle><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"></path></svg>
                  <span class="mono">{{ feed.length }}</span>
                </span>
              </span>
            </div>
          </div>

          <div class="timeline-feed">
            <div class="timeline-axis"></div>

            <TransitionGroup name="timeline-item">
              <div
                v-for="action in feed"
                :key="action.uid"
                class="timeline-item opinion-space"
                @click="openChat(action.agent_id)"
                style="cursor: pointer;"
              >
                <div class="timeline-marker">
                  <div class="marker-dot"></div>
                </div>

                <div class="timeline-card">
                  <div class="card-header">
                    <div class="agent-info">
                      <div class="avatar-placeholder">{{ (action.agent_name || 'A')[0] }}</div>
                      <span class="agent-name">{{ action.agent_name }}</span>
                      <span v-if="action.stance_changed" class="agent-custom-badge">shifted</span>
                      <span class="chat-hint">💬</span>
                    </div>

                    <div class="header-meta">
                      <div class="platform-indicator">
                        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"></circle><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"></path></svg>
                      </div>
                      <div class="action-badge" :class="action.round === 1 ? 'badge-post' : 'badge-comment'">
                        {{ action.action_type }}
                      </div>
                    </div>
                  </div>

                  <div class="card-body">
                    <div class="content-text main-text">
                      {{ action.content }}
                    </div>

                    <div v-if="action.stance_changed" class="quoted-block">
                      <div class="quote-header">
                        <span class="quote-label">Stance shift</span>
                      </div>
                      <div class="quote-content">
                        {{ stanceLabel(action.stance_before) }} → {{ stanceLabel(action.stance_after) }}
                      </div>
                    </div>

                    <div v-if="action.round > 1" class="comment-context">
                      <svg class="icon-small" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>
                      <span>Round {{ action.round }} reaction</span>
                    </div>
                  </div>
                </div>
              </div>
            </TransitionGroup>

            <!-- Typing indicator while sim is live -->
            <div v-if="feedLive" class="timeline-item opinion-space">
              <div class="timeline-marker">
                <div class="marker-dot" style="background: #1E9E5A; animation: pulse 1s infinite;"></div>
              </div>
              <div class="timeline-card" style="opacity: 0.6;">
                <div class="chat-typing-indicator">
                  <span class="typing-dot"></span>
                  <span class="typing-dot"></span>
                  <span class="typing-dot"></span>
                  <span class="typing-text">More reactions forming…</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ── Stance spectrum (panel mode) ─────────────────────────────── -->
        <div v-else class="main-content-area" ref="scrollContainer">
          <!-- Pitched banner -->
          <div class="spectrum-pitched">
            <span class="spectrum-pitched-label">PITCHED:</span> {{ query }}
          </div>

          <!-- The stance spectrum box -->
          <div class="spectrum-box">
            <div class="spectrum-header">
              <span class="spectrum-title">Stance spectrum</span>
              <span class="spectrum-count">{{ panelAgents.length }} personas</span>
            </div>

            <!-- Stance groups — each a row with heading + avatar line -->
            <div class="spectrum-groups">
              <div
                v-for="s in STANCES"
                :key="s.key"
                class="spectrum-group"
                :class="{ empty: agentsByStance(s.key).length === 0 }"
              >
                <div class="spectrum-group-head">
                  <span class="spectrum-group-dot" :style="{ background: s.color }"></span>
                  <span class="spectrum-group-label">{{ s.label }}</span>
                  <span class="spectrum-group-count">{{ agentsByStance(s.key).length }}</span>
                </div>
                <div class="spectrum-group-avatars">
                  <div
                    v-for="agent in agentsByStance(s.key)"
                    :key="agent.id"
                    class="spectrum-avatar-wrap"
                    @mouseenter="hoveredAgent = agent"
                    @mouseleave="hoveredAgent = null"
                    @click="openChat(agent.id)"
                  >
                    <img :src="agent.avatarUrl" :alt="agent.name" class="spectrum-avatar" :style="{ '--ring': s.color }" />
                    <span class="spectrum-avatar-name">{{ agent.name }}</span>
                    <span v-if="agent.stance_changed" class="spectrum-shift-badge">shifted</span>

                    <!-- Hover popover: agent's opinion -->
                    <Transition name="pop">
                      <div v-if="hoveredAgent && hoveredAgent.id === agent.id" class="spectrum-popover">
                        <span class="spectrum-pop-name">{{ agent.name }}</span>
                        <span class="spectrum-pop-arch">{{ agent.archetype }}</span>
                        <span class="spectrum-pop-stance" :style="{ color: s.color }">{{ stanceLabel(agent.stance_after) }}</span>
                        <span class="spectrum-pop-text">{{ agent.currentReaction }}</span>
                      </div>
                    </Transition>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Typing indicator while panel is live -->
          <div v-if="feedLive" class="spectrum-typing">
            <div class="chat-typing-indicator">
              <span class="typing-dot"></span>
              <span class="typing-dot"></span>
              <span class="typing-dot"></span>
              <span class="typing-text">Panel is reacting…</span>
            </div>
          </div>

          <!-- Summary of what agents feel -->
          <div class="spectrum-summary">
            <div class="spectrum-summary-head">Summary</div>
            <div class="spectrum-summary-body">
              <p>{{ summaryText }}</p>
            </div>
            <div class="spectrum-summary-tags">
              <span
                v-for="s in STANCES"
                :key="s.key"
                v-show="agentsByStance(s.key).length > 0"
                class="spectrum-summary-tag"
                :style="{ '--tag-color': s.color }"
              >
                {{ agentsByStance(s.key).length }} {{ s.label.toLowerCase() }}
              </span>
            </div>
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
  broadcastIntervention
} from '../../api/simulation'
import { getSession, pitchSession, askAgent, listRounds } from '../../api/panel'

const props = defineProps({
  query: { type: String, default: '' },
  mode: { type: String, default: 'sim' },  // 'sim' | 'panel'
  simulationId: { type: String, default: null },
  sessionId: { type: String, default: null }
})
const emit = defineEmits(['back'])

const isPanel = computed(() => props.mode === 'panel')

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

// Panel-specific state
const hoveredAgent = ref(null)

// Panel agents — the spectrum reads straight off the live roster.
const panelAgents = computed(() => agents.value)

// Summary text — qualitative read of where the room sits
const summaryText = computed(() => {
  const total = panelAgents.value.length
  const support = agentsByStance('support').length
  const concerned = agentsByStance('concerned').length
  const oppose = agentsByStance('oppose').length
  const neutral = agentsByStance('neutral').length

  if (support > total / 2) return 'The room leans positive. Most personas are won over or warming to the pitch, though a few still have conditions before they would commit.'
  if (oppose > total / 2) return 'The room leans resistant. Most personas are unconvinced or actively opposed — the pitch is not landing with this group as it stands.'
  if (concerned > total / 3) return 'The room is cautious. A large share is unconviced — they see potential but have specific conditions or objections before they would engage.'
  if (neutral >= total / 2) return 'The room is curious but undecided. Most personas are open to hearing more, but nobody is committed yet.'
  return 'The room is mixed. Opinions are spread across the spectrum with no clear majority in any direction.'
})

// ── Feed — timeline actions ─────────────────────────────────────────────────
const feed = ref([])
const feedLive = ref(true)
const scrollContainer = ref(null)

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
@keyframes pulse { 50% { opacity: 0.5; } }

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
.chat-agent-reaction { padding: 14px 20px; border-bottom: 1px solid #F0F0F0; background: #F9FAFB; flex-shrink: 0; }
.chat-agent-reaction-label {
  display: block; font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 700;
  letter-spacing: 0.5px; text-transform: uppercase; color: #9CA3AF; margin-bottom: 6px;
}
.chat-agent-reaction-text { margin: 0; font-size: 14px; line-height: 1.55; color: #374151; }

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

/* ── Timeline feed — exact copy of Step3Simulation ────────────────────────── */
.main-content-area { flex: 1; overflow-y: auto; }
.timeline-header { padding: 16px 24px; border-bottom: 1px solid #F0F0F0; }
.timeline-stats { display: flex; align-items: center; gap: 16px; }
.total-count { font-size: 11px; font-weight: 600; color: #666; text-transform: uppercase; letter-spacing: 0.05em; }
.platform-breakdown { display: flex; align-items: center; gap: 8px; }
.breakdown-item { display: flex; align-items: center; gap: 4px; font-size: 11px; color: #666; }
.breakdown-item.opinion-space { color: #000; }
.mini-icon { opacity: 0.6; }

.timeline-feed { padding: 24px 0; position: relative; min-height: 100%; max-width: 900px; margin: 0 auto; }
.timeline-axis { position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: #EAEAEA; transform: translateX(-50%); }
.timeline-item { display: flex; justify-content: center; margin-bottom: 32px; position: relative; width: 100%; }
.timeline-marker { position: absolute; left: 50%; top: 24px; width: 10px; height: 10px; background: #FFF; border: 1px solid #CCC; border-radius: 50%; transform: translateX(-50%); z-index: 2; display: flex; align-items: center; justify-content: center; }
.marker-dot { width: 4px; height: 4px; background: #CCC; border-radius: 50%; }
.timeline-item.opinion-space .marker-dot { background: #000; }
.timeline-item.opinion-space .timeline-marker { border-color: #000; }

/* Card */
.timeline-card { width: calc(100% - 48px); background: #FFF; border-radius: 2px; padding: 16px 20px; border: 1px solid #EAEAEA; box-shadow: 0 2px 10px rgba(0,0,0,0.02); position: relative; transition: all 0.2s; }
.timeline-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.05); border-color: #DDD; }
.timeline-item.opinion-space { justify-content: flex-start; padding-right: 50%; }
.timeline-item.opinion-space .timeline-card { margin-left: auto; margin-right: 32px; }

/* Card content */
.card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #F5F5F5; }
.agent-info { display: flex; align-items: center; gap: 10px; }
.avatar-placeholder { width: 24px; height: 24px; background: #000; color: #FFF; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; text-transform: uppercase; }
.agent-name { font-size: 13px; font-weight: 600; color: #000; }
.chat-hint { margin-left: 6px; font-size: 14px; opacity: 0; transition: opacity 0.2s; }
.timeline-item:hover .chat-hint { opacity: 1; }
.agent-custom-badge { margin-left: 6px; font-size: 10px; font-weight: 600; line-height: 1; color: #1E9E5A; background: rgba(30, 158, 90, 0.10); border: 1px solid rgba(30, 158, 90, 0.35); padding: 2px 6px; border-radius: 10px; white-space: nowrap; }
.header-meta { display: flex; align-items: center; gap: 8px; }
.platform-indicator { color: #999; display: flex; align-items: center; }
.action-badge { font-size: 9px; padding: 2px 6px; border-radius: 2px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; border: 1px solid transparent; }
.badge-post { background: #F0F0F0; color: #333; border-color: #E0E0E0; }
.badge-comment { background: #F0F0F0; color: #666; border-color: #E0E0E0; }

.content-text { font-size: 13px; line-height: 1.6; color: #333; margin-bottom: 10px; }
.content-text.main-text { font-size: 14px; color: #000; }

.quoted-block { background: #F9F9F9; border: 1px solid #EEE; padding: 10px 12px; border-radius: 2px; margin-top: 8px; font-size: 12px; color: #555; }
.quote-header { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; font-size: 11px; color: #666; }
.quote-label { font-weight: 600; }
.quote-content { font-size: 12px; color: #555; }

.comment-context { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; font-size: 11px; color: #666; }
.icon-small { opacity: 0.6; }

/* Timeline transitions */
.timeline-item-enter-active, .timeline-item-leave-active { transition: all 0.4s ease; }
.timeline-item-enter-from { opacity: 0; transform: translateY(20px); }
.timeline-item-leave-to { opacity: 0; transform: translateX(-20px); }

/* ── Stance spectrum (panel mode) ─────────────────────────────────────────── */
.spectrum-pitched {
  margin: 16px 24px 0;
  padding: 10px 14px;
  background: #FAFAFA; border: 1px solid #EEE; border-radius: 12px;
  font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #555; line-height: 1.5;
}
.spectrum-pitched-label { color: #1E9E5A; font-weight: 700; margin-right: 6px; }

.spectrum-box {
  margin: 16px 24px;
  background: #FFF; border: 1px solid #E5E7EB; border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  /* visible so the reaction popover can extend below an avatar row without being clipped */
  overflow: visible;
}
.spectrum-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 20px; border-bottom: 1px solid #E5E7EB; background: #F9FAFB;
}
.spectrum-title { font-size: 14px; font-weight: 600; color: #1F2937; }
.spectrum-count { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #9CA3AF; }

/* Stance groups — each stance is a row with heading + avatar line, separated by dividers */
.spectrum-groups {
  padding: 4px 0;
}
.spectrum-group {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 16px 20px;
  border-bottom: 1px solid #F0F0F0;
}
.spectrum-group:last-child { border-bottom: none; }
.spectrum-group.empty { opacity: 0.4; }

.spectrum-group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  width: 140px;
}
.spectrum-group-dot {
  width: 8px; height: 8px; border-radius: 50%;
  flex-shrink: 0;
}
.spectrum-group-label {
  font-size: 13px; font-weight: 600; color: #1F2937;
}
.spectrum-group-count {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px; color: #9CA3AF;
}

.spectrum-group-avatars {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  flex: 1;
}

.spectrum-avatar-wrap {
  position: relative; display: flex; flex-direction: column;
  align-items: center; gap: 4px; cursor: pointer;
}
.spectrum-avatar {
  width: 40px; height: 40px; border-radius: 50%;
  border: 3px solid var(--ring, #E5E7EB);
  background: #FFF;
  box-shadow: 0 2px 6px rgba(0,0,0,0.08);
  transition: transform 0.16s ease, box-shadow 0.16s ease;
}
.spectrum-avatar-wrap:hover .spectrum-avatar {
  transform: scale(1.15);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.16);
}
.spectrum-avatar-name {
  font-size: 10px; font-weight: 600; color: #374151;
  white-space: nowrap;
}
.spectrum-shift-badge {
  font-size: 7px; font-weight: 700; color: #1E9E5A;
  background: rgba(30, 158, 90, 0.1);
  border: 1px solid rgba(30, 158, 90, 0.35);
  padding: 0 4px; border-radius: 6px;
  white-space: nowrap;
}

/* Reaction popover — sits below the avatar and pops up from the bottom.
   Wider + larger type so the full reaction is comfortable to read. */
.spectrum-popover {
  position: absolute; top: calc(100% + 12px); left: 50%;
  transform: translateX(-50%);
  width: 340px; max-width: 78vw; background: #FFF; border: 1px solid #E5E7EB;
  border-radius: 12px; padding: 16px 18px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.16);
  display: flex; flex-direction: column; gap: 6px;
  z-index: 30; pointer-events: none;
}
.spectrum-popover::after {
  content: ''; position: absolute; bottom: 100%; left: 50%;
  transform: translateX(-50%);
  border: 7px solid transparent; border-bottom-color: #FFF;
}
.spectrum-pop-name { font-size: 15px; font-weight: 700; color: #1F2937; }
.spectrum-pop-arch { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #9CA3AF; }
.spectrum-pop-stance { font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 700; text-transform: uppercase; }
.spectrum-pop-text { font-size: 14px; line-height: 1.55; color: #374151; margin-top: 4px; }

/* Rise up into place from below — "pop out from the bottom". */
.pop-enter-active, .pop-leave-active { transition: opacity 0.18s ease, transform 0.18s ease; }
.pop-enter-from, .pop-leave-to { opacity: 0; transform: translateX(-50%) translateY(8px); }

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
  padding: 14px 20px;
  border-bottom: 1px solid #E5E7EB;
  background: #F9FAFB;
  font-size: 14px; font-weight: 600; color: #1F2937;
}
.spectrum-summary-body {
  padding: 16px 20px;
}
.spectrum-summary-body p {
  margin: 0;
  font-size: 14px; line-height: 1.6; color: #374151;
}
.spectrum-summary-tags {
  display: flex; flex-wrap: wrap; gap: 8px;
  padding: 0 20px 16px;
}
.spectrum-summary-tag {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px; font-weight: 600;
  color: var(--tag-color, #666);
  background: #F9FAFB;
  border: 1px solid #E5E7EB;
  padding: 3px 10px; border-radius: 999px;
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

@media (max-width: 760px) {
  .timeline-axis { left: 20px; }
  .timeline-marker { left: 20px; }
  .timeline-item.opinion-space { padding-right: 0; padding-left: 40px; }
  .timeline-item.opinion-space .timeline-card { margin-right: 0; margin-left: 0; }
}
</style>
