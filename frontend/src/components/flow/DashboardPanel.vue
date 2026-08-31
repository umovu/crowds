<template>
  <div class="dashboard-panel">
    <div class="page-head">
      <div class="page-title">Dashboard</div>
      <div class="page-sub">{{ periodLabel }}</div>
    </div>

    <div v-if="loading" class="dash-loading">Loading…</div>
    <div v-else-if="error" class="dash-error">{{ error }}</div>

    <template v-else>
      <!-- Row 1: at-a-glance tiles -->
      <div class="tile-row">
        <div v-if="SIM_ENABLED" class="tile">
          <div class="tile-label">Sims run</div>
          <div class="tile-value">{{ sims.length }}</div>
          <div class="tile-delta">{{ simsThisMonth }} this month</div>
        </div>
        <div class="tile">
          <div class="tile-label">Panels run</div>
          <div class="tile-value">{{ panels.length }}</div>
          <div class="tile-delta">{{ panelsThisMonth }} this month</div>
        </div>
        <div class="tile">
          <div class="tile-label">{{ SIM_ENABLED ? 'Agents simulated' : 'People in rooms' }}</div>
          <div class="tile-value">{{ totalAgents }}</div>
          <div class="tile-delta flat">across {{ activity.length }} {{ unitPlural }}</div>
        </div>
        <div class="tile">
          <div class="tile-label">{{ SIM_ENABLED ? 'Rounds simulated' : 'Rounds run' }}</div>
          <div class="tile-value">{{ totalRounds.toLocaleString() }}</div>
          <div class="tile-delta flat">avg {{ avgRounds }} / {{ unitSingular }}</div>
        </div>
      </div>

      <!-- Row 2: plan + quota -->
      <div class="plan-row">
        <div class="plan-card">
          <div class="plan-left">
            <div class="plan-name">Current plan</div>
            <div class="plan-tier">Free — local mode</div>
            <div class="plan-note">No limits while running on your own LLM keys</div>
          </div>
          <button class="plan-upgrade disabled" disabled>Upgrade →</button>
        </div>
        <div class="quota-card">
          <div class="quota-head">
            <span class="quota-label">{{ SIM_ENABLED ? 'Sims' : 'Panels' }} this month</span>
            <span class="quota-count">{{ SIM_ENABLED ? simsThisMonth : panelsThisMonth }} / ∞</span>
          </div>
          <div class="quota-bar"><div class="quota-fill" :style="{ width: '20%' }"></div></div>
          <div class="quota-foot">No monthly cap · local mode</div>
        </div>
      </div>

      <!-- Row 3: charts -->
      <div class="chart-row">
        <div class="chart-card">
          <div class="chart-title">{{ unitPluralCap }} per week · last 8 weeks</div>
          <div class="chart-body">
            <div class="bar-chart">
              <div v-for="w in weeklyData" :key="w.label" class="bar-col">
                <div class="bar" :style="{ height: w.height + '%' }">
                  <span class="bar-val">{{ w.count }}</span>
                </div>
                <div class="bar-label">{{ w.label }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="chart-card">
          <div class="chart-title">Mode split</div>
          <div class="chart-body">
            <div class="donut-wrap">
              <div class="donut" :style="donutStyle">
                <div class="donut-center">
                  <div class="donut-num">{{ activity.length }}</div>
                  <div class="donut-lbl">{{ unitPlural }}</div>
                </div>
              </div>
              <div class="donut-legend">
                <div class="legend-row">
                  <span class="legend-swatch" style="background: #1E9E5A;"></span>
                  <span class="legend-text">Policy <b class="legend-val">{{ policyCount }}</b></span>
                </div>
                <div class="legend-row">
                  <span class="legend-swatch" style="background: #B8E6CC;"></span>
                  <span class="legend-text">Product <b class="legend-val">{{ productCount }}</b></span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="chart-card">
          <div class="chart-title">{{ SIM_ENABLED ? 'Agent count' : 'Room size' }}</div>
          <div class="chart-body">
            <div class="hbar-list">
              <div class="hbar-row">
                <div class="hbar-top"><span>Small · ≤20</span><b>{{ agentBuckets.small }}</b></div>
                <div class="hbar-track"><div class="hbar-fill" :style="{ width: bucketPct('small') + '%' }"></div></div>
              </div>
              <div class="hbar-row">
                <div class="hbar-top"><span>Medium · 21–40</span><b>{{ agentBuckets.medium }}</b></div>
                <div class="hbar-track"><div class="hbar-fill" :style="{ width: bucketPct('medium') + '%' }"></div></div>
              </div>
              <div class="hbar-row">
                <div class="hbar-top"><span>Large · 41+</span><b>{{ agentBuckets.large }}</b></div>
                <div class="hbar-track"><div class="hbar-fill" :style="{ width: bucketPct('large') + '%' }"></div></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Row 4: recent activity table -->
      <div class="table-card">
        <div class="table-head">
          <div class="table-title">Recent activity</div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Mode</th>
              <th class="right">{{ SIM_ENABLED ? 'Agents' : 'People' }}</th>
              <th class="right">Rounds</th>
              <th>Status</th>
              <th>Date</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in recentActivity" :key="row.id" @click="openRow(row)">
              <td class="title">{{ row.title }}</td>
              <td><span class="mode-pill" :class="row.mode">{{ row.modeLabel }}</span></td>
              <td class="num">{{ row.people }}</td>
              <td class="num">{{ row.rounds }}</td>
              <td><span class="status-dot" :class="row.statusClass">{{ row.statusLabel }}</span></td>
              <td class="num">{{ row.date }}</td>
            </tr>
            <tr v-if="!recentActivity.length">
              <td colspan="6" class="empty-row">No {{ unitPlural }} yet.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { getSimulationHistory } from '../../api/simulation'
import { listSessions } from '../../api/panel'
import { SIM_ENABLED } from '../../features'

const emit = defineEmits(['open-sim'])

const sims = ref([])
const panels = ref([])
const loading = ref(true)
const error = ref('')

const periodLabel = computed(() => {
  const d = new Date()
  const m = d.toLocaleString('en', { month: 'short' }).toUpperCase()
  return `${m} ${d.getFullYear()} · ALL-TIME`
})

const now = new Date()
const monthAgo = new Date(now.getFullYear(), now.getMonth(), 1)

const simsThisMonth = computed(() =>
  sims.value.filter(s => {
    const d = new Date(s.created_at || s.created_date || '')
    return d >= monthAgo
  }).length
)

const panelsThisMonth = computed(() =>
  panels.value.filter(p => {
    const d = new Date(p.created_at || p.timestamp || '')
    return d >= monthAgo
  }).length
)

// While the sim tier is hidden the dashboard counts panels instead, so every
// tile, chart and row reads off ONE normalised list rather than two parallel
// sets of computeds that could disagree with each other.
const _normSim = (s) => ({
  id: s.simulation_id,
  title: s.simulation_requirement || 'Untitled simulation',
  mode: (s.mode === 'product') ? 'product' : 'policy',
  modeLabel: (s.mode === 'product') ? 'Product' : 'Policy',
  people: s.profiles_count || s.entities_count || 0,
  rounds: s.total_rounds || 0,
  statusClass: simStatusClass(s),
  statusLabel: simStatusLabel(s),
  date: s.created_date || '—',
  at: s.created_at || s.created_date || '',
  raw: s,
})
const _normPanel = (p) => ({
  id: p.session_id,
  title: p.pitch || '(no pitch)',
  mode: (p.mode === 'policy') ? 'policy' : 'product',
  modeLabel: (p.mode === 'policy') ? 'Policy' : 'Product',
  people: p.cast_size || 0,
  rounds: p.rounds_run || 0,
  statusClass: '',
  statusLabel: (p.rounds_run || 0) > 0 ? 'run' : 'not run',
  date: (p.created_at || '').slice(0, 10) || '—',
  at: p.created_at || '',
  raw: p,
})

const activity = computed(() =>
  SIM_ENABLED ? sims.value.map(_normSim) : panels.value.map(_normPanel)
)

const unitSingular = computed(() => (SIM_ENABLED ? 'sim' : 'panel'))
const unitPlural = computed(() => (SIM_ENABLED ? 'sims' : 'panels'))
const unitPluralCap = computed(() => (SIM_ENABLED ? 'Sims' : 'Panels'))

const totalAgents = computed(() =>
  activity.value.reduce((sum, a) => sum + a.people, 0)
)

const totalRounds = computed(() =>
  activity.value.reduce((sum, a) => sum + a.rounds, 0)
)

const avgRounds = computed(() => {
  if (!activity.value.length) return 0
  return Math.round(totalRounds.value / activity.value.length)
})

const recentActivity = computed(() =>
  [...activity.value]
    .sort((a, b) => new Date(b.at || 0) - new Date(a.at || 0))
    .slice(0, 8)
)

function simStatusClass(sim) {
  const st = sim.runner_status || sim.status || 'idle'
  if (st === 'running') return 'running'
  if (st === 'failed' || st === 'error') return 'failed'
  return ''
}

function simStatusLabel(sim) {
  const st = sim.runner_status || sim.status || 'idle'
  if (st === 'running') return 'running'
  if (st === 'completed' || st === 'idle') return 'completed'
  return st
}

const policyCount = computed(() => activity.value.filter(a => a.mode === 'policy').length)
const productCount = computed(() => activity.value.filter(a => a.mode === 'product').length)

const donutStyle = computed(() => {
  const total = activity.value.length || 1
  const policyDeg = Math.round((policyCount.value / total) * 360)
  return {
    background: `conic-gradient(#1E9E5A 0deg ${policyDeg}deg, #B8E6CC ${policyDeg}deg 360deg)`
  }
})

const agentBuckets = computed(() => {
  const buckets = { small: 0, medium: 0, large: 0 }
  for (const a of activity.value) {
    const n = a.people
    if (n <= 20) buckets.small++
    else if (n <= 40) buckets.medium++
    else buckets.large++
  }
  return buckets
})

function bucketPct(key) {
  const max = Math.max(...Object.values(agentBuckets.value), 1)
  return Math.round((agentBuckets.value[key] / max) * 100)
}

const weeklyData = computed(() => {
  const weeks = []
  const today = new Date()
  for (let i = 7; i >= 0; i--) {
    const weekStart = new Date(today)
    weekStart.setDate(today.getDate() - i * 7 - today.getDay())
    const weekEnd = new Date(weekStart)
    weekEnd.setDate(weekStart.getDate() + 7)
    const count = activity.value.filter(a => {
      const d = new Date(a.at || '')
      return d >= weekStart && d < weekEnd
    }).length
    weeks.push({
      label: i === 0 ? 'now' : `w-${i}`,
      count,
      height: count > 0 ? Math.max(13, Math.round((count / Math.max(activity.value.length, 8)) * 100)) : 4
    })
  }
  const maxCount = Math.max(...weeks.map(w => w.count), 1)
  return weeks.map(w => ({ ...w, height: w.count > 0 ? Math.max(13, (w.count / maxCount) * 100) : 4 }))
})

function openRow(row) {
  // Only a sim has a view to open from here. Panel rows stay inert while the
  // sim tier is hidden — the sidebar is where panels are reopened.
  if (SIM_ENABLED) emit('open-sim', row.raw)
}

onMounted(async () => {
  loading.value = true
  error.value = ''
  try {
    const [histRes, panRes] = await Promise.all([
      SIM_ENABLED ? getSimulationHistory(50) : Promise.resolve({ data: [] }),
      listSessions()
    ])
    sims.value = histRes.data || []
    panels.value = panRes.data?.sessions || []
  } catch (e) {
    error.value = e.message || 'Failed to load dashboard data'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.dashboard-panel { display: flex; flex-direction: column; gap: 18px; }

.page-head {
  display: flex; align-items: baseline; justify-content: space-between;
  gap: 16px;
}
.page-title { font-size: 1.6rem; font-weight: 600; letter-spacing: -0.5px; color: #1a1a1a; }
.page-sub { font-family: 'JetBrains Mono', monospace; font-size: 0.74rem; color: #999; letter-spacing: 0.4px; }

.dash-loading, .dash-error {
  padding: 40px; text-align: center;
  font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; color: #999;
}
.dash-error { color: #C0392B; }

.tile-row {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px;
}
.tile {
  background: #fff; border: 1px solid #E8E8E8; border-radius: 14px;
  padding: 18px 20px 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  display: flex; flex-direction: column; gap: 4px;
  transition: box-shadow 0.15s, transform 0.15s;
}
.tile:hover { box-shadow: 0 4px 14px rgba(0,0,0,0.06); transform: translateY(-1px); }
.tile-label {
  font-family: 'JetBrains Mono', monospace; font-size: 0.66rem; font-weight: 700;
  letter-spacing: 0.5px; text-transform: uppercase; color: #999;
}
.tile-value { font-size: 1.85rem; font-weight: 700; line-height: 1.1; color: #1a1a1a; letter-spacing: -0.5px; }
.tile-delta { font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; color: #1E9E5A; font-weight: 600; }
.tile-delta.flat { color: #999; }

.plan-row { display: grid; grid-template-columns: 2fr 1fr; gap: 14px; }
.plan-card {
  background: linear-gradient(135deg, #F0FAF4 0%, #fff 60%);
  border: 1px solid rgba(30,158,90,0.3); border-radius: 14px;
  padding: 18px 22px;
  display: flex; align-items: center; justify-content: space-between; gap: 20px;
}
.plan-left { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.plan-name { font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.6px; text-transform: uppercase; color: #1E9E5A; }
.plan-tier { font-size: 1.25rem; font-weight: 700; color: #1a1a1a; letter-spacing: -0.3px; }
.plan-note { font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #555; }
.plan-upgrade {
  background: #1E9E5A; color: #fff; border: none; border-radius: 10px;
  padding: 11px 20px; font-family: 'JetBrains Mono', monospace;
  font-size: 0.82rem; font-weight: 700; cursor: pointer; white-space: nowrap;
}
.plan-upgrade:hover:not(:disabled) { background: #178048; }
.plan-upgrade.disabled { background: #DDD; color: #fff; cursor: not-allowed; }

.quota-card {
  background: #fff; border: 1px solid #E8E8E8; border-radius: 14px;
  padding: 16px 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  display: flex; flex-direction: column; gap: 10px;
}
.quota-head { display: flex; justify-content: space-between; align-items: baseline; }
.quota-label { font-family: 'JetBrains Mono', monospace; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; color: #999; }
.quota-count { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; font-weight: 700; color: #1a1a1a; }
.quota-bar { height: 6px; background: #EEE; border-radius: 999px; overflow: hidden; }
.quota-fill { height: 100%; background: #1E9E5A; border-radius: 999px; transition: width 0.3s; }
.quota-foot { font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; color: #bbb; }

.chart-row { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 14px; }
.chart-card {
  background: #fff; border: 1px solid #E8E8E8; border-radius: 14px;
  padding: 18px 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  display: flex; flex-direction: column; gap: 14px;
}
.chart-title { font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; color: #999; }
.chart-body { flex: 1; min-height: 160px; }

.bar-chart { display: flex; align-items: flex-end; gap: 8px; height: 160px; padding-top: 8px; }
.bar-col { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6px; height: 100%; justify-content: flex-end; }
.bar { width: 100%; max-width: 32px; background: #1E9E5A; border-radius: 6px 6px 0 0; transition: background 0.15s; position: relative; }
.bar:hover { background: #178048; }
.bar-val { position: absolute; top: -18px; left: 50%; transform: translateX(-50%); font-family: 'JetBrains Mono', monospace; font-size: 0.62rem; font-weight: 700; color: #555; opacity: 0; transition: opacity 0.15s; }
.bar-col:hover .bar-val { opacity: 1; }
.bar-label { font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; color: #bbb; }

.donut-wrap { display: flex; align-items: center; gap: 18px; height: 100%; }
.donut { width: 110px; height: 110px; border-radius: 50%; flex-shrink: 0; position: relative; }
.donut::after { content: ''; position: absolute; inset: 18px; background: #fff; border-radius: 50%; }
.donut-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; z-index: 1; }
.donut-num { font-size: 1.3rem; font-weight: 700; color: #1a1a1a; line-height: 1; }
.donut-lbl { font-family: 'JetBrains Mono', monospace; font-size: 0.58rem; color: #999; margin-top: 2px; }
.donut-legend { display: flex; flex-direction: column; gap: 8px; }
.legend-row { display: flex; align-items: center; gap: 8px; }
.legend-swatch { width: 10px; height: 10px; border-radius: 3px; flex-shrink: 0; }
.legend-text { font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #555; }
.legend-val { font-weight: 700; color: #1a1a1a; }

.hbar-list { display: flex; flex-direction: column; gap: 12px; padding-top: 4px; }
.hbar-row { display: flex; flex-direction: column; gap: 4px; }
.hbar-top { display: flex; justify-content: space-between; font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #555; }
.hbar-top b { color: #1a1a1a; font-weight: 700; }
.hbar-track { height: 6px; background: #EEE; border-radius: 999px; overflow: hidden; }
.hbar-fill { height: 100%; background: #1E9E5A; border-radius: 999px; }

.table-card { background: #fff; border: 1px solid #E8E8E8; border-radius: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); overflow: hidden; }
.table-head { padding: 16px 20px; border-bottom: 1px solid #ECECEC; display: flex; justify-content: space-between; align-items: baseline; }
.table-title { font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; color: #999; }

table { width: 100%; border-collapse: collapse; }
thead th { text-align: left; padding: 10px 20px; font-family: 'JetBrains Mono', monospace; font-size: 0.62rem; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; color: #999; background: #FAFAFA; border-bottom: 1px solid #ECECEC; }
thead th.right { text-align: right; }
tbody td { padding: 12px 20px; font-size: 0.84rem; color: #1a1a1a; border-bottom: 1px solid #F4F4F4; }
tbody tr:last-child td { border-bottom: none; }
tbody tr { cursor: pointer; transition: background 0.12s; }
tbody tr:hover { background: #F0FAF4; }
td.title { font-weight: 600; color: #1a1a1a; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
td.num { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; text-align: right; color: #555; }
.empty-row { text-align: center; color: #999; font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; padding: 24px; }

.mode-pill { display: inline-block; padding: 2px 9px; border-radius: 999px; font-family: 'JetBrains Mono', monospace; font-size: 0.62rem; font-weight: 700; letter-spacing: 0.3px; text-transform: uppercase; }
.mode-pill.policy { background: #EEF; color: #4A6FA5; }
.mode-pill.product { background: #FFF4E6; color: #B8731A; }

.status-dot { display: inline-flex; align-items: center; gap: 6px; font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; color: #555; }
.status-dot::before { content: ''; width: 7px; height: 7px; border-radius: 50%; background: #1E9E5A; }
.status-dot.running::before { background: #E67E22; animation: pulse 1.4s infinite; }
.status-dot.failed::before { background: #C0392B; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

@media (max-width: 980px) {
  .tile-row { grid-template-columns: repeat(2, 1fr); }
  .plan-row { grid-template-columns: 1fr; }
  .chart-row { grid-template-columns: 1fr; }
}

@media (max-width: 640px) {
  /* Activity table scrolls sideways inside its card instead of squashing. */
  .table-card { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  table { min-width: 560px; }
  thead th, tbody td { padding-left: 12px; padding-right: 12px; }
  td.title { max-width: 180px; }
}
</style>
