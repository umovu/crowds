<template>
  <div class="home-container">
    <!-- Top Navigation Bar -->
    <nav class="navbar" :style="s.navbar">
        <div class="nav-brand" :style="s.navBrand">fubsandbox</div>
    </nav>

    <div class="main-content" :style="s.mainContent">
      <div class="view-tabs">
        <button
          class="view-tab"
          :class="{ active: activeView === 'console' }"
          @click="activeView = 'console'"
        >Console</button>
        <button
          class="view-tab"
          :class="{ active: activeView === 'panel' }"
          @click="activeView = 'panel'"
        >Panel Pitch</button>
        <button
          class="view-tab"
          :class="{ active: activeView === 'personas' }"
          @click="activeView = 'personas'"
        >Personas</button>
      </div>

      <div class="roster-chips">
        <span class="chips-label">Sim roster</span>
        <div v-if="customAgents.length === 0" class="chips-empty">
          No personas preselected — pick from the Personas tab.
        </div>
        <div v-else class="chips-list">
          <span
            v-for="(p, idx) in customAgents"
            :key="(p.name || '') + '_' + idx"
            class="chip"
            :title="p.persona || ''"
          >
            <span class="chip-name">{{ p.name || 'Unnamed' }}</span>
            <span v-if="p.actor_archetype" class="chip-arch">{{ p.actor_archetype.replace(/_/g, ' ') }}</span>
            <span v-if="p.province" class="chip-province">{{ p.province }}</span>
            <button class="chip-remove" @click="removeFromRoster(idx)" title="Remove from roster">×</button>
          </span>
        </div>
        <div v-if="customAgents.length > 0" class="chips-actions">
          <button class="chips-clear" @click="clearRoster">Clear all</button>
        </div>
      </div>

      <div v-if="activeView === 'panel'" class="panel-pitch-view">
        <PanelPitchPanel />
      </div>

      <div v-else-if="activeView === 'personas'" class="personas-view">
        <header class="view-header">
          <h1>Persona Library</h1>
          <p>{{ personaCount }} personas grounded in South African socio-economic context — sampled from Stats SA QLFS microdata, textured with a reasoning model. Click <strong>☐ Select</strong> to pick personas to add to your sim roster.</p>
        </header>
        <div v-if="customAgentsEnabled && customAgents.length > 0" class="roster-banner">
          <span class="roster-banner-text">
            <strong>{{ customAgents.length }}</strong> persona{{ customAgents.length !== 1 ? 's' : '' }} in your sim roster
          </span>
          <button class="roster-banner-btn" @click="activeView = 'console'">View in Custom Agents →</button>
        </div>
        <div class="panel-container">
          <PersonaLibraryPanel @add-to-roster="onAddToRoster" />
        </div>
      </div>

      <section v-else class="dashboard-section" :style="s.dashboardSection">
        <!-- Left column: marketing pitch + agent pre-selection (tabbed, like the
             Panel's sectioned style) -->
        <aside class="pitch-panel">
          <div class="pitch-tabs" role="tablist">
            <button
              class="pitch-tab"
              role="tab"
              :class="{ active: pitchTab === 'overview' }"
              :aria-selected="pitchTab === 'overview'"
              @click="pitchTab = 'overview'"
            >Overview</button>
            <button
              class="pitch-tab"
              role="tab"
              :class="{ active: pitchTab === 'cast' }"
              :aria-selected="pitchTab === 'cast'"
              @click="setPitchTab('cast')"
            >
              Pick cast
              <span v-if="pickedIds.size" class="pitch-tab-count">{{ pickedIds.size }}</span>
            </button>
          </div>

          <!-- TAB: Overview — brief marketing / what-is-this -->
          <div v-show="pitchTab === 'overview'" class="pitch-tab-pane" role="tabpanel">
            <div class="pitch-tag">{{ pitchCopy.tag }}</div>
            <h1 class="pitch-title" v-html="pitchCopy.title"></h1>

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
                  <div class="pitch-bullet-desc">{{ pitchCopy.bullet3 }}</div>
                </div>
              </li>
            </ul>

            <div class="pitch-foot">
              <span class="pitch-foot-dot"></span>
              Built for South African policy and product questions. Designed for evidence, not vibes.
            </div>
          </div>

          <!-- TAB: Cast — pre-select agents from the library, like the Panel's
               WHO'S IN THE ROOM. Group cards (top) bulk-pick all members of a
               group with one click; individual cards (below) fine-tune. The
               "Add to roster" button merges them into the right column's
               custom agents list. -->
          <div v-show="pitchTab === 'cast'" class="pitch-tab-pane" role="tabpanel">
            <div class="cast-section">
              <div class="cast-section-header">
                <span class="cast-section-title">02 / WHO'S IN THE ROOM — pick personas to seed your sim</span>
                <span class="cast-section-count">{{ libraryPersonas.length }} in library · {{ pickedIds.size }} picked</span>
              </div>

              <div v-if="libraryLoading" class="cast-loading">Loading personas…</div>
              <div v-else-if="!libraryPersonas.length" class="cast-empty">
                No personas in the library yet. Add some on the Personas tab.
              </div>
              <template v-else>
                <!-- Fee-status groups: Fee-paying vs No-fee-school.
                     Mirrors the predicates in panel_service.SEGMENTS so the
                     Console's Cast picker matches the Panel's segments 1:1. -->
                <div class="cast-groups">
                  <button
                    type="button"
                    class="cast-group"
                    :class="{
                      selected: feeGroupState('paying') === 'full',
                      partial: feeGroupState('paying') === 'partial',
                    }"
                    :disabled="feeGroupCount('paying') === 0"
                    @click="toggleFeeGroup('paying')"
                    title="Households already paying school fees — proven education spend"
                  >
                    <span class="cast-group-top">
                      <span class="cast-group-label">Fee-paying households</span>
                      <span class="cast-group-count">{{ pickedInFeeGroup('paying') }}/{{ feeGroupCount('paying') }}</span>
                    </span>
                    <span class="cast-group-desc">Already paying school fees (GHS)</span>
                  </button>
                  <button
                    type="button"
                    class="cast-group"
                    :class="{
                      selected: feeGroupState('non_paying') === 'full',
                      partial: feeGroupState('non_paying') === 'partial',
                    }"
                    :disabled="feeGroupCount('non_paying') === 0"
                    @click="toggleFeeGroup('non_paying')"
                    title="Households at no-fee schools — tightest affordability test"
                  >
                    <span class="cast-group-top">
                      <span class="cast-group-label">No-fee-school households</span>
                      <span class="cast-group-count">{{ pickedInFeeGroup('non_paying') }}/{{ feeGroupCount('non_paying') }}</span>
                    </span>
                    <span class="cast-group-desc">No-fee schools only (GHS) — tightest affordability test</span>
                  </button>
                </div>

                <!-- Archetype groups: every actor_archetype in the library.
                     "Everyone" picks the full library in one click. -->
                <div class="cast-group-section-label">By archetype</div>
                <div class="cast-groups">
                  <button
                    type="button"
                    class="cast-group"
                    :class="{ selected: isAllPicked }"
                    :disabled="libraryPersonas.length === 0"
                    @click="toggleGroup('__all__')"
                  >
                    <span class="cast-group-top">
                      <span class="cast-group-label">Everyone</span>
                      <span class="cast-group-count">{{ pickedIds.size }}/{{ libraryPersonas.length }}</span>
                    </span>
                    <span class="cast-group-desc">Pick the full library</span>
                  </button>
                  <button
                    v-for="a in castArchetypes"
                    :key="a.key"
                    type="button"
                    class="cast-group"
                    :class="{
                      selected: groupState(a.key) === 'full',
                      partial: groupState(a.key) === 'partial',
                    }"
                    @click="toggleGroup(a.key)"
                  >
                    <span class="cast-group-top">
                      <span class="cast-group-label">{{ a.key.replace(/_/g, ' ') }}</span>
                      <span class="cast-group-count">{{ pickedInGroup(a.key) }}/{{ a.count }}</span>
                    </span>
                    <span class="cast-group-desc">
                      {{ groupState(a.key) === 'full' ? 'Picked' : groupState(a.key) === 'partial' ? 'Partially picked' : 'Not picked' }}
                    </span>
                  </button>
                </div>

                <div class="cast-controls">
                  <input
                    v-model="castSearch"
                    class="cast-search"
                    type="text"
                    placeholder="Search personas by name, occupation…"
                  />
                  <select v-model="castArchetypeFilter" class="cast-filter">
                    <option value="">All groups ({{ libraryPersonas.length }})</option>
                    <option v-for="a in castArchetypes" :key="a.key" :value="a.key">
                      {{ a.key.replace(/_/g, ' ') }} ({{ a.count }})
                    </option>
                  </select>
                </div>

                <div v-if="filteredLibrary.length === 0" class="cast-empty">No personas match.</div>
                <div v-else class="cast-grid">
                  <button
                    v-for="p in filteredLibrary"
                    :key="personaIdOf(p)"
                    type="button"
                    class="cast-card"
                    :class="{ selected: pickedIds.has(personaIdOf(p)) }"
                    :title="p.persona || ''"
                    @click="togglePicked(p)"
                  >
                    <span class="cast-avatar">{{ (p.name || '?').slice(0, 1).toUpperCase() }}</span>
                    <span class="cast-body">
                      <span class="cast-name">{{ p.name || 'Unnamed' }}</span>
                      <span class="cast-meta">
                        <span class="cast-arch">{{ (p.actor_archetype || 'unknown').replace(/_/g, ' ') }}</span>
                        <span v-if="p.province" class="cast-province">{{ p.province }}</span>
                      </span>
                      <span v-if="p.budget_tier" class="cast-tier" :class="'tier-' + p.budget_tier">{{ p.budget_tier }}</span>
                    </span>
                    <span class="cast-check">
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3">
                        <polyline points="20 6 9 17 4 12"></polyline>
                      </svg>
                    </span>
                  </button>
                </div>

                <div class="cast-actions">
                  <button class="cast-link" @click="selectAllFiltered" :disabled="!filteredLibrary.length">Select all visible</button>
                  <span class="cast-divider">|</span>
                  <button class="cast-link" @click="clearPicked" :disabled="pickedIds.size === 0">Clear</button>
                  <button
                    class="cast-add"
                    :disabled="pickedIds.size === 0"
                    @click="addPickedToRoster"
                  >
                    Add {{ pickedIds.size }} to roster →
                  </button>
                </div>
              </template>
            </div>
          </div>
        </aside>

        <!-- Right column: the actual console -->
        <div class="right-panel" :style="{ ...s.rightPanel, flex: '1' }">
          <div class="console-box" :style="s.consoleBox">

            <!-- Mode selector: Policy vs Product -->
            <div class="mode-switch">
              <button
                class="mode-btn"
                :class="{ active: mode === 'policy' }"
                :disabled="loading || seedLoading"
                @click="mode = 'policy'"
              >Policy</button>
              <button
                class="mode-btn"
                :class="{ active: mode === 'product' }"
                :disabled="loading || seedLoading"
                @click="mode = 'product'"
              >Product</button>
              <span class="mode-hint">{{ pitchCopy.modeHint }}</span>
            </div>

            <!-- 01: Seed Message -->
            <div :style="s.consoleSection">
              <div class="console-header" :style="s.consoleHeader">
                <span>01 / {{ pitchCopy.seedHeader }}</span>
                <span>Required</span>
              </div>
              <div :style="s.inputWrapper">
                <textarea
                  v-model="formData.simulationRequirement"
                  :style="s.codeInput"
                  :placeholder="pitchCopy.seedPlaceholder"
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
                v-model:customOnly="customAgentsOnly"
              />
            </div>

            <!-- Graph engine picker -->
            <div :style="s.consoleSection">
              <div class="console-header" :style="s.consoleHeader">
                <span>04 / Graph Engine</span>
                <span>Choose one</span>
              </div>
              <div class="engine-grid">
                <label
                  class="engine-card"
                  :class="{ selected: selectedBackend === 'ladybug' }"
                >
                  <input
                    type="radio"
                    value="ladybug"
                    v-model="selectedBackend"
                    @change="switchBackend"
                    :disabled="loading"
                    class="engine-radio"
                  />
                  <div class="engine-card-body">
                    <div class="engine-card-top">
                      <span class="engine-name">LadybugDB</span>
                      <span class="engine-tag">Recommended</span>
                    </div>
                    <div class="engine-desc">
                      Embedded, no Docker needed. Persists to a file on disk.
                      Best for solo / local use.
                    </div>
                  </div>
                </label>

                <label
                  class="engine-card"
                  :class="{ selected: selectedBackend === 'neo4j' }"
                >
                  <input
                    type="radio"
                    value="neo4j"
                    v-model="selectedBackend"
                    @change="switchBackend"
                    :disabled="loading"
                    class="engine-radio"
                  />
                  <div class="engine-card-body">
                    <div class="engine-card-top">
                      <span class="engine-name">Neo4j</span>
                      <span class="engine-tag-muted">Needs Docker</span>
                    </div>
                    <div class="engine-desc">
                      Industry-standard graph server. Built-in browser UI,
                      handles bigger graphs, supports multi-process access.
                    </div>
                  </div>
                </label>
              </div>
            </div>

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

    </div>
    <PersonaLibraryDrawer />
    <SimsDrawer />
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import CustomAgentPanel from '../components/CustomAgentPanel.vue'
import SimsDrawer from '../components/SimsDrawer.vue'
import PersonaLibraryDrawer from '../components/PersonaLibraryDrawer.vue'
import PersonaLibraryPanel from '../components/PersonaLibraryPanel.vue'
import PanelPitchPanel from '../components/PanelPitchPanel.vue'
import AgentPicker from '../components/AgentPicker.vue'
import { generateSeedFromWeb, listPersonas, getPersona } from '../api/research'

const mono = 'JetBrains Mono, monospace'
const sans = 'Space Grotesk, Noto Sans SC, system-ui, sans-serif'

const s = reactive({
  navbar: { height: '60px', background: 'transparent', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0 40px' },
  navBrand: { fontFamily: mono, fontWeight: '800', letterSpacing: '1px', fontSize: '1.2rem', color: '#1E9E5A' },
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

const activeView = ref('console')
const personaCount = ref(199)

const onAddToRoster = (personas) => {
  const existing = new Set(customAgents.value.map(a => (a.name || '').toLowerCase()))
  const fresh = personas.filter(p => p && p.name && !existing.has(p.name.toLowerCase()))
  if (fresh.length === 0) return
  customAgents.value = [...customAgents.value, ...fresh]
  customAgentsEnabled.value = true
}

const removeFromRoster = (idx) => {
  const list = [...customAgents.value]
  list.splice(idx, 1)
  customAgents.value = list
  if (list.length === 0) customAgentsEnabled.value = false
}

const clearRoster = () => {
  customAgents.value = []
  customAgentsEnabled.value = false
}

// Left-column persona picker — choose the sim cast from the library directly.
const libraryPersonas = ref([])
const libraryLoading = ref(false)
const pickedIds = ref(new Set())
const personaIdOf = (p) => p.id ?? p.persona_id ?? p.name

// Left-column tab state. 'overview' is the marketing strap; 'cast' is the
// agent pre-selection grid (mirrors the Panel's "WHO'S IN THE ROOM").
const pitchTab = ref('overview')

// Lazy-load the persona library the first time the Cast tab is opened, so
// first paint of the marketing tab stays fast.
const setPitchTab = (tab) => {
  pitchTab.value = tab
  if (tab === 'cast') loadLibrary()
}

// Cast-tab local filters. Kept separate from the global `pickedIds` so typing
// in the search box doesn't blow away the selection.
const castSearch = ref('')
const castArchetypeFilter = ref('')

const castArchetypes = computed(() => {
  const counts = {}
  for (const p of libraryPersonas.value) {
    const k = p.actor_archetype || 'unknown'
    counts[k] = (counts[k] || 0) + 1
  }
  return Object.entries(counts)
    .map(([key, count]) => ({ key, count }))
    .sort((a, b) => b.count - a.count)
})

const filteredLibrary = computed(() => {
  const q = castSearch.value.trim().toLowerCase()
  return libraryPersonas.value.filter((p) => {
    if (castArchetypeFilter.value && (p.actor_archetype || 'unknown') !== castArchetypeFilter.value) return false
    if (!q) return true
    return (
      (p.name || '').toLowerCase().includes(q) ||
      (p.occupation || '').toLowerCase().includes(q) ||
      (p.actor_archetype || '').toLowerCase().includes(q)
    )
  })
})

const loadLibrary = async () => {
  if (libraryPersonas.value.length || libraryLoading.value) return
  libraryLoading.value = true
  try {
    const res = await listPersonas()
    libraryPersonas.value = (res.personas || []).map(p => ({
      ...p,
      actor_archetype: p.actor_archetype || p.archetype,
    }))
  } catch (e) {
    console.error('Failed to load persona library:', e)
  } finally {
    libraryLoading.value = false
  }
}

const togglePicked = (p) => {
  const id = personaIdOf(p)
  const next = new Set(pickedIds.value)
  next.has(id) ? next.delete(id) : next.add(id)
  pickedIds.value = next
}

// Group helpers — back the "WHO'S IN THE ROOM" group cards. A group is
// `full` when every persona in it is picked, `partial` when at least one
// is, and `none` otherwise. `__all__` is the synthetic "Everyone" group.
const personasInGroup = (arch) => libraryPersonas.value.filter(
  (p) => (p.actor_archetype || 'unknown') === arch
)
const pickedInGroup = (arch) => personasInGroup(arch).filter(
  (p) => pickedIds.value.has(personaIdOf(p))
).length
const groupState = (arch) => {
  const total = personasInGroup(arch).length
  if (total === 0) return 'none'
  const picked = pickedInGroup(arch)
  if (picked === 0) return 'none'
  if (picked === total) return 'full'
  return 'partial'
}
const isAllPicked = computed(() =>
  libraryPersonas.value.length > 0 &&
  libraryPersonas.value.every((p) => pickedIds.value.has(personaIdOf(p)))
)
const toggleGroup = (arch) => {
  const next = new Set(pickedIds.value)
  if (arch === '__all__') {
    const fullyPicked = isAllPicked.value
    if (fullyPicked) {
      next.clear()
    } else {
      for (const p of libraryPersonas.value) next.add(personaIdOf(p))
    }
  } else {
    const state = groupState(arch)
    const members = personasInGroup(arch)
    if (state === 'full') {
      for (const p of members) next.delete(personaIdOf(p))
    } else {
      for (const p of members) next.add(personaIdOf(p))
    }
  }
  pickedIds.value = next
}

// Fee-status groups. Mirrors panel_service._pays_school_fees / _no_fee_only
// (same predicate, same persona fields), so the Console picker agrees with
// the Panel's `fee_paying` / `no_fee_school` segments 1:1.
const personaFeeBands = (p) => {
  const bands = Array.isArray(p.learner_fee_bands) ? [...p.learner_fee_bands] : []
  if (p.fees_band) bands.push(p.fees_band)
  return bands.filter(Boolean)
}
const isFeePaying = (p) => personaFeeBands(p).some((b) => b && b !== 'No fees')
const isNoFeeOnly = (p) => {
  const bands = personaFeeBands(p)
  return bands.length > 0 && bands.every((b) => b === 'No fees')
}
const personasInFeeGroup = (kind) => libraryPersonas.value.filter(
  (p) => (kind === 'paying' ? isFeePaying(p) : isNoFeeOnly(p))
)
const pickedInFeeGroup = (kind) => personasInFeeGroup(kind).filter(
  (p) => pickedIds.value.has(personaIdOf(p))
).length
const feeGroupCount = (kind) => personasInFeeGroup(kind).length
const feeGroupState = (kind) => {
  const total = feeGroupCount(kind)
  if (total === 0) return 'none'
  const picked = pickedInFeeGroup(kind)
  if (picked === 0) return 'none'
  if (picked === total) return 'full'
  return 'partial'
}
const toggleFeeGroup = (kind) => {
  const state = feeGroupState(kind)
  const members = personasInFeeGroup(kind)
  if (members.length === 0) return
  const next = new Set(pickedIds.value)
  if (state === 'full') {
    for (const p of members) next.delete(personaIdOf(p))
  } else {
    for (const p of members) next.add(personaIdOf(p))
  }
  pickedIds.value = next
}

const selectAllFiltered = () => {
  const next = new Set(pickedIds.value)
  for (const p of filteredLibrary.value) next.add(personaIdOf(p))
  pickedIds.value = next
}

const clearPicked = () => {
  pickedIds.value = new Set()
}

const addPickedToRoster = async () => {
  const existingNames = new Set(customAgents.value.map(a => (a.name || '').toLowerCase()))
  const added = []
  for (const id of pickedIds.value) {
    const meta = libraryPersonas.value.find(p => personaIdOf(p) === id)
    if (!meta || existingNames.has((meta.name || '').toLowerCase())) continue
    let full = meta
    try {
      const res = await getPersona(id)
      if (res.success && res.persona) {
        full = { ...res.persona, actor_archetype: res.persona.actor_archetype || res.persona.archetype }
      }
    } catch (e) {
      console.warn('Falling back to metadata for persona', id, e)
    }
    added.push(full)
  }
  if (added.length) onAddToRoster(added)   // reuse the existing roster merge
  pickedIds.value = new Set()
}

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
const customAgentsOnly = ref(false)

// Simulation mode: 'policy' (citizens vs a policy) or 'product' (a SA market vs a product idea)
const mode = ref('policy')

// Mode-driven pitch + input copy. Policy strings are the originals, so the
// default view is unchanged.
const pitchCopy = computed(() => {
  if (mode.value === 'product') {
    return {
      tag: 'PRODUCT WIND TUNNEL',
      title: 'Stress-test a product idea<br />against a South African market.',
      bullet3: 'Pause and test a price, feature, or pitch change. Compare reactions.',
      modeHint: 'How would a SA market react to your product idea?',
      seedHeader: 'Product Idea',
      seedPlaceholder: 'Describe the product idea, pitch, or positioning you want to stress-test. What is it? Who is it for? What problem does it solve?'
    }
  }
  return {
    tag: 'POLICY WIND TUNNEL',
    title: 'Test events on <span class="pitch-accent">digital agents</span><br />before they happen to real people.',
    bullet3: 'Pause and test a policy announcement. Compare trajectories.',
    modeHint: 'How would the public react to your policy or announcement?',
    seedHeader: 'Seed Message',
    seedPlaceholder: 'Describe the policy, event, or scenario you want to simulate. What are you testing? Who is the audience?'
  }
})

// Use VITE_API_BASE_URL so the deployed frontend calls the configured
// backend (e.g. a tunnel URL), not its own origin. Empty string falls back
// to same-origin for local dev where the Vite proxy handles /api/*.
const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

const fetchBackend = async () => {
  try {
    const response = await fetch(`${API_BASE}/api/config/backend`)
    const data = await response.json()
    selectedBackend.value = data.backend || 'ladybug'
  } catch (e) {
    console.warn('Could not fetch backend config:', e)
  }
}

const switchBackend = async () => {
  try {
    const response = await fetch(`${API_BASE}/api/config/backend`, {
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
    const res = await generateSeedFromWeb({ topic: query, mode: mode.value })
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
      customAgentsEnabled.value,
      customAgentsEnabled.value && customAgentsOnly.value,
      mode.value
    )
    router.push({ name: 'Process', params: { projectId: 'new' } })
  })

  loading.value = false
}
</script>

<style scoped>
/* Mode selector — Policy vs Product. Drives pitch + input copy and the
   simulation mode sent to /prepare. */
.mode-switch {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}
.mode-btn {
  padding: 6px 16px;
  border: 1px solid #DDD;
  background: #fff;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  font-weight: 600;
  color: #666;
  cursor: pointer;
  transition: all 0.15s;
}
.mode-btn:first-of-type { border-radius: 6px 0 0 6px; }
.mode-btn:nth-of-type(2) { border-radius: 0 6px 6px 0; border-left: none; }
.mode-btn.active {
  background: #1E9E5A;
  border-color: #1E9E5A;
  color: #fff;
}
.mode-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.mode-hint {
  font-size: 0.75rem;
  color: #999;
  margin-left: 4px;
}

/* Left-column pitch panel — brief what-is-this strap so first-time visitors
   understand the product without a separate landing page. Designed to sit
   beside the console, not above it. */
.pitch-panel {
  flex: 0.85;
  max-width: 460px;
  padding: 10px 40px 10px 0;
  display: flex;
  flex-direction: column;
  gap: 24px;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

/* Tab bar — mirrors the Panel's numbered section style ("02 / WHO'S IN THE
   ROOM") so it feels like the same product. */
.pitch-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid #E5E5E5;
}
.pitch-tab {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem;
  font-weight: 600;
  color: #999;
  cursor: pointer;
  margin-bottom: -1px;
  transition: color 0.15s, border-color 0.15s;
}
.pitch-tab:hover { color: #000; }
.pitch-tab.active {
  color: #000;
  border-bottom-color: #1E9E5A;
}
.pitch-tab-count {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.65rem;
  font-weight: 700;
  background: #1E9E5A;
  color: #fff;
  padding: 1px 6px;
  border-radius: 8px;
}
.pitch-tab-pane {
  display: flex;
  flex-direction: column;
  gap: 24px;
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

/* Cast tab — pre-select agents. Visually echoes the Panel's
   "02 / WHO'S IN THE ROOM" section header and segment-card grid, but with
   individual personas (not groups) as the cards. */
.cast-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.cast-section-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  color: #666;
  letter-spacing: 0.5px;
}
.cast-section-title { font-weight: 600; }
.cast-section-count { color: #999; }
.cast-loading,
.cast-empty {
  padding: 24px 12px;
  text-align: center;
  color: #999;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem;
  border: 1px dashed #DDD;
  background: #FAFAFA;
}
.cast-controls { display: flex; gap: 8px; }
.cast-search,
.cast-filter {
  border: 1px solid #DDD;
  padding: 7px 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem;
  background: #fff;
  outline: none;
}
.cast-search { flex: 1; }
.cast-search:focus,
.cast-filter:focus { border-color: #1E9E5A; }

/* Group quick-select cards (mirrors PanelPitchPanel's pp-segments). One click
   picks every persona in the group; click again to deselect. Partial state
   shows when a group has been individually fine-tuned. */
.cast-groups {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 8px;
}
.cast-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid #DDD;
  background: #fff;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s, background 0.15s;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}
.cast-group:hover:not(:disabled) { border-color: #1E9E5A; }
.cast-group.selected {
  border-color: #1E9E5A;
  background: #F0FAF4;
}
.cast-group.partial {
  border-color: rgba(30, 158, 90, 0.5);
  background: #FCFEFC;
}
.cast-group:disabled { opacity: 0.5; cursor: not-allowed; }
.cast-group-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.cast-group-label {
  font-weight: 600;
  font-size: 0.82rem;
  color: #000;
  text-transform: capitalize;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cast-group-count {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.66rem;
  font-weight: 700;
  color: #1E9E5A;
  background: rgba(30, 158, 90, 0.1);
  padding: 1px 7px;
  border-radius: 8px;
  flex-shrink: 0;
}
.cast-group-desc {
  font-size: 0.68rem;
  color: #888;
  line-height: 1.3;
}
.cast-group-section-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.68rem;
  font-weight: 700;
  color: #999;
  letter-spacing: 1px;
  text-transform: uppercase;
  margin-top: 4px;
}

.cast-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
  padding-right: 4px;
}
.cast-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #E5E5E5;
  background: #fff;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s, background 0.15s;
  position: relative;
}
.cast-card:hover { border-color: #1E9E5A; }
.cast-card.selected {
  border-color: #1E9E5A;
  background: #F0FAF4;
}
.cast-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #F0FAF4;
  border: 1px solid rgba(30, 158, 90, 0.3);
  color: #1E9E5A;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.cast-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}
.cast-name {
  font-weight: 700;
  font-size: 0.82rem;
  color: #000;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cast-meta { display: flex; gap: 6px; flex-wrap: wrap; }
.cast-arch,
.cast-province {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.62rem;
  color: #666;
}
.cast-province { color: #999; }
.cast-tier {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.58rem;
  font-weight: 700;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  padding: 1px 6px;
  border-radius: 2px;
  align-self: flex-start;
}
.tier-tight { background: #FDEDEB; color: #C0392B; border: 1px solid #E6B0AA; }
.tier-moderate { background: #F4F4F4; color: #666; border: 1px solid #DDD; }
.tier-loose { background: rgba(30, 158, 90, 0.1); color: #1E9E5A; border: 1px solid rgba(30, 158, 90, 0.4); }

.cast-check {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 18px;
  height: 18px;
  border: 1px solid #DDD;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: transparent;
  background: #fff;
  transition: all 0.15s;
}
.cast-card.selected .cast-check {
  background: #1E9E5A;
  border-color: #1E9E5A;
  color: #fff;
}

.cast-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.cast-link {
  background: transparent;
  border: none;
  padding: 4px 0;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  color: #1E9E5A;
  cursor: pointer;
  font-weight: 600;
}
.cast-link:hover:not(:disabled) { text-decoration: underline; }
.cast-link:disabled { color: #BBB; cursor: not-allowed; }
.cast-divider { color: #DDD; }
.cast-add {
  margin-left: auto;
  padding: 9px 18px;
  background: #1E9E5A;
  color: #fff;
  border: none;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.3px;
  cursor: pointer;
  transition: background 0.15s;
}
.cast-add:hover:not(:disabled) { background: #178048; }
.cast-add:disabled { background: #DDD; cursor: not-allowed; }

/* Graph-engine picker — two radio cards, one selected.
   Promoted out of the "advanced" fold so the user makes a deliberate
   choice between the two supported backends (Ladybug / Neo4j). */
.engine-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.engine-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid #DDD;
  cursor: pointer;
  background: #fff;
  transition: border-color 0.15s, background 0.15s;
}
.engine-card:hover {
  border-color: #1E9E5A;
}
.engine-card.selected {
  border-color: #1E9E5A;
  background: #F0FAF4;
}
.engine-radio {
  margin-top: 3px;
  accent-color: #1E9E5A;
  cursor: pointer;
}
.engine-card-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.engine-card-top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.engine-name {
  font-weight: 600;
  font-size: 0.9rem;
  color: #000;
}
.engine-tag {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.65rem;
  font-weight: 700;
  background: #1E9E5A;
  color: #fff;
  padding: 1px 6px;
}
.engine-tag-muted {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.65rem;
  font-weight: 600;
  color: #999;
  background: #F4F4F4;
  padding: 1px 6px;
}
.engine-desc {
  font-size: 0.75rem;
  color: #666;
  line-height: 1.45;
}
@media (max-width: 720px) {
  .engine-grid { grid-template-columns: 1fr; }
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

/* View tabs — switch between Console and Personas at the top of the page */
.view-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid #E5E5E5;
  margin-bottom: 0;
}
.view-tab {
  padding: 12px 24px;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  font-weight: 600;
  color: #999;
  cursor: pointer;
  transition: all 0.15s;
  margin-bottom: -1px;
}
.view-tab:hover { color: #000; }
.view-tab.active {
  color: #000;
  border-bottom-color: #1E9E5A;
}

/* Roster chips — picked personas visible on every view, above the active panel */
.roster-chips {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 0;
  border-bottom: 1px solid #E5E5E5;
  margin-bottom: 24px;
}
.chips-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  font-weight: 700;
  color: #999;
  letter-spacing: 1px;
  text-transform: uppercase;
  margin-right: 4px;
}
.chips-empty {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #999;
  font-style: italic;
}
.chips-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  flex: 1;
  min-width: 0;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px 4px 10px;
  background: #F0FAF4;
  border: 1px solid #1E9E5A;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  color: #000;
  max-width: 320px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.chip-name {
  font-weight: 700;
  color: #1E9E5A;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.chip-arch {
  color: #666;
  font-size: 0.68rem;
  white-space: nowrap;
}
.chip-province {
  color: #999;
  font-size: 0.68rem;
  white-space: nowrap;
}
.chip-remove {
  background: transparent;
  border: none;
  color: #1E9E5A;
  font-size: 1.1rem;
  line-height: 1;
  cursor: pointer;
  padding: 0 4px;
  margin-left: 2px;
  font-weight: 700;
}
.chip-remove:hover { color: #C0392B; }
.chips-actions { margin-left: auto; }
.chips-clear {
  background: transparent;
  border: 1px solid #DDD;
  padding: 4px 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: #666;
  cursor: pointer;
}
.chips-clear:hover { border-color: #C0392B; color: #C0392B; }

/* Panel Pitch view — full-width below the tab bar */
.panel-pitch-view {
  margin-top: 24px;
}

/* Personas view — full-width panel below the tab bar */
.personas-view {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 60px - 50px - 80px);
  min-height: 500px;
  border: 1px solid #E5E5E5;
}
.view-header {
  padding: 24px 32px 16px;
  border-bottom: 1px solid #EAEAEA;
  flex-shrink: 0;
}
.view-header h1 {
  margin: 0 0 6px;
  font-size: 1.5rem;
  font-weight: 600;
  color: #000;
}
.view-header p {
  margin: 0;
  font-size: 0.85rem;
  color: #666;
  line-height: 1.5;
  max-width: 720px;
}
.panel-container {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.roster-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 32px;
  background: #F0FAF4;
  border-bottom: 1px solid #DDD;
  flex-shrink: 0;
}
.roster-banner-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  color: #1E9E5A;
  flex: 1;
}
.roster-banner-btn {
  background: #1E9E5A;
  color: #fff;
  border: none;
  padding: 6px 14px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
}
.roster-banner-btn:hover { background: #178048; }
</style>
