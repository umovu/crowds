<template>
  <div class="main-view">
    <!-- Header -->
    <header class="app-header">
      <div class="header-left">
        <div class="brand" @click="router.push('/')">
          <span class="brand-mark">f</span>
          <span class="brand-word"><span class="brand-strong">fub</span>sandbox</span>
        </div>
      </div>
      
      <div class="header-center">
        <div class="view-switcher">
          <button 
            v-for="mode in ['graph', 'split', 'workbench']" 
            :key="mode"
            class="switch-btn"
            :class="{ active: viewMode === mode }"
            @click="viewMode = mode"
          >
            {{ { graph: 'Graph', split: 'Split', workbench: 'Workbench' }[mode] }}
          </button>
        </div>
      </div>

      <div class="header-right">
        <div class="workflow-step">
          <span class="step-num">{{ stepLabel }}</span>
          <span class="step-name">{{ stepSubLabel }}</span>
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
      <!-- Left Panel: Graph -->
      <div class="panel-wrapper left" :style="leftPanelStyle">
        <GraphPanel 
          :graphData="graphData"
          :loading="graphLoading"
          :currentPhase="currentPhase"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
        />
      </div>

      <!-- Right Panel: Step Components -->
      <div class="panel-wrapper right" :style="rightPanelStyle">
        <!-- Sim2: narrated pipeline box replaces the step 1–2 build wizard
             (flag-gated via ?sim2=1; existing step UI untouched when off) -->
        <PipelineBox
          v-if="useSim2 && currentStep <= 2"
          :progress="sim2Progress"
          :message="sim2Message"
          :query="sim2Query"
          :errored="!!error"
          :error-message="error"
          @view-reactions="onSim2ViewReactions"
          @retry="initProject"
        />

        <!-- Step 1: Graph Build -->
        <div v-if="!useSim2 && currentStep === 1" class="step-content">
          <div class="step-header">
            <h2>Graph Build</h2>
            <p class="step-description">Building knowledge graph from your documents...</p>
          </div>
          <div class="step-status">
            <div class="phase-indicator" :class="['phase', currentPhase >= 0 ? 'active' : '']">
              <span class="phase-label">Ontology</span>
              <span class="phase-status" :class="{ completed: currentPhase > 0, active: currentPhase === 0 }">{{ currentPhase > 0 ? '✓' : '●' }}</span>
            </div>
            <div class="phase-indicator" :class="['phase', currentPhase >= 1 ? 'active' : '']">
              <span class="phase-label">Graph Build</span>
              <span class="phase-status" :class="{ completed: currentPhase > 1, active: currentPhase === 1 }">{{ currentPhase > 1 ? '✓' : '●' }}</span>
            </div>
            <div class="phase-indicator" :class="['phase', currentPhase >= 2 ? 'active' : '']">
              <span class="phase-label">Complete</span>
              <span class="phase-status" :class="{ completed: currentPhase >= 2, active: currentPhase === 2 }">{{ currentPhase >= 2 ? '✓' : '○' }}</span>
            </div>
          </div>
          <div v-if="currentPhase === 1" class="build-progress">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: (buildProgress?.progress || 0) + '%' }"></div>
            </div>
            <p class="progress-message">{{ buildProgress?.message || 'Building graph...' }}</p>
          </div>
          <div v-else-if="currentPhase === 0" class="build-progress">
            <div class="progress-bar indeterminate"></div>
            <p class="progress-message">{{ ontologyProgress?.message || 'Generating ontology...' }}</p>
          </div>
          <div v-else-if="currentPhase >= 2" class="step-complete">
            <p>Graph ready — personas grounded in your documents</p>
            <button class="action-btn primary" @click="handleNextStep">
              Continue → Create Simulation
            </button>
          </div>
        </div>

        <!-- Step 2: Create Simulation -->
        <div v-else-if="!useSim2 && currentStep === 2" class="step-content">
          <div class="step-header">
            <h2>Create Simulation</h2>
            <p class="step-description">Initialize simulation environment with generated personas</p>
          </div>
          <div v-if="loading" class="creating-simulation">
            <div class="spinner"></div>
            <p>Creating simulation...</p>
          </div>
          <div v-else-if="error" class="error-message">{{ error }}</div>
          <div v-else class="simulation-ready">
            <p>Graph complete. Ready to initialize simulation with {{ projectData?.graph_id ? 'generated personas' : 'custom agents' }}.</p>
            <button class="action-btn primary" @click="createSimulation" :disabled="loading">
              Create Simulation
            </button>
          </div>
        </div>

        <!-- Step 3+: Handled by SimulationView / SimulationRunView -->
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GraphPanel from '../components/GraphPanel.vue'
import PipelineBox from '../components/sim2/PipelineBox.vue'
import { generateOntology, getProject, buildGraph, getTaskStatus, getGraphData } from '../api/graph'
import { createSimulation as apiCreateSimulation } from '../api/simulation'
import { getPendingUpload, clearPendingUpload } from '../store/pendingUpload'

// Flag-gated new pipeline UI. Off by default — the existing step UI is untouched.
// Toggle by adding ?sim2=1 to the URL while we iterate on the new flow.
const useSim2 = ref(false)

const route = useRoute()
const router = useRouter()

// Layout State
const viewMode = ref('split') // graph | split | workbench

// Step State
const currentStep = ref(1) // 1: Graph Build, 2: Create Simulation, 3: Simulation, 4: Report, 5: Interaction
const stepNames = ['Graph Build', 'Create Simulation', 'Simulation', 'Report', 'Interaction']

// Data State
const currentProjectId = ref(route.params.projectId)
const loading = ref(false)
const graphLoading = ref(false)
const error = ref('')
const projectData = ref(null)
const graphData = ref(null)
const currentPhase = ref(-1) // -1: Upload, 0: Ontology, 1: Build, 2: Complete
const ontologyProgress = ref(null)
const buildProgress = ref(null)
const systemLogs = ref([])
const customAgents = ref([])
const customAgentsEnabled = ref(false)
const customAgentsOnly = ref(false)
const mode = ref('policy')
const simulationId = ref(null)

// Polling timers
let pollTimer = null
let graphPollTimer = null

// --- Sim2 pipeline-box progress mapping ---
// Map the real build signals (currentPhase -1→2 + buildProgress.progress) onto
// the box's single 0–100 scale. Windows mirror the box's phase narration:
//   ontology/search 0–15, graph build 15–66 (driven by buildProgress), ready 100.
const sim2Progress = computed(() => {
  const phase = currentPhase.value
  if (phase >= 2) return 100
  if (phase === 1) {
    const gp = buildProgress.value?.progress || 0
    return 15 + Math.min(100, gp) * 0.75 // 15 → 90 across the build
  }
  if (phase === 0) return 8                // ontology generating
  return 2                                  // uploading / starting
})
const sim2Message = computed(() => {
  if (currentPhase.value === 1) return buildProgress.value?.message || ''
  if (currentPhase.value === 0) return ontologyProgress.value?.message || ''
  return ''
})
const sim2Query = computed(() =>
  getPendingUpload?.()?.simulationRequirement || projectData.value?.requirement || ''
)
const onSim2ViewReactions = () => handleNextStep()

// --- Computed Layout Styles ---
const leftPanelStyle = computed(() => {
  if (viewMode.value === 'graph') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'workbench') return { width: '0%', opacity: 0, transform: 'translateX(-20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

const rightPanelStyle = computed(() => {
  if (viewMode.value === 'workbench') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'graph') return { width: '0%', opacity: 0, transform: 'translateX(20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

// --- Status Computed ---
const statusClass = computed(() => {
  if (error.value) return 'error'
  if (currentPhase.value >= 2) return 'completed'
  return 'processing'
})

const statusText = computed(() => {
  if (error.value) return 'Error'
  if (currentPhase.value >= 2) return 'Ready'
  if (currentPhase.value === 1) return 'Building Graph'
  if (currentPhase.value === 0) return 'Generating Ontology'
  return 'Initializing'
})

// Step labels
const stepLabel = computed(() => {
  return `Step ${currentStep.value}/5`
})
const stepSubLabel = computed(() => {
  if (currentStep.value === 1) {
    if (currentPhase.value === 0) return 'Generating ontology...'
    if (currentPhase.value === 1) return 'Building graph...'
    if (currentPhase.value >= 2) return 'Graph complete'
    return 'Initializing...'
  }
  if (currentStep.value === 2) {
    if (loading.value) return 'Creating simulation...'
    return 'Ready to create simulation'
  }
  return stepNames[currentStep.value - 1]
})

// --- Helpers ---
const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' + new Date().getMilliseconds().toString().padStart(3, '0')
  systemLogs.value.push({ time, msg })
  // Keep last 100 logs
  if (systemLogs.value.length > 100) {
    systemLogs.value.shift()
  }
}

// --- Layout Methods ---
const toggleMaximize = (target) => {
  if (viewMode.value === target) {
    viewMode.value = 'split'
  } else {
    viewMode.value = target
  }
}

const createSimulation = async () => {
  if (!projectData.value?.graph_id) {
    error.value = 'Graph not ready'
    return
  }
  loading.value = true
  error.value = null
  try {
    const res = await apiCreateSimulation({
      project_id: projectData.value.project_id,
      graph_id: projectData.value.graph_id
    })
    if (res.success && res.data?.simulation_id) {
      simulationId.value = res.data.simulation_id
      addLog(`Simulation created: ${res.data.simulation_id}`)
      router.push({ name: 'Simulation', params: { simulationId: res.data.simulation_id } })
    } else {
      error.value = res.error || 'Failed to create simulation'
    }
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

const handleNextStep = async (params = {}) => {
  if (currentStep.value === 1) {
    // Step 1 (Graph) → Step 2 (Create Simulation)
    if (currentPhase.value >= 2) {
      currentStep.value = 2
      addLog('Graph complete — ready to create simulation')
    }
    return
  }
  if (currentStep.value === 2) {
    // Step 2 (Create Simulation) → Step 3 (Simulation)
    if (!simulationId.value) {
      await createSimulation()
    } else {
      router.push({ name: 'Simulation', params: { simulationId: simulationId.value } })
    }
    return
  }
  if (currentStep.value < 5) {
    currentStep.value++
    addLog(`Entering Step ${currentStep.value}: ${stepNames[currentStep.value - 1]}`)
  }
}

const handleGoBack = () => {
  if (currentStep.value > 1) {
    currentStep.value--
    addLog(`Back to Step ${currentStep.value}: ${stepNames[currentStep.value - 1]}`)
  }
}

// When graph completes, notify user but don't auto-advance (user clicks "Create Simulation")
watch(currentPhase, (phase) => {
  if (phase === 2 && currentStep.value === 1) {
    addLog('Graph ready — ready to create simulation')
  }
})

// --- Data Logic ---

const initProject = async () => {
  addLog('Project view initialized.')
  if (currentProjectId.value === 'new') {
    await handleNewProject()
  } else {
    await loadProject()
  }
}

const handleNewProject = async () => {
  const pending = getPendingUpload()
  customAgents.value = pending.customAgents || []
  customAgentsEnabled.value = pending.customAgentsEnabled || false
  customAgentsOnly.value = pending.customAgentsOnly || false
  mode.value = pending.mode || 'policy'

  const seedText = (pending.simulationRequirement || '').trim()
  const hasFiles = pending.files && pending.files.length > 0
  const hasCustomAgents = customAgentsEnabled.value && customAgents.value.length > 0
  // Web-research-synthesized seed material is a valid standalone input
  const hasSubstantialSeed = seedText.length >= 100

  if (!pending.isPending || (!hasFiles && !hasCustomAgents && !hasSubstantialSeed)) {
    error.value = 'No simulation input found. Provide a seed message, upload a document, or add custom agents.'
    addLog('Error: No pending files, custom agents, or seed material found.')
    return
  }

  if (!hasFiles && hasCustomAgents) {
    addLog('Custom agents mode: no documents uploaded. Skipping graph build...')
  }
  if (!hasFiles && !hasCustomAgents && hasSubstantialSeed) {
    addLog(`Seed-only mode: using simulation_requirement (${seedText.length} chars) as source document`)
  }

  try {
    loading.value = true
    currentPhase.value = 0
    ontologyProgress.value = { message: 'Uploading and analyzing docs...' }
    addLog('Starting ontology generation: Uploading files...')

    const formData = new FormData()
    pending.files.forEach(f => formData.append('files', f))
    formData.append('simulation_requirement', pending.simulationRequirement)
    if (hasCustomAgents) {
      formData.append('custom_agents', JSON.stringify(customAgents.value))
    }

    const res = await generateOntology(formData)
    if (res.success) {
      clearPendingUpload()
      currentProjectId.value = res.data.project_id
      projectData.value = res.data

      // Merge custom agents extracted from seed document with any UI-defined ones
      if (res.data.custom_agents && res.data.custom_agents.length > 0) {
        const existingNames = new Set(customAgents.value.map(a => a.name?.toLowerCase()))
        const newAgents = res.data.custom_agents.filter(a => a.name && !existingNames.has(a.name.toLowerCase()))
        if (newAgents.length > 0) {
          customAgents.value = [...customAgents.value, ...newAgents]
          customAgentsEnabled.value = true
          addLog(`Document '# Agents' section: merged ${newAgents.length} new agents (${res.data.custom_agents.length} total in doc)`)
        } else {
          addLog(`Document '# Agents' section: all ${res.data.custom_agents.length} agents already defined`)
        }
      }

      router.replace({ name: 'Process', params: { projectId: res.data.project_id } })
      ontologyProgress.value = null
      addLog(`Ontology generated successfully for project ${res.data.project_id}`)
      await startBuildGraph()
    } else {
      error.value = res.error || 'Ontology generation failed'
      addLog(`Error generating ontology: ${error.value}`)
    }
  } catch (err) {
    error.value = err.message
    addLog(`Exception in handleNewProject: ${err.message}`)
  } finally {
    loading.value = false
  }
}

const loadProject = async () => {
  try {
    loading.value = true
    addLog(`Loading project ${currentProjectId.value}...`)
    const res = await getProject(currentProjectId.value)
    if (res.success) {
      projectData.value = res.data
      updatePhaseByStatus(res.data.status)
      addLog(`Project loaded. Status: ${res.data.status}`)

      // Load custom agents if persisted with project
      if (res.data.custom_agents && res.data.custom_agents.length > 0) {
        customAgents.value = res.data.custom_agents
        customAgentsEnabled.value = true
        addLog(`Loaded ${res.data.custom_agents.length} custom agents from project`)
      }

      if (res.data.status === 'ontology_generated' && !res.data.graph_id) {
        await startBuildGraph()
      } else if (res.data.status === 'graph_building' && res.data.graph_build_task_id) {
        currentPhase.value = 1
        startPollingTask(res.data.graph_build_task_id)
        startGraphPolling()
      } else if (res.data.status === 'graph_completed' && res.data.graph_id) {
        currentPhase.value = 2
        await loadGraph(res.data.graph_id)
      }
    } else {
      error.value = res.error
      addLog(`Error loading project: ${res.error}`)
    }
  } catch (err) {
    error.value = err.message
    addLog(`Exception in loadProject: ${err.message}`)
  } finally {
    loading.value = false
  }
}

const updatePhaseByStatus = (status) => {
  switch (status) {
    case 'created':
    case 'ontology_generated': currentPhase.value = 0; break;
    case 'graph_building': currentPhase.value = 1; break;
    case 'graph_completed': currentPhase.value = 2; break;
    case 'failed': error.value = 'Project failed'; break;
  }
}

const startBuildGraph = async () => {
  try {
    currentPhase.value = 1
    buildProgress.value = { progress: 0, message: 'Starting build...' }
    addLog('Initiating graph build...')
    
    const res = await buildGraph({ project_id: currentProjectId.value })
    if (res.success) {
      addLog(`Graph build task started. Task ID: ${res.data.task_id}`)
      startGraphPolling()
      startPollingTask(res.data.task_id)
    } else {
      error.value = res.error
      addLog(`Error starting build: ${res.error}`)
    }
  } catch (err) {
    error.value = err.message
    addLog(`Exception in startBuildGraph: ${err.message}`)
  }
}

const startGraphPolling = () => {
  addLog('Started polling for graph data...')
  fetchGraphData()
  graphPollTimer = setInterval(fetchGraphData, 10000)
}

const fetchGraphData = async () => {
  try {
    // Refresh project info to check for graph_id
    const projRes = await getProject(currentProjectId.value)
    if (projRes.success && projRes.data.graph_id) {
      const gRes = await getGraphData(projRes.data.graph_id)
      if (gRes.success) {
        graphData.value = gRes.data
        const nodeCount = gRes.data.node_count || gRes.data.nodes?.length || 0
        const edgeCount = gRes.data.edge_count || gRes.data.edges?.length || 0
        addLog(`Graph data refreshed. Nodes: ${nodeCount}, Edges: ${edgeCount}`)
      }
    }
  } catch (err) {
    console.warn('Graph fetch error:', err)
  }
}

const startPollingTask = (taskId) => {
  pollTaskStatus(taskId)
  pollTimer = setInterval(() => pollTaskStatus(taskId), 2000)
}

const pollTaskStatus = async (taskId) => {
  try {
    const res = await getTaskStatus(taskId)
    if (res.success) {
      const task = res.data
      
      // Log progress message if it changed
      if (task.message && task.message !== buildProgress.value?.message) {
        addLog(task.message)
      }
      
      buildProgress.value = { progress: task.progress || 0, message: task.message }
      
      if (task.status === 'completed') {
        addLog('Graph build task completed.')
        stopPolling()
        stopGraphPolling() // Stop polling, do final load
        currentPhase.value = 2
        
        // Final load
        const projRes = await getProject(currentProjectId.value)
        if (projRes.success && projRes.data.graph_id) {
            projectData.value = projRes.data
            await loadGraph(projRes.data.graph_id)
        }
      } else if (task.status === 'failed') {
        stopPolling()
        error.value = task.error
        addLog(`Graph build task failed: ${task.error}`)
      }
    }
  } catch (e) {
    console.error(e)
  }
}

const loadGraph = async (graphId) => {
  graphLoading.value = true
  addLog(`Loading full graph data: ${graphId}`)
  try {
    const res = await getGraphData(graphId)
    if (res.success) {
      graphData.value = res.data
      addLog('Graph data loaded successfully.')
    } else {
      addLog(`Failed to load graph data: ${res.error}`)
    }
  } catch (e) {
    addLog(`Exception loading graph: ${e.message}`)
  } finally {
    graphLoading.value = false
  }
}

const refreshGraph = () => {
  if (projectData.value?.graph_id) {
    addLog('Manual graph refresh triggered.')
    loadGraph(projectData.value.graph_id)
  }
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const stopGraphPolling = () => {
  if (graphPollTimer) {
    clearInterval(graphPollTimer)
    graphPollTimer = null
    addLog('Graph polling stopped.')
  }
}

onMounted(() => {
  // Opt into the new pipeline UI with ?sim2=1 (off by default).
  useSim2.value = route.query.sim2 === '1' || route.query.sim2 === 'true'
  initProject()
})

onUnmounted(() => {
  stopPolling()
  stopGraphPolling()
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
  display: flex;
  align-items: center;
  gap: 9px;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 18px;
  cursor: pointer;
  user-select: none;
}
.brand:hover .brand-mark {
  box-shadow: 0 3px 10px rgba(30, 158, 90, 0.35);
  transform: translateY(-1px);
}
.brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 7px;
  background: linear-gradient(160deg, #25b368 0%, #1E9E5A 60%, #178048 100%);
  color: #fff;
  font-size: 17px;
  line-height: 1;
  flex-shrink: 0;
  box-shadow: 0 2px 6px rgba(30, 158, 90, 0.28);
  transition: box-shadow 0.18s ease, transform 0.18s ease;
}
.brand-word { line-height: 1; letter-spacing: -0.3px; color: #6b6b6b; font-weight: 700; }
.brand-strong { color: #1E9E5A; }

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

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #666;
  font-weight: 500;
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

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #CCC;
}

.status-indicator.processing .dot { background: #FF5722; animation: pulse 1s infinite; }
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

.panel-wrapper {
  height: 100%;
  overflow: hidden;
  transition: width 0.4s cubic-bezier(0.25, 0.8, 0.25, 1), opacity 0.3s ease, transform 0.3s ease;
  will-change: width, opacity, transform;
}

.panel-wrapper.left {
  border-right: 1px solid #EAEAEA;
}

/* Step Content (new flow) */
.step-content {
  padding: 32px 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  overflow-y: auto;
  height: 100%;
}

.step-header h2 {
  margin: 0 0 8px 0;
  font-size: 24px;
  font-weight: 700;
  color: #1F2937;
}

.step-description {
  margin: 0;
  font-size: 14px;
  color: #6B7280;
}

.step-status {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: #F9FAFB;
  border-radius: 8px;
  border: 1px solid #E5E7EB;
}

.phase-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.phase-label {
  font-size: 13px;
  font-weight: 500;
  color: #6B7280;
}

.phase-indicator.active .phase-label {
  color: #1F2937;
  font-weight: 600;
}

.phase-status {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  background: #E5E7EB;
  color: #9CA3AF;
}

.phase-status.active {
  background: #FF5722;
  color: #FFF;
  animation: pulse 1s infinite;
}

.phase-status.completed {
  background: #1E9E5A;
  color: #FFF;
}

.build-progress {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: #E5E7EB;
  border-radius: 4px;
  overflow: hidden;
}

.progress-bar.indeterminate {
  background: linear-gradient(90deg, #E5E7EB 25%, #1E9E5A 50%, #E5E7EB 75%);
  background-size: 200% 100%;
  animation: indeterminate 1.5s linear infinite;
}

.progress-fill {
  height: 100%;
  background: #1E9E5A;
  transition: width 0.3s ease;
}

@keyframes indeterminate {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.progress-message {
  margin: 0;
  font-size: 13px;
  color: #6B7280;
}

.step-complete {
  padding: 16px;
  background: #F0F9F4;
  border: 1px solid #C8E6D2;
  border-radius: 8px;
  color: #1E9E5A;
  font-weight: 500;
}

.simulation-ready {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  background: #F9FAFB;
  border-radius: 8px;
  border: 1px solid #E5E7EB;
}

.simulation-ready p {
  margin: 0;
  color: #1F2937;
}

.creating-simulation {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #E5E7EB;
  border-top-color: #1E9E5A;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.action-btn {
  padding: 12px 24px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  align-self: flex-start;
  transition: background 0.2s;
}

.action-btn.primary {
  background: #1E9E5A;
  color: #FFF;
}

.action-btn.primary:hover:not(:disabled) {
  background: #178F4D;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-message {
  background: #FEE2E2;
  color: #991B1B;
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 13px;
}
</style>
