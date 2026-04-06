<template>
  <div class="main-view">
    <!-- Header -->
    <header class="app-header">
      <div class="header-left">
        <div class="brand" @click="router.push('/')">MIROFISH OFFLINE</div>
      </div>
      
      <div class="header-center">
      </div>

      <div class="header-right">
        <div class="workflow-step">
          <span class="step-name">Results</span>
        </div>
        <div class="step-divider"></div>
        <span class="status-indicator" :class="statusClass">
          <span class="dot"></span>
          {{ statusText }}
        </span>
      </div>
    </header>

    <!-- Main Content Area -->
    <main class="content-area">
      <!-- Step4 Report fills the full area -->
      <div class="report-area">
        <Step4Report
          :reportId="currentReportId"
          :simulationId="simulationId"
          :systemLogs="systemLogs"
          @add-log="addLog"
          @update-status="updateStatus"
        />
      </div>

      <!-- Chat/Survey Side Panel (collapsible) -->
      <div class="interaction-panel-wrapper" :class="{ expanded: interactionPanelOpen }">
        <!-- Tab trigger on left edge -->
        <button class="interaction-tab" @click="interactionPanelOpen = !interactionPanelOpen">
          <span class="tab-label">{{ interactionPanelOpen ? 'Close ✕' : 'Chat / Survey ▸' }}</span>
        </button>

        <!-- Panel content -->
        <div class="interaction-panel-content" v-if="interactionPanelOpen">
          <Step5Interaction
            :reportId="currentReportId"
            :simulationId="simulationId"
            :systemLogs="systemLogs"
            :sidePanel="true"
            @add-log="addLog"
            @update-status="updateStatus"
          />
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Step4Report from '../components/Step4Report.vue'
import Step5Interaction from '../components/Step5Interaction.vue'
import { getReport } from '../api/report'

const route = useRoute()
const router = useRouter()

// Props
const props = defineProps({
  reportId: String
})

// Interaction panel state (collapsed by default)
const interactionPanelOpen = ref(false)

// Data State
const currentReportId = ref(route.params.reportId)
const simulationId = ref(null)
const systemLogs = ref([])
const currentStatus = ref('processing') // processing | completed | error

// --- Status Computed ---
const statusClass = computed(() => {
  return currentStatus.value
})

const statusText = computed(() => {
  if (currentStatus.value === 'error') return 'Error'
  if (currentStatus.value === 'completed') return 'Completed'
  return 'Generating'
})

// --- Helpers ---
const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' + new Date().getMilliseconds().toString().padStart(3, '0')
  systemLogs.value.push({ time, msg })
  if (systemLogs.value.length > 200) {
    systemLogs.value.shift()
  }
}

const updateStatus = (status) => {
  currentStatus.value = status
}

// --- Data Logic ---
const loadReportData = async () => {
  try {
    addLog(`Loading report data: ${currentReportId.value}`)

    // Get report info to retrieve simulation_id
    const reportRes = await getReport(currentReportId.value)
    if (reportRes.success && reportRes.data) {
      simulationId.value = reportRes.data.simulation_id
    } else {
      addLog(`Failed to load report: ${reportRes.error || 'Unknown error'}`)
    }
  } catch (err) {
    addLog(`Load error: ${err.message}`)
  }
}

// Watch route params
watch(() => route.params.reportId, (newId) => {
  if (newId && newId !== currentReportId.value) {
    currentReportId.value = newId
    loadReportData()
  }
}, { immediate: true })

onMounted(() => {
  addLog('ReportView initialized')
  loadReportData()
})
</script>

<style scoped>
.main-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #FFF;
  overflow: hidden;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

/* Header */
.app-header {
  height: 60px;
  border-bottom: 1px solid #EAEAEA;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #FFF;
  z-index: 100;
  position: relative;
}

.header-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}

.brand {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 18px;
  letter-spacing: 1px;
  cursor: pointer;
}

.view-switcher {
  display: flex;
  background: #F5F5F5;
  padding: 4px;
  border-radius: 6px;
  gap: 4px;
}

.switch-btn {
  border: none;
  background: transparent;
  padding: 6px 16px;
  font-size: 12px;
  font-weight: 600;
  color: #666;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.switch-btn.active {
  background: #FFF;
  color: #000;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.workflow-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  color: #999;
}

.step-name {
  font-weight: 700;
  color: #000;
}

.step-divider {
  width: 1px;
  height: 14px;
  background-color: #E0E0E0;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #666;
  font-weight: 500;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #CCC;
}

.status-indicator.processing .dot { background: #FF9800; animation: pulse 1s infinite; }
.status-indicator.completed .dot { background: #4CAF50; }
.status-indicator.error .dot { background: #F44336; }

@keyframes pulse { 50% { opacity: 0.5; } }

/* Content */
.content-area {
  flex: 1;
  display: flex;
  position: relative;
  overflow: hidden;
}

/* Report fills full width */
.report-area {
  flex: 1;
  height: 100%;
  overflow: hidden;
}

/* Collapsible interaction side panel */
.interaction-panel-wrapper {
  position: relative;
  height: 100%;
  width: 0;
  transition: width 0.35s cubic-bezier(0.25, 0.8, 0.25, 1);
  border-left: 1px solid #EAEAEA;
  overflow: visible;
}

.interaction-panel-wrapper.expanded {
  width: 400px;
}

.interaction-tab {
  position: absolute;
  left: -40px;
  top: 50%;
  transform: translateY(-50%) rotate(-90deg);
  background: #000;
  color: #FFF;
  border: none;
  padding: 6px 14px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  border-radius: 4px 4px 0 0;
  white-space: nowrap;
  z-index: 10;
  transition: background 0.2s;
}

.interaction-tab:hover {
  background: #333;
}

.tab-label {
  letter-spacing: 0.5px;
}

.interaction-panel-content {
  height: 100%;
  overflow-y: auto;
  width: 400px;
}
</style>
