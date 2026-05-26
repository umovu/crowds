<template>
  <div class="home-container">
    <!-- Top Navigation Bar -->
    <nav class="navbar" :style="s.navbar">
      <div class="nav-brand" :style="s.navBrand">FUB POLICY SIM</div>
    </nav>

    <div class="main-content" :style="s.mainContent">
      <section class="dashboard-section" :style="s.dashboardSection">
        <!-- Left column: brief marketing / what-is-this -->
        <aside class="pitch-panel">
          <div class="pitch-tag">POLICY WIND TUNNEL</div>
          <h1 class="pitch-title">
            Test events on <span class="pitch-accent">digital agents</span><br />
            before they happen to real people.
          </h1>

          <ul class="pitch-list">
            <li>
              <span class="pitch-bullet">01</span>
              <div>
                <div class="pitch-bullet-title">Build a synthetic population</div>
                <div class="pitch-bullet-desc">Personas grounded in real socio-economic context — not generic chatbots.</div>
              </div>
            </li>
            <li>
              <span class="pitch-bullet">02</span>
              <div>
                <div class="pitch-bullet-title">Run the scenario</div>
                <div class="pitch-bullet-desc">Watch opinions form, polarize, and shift round by round.</div>
              </div>
            </li>
            <li>
              <span class="pitch-bullet">03</span>
              <div>
                <div class="pitch-bullet-title">Intervene mid-flight</div>
                <div class="pitch-bullet-desc">Pause and test a policy announcement. Compare trajectories.</div>
              </div>
            </li>
          </ul>

          <div class="pitch-foot">
            <span class="pitch-foot-dot"></span>
            Built for South African policy questions. Designed for evidence, not vibes.
          </div>
        </aside>

        <!-- Right column: the actual console -->
        <div class="right-panel" :style="{ ...s.rightPanel, flex: '1' }">
          <div class="console-box" :style="s.consoleBox">

            <!-- 01: Seed Message -->
            <div :style="s.consoleSection">
              <div class="console-header" :style="s.consoleHeader">
                <span>01 / Seed Message</span>
                <span>Required</span>
              </div>
              <div :style="s.inputWrapper">
                <textarea
                  v-model="formData.simulationRequirement"
                  :style="s.codeInput"
                  placeholder="Describe the policy, event, or scenario you want to simulate. What are you testing? Who is the audience?"
                  rows="8"
                  :disabled="loading || seedLoading"
                ></textarea>
              </div>

              <!-- Augment with web research (uses textarea content as the query) -->
              <div class="web-seed-bar">
                <button
                  class="web-seed-btn"
                  :disabled="!formData.simulationRequirement.trim() || seedLoading || loading"
                  @click="handleGenerateSeed"
                  :title="!formData.simulationRequirement.trim() ? 'Type your simulation query above first' : 'Search the web and expand your query into a full briefing'"
                >
                  <span v-if="seedLoading">🔍 Researching the web… (~30-60s)</span>
                  <span v-else>🔍 Ground my query in real-world data</span>
                </button>
                <div class="web-seed-hint-inline">
                  Optional. Searches South African news for your scenario and rewrites it as a structured briefing — gives agents real context to react to.
                </div>
                <div v-if="seedError" class="web-seed-error">{{ seedError }}</div>
                <div v-if="seedSources.length > 0" class="web-seed-sources">
                  ✓ Expanded from {{ seedSources.length }} sources:
                  <ul>
                    <li v-for="src in seedSources" :key="src.url">
                      <a :href="src.url" target="_blank">{{ src.title || src.url }}</a>
                    </li>
                  </ul>
                  <div class="web-seed-hint">Edit the text above to refine before starting the engine.</div>
                </div>
              </div>
            </div>

            <!-- 02: Reality Seeds (Document Upload) -->
            <div :style="s.consoleSection">
              <div class="console-header" :style="s.consoleHeader">
                <span>02 / Reality Seeds</span>
                <span>{{ customAgentsEnabled ? 'Optional' : 'Required' }}</span>
              </div>
              <div
                :style="s.uploadZone"
                @dragover.prevent="handleDragOver"
                @dragleave.prevent="handleDragLeave"
                @drop.prevent="handleDrop"
                @click="triggerFileInput"
              >
                <input ref="fileInput" type="file" multiple accept=".pdf,.md,.txt" @change="handleFileSelect" style="display: none" :disabled="loading" />
                <div v-if="files.length === 0" :style="s.uploadPlaceholder">
                  <div :style="s.uploadIcon">↑</div>
                  <div :style="s.uploadTitle">Drag & drop files here</div>
                  <div :style="s.uploadHint">PDF, MD, TXT — or skip if using custom agents only</div>
                </div>
                <div v-else :style="s.fileList">
                  <div v-for="(file, index) in files" :key="index" :style="s.fileItem">
                    <span>📄</span>
                    <span :style="s.fileName">{{ file.name }}</span>
                    <button @click.stop="removeFile(index)" :style="s.removeBtn">×</button>
                  </div>
                </div>
              </div>
            </div>

            <!-- 03: Custom Agents -->
            <div :style="s.consoleSection">
              <CustomAgentPanel
                v-model="customAgents"
                v-model:enabled="customAgentsEnabled"
              />
            </div>

            <!-- Advanced settings (collapsed by default) -->
            <details class="advanced-settings">
              <summary class="advanced-summary">Advanced settings</summary>
              <div class="advanced-body">
                <div class="advanced-row">
                  <span class="advanced-label">Graph engine</span>
                  <select v-model="selectedBackend" @change="switchBackend" class="advanced-select" :disabled="loading">
                    <option value="ladybug">LadybugDB — Embedded (recommended)</option>
                    <option value="neo4j">Neo4j — Server, needs Docker</option>
                    <option value="kglite">KGLite — In-memory (dev only)</option>
                  </select>
                </div>
                <div class="advanced-hint">
                  The default works for almost everyone. Only change this if you know why.
                </div>
              </div>
            </details>

            <div :style="s.btnSection">
              <button :style="s.startEngineBtn" @click="startSimulation" :disabled="!canSubmit || loading">
                <span v-if="!loading">Start Engine</span>
                <span v-else>Initializing...</span>
                <span>→</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      <HistoryDatabase />
    </div>
    <PersonaLibraryDrawer />
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import HistoryDatabase from '../components/HistoryDatabase.vue'
import CustomAgentPanel from '../components/CustomAgentPanel.vue'
import PersonaLibraryDrawer from '../components/PersonaLibraryDrawer.vue'
import { generateSeedFromWeb } from '../api/research'

const mono = 'JetBrains Mono, monospace'
const sans = 'Space Grotesk, Noto Sans SC, system-ui, sans-serif'

const s = reactive({
  navbar: { height: '60px', background: '#000', color: '#fff', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0 40px' },
  navBrand: { fontFamily: mono, fontWeight: '800', letterSpacing: '1px', fontSize: '1.2rem' },
  mainContent: { maxWidth: '1400px', margin: '0 auto', padding: '40px 40px' },
  dashboardSection: { display: 'flex', gap: '60px', alignItems: 'flex-start' },
  leftPanel: { flex: '0.8', display: 'flex', flexDirection: 'column' },
  panelHeader: { fontFamily: mono, fontSize: '0.8rem', color: '#999', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px' },
  statusDot: { color: '#1E9E5A', fontSize: '0.8rem' },
  sectionTitle: { fontSize: '2rem', fontWeight: '520', margin: '0 0 15px 0' },
  sectionDesc: { color: '#666', marginBottom: '25px', lineHeight: '1.6' },
  metricsRow: { display: 'flex', gap: '20px', marginBottom: '15px' },
  metricCard: { border: '1px solid #E5E5E5', padding: '20px 30px', minWidth: '150px' },
  metricValue: { fontFamily: mono, fontSize: '1.8rem', fontWeight: '520', marginBottom: '5px' },
  metricLabel: { fontSize: '0.85rem', color: '#999' },
  researchCta: { marginTop: '20px' },
  researchBtn: { width: '100%', display: 'flex', alignItems: 'center', gap: '15px', padding: '15px 20px', background: '#F0FAF4', border: '1px solid #1E9E5A', cursor: 'pointer', textAlign: 'left' },
  researchBtnTitle: { fontFamily: mono, fontWeight: '700', fontSize: '0.9rem', color: '#000' },
  researchBtnDesc: { fontFamily: mono, fontSize: '0.75rem', color: '#666' },
  stepsContainer: { border: '1px solid #E5E5E5', padding: '30px', position: 'relative' },
  stepsHeader: { fontFamily: mono, fontSize: '0.8rem', color: '#999', marginBottom: '25px', display: 'flex', alignItems: 'center', gap: '8px' },
  diamondIcon: { fontSize: '1.2rem', lineHeight: '1' },
  workflowList: { display: 'flex', flexDirection: 'column', gap: '20px' },
  workflowItem: { display: 'flex', alignItems: 'flex-start', gap: '20px' },
  stepNum: { fontFamily: mono, fontWeight: '700', color: '#000', opacity: '0.3' },
  stepInfo: { flex: '1' },
  stepTitle: { fontWeight: '520', fontSize: '1rem', marginBottom: '4px' },
  stepDesc: { fontSize: '0.85rem', color: '#666' },
  rightPanel: { flex: '1.2', display: 'flex', flexDirection: 'column' },
  consoleBox: { border: '1px solid #CCC', padding: '8px' },
  consoleSection: { padding: '20px' },
  consoleHeader: { display: 'flex', justifyContent: 'space-between', marginBottom: '15px', fontFamily: mono, fontSize: '0.75rem', color: '#666' },
  uploadZone: { border: '1px dashed #CCC', height: '160px', overflowY: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', background: '#FAFAFA' },
  uploadPlaceholder: { textAlign: 'center' },
  uploadIcon: { width: '40px', height: '40px', border: '1px solid #DDD', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 15px', color: '#999' },
  uploadTitle: { fontWeight: '500', fontSize: '0.9rem', marginBottom: '5px' },
  uploadHint: { fontFamily: mono, fontSize: '0.75rem', color: '#999' },
  fileList: { width: '100%', padding: '15px', display: 'flex', flexDirection: 'column', gap: '10px' },
  fileItem: { display: 'flex', alignItems: 'center', background: '#fff', padding: '8px 12px', border: '1px solid #EEE', fontFamily: mono, fontSize: '0.85rem' },
  fileName: { flex: '1', margin: '0 10px' },
  removeBtn: { background: 'none', border: 'none', cursor: 'pointer', fontSize: '1.2rem', color: '#999' },
  consoleDivider: { display: 'flex', alignItems: 'center', margin: '10px 0', borderTop: '1px solid #EEE' },
  consoleDividerText: { padding: '0 15px', fontFamily: mono, fontSize: '0.7rem', color: '#BBB', letterSpacing: '1px' },
  inputWrapper: { position: 'relative', border: '1px solid #DDD', background: '#FAFAFA' },
  codeInput: { width: '100%', border: 'none', background: 'transparent', padding: '20px', fontFamily: mono, fontSize: '0.9rem', lineHeight: '1.6', resize: 'vertical', outline: 'none', minHeight: '120px' },
  engineSelectorRow: { display: 'flex', alignItems: 'center', gap: '12px' },
  engineLabel: { fontFamily: mono, fontSize: '0.75rem', color: '#AAA' },
  engineSelect: { fontFamily: mono, fontSize: '0.8rem', padding: '6px 10px', border: '1px solid #DDD', background: '#fff', cursor: 'pointer', outline: 'none', flex: '1' },
  btnSection: { padding: '0 20px 20px' },
  startEngineBtn: { width: '100%', background: '#000', color: '#fff', border: 'none', padding: '20px', fontFamily: mono, fontWeight: '700', fontSize: '1.1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', letterSpacing: '1px' },
  researchHint: { fontSize: '0.8rem', color: '#888', marginBottom: '12px', lineHeight: '1.5', fontFamily: sans },
  archetypeList: { display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '12px' },
  archetypeTag: { fontFamily: mono, fontSize: '0.7rem', padding: '4px 10px', background: '#F0FAF4', border: '1px solid #1E9E5A', color: '#1E9E5A', borderRadius: '3px' },
  researchActionBtn: { width: '100%', padding: '12px 20px', background: '#F0FAF4', border: '1px solid #1E9E5A', color: '#1E9E5A', fontFamily: mono, fontWeight: '700', fontSize: '0.85rem', cursor: 'pointer', borderRadius: '4px' },
  researchResults: { marginTop: '15px', display: 'flex', flexDirection: 'column', gap: '8px' },
  resultItem: { display: 'flex', alignItems: 'flex-start', gap: '8px', padding: '8px 12px', background: '#FAFAFA', border: '1px solid #EEE', borderRadius: '4px', fontSize: '0.8rem' },
  resultCheck: { color: '#4CAF50', fontWeight: '700' },
  resultArchetype: { fontFamily: mono, fontWeight: '700', color: '#000', minWidth: '120px' },
  resultPreview: { color: '#666', flex: '1' },
  researchError: { marginTop: '10px', padding: '10px', background: '#FEE', border: '1px solid #FCC', color: '#C00', fontFamily: mono, fontSize: '0.75rem', borderRadius: '4px' },
  researchConsole: { marginTop: '15px', border: '1px solid #333', borderRadius: '4px', overflow: 'hidden', background: '#0D0D0D' },
  consoleTitle: { padding: '8px 12px', background: '#1A1A1A', color: '#1E9E5A', fontFamily: mono, fontSize: '0.7rem', fontWeight: '700', borderBottom: '1px solid #333', display: 'flex', alignItems: 'center', gap: '8px' },
  consoleBody: { padding: '12px', maxHeight: '280px', overflowY: 'auto', fontFamily: mono, fontSize: '0.75rem', lineHeight: '1.6' },
  logTime: { color: '#555', marginRight: '8px', fontSize: '0.65rem' },
  impactSummary: { marginTop: '20px', border: '1px solid #333', borderRadius: '4px', overflow: 'hidden', background: '#0D0D0D' },
  impactHeader: { padding: '12px 16px', background: '#1A1A1A', borderBottom: '1px solid #333', display: 'flex', alignItems: 'center', gap: '8px' },
  impactIcon: { color: '#1E9E5A', fontSize: '12px' },
  impactTitle: { fontFamily: mono, fontSize: '0.7rem', fontWeight: '700', color: '#1E9E5A', letterSpacing: '1px' },
  impactGrid: { display: 'flex', gap: '0', borderBottom: '1px solid #222' },
  impactMetric: { flex: '1', padding: '16px', textAlign: 'center', borderRight: '1px solid #222' },
  impactMetricValue: { fontFamily: mono, fontSize: '1.5rem', fontWeight: '700', color: '#1E9E5A' },
  impactMetricLabel: { fontFamily: mono, fontSize: '0.65rem', color: '#666', marginTop: '4px', letterSpacing: '0.5px' },
  impactSources: { padding: '12px 16px', borderBottom: '1px solid #222' },
  sourcesLabel: { fontFamily: mono, fontSize: '0.6rem', color: '#555', letterSpacing: '0.5px', marginBottom: '8px', textTransform: 'uppercase' },
  sourcesList: { display: 'flex', flexWrap: 'wrap', gap: '6px' },
  sourceTag: { fontFamily: mono, fontSize: '0.65rem', padding: '3px 8px', background: 'rgba(30, 158, 90, 0.1)', border: '1px solid rgba(30, 158, 90, 0.3)', color: '#1E9E5A', borderRadius: '2px' },
  impactFindings: { padding: '12px 16px' },
  findingsLabel: { fontFamily: mono, fontSize: '0.6rem', color: '#555', letterSpacing: '0.5px', marginBottom: '10px', textTransform: 'uppercase' },
  findingItem: { marginBottom: '10px', paddingBottom: '10px', borderBottom: '1px solid #1A1A1A' },
  findingArchetype: { fontFamily: mono, fontSize: '0.7rem', fontWeight: '700', color: '#1E9E5A', display: 'block', marginBottom: '4px' },
  findingText: { fontFamily: mono, fontSize: '0.7rem', color: '#888', lineHeight: '1.5' },
})

const router = useRouter()

const formData = ref({ simulationRequirement: '' })
const files = ref([])
const loading = ref(false)

// Web seed generation
const seedLoading = ref(false)
const seedError = ref('')
const seedSources = ref([])
const error = ref('')
const isDragOver = ref(false)
const fileInput = ref(null)
const selectedBackend = ref('ladybug')
const customAgentsEnabled = ref(false)
const customAgents = ref([])

const fetchBackend = async () => {
  try {
    const response = await fetch('/api/config/backend')
    const data = await response.json()
    selectedBackend.value = data.backend || 'ladybug'
  } catch (e) {
    console.warn('Could not fetch backend config:', e)
  }
}

const switchBackend = async () => {
  try {
    const response = await fetch('/api/config/backend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ backend: selectedBackend.value })
    })
    const data = await response.json()
    if (!response.ok) {
      alert('Failed to switch backend: ' + (data.error || 'Unknown error'))
      fetchBackend()
    }
  } catch (e) {
    alert('Failed to switch backend: ' + e.message)
    fetchBackend()
  }
}

onMounted(() => {
  fetchBackend()
})

const canSubmit = computed(() => {
  const hasSeed = formData.value.simulationRequirement.trim() !== ''
  return hasSeed
})

const triggerFileInput = () => { if (!loading.value) fileInput.value?.click() }

const handleGenerateSeed = async () => {
  const query = formData.value.simulationRequirement.trim()
  if (!query || seedLoading.value) return
  seedLoading.value = true
  seedError.value = ''
  seedSources.value = []

  try {
    // Pass the user's natural-language query as the topic; backend infers + expands.
    const res = await generateSeedFromWeb({ topic: query })
    if (res.success && res.seed_text) {
      formData.value.simulationRequirement = res.seed_text
      seedSources.value = res.sources || []
    } else {
      seedError.value = res.error || 'Generation returned no content'
    }
  } catch (e) {
    seedError.value = e.message || 'Network or API error — check Firecrawl/Serper keys'
  } finally {
    seedLoading.value = false
  }
}
const handleFileSelect = (event) => { addFiles(Array.from(event.target.files)) }
const handleDragOver = (e) => { isDragOver.value = true }
const handleDragLeave = (e) => { isDragOver.value = false }
const handleDrop = (e) => { isDragOver.value = false; addFiles(Array.from(e.dataTransfer.files)) }

const addFiles = (newFiles) => {
  const allowed = ['.pdf', '.md', '.txt']
  const valid = newFiles.filter(f => allowed.some(ext => f.name.toLowerCase().endsWith(ext)))
  files.value = [...files.value, ...valid]
}

const removeFile = (index) => { files.value.splice(index, 1) }

const startSimulation = async () => {
  if (!canSubmit.value || loading.value) return
  loading.value = true

  // Deep research runs later, during Step 2 (Prepare), where the graph entity
  // types are known. Just hand the document + requirement to the Process page.
  import('../store/pendingUpload.js').then(({ setPendingUpload }) => {
    setPendingUpload(
      files.value,
      formData.value.simulationRequirement,
      customAgentsEnabled.value ? customAgents.value : [],
      customAgentsEnabled.value
    )
    router.push({ name: 'Process', params: { projectId: 'new' } })
  })

  loading.value = false
}
</script>

<style scoped>
/* Left-column pitch panel — brief what-is-this strap so first-time visitors
   understand the product without a separate landing page. Designed to sit
   beside the console, not above it. */
.pitch-panel {
  flex: 0.85;
  max-width: 460px;
  padding: 10px 40px 10px 0;
  display: flex;
  flex-direction: column;
  gap: 28px;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}
.pitch-tag {
  display: inline-block;
  align-self: flex-start;
  background: #1E9E5A;
  color: #fff;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 1.5px;
  padding: 4px 10px;
}
.pitch-title {
  font-size: 2.4rem;
  line-height: 1.15;
  font-weight: 500;
  letter-spacing: -1px;
  color: #000;
  margin: 0;
}
.pitch-accent {
  color: #1E9E5A;
  font-weight: 700;
}
.pitch-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 18px;
  border-top: 1px solid #EEE;
  padding-top: 24px;
}
.pitch-list li {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.pitch-bullet {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  font-size: 0.75rem;
  color: #1E9E5A;
  opacity: 0.55;
  margin-top: 2px;
  min-width: 22px;
}
.pitch-bullet-title {
  font-weight: 600;
  font-size: 0.95rem;
  color: #000;
  margin-bottom: 4px;
}
.pitch-bullet-desc {
  font-size: 0.82rem;
  color: #666;
  line-height: 1.5;
}
.pitch-foot {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  padding-top: 24px;
  border-top: 1px solid #EEE;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  color: #888;
  line-height: 1.55;
}
.pitch-foot-dot {
  width: 8px;
  height: 8px;
  background: #1E9E5A;
  flex-shrink: 0;
  margin-top: 1px;
}

/* Stack vertically on narrower screens */
@media (max-width: 1024px) {
  .pitch-panel {
    flex: 1;
    max-width: 100%;
    padding: 0 0 30px 0;
  }
}

/* Advanced settings fold — hides expert controls (graph engine, etc.)
   behind a collapsible section so first-run users aren't asked questions
   they can't answer. Click to expand. */
.advanced-settings {
  margin: 8px 20px 20px;
  border-top: 1px solid #EEE;
  padding-top: 12px;
}
.advanced-summary {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #999;
  cursor: pointer;
  padding: 4px 0;
  list-style: none;
  user-select: none;
}
.advanced-summary::before {
  content: '▸ ';
  color: #BBB;
  font-size: 0.7rem;
}
.advanced-settings[open] .advanced-summary::before {
  content: '▾ ';
}
.advanced-summary:hover { color: #1E9E5A; }
.advanced-body {
  padding: 12px 0 4px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.advanced-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.advanced-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #777;
  min-width: 100px;
}
.advanced-select {
  flex: 1;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  padding: 6px 10px;
  border: 1px solid #DDD;
  background: #fff;
  cursor: pointer;
  outline: none;
}
.advanced-hint {
  font-size: 0.7rem;
  color: #AAA;
  font-style: italic;
}

.console-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #555;
}
.console-dot.active {
  background: #1E9E5A;
  animation: pulse 1s infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* Web seed generation — inline action under the seed textarea */
.web-seed-bar {
  margin-top: 8px;
}

.web-seed-hint-inline {
  margin-top: 6px;
  font-size: 0.7rem;
  color: #999;
  font-style: italic;
  line-height: 1.4;
}

.web-seed-btn {
  width: 100%;
  padding: 10px;
  background: #F0FAF4;
  border: 1px solid #1E9E5A;
  color: #1E9E5A;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  font-weight: 700;
  cursor: pointer;
  border-radius: 4px;
}

.web-seed-btn:hover:not(:disabled) { background: #1E9E5A; color: #fff; }
.web-seed-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.web-seed-error {
  margin-top: 8px;
  padding: 8px 10px;
  background: #FEE;
  border: 1px solid #FCC;
  color: #C00;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  border-radius: 3px;
}

.web-seed-sources {
  margin-top: 12px;
  padding: 10px 12px;
  background: #FFF;
  border: 1px solid #DDD;
  border-radius: 4px;
  font-size: 0.75rem;
  color: #333;
}

.web-seed-sources ul {
  margin: 6px 0 0 0;
  padding-left: 18px;
}

.web-seed-sources li {
  margin: 3px 0;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
}

.web-seed-sources a {
  color: #1E9E5A;
  text-decoration: none;
}

.web-seed-sources a:hover { text-decoration: underline; }

.web-seed-hint {
  margin-top: 8px;
  font-size: 0.7rem;
  color: #888;
  font-style: italic;
}
</style>
