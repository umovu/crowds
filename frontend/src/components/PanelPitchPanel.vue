<template>
  <div class="panel-pitch">

    <!-- Intro strap -->
    <header class="pp-header">
      <div>
        <div class="pp-tag">PANEL PITCH</div>
        <h2 class="pp-title">Pitch it straight to the people it's for.</h2>
        <p class="pp-sub">
          Pick a group, assemble a panel of data-backed personas, and get honest reactions in
          seconds — no simulation build. Same cast, every variant, so differences come from your
          pitch, not the room.
        </p>
      </div>
      <div class="pp-header-right">
        <div class="pp-session-bar">
          <button class="pp-link-btn" :class="{ active: showPast }" :disabled="busy" @click="openPast">Past panels ▾</button>
          <button v-if="session" class="pp-link-btn" :disabled="busy" @click="newPanel">+ New panel</button>
        </div>
        <div class="pp-mode-switch">
          <button class="pp-mode-btn" :class="{ active: mode === 'product' }" :disabled="busy || !!session" @click="mode = 'product'">Product</button>
          <button class="pp-mode-btn" :class="{ active: mode === 'policy' }" :disabled="busy || !!session" @click="mode = 'policy'">Policy</button>
        </div>
      </div>

      <!-- Past panels dropdown — saved sessions on disk, click to reopen -->
      <div v-if="showPast" class="pp-past">
        <div v-if="pastSessions.length === 0" class="pp-past-empty">No saved panels yet.</div>
        <button
          v-for="s in pastSessions"
          :key="s.session_id"
          class="pp-past-row"
          :class="{ current: session && session.session_id === s.session_id }"
          @click="restoreSession(s.session_id)"
        >
          <span class="pp-past-pitch">{{ s.pitch || '(no pitch)' }}</span>
          <span class="pp-past-meta">
            {{ s.segment_label }} · {{ s.cast_size }} personas · {{ s.rounds_run || 0 }} round{{ (s.rounds_run || 0) !== 1 ? 's' : '' }}
            · {{ (s.created_at || '').slice(0, 16).replace('T', ' ') }}
          </span>
        </button>
      </div>
    </header>

    <div v-if="session" class="pp-resumed-banner">
      Resumed panel — saved on disk. Reactions persist across refresh.
    </div>

    <!-- 01 / The pitch -->
    <section class="pp-section">
      <div class="pp-section-header">
        <span>01 / {{ mode === 'product' ? 'THE PITCH' : 'THE ANNOUNCEMENT' }}</span>
        <span>Required</span>
      </div>
      <textarea
        v-model="pitchText"
        class="pp-textarea"
        rows="4"
        :disabled="busy"
        :placeholder="mode === 'product'
          ? 'Describe the product and the price. e.g. A R99/month prepaid solar lantern subscription for township households, paid via airtime.'
          : 'Describe the policy or announcement. e.g. A new municipal water tariff adding R150/month for households above 6kL.'"
      ></textarea>
    </section>

    <!-- 02 / Who's in the room -->
    <section class="pp-section">
      <div class="pp-section-header">
        <span>02 / WHO'S IN THE ROOM — pick one group or mix several</span>
        <span>{{ selectedSegmentLabel }}</span>
      </div>
      <div class="pp-segments">
        <button
          v-for="seg in segments"
          :key="seg.id"
          class="pp-segment"
          :class="{ selected: selectedSegments.includes(seg.id) }"
          :disabled="busy"
          @click="toggleSegment(seg.id)"
        >
          <span class="pp-segment-top">
            <span class="pp-segment-label">{{ seg.label }}</span>
            <span class="pp-segment-count">{{ seg.count }}</span>
          </span>
          <span class="pp-segment-desc">{{ seg.description }}</span>
        </button>
      </div>

      <div class="pp-controls">
        <span class="pp-control-label">Panel size</span>
        <div class="pp-size-btns">
          <button
            v-for="opt in sizeOptions"
            :key="opt"
            class="pp-size-btn"
            :class="{ active: size === opt }"
            :disabled="busy"
            @click="size = opt"
          >{{ opt }}</button>
        </div>
        <button
          class="pp-assemble-btn"
          :disabled="!pitchText.trim() || busy"
          @click="assemblePanel()"
        >
          <span v-if="assembling">Assembling…</span>
          <span v-else-if="session">Re-assemble panel</span>
          <span v-else>Assemble panel</span>
          <span>→</span>
        </button>
      </div>
      <div v-if="error" class="pp-error">{{ error }}</div>
    </section>

    <!-- 03 / The room -->
    <section v-if="session" class="pp-section">
      <div class="pp-section-header">
        <span>03 / THE ROOM</span>
        <span>{{ session.cast_size }} personas · {{ allocationLine }} <template v-if="session.mode === 'product'">· budget mix {{ tierMixLine }}</template></span>
      </div>
      <div class="pp-roster">
        <span v-for="a in session.agents" :key="a.id" class="pp-roster-chip" :title="a.persona || ''">
          <span class="pp-roster-name">{{ a.name }}</span>
          <span class="pp-roster-meta">{{ pretty(a.actor_archetype) }} · {{ a.province }}</span>
          <span v-if="a.budget_tier" class="pp-tier" :class="'tier-' + a.budget_tier">{{ a.budget_tier }}</span>
        </span>
      </div>
      <div class="pp-room-actions">
        <button class="pp-reroll-btn" :disabled="busy" @click="assemblePanel(true)" title="Same group, different people">↻ Re-roll the room</button>
        <button class="pp-pitch-btn" :disabled="busy" @click="runPitch()">
          <span v-if="pitching">Panel is reacting… ({{ session.cast_size }} personas, ~{{ Math.ceil(session.cast_size / 6) * 10 }}s)</span>
          <span v-else>Pitch this panel</span>
          <span v-if="!pitching">→</span>
        </button>
      </div>
    </section>

    <!-- 04 / Reactions -->
    <section v-if="rounds.length > 0" class="pp-section">
      <div class="pp-section-header">
        <span>04 / REACTIONS</span>
        <span>{{ rounds.length }} round{{ rounds.length !== 1 ? 's' : '' }}</span>
      </div>

      <!-- Round tabs (variants) -->
      <div class="pp-round-tabs">
        <button
          v-for="(r, idx) in rounds"
          :key="idx"
          class="pp-round-tab"
          :class="{ active: activeRound === idx }"
          @click="activeRound = idx"
          :title="r.pitch"
        >Round {{ r.round }}</button>
        <button class="pp-round-tab variant" :disabled="busy" @click="showVariant = !showVariant">+ Pitch a variant</button>
      </div>

      <!-- Variant composer -->
      <div v-if="showVariant" class="pp-variant">
        <textarea
          v-model="variantText"
          class="pp-textarea"
          rows="3"
          :disabled="busy"
          placeholder="Change the price, the framing, the offer — same panel, so the difference is your pitch."
        ></textarea>
        <button class="pp-pitch-btn" :disabled="!variantText.trim() || busy" @click="runPitch(variantText)">
          <span v-if="pitching">Panel is reacting…</span>
          <span v-else>Pitch variant to the same panel →</span>
        </button>
      </div>

      <template v-if="currentRound">
        <!-- What was pitched -->
        <div class="pp-pitched">
          <span class="pp-pitched-label">PITCHED:</span> {{ currentRound.pitch }}
        </div>

        <!-- Dashboard strip: counts of qualitative outputs, never a buy score -->
        <div class="pp-dash">
          <div class="pp-dash-card">
            <div class="pp-dash-value">{{ currentRound.successful }}/{{ currentRound.total_interviewed }}</div>
            <div class="pp-dash-label">reactions</div>
          </div>
          <div class="pp-dash-card">
            <div class="pp-dash-value">{{ dashboard.stance_changed_count ?? 0 }}</div>
            <div class="pp-dash-label">stances shifted</div>
          </div>
          <div class="pp-dash-card">
            <div class="pp-dash-value">{{ stanceLine }}</div>
            <div class="pp-dash-label">stance spread</div>
          </div>
          <div class="pp-dash-card">
            <div class="pp-dash-value">{{ emotionLine }}</div>
            <div class="pp-dash-label">emotional temperature</div>
          </div>
          <div v-if="session && session.mode === 'product'" class="pp-dash-card">
            <div class="pp-dash-value">{{ tierMixLine }}</div>
            <div class="pp-dash-label">budget mix (from real data)</div>
          </div>
        </div>

        <!-- Reaction map — avatars clustered by stance, click a face to open
             that persona's reaction + follow-up. Clustering is deterministic
             (stance buckets), so it holds with the LLM switched off. -->
        <div class="pp-clusters">
          <div v-for="c in reactionClusters" :key="c.key" class="pp-cluster">
            <div class="pp-cluster-head">
              <span class="pp-cluster-name">{{ c.label }}</span>
              <span class="pp-cluster-count">{{ c.members.length }}</span>
            </div>
            <div class="pp-cluster-avatars">
              <button
                v-for="r in c.members"
                :key="r.agent_id"
                class="pp-av-btn"
                :class="{ active: activeAgentId === r.agent_id, failed: r.error }"
                :title="r.agent_name"
                @click.stop="openReaction(r, $event)"
              >
                <img :src="avatarFor(r.agent_name || ('Agent ' + r.agent_id))" :alt="r.agent_name" />
              </button>
            </div>
          </div>
        </div>

        <!-- Persona popover — anchored to the clicked avatar -->
        <div v-if="activeResult" class="pp-pop-backdrop" @click="closeReaction"></div>
        <div v-if="activeResult" class="pp-pop" :style="popStyle" @click.stop>
          <div class="pp-pop-head">
            <img :src="avatarFor(activeResult.agent_name || ('Agent ' + activeResult.agent_id))" :alt="activeResult.agent_name" />
            <div class="pp-pop-id">
              <span class="pp-pop-name">{{ activeResult.agent_name || ('Agent ' + activeResult.agent_id) }}</span>
              <span class="pp-pop-role">{{ pretty(activeResult.actor_archetype) }}</span>
            </div>
            <button class="pp-pop-close" @click="closeReaction">×</button>
          </div>
          <div class="pp-pop-tags">
            <span v-if="activeResult.stance_changed" class="pp-feed-shift">
              {{ stanceLabel(activeResult.stance_before) }} → {{ stanceLabel(activeResult.stance_after) }}
            </span>
            <span v-if="activeResult.budget_tier" class="pp-tier" :class="'tier-' + activeResult.budget_tier" title="Computed from real persona data — not the model's opinion">{{ activeResult.budget_tier }}</span>
          </div>
          <p class="pp-pop-text">{{ activeResult.response }}</p>

          <!-- Follow-up thread -->
          <div v-if="followups[activeResult.agent_id] && followups[activeResult.agent_id].thread.length" class="pp-thread">
            <div v-for="(qa, i) in followups[activeResult.agent_id].thread" :key="i" class="pp-thread-item">
              <div class="pp-thread-q">You: {{ qa.q }}</div>
              <div class="pp-thread-a">{{ qa.a }}</div>
            </div>
          </div>
          <div class="pp-followup">
            <input
              v-model="followupDrafts[activeResult.agent_id]"
              class="pp-followup-input"
              :placeholder="'Ask ' + firstName(activeResult.agent_name) + ' a follow-up…'"
              :disabled="isAsking(activeResult.agent_id)"
              @keyup.enter="ask(activeResult.agent_id)"
            />
            <button class="pp-followup-btn" :disabled="!(followupDrafts[activeResult.agent_id] || '').trim() || isAsking(activeResult.agent_id)" @click="ask(activeResult.agent_id)">
              {{ isAsking(activeResult.agent_id) ? '…' : 'Ask' }}
            </button>
          </div>
        </div>
      </template>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { createAvatar } from '@dicebear/core'
import { avataaars } from '@dicebear/collection'
import { listSegments, createSession, getSession, pitchSession, askAgent, listSessions, listRounds } from '../api/panel'

// DiceBear avatar per persona — seeded by name so the same face is stable
// across rounds and reopens.
const _avatarCache = new Map()
const avatarFor = (name) => {
  const seed = name || 'unknown'
  if (_avatarCache.has(seed)) return _avatarCache.get(seed)
  const svg = createAvatar(avataaars, {
    seed, radius: 50,
    backgroundColor: ['b6e3f4', 'c0e8d5', 'fde68a', 'ffd6a5'],
    backgroundType: ['solid'],
  }).toString()
  const uri = `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
  _avatarCache.set(seed, uri)
  return uri
}

const ACTIVE_KEY = 'panelPitch.activeSession'

const segments = ref([])
const pastSessions = ref([])       // saved sessions on disk (for "Past panels")
const showPast = ref(false)
// Multi-select: "everyone" is exclusive (it's already the full mix); picking
// any specific group drops it, and clearing every group falls back to it.
const selectedSegments = ref(['everyone'])
const mode = ref('product')
const pitchText = ref('')
const size = ref(12)
const sizeOptions = [8, 12, 20]

const session = ref(null)          // meta + agents
const rounds = ref([])             // [{ round, pitch, results, impact_dashboard, ... }]
const activeRound = ref(0)
const showVariant = ref(false)
const variantText = ref('')

const assembling = ref(false)
const pitching = ref(false)
const error = ref('')
const followups = reactive({})       // agent_id -> { loading, thread: [{q, a}] }
const followupDrafts = reactive({})  // agent_id -> draft text

const busy = computed(() => assembling.value || pitching.value)
const currentRound = computed(() => rounds.value[activeRound.value] || null)
const dashboard = computed(() => currentRound.value?.impact_dashboard || {})

const toggleSegment = (id) => {
  if (id === 'everyone') {
    selectedSegments.value = ['everyone']
    return
  }
  let next = selectedSegments.value.filter(s => s !== 'everyone')
  next = next.includes(id) ? next.filter(s => s !== id) : [...next, id]
  selectedSegments.value = next.length ? next : ['everyone']
}

const selectedSegmentLabel = computed(() => {
  const chosen = segments.value.filter(s => selectedSegments.value.includes(s.id))
  if (chosen.length === 0) return ''
  if (chosen.length === 1) return `${chosen[0].label} · ${chosen[0].count} in library`
  return `Mixing ${chosen.length} groups: ${chosen.map(s => s.label).join(' + ')}`
})

const allocationLine = computed(() => {
  const alloc = session.value?.segment_allocation || {}
  const parts = Object.entries(alloc).map(([label, count]) => `${count} ${label}`)
  return parts.length > 1 ? parts.join(' · ') : (session.value?.segment_label || '')
})

const tierMixLine = computed(() => {
  const dist = session.value?.budget_tier_distribution || {}
  return ['tight', 'moderate', 'loose']
    .filter(t => dist[t])
    .map(t => `${dist[t]} ${t}`)
    .join(' · ') || '—'
})

const stanceLine = computed(() => {
  const dist = dashboard.value.stance_distribution || {}
  return Object.entries(dist).sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `${v} ${stanceLabel(k)}`).join(' · ') || '—'
})

const emotionLine = computed(() => {
  const dist = dashboard.value.emotional_temperature || {}
  return Object.entries(dist).sort((a, b) => b[1] - a[1]).slice(0, 3)
    .map(([k, v]) => `${v} ${k}`).join(' · ') || '—'
})

const pretty = (s) => (s || '').replace(/_/g, ' ')

// ── Reaction map: cluster personas by stance, deterministically ──────────────
// Buckets in a fixed spread (won-over → resistant), labelled via stanceLabel so
// product mode reads "won over / curious / unconvinced …". No LLM, no scoring.
const STANCE_ORDER = ['support', 'neutral', 'concerned', 'oppose', 'resist']
const reactionClusters = computed(() => {
  const results = currentRound.value?.results || []
  const groups = {}
  for (const r of results) {
    const key = r.stance_after || r.stance_before || 'neutral'
    ;(groups[key] || (groups[key] = [])).push(r)
  }
  const keys = [...STANCE_ORDER, ...Object.keys(groups).filter(k => !STANCE_ORDER.includes(k))]
  return keys.filter(k => groups[k]?.length).map(k => ({ key: k, label: stanceLabel(k), members: groups[k] }))
})

// Popover anchored to the clicked avatar.
const activeAgentId = ref(null)
const popStyle = ref({})
const activeResult = computed(() =>
  (currentRound.value?.results || []).find(r => r.agent_id === activeAgentId.value) || null
)
const openReaction = (r, ev) => {
  if (activeAgentId.value === r.agent_id) { activeAgentId.value = null; return }
  activeAgentId.value = r.agent_id
  const rect = ev.currentTarget.getBoundingClientRect()
  const POP_W = 380
  let left = rect.left + rect.width / 2 - POP_W / 2
  left = Math.max(12, Math.min(left, window.innerWidth - POP_W - 12))
  popStyle.value = { left: left + 'px', top: (rect.bottom + 10) + 'px' }
}
const closeReaction = () => { activeAgentId.value = null }

// Product mode shows the reaction ladder instead of policy stance words.
const PRODUCT_STANCE_LABELS = {
  support: 'won over', neutral: 'curious', concerned: 'unconvinced',
  oppose: 'resistant', resist: 'hostile',
}
const stanceLabel = (s) => (session.value && session.value.mode === 'product'
  ? (PRODUCT_STANCE_LABELS[s] || s) : s)
const firstName = (s) => (s || 'them').split(' ')[0]
const isAsking = (id) => !!(followups[id] && followups[id].loading)

const loadSegments = async () => {
  try {
    const res = await listSegments()
    segments.value = res.data.segments
  } catch (e) {
    error.value = 'Could not load groups: ' + e.message
  }
}

const assemblePanel = async (reroll = false) => {
  if (!pitchText.value.trim() || busy.value) return
  assembling.value = true
  error.value = ''
  try {
    const res = await createSession({
      pitch: pitchText.value.trim(),
      mode: mode.value,
      n: size.value,
      segments: selectedSegments.value,
      // Re-roll = same groups, different people. Otherwise stable for the session.
      seed: reroll ? Math.floor(Math.random() * 1000000) : undefined,
    })
    const detail = await getSession(res.data.session_id)
    session.value = detail.data
    // New room invalidates old reactions — they belonged to different people.
    rounds.value = []
    activeRound.value = 0
    showVariant.value = false
    Object.keys(followups).forEach(k => delete followups[k])
    localStorage.setItem(ACTIVE_KEY, session.value.session_id)  // survive refresh
  } catch (e) {
    error.value = e.message
  } finally {
    assembling.value = false
  }
}

// Reconnect to a session saved on disk — full roster + every past round +
// follow-up threads, so a refresh or "Past panels" click looks like you left it.
const restoreSession = async (sessionId) => {
  assembling.value = true
  error.value = ''
  try {
    const detail = await getSession(sessionId)
    session.value = detail.data
    pitchText.value = detail.data.pitch || pitchText.value
    if (Array.isArray(detail.data.segments) && detail.data.segments.length) {
      selectedSegments.value = detail.data.segments
    }
    if (detail.data.mode) mode.value = detail.data.mode

    const rRes = await listRounds(sessionId, true)   // full=1 → per-agent results
    const restored = (rRes.data.rounds || []).map(r => ({
      round: r.round,
      pitch: r.pitch,
      ...(r.result || {}),       // total_interviewed, successful, results, impact_dashboard…
    }))
    rounds.value = restored
    activeRound.value = Math.max(0, restored.length - 1)

    // Rebuild follow-up threads from each agent's persisted chat memory.
    Object.keys(followups).forEach(k => delete followups[k])
    for (const a of detail.data.agents || []) {
      const thread = (a.chat_state?.interview_memory || [])
        .filter(m => m.source !== 'pitch_round')
        .map(m => ({ q: m.question, a: m.response }))
      if (thread.length) followups[a.id] = { loading: false, thread }
    }

    showVariant.value = false
    showPast.value = false
    localStorage.setItem(ACTIVE_KEY, sessionId)
  } catch (e) {
    error.value = 'Could not reopen panel: ' + e.message
    localStorage.removeItem(ACTIVE_KEY)   // stale/deleted session — clear pointer
  } finally {
    assembling.value = false
  }
}

const newPanel = () => {
  session.value = null
  rounds.value = []
  activeRound.value = 0
  showVariant.value = false
  Object.keys(followups).forEach(k => delete followups[k])
  localStorage.removeItem(ACTIVE_KEY)
}

const openPast = async () => {
  showPast.value = !showPast.value
  if (showPast.value) {
    try {
      const res = await listSessions()
      pastSessions.value = res.data.sessions || []
    } catch (e) {
      error.value = 'Could not load past panels: ' + e.message
    }
  }
}

const runPitch = async (text = null) => {
  if (!session.value || busy.value) return
  pitching.value = true
  error.value = ''
  try {
    const payload = { concurrency: 6 }
    if (text && text.trim()) payload.pitch = text.trim()
    const res = await pitchSession(session.value.session_id, payload)
    rounds.value = [...rounds.value, res.data]
    activeRound.value = rounds.value.length - 1
    showVariant.value = false
    variantText.value = ''
    localStorage.setItem(ACTIVE_KEY, session.value.session_id)  // pitched → keep reconnectable
  } catch (e) {
    error.value = e.message
  } finally {
    pitching.value = false
  }
}

const ask = async (agentId) => {
  const q = (followupDrafts[agentId] || '').trim()
  if (!q || isAsking(agentId)) return
  if (!followups[agentId]) followups[agentId] = { loading: false, thread: [] }
  followups[agentId].loading = true
  try {
    const res = await askAgent(session.value.session_id, agentId, q)
    followups[agentId].thread.push({ q, a: res.data.response })
    followupDrafts[agentId] = ''
  } catch (e) {
    followups[agentId].thread.push({ q, a: '(failed: ' + e.message + ')' })
  } finally {
    followups[agentId].loading = false
  }
}

onMounted(async () => {
  await loadSegments()
  // Reconnect to the last active panel after a refresh, if it still exists.
  const last = localStorage.getItem(ACTIVE_KEY)
  if (last) await restoreSession(last)
})
</script>

<style scoped>
.panel-pitch {
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  color: #1a1a1a;
}

/* Header */
.pp-header {
  position: relative;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  padding: 20px 20px 8px;
}
.pp-tag {
  display: inline-block;
  background: #1E9E5A;
  color: #fff;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 1.5px;
  padding: 4px 10px;
  margin-bottom: 12px;
}
.pp-title {
  margin: 0 0 8px;
  font-size: 1.6rem;
  font-weight: 500;
  letter-spacing: -0.5px;
  color: #1a1a1a;
}
.pp-sub {
  margin: 0;
  font-size: 0.85rem;
  color: #666;
  line-height: 1.55;
  max-width: 640px;
}
.pp-header-right { display: flex; flex-direction: column; align-items: flex-end; gap: 10px; flex-shrink: 0; }
.pp-session-bar { display: flex; gap: 8px; }
.pp-link-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 16px;
  background: #fff;
  border: 1px solid #E5E5E5;
  border-radius: 999px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  font-weight: 600;
  color: #777;
  cursor: pointer;
  transition: all 0.15s;
}
.pp-link-btn:hover:not(:disabled) { border-color: #1E9E5A; color: #1E9E5A; }
.pp-link-btn.active { background: #F0FAF4; border-color: #1E9E5A; color: #1E9E5A; }
.pp-link-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.pp-past {
  position: absolute;
  right: 20px;
  top: 64px;
  z-index: 20;
  width: min(560px, 90vw);
  max-height: 360px;
  overflow-y: auto;
  background: #fff;
  border: 1px solid #DDD;
  border-radius: 16px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.12);
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pp-past-empty { padding: 32px 16px; text-align: center; color: #999; font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; }
.pp-past-row {
  display: flex;
  flex-direction: column;
  gap: 3px;
  width: 100%;
  text-align: left;
  padding: 10px 14px;
  background: #fff;
  border: 1px solid #E5E5E5;
  border-radius: 12px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.pp-past-row:hover { border-color: #1E9E5A; }
.pp-past-row.current { background: #F0FAF4; border-color: #1E9E5A; }
.pp-past-pitch {
  font-size: 0.85rem;
  color: #222;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pp-past-meta { font-family: 'JetBrains Mono', monospace; font-size: 0.66rem; color: #999; }

.pp-resumed-banner {
  margin: 0 20px;
  padding: 6px 12px;
  background: #F0FAF4;
  border: 1px solid rgba(30, 158, 90, 0.3);
  border-radius: 8px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.68rem;
  color: #1E9E5A;
}

.pp-mode-switch { display: flex; gap: 4px; flex-shrink: 0; }
.pp-mode-btn {
  padding: 5px 14px;
  border: 1px solid #E5E5E5;
  background: #fff;
  border-radius: 999px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  font-weight: 600;
  color: #777;
  cursor: pointer;
  transition: all 0.15s;
}
.pp-mode-btn:hover:not(:disabled) { border-color: #1E9E5A; color: #1E9E5A; }
.pp-mode-btn.active { background: #1E9E5A; border-color: #1E9E5A; color: #fff; }
.pp-mode-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* Sections */
.pp-section { padding: 20px; }
.pp-section-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 15px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #666;
}
.pp-textarea {
  width: 100%;
  border: 1px solid #DDD;
  border-radius: 16px;
  background: #fff;
  padding: 16px 20px;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  font-size: 0.95rem;
  line-height: 1.6;
  color: #1a1a1a;
  resize: vertical;
  outline: none;
  box-sizing: border-box;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.pp-textarea:focus {
  border-color: #1E9E5A;
  box-shadow: 0 2px 12px rgba(30, 158, 90, 0.12);
}
.pp-textarea::placeholder { color: #9a9a9a; }

/* Segment chips */
.pp-segments {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 10px;
}
.pp-segment {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border: 1px solid #E5E5E5;
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s, background 0.15s;
}
.pp-segment:hover { border-color: #1E9E5A; }
.pp-segment.selected { border-color: #1E9E5A; background: #F0FAF4; }
.pp-segment:disabled { opacity: 0.6; cursor: not-allowed; }
.pp-segment-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.pp-segment-label { font-weight: 600; font-size: 0.88rem; color: #000; }
.pp-segment-count {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  font-weight: 700;
  color: #1E9E5A;
  background: rgba(30, 158, 90, 0.1);
  padding: 1px 7px;
  border-radius: 8px;
}
.pp-segment-desc { font-size: 0.73rem; color: #777; line-height: 1.4; }

/* Controls row */
.pp-controls {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 16px;
  flex-wrap: wrap;
}
.pp-control-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  color: #999;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}
.pp-size-btns { display: flex; gap: 4px; }
.pp-size-btn {
  padding: 5px 14px;
  border: 1px solid #E5E5E5;
  background: #fff;
  border-radius: 999px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  font-weight: 600;
  color: #777;
  cursor: pointer;
  transition: all 0.15s;
}
.pp-size-btn:hover:not(:disabled) { border-color: #1E9E5A; color: #1E9E5A; }
.pp-size-btn.active { background: #1E9E5A; border-color: #1E9E5A; color: #fff; }
.pp-size-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.pp-assemble-btn {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
  background: #1E9E5A;
  color: #fff;
  border: none;
  border-radius: 999px;
  padding: 11px 24px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  font-size: 0.85rem;
  letter-spacing: 0.5px;
  cursor: pointer;
  transition: background 0.15s;
}
.pp-assemble-btn:hover:not(:disabled) { background: #178048; }
.pp-assemble-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.pp-error {
  margin-top: 12px;
  padding: 10px 12px;
  background: #FEE;
  border: 1px solid #FCC;
  border-radius: 8px;
  color: #C00;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
}

/* Roster */
.pp-roster { display: flex; flex-wrap: wrap; gap: 6px; }
.pp-roster-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  background: #F0FAF4;
  border: 1px solid #1E9E5A;
  border-radius: 999px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
}
.pp-roster-name { font-weight: 700; color: #1E9E5A; }
.pp-roster-meta { color: #777; font-size: 0.68rem; }
.pp-tier {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  padding: 1px 6px;
  border-radius: 2px;
}
.tier-tight { background: #FDEDEB; color: #C0392B; border: 1px solid #E6B0AA; }
.tier-moderate { background: #F4F4F4; color: #666; border: 1px solid #DDD; }
.tier-loose { background: rgba(30, 158, 90, 0.1); color: #1E9E5A; border: 1px solid rgba(30, 158, 90, 0.4); }

.pp-room-actions {
  display: flex;
  gap: 10px;
  margin-top: 16px;
}
.pp-reroll-btn {
  padding: 11px 18px;
  background: #fff;
  border: 1px solid #E5E5E5;
  border-radius: 999px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem;
  font-weight: 600;
  color: #777;
  cursor: pointer;
  transition: all 0.15s;
}
.pp-reroll-btn:hover:not(:disabled) { border-color: #1E9E5A; color: #1E9E5A; }
.pp-reroll-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.pp-pitch-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: #1E9E5A;
  color: #fff;
  border: none;
  border-radius: 999px;
  padding: 11px 24px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  font-size: 0.85rem;
  letter-spacing: 0.5px;
  cursor: pointer;
  transition: background 0.15s;
}
.pp-pitch-btn:hover:not(:disabled) { background: #178048; }
.pp-pitch-btn:disabled { opacity: 0.6; cursor: not-allowed; }

/* Rounds */
.pp-round-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid #E5E5E5;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.pp-round-tab {
  padding: 8px 18px;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  font-weight: 600;
  color: #999;
  cursor: pointer;
  margin-bottom: -1px;
}
.pp-round-tab:hover { color: #000; }
.pp-round-tab.active { color: #000; border-bottom-color: #1E9E5A; }
.pp-round-tab.variant { color: #1E9E5A; }
.pp-variant { display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px; }

.pp-pitched {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #555;
  background: #FAFAFA;
  border: 1px solid #EEE;
  border-radius: 12px;
  padding: 10px 14px;
  margin-bottom: 16px;
  line-height: 1.5;
}
.pp-pitched-label { color: #1E9E5A; font-weight: 700; margin-right: 6px; }

/* Dashboard strip */
.pp-dash {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
  border: 1px solid #E5E5E5;
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 16px;
}
.pp-dash-card {
  flex: 1;
  min-width: 140px;
  padding: 14px 16px;
  border-right: 1px solid #E5E5E5;
}
.pp-dash-card:last-child { border-right: none; }
.pp-dash-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.95rem;
  font-weight: 700;
  color: #000;
  line-height: 1.4;
}
.pp-dash-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.62rem;
  color: #999;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  margin-top: 4px;
}

/* Reaction map — avatars clustered into stance columns */
.pp-clusters { display: flex; gap: 0; flex-wrap: wrap; }
.pp-cluster {
  flex: 1; min-width: 200px;
  padding: 0 18px;
  border-right: 1px dashed #E5E5E5;
}
.pp-cluster:last-child { border-right: none; }
.pp-cluster:first-child { padding-left: 0; }
.pp-cluster-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 14px; }
.pp-cluster-name { font-size: 0.92rem; font-weight: 700; color: #111; }
.pp-cluster-count {
  font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; font-weight: 700;
  color: #1E9E5A; background: rgba(30, 158, 90, 0.1);
  padding: 1px 8px; border-radius: 999px;
}
.pp-cluster-avatars { display: flex; flex-wrap: wrap; gap: 8px; }
.pp-av-btn { padding: 0; border: none; background: none; cursor: pointer; border-radius: 50%; line-height: 0; transition: transform 0.12s; }
.pp-av-btn:hover, .pp-av-btn.active { transform: translateY(-3px); }
.pp-av-btn img {
  width: 46px; height: 46px; border-radius: 50%;
  border: 2px solid #E5E7EB; background: #fff; transition: border-color 0.12s, box-shadow 0.12s;
}
.pp-av-btn:hover img, .pp-av-btn.active img { border-color: #1E9E5A; box-shadow: 0 0 0 3px rgba(30, 158, 90, 0.1); }
.pp-av-btn.failed img { opacity: 0.45; }

/* Persona popover */
.pp-pop-backdrop { position: fixed; inset: 0; z-index: 60; background: transparent; }
.pp-pop {
  position: fixed; z-index: 61; width: 380px; max-width: 92vw;
  background: #fff; border: 1px solid #E0E0E0; border-radius: 16px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18); padding: 18px;
}
.pp-pop-head { display: flex; gap: 12px; align-items: center; margin-bottom: 10px; }
.pp-pop-head img { width: 46px; height: 46px; border-radius: 50%; border: 2px solid #1E9E5A; flex-shrink: 0; }
.pp-pop-id { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.pp-pop-name { font-weight: 700; font-size: 0.92rem; color: #111; }
.pp-pop-role { font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #999; }
.pp-pop-close { background: none; border: none; font-size: 1.4rem; line-height: 1; color: #aaa; cursor: pointer; padding: 0 2px; }
.pp-pop-close:hover { color: #333; }
.pp-pop-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.pp-pop-text { margin: 0 0 12px; font-size: 0.86rem; line-height: 1.6; color: #333; max-height: 260px; overflow-y: auto; }
.pp-feed-shift {
  font-family: 'JetBrains Mono', monospace; font-size: 0.62rem; font-weight: 700;
  color: #1E9E5A; background: rgba(30, 158, 90, 0.1);
  border: 1px solid rgba(30, 158, 90, 0.3); padding: 1px 7px; border-radius: 999px;
}

/* Follow-up */
.pp-thread {
  border-top: 1px dashed #E5E5E5;
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pp-thread-q {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  color: #1E9E5A;
  font-weight: 600;
}
.pp-thread-a { font-size: 0.8rem; color: #444; line-height: 1.5; }
.pp-followup { display: flex; gap: 6px; margin-top: auto; }
.pp-followup-input {
  flex: 1;
  border: 1px solid #DDD;
  border-radius: 999px;
  padding: 7px 14px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  outline: none;
  background: #fff;
  transition: border-color 0.15s;
}
.pp-followup-input:focus { border-color: #1E9E5A; }
.pp-followup-btn {
  padding: 7px 16px;
  background: #fff;
  border: 1px solid #1E9E5A;
  border-radius: 999px;
  color: #1E9E5A;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s;
}
.pp-followup-btn:hover:not(:disabled) { background: #1E9E5A; color: #fff; }
.pp-followup-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
