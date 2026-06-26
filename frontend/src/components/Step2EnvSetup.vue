<template>
  <div class="env-setup-panel">
    <div class="scroll-container">
      <!-- Background graph-build status: shown while the document graph is still
           building so the user knows personas are being grounded, not stalled. -->
      <div v-if="currentPhase > -1 && currentPhase < 2" class="grounding-banner">
        <div class="grounding-spinner"></div>
        <span class="grounding-text">
          {{ currentPhase === 0
              ? 'Reading your documents…'
              : 'Grounding personas in your documents…' }}
        </span>
      </div>

      <!-- Mode detection banner: shown when the backend auto-detected the mode from
           the seed (not when the user pinned it). One click flips + pins the mode. -->
      <div v-if="showModeBanner" class="mode-detect-banner">
        <span class="mode-detect-text">
          Detected: <strong>{{ detectedModeLabel }}</strong>
          <span v-if="resolvedConverged" class="mode-detect-badge">+ {{ convergedLensLabel }}</span>
        </span>
        <button class="mode-detect-btn" @click="switchDetectedMode">Switch to {{ otherModeLabel }}</button>
      </div>

      <!-- Step 01: Simulation Instance -->
      <div class="step-card" :class="{ 'active': phase === 0, 'completed': phase > 0 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">01</span>
            <span class="step-title">Simulation Instance Initialization</span>
          </div>
          <div class="step-status">
            <span v-if="phase > 0" class="badge success">Completed</span>
            <span v-else class="badge processing">Initialization</span>
          </div>
        </div>
        
        <div class="card-content">
          <p class="api-note">POST /api/simulation/create</p>
          <p class="description">
            Create new simulation instance and fetch simulated world parameter template
          </p>

          <div v-if="simulationId" class="info-card">
            <div class="info-row">
              <span class="info-label">Project ID</span>
              <span class="info-value mono">{{ projectData?.project_id }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Graph ID</span>
              <span class="info-value mono">{{ projectData?.graph_id }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Simulation ID</span>
              <span class="info-value mono">{{ simulationId }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Task ID</span>
              <span class="info-value mono">{{ taskId || 'Async task completed' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 02: Assemble Persona Cast -->
      <div class="step-card" :class="{ 'active': phase === 1, 'completed': phase > 1 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">02</span>
            <span class="step-title">Assemble Persona Cast</span>
          </div>
          <div class="step-status">
            <span v-if="phase > 1" class="badge success">Completed</span>
            <span v-else-if="phase === 1" class="badge processing">{{ prepareProgress }}%</span>
            <span v-else class="badge pending">Waiting</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/simulation/prepare</p>
          <p class="description">
            Draw a representative cast from the curated persona library (survey-grounded), tilted toward the reality seed. The knowledge graph supplies context only — it never authors personas.
          </p>

          <!-- Profiles Stats -->
          <div v-if="profiles.length > 0" class="stats-grid">
            <div class="stat-card">
              <span class="stat-value">{{ profiles.length }}</span>
              <span class="stat-label">Current Agent Count</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ expectedTotal || '-' }}</span>
              <span class="stat-label">Expected Agent Total</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ totalTopicsCount }}</span>
              <span class="stat-label">Current Related Topics Count for Reality Seed</span>
            </div>
          </div>

          <!-- Profiles List Preview -->
          <div v-if="profiles.length > 0" class="profiles-preview">
            <div class="preview-header">
              <span class="preview-title">Persona Cast</span>
            </div>
            <div class="profiles-list">
              <div 
                v-for="(profile, idx) in profiles" 
                :key="idx" 
                class="profile-card"
                @click="selectProfile(profile)"
              >
                <div class="profile-header">
                  <span class="profile-realname">{{ profile.username || 'Unknown' }}</span>
                  <span class="profile-username">@{{ profile.name || `agent_${idx}` }}</span>
                </div>
                <div class="profile-meta">
                  <span class="profile-profession">{{ profile.profession || 'Unknown Profession' }}</span>
                </div>
                <p class="profile-bio">{{ profile.bio || 'No introduction available' }}</p>
                <div v-if="profile.interested_topics?.length" class="profile-topics">
                  <span 
                    v-for="topic in profile.interested_topics.slice(0, 3)" 
                    :key="topic" 
                    class="topic-tag"
                  >{{ topic }}</span>
                  <span v-if="profile.interested_topics.length > 3" class="topic-more">
                    +{{ profile.interested_topics.length - 3 }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- Deep Research Panel (visible when deep research ran) -->
          <div v-if="Object.keys(enrichmentData).length > 0 || researchRunning" class="enrichment-section">
            <div class="preview-header">
              <span class="preview-title">Deep Research</span>
              <span class="preview-hint">Web research grounding agent personas in real conditions</span>
            </div>

            <!-- Stats row -->
            <div v-if="Object.keys(enrichmentData).length > 0" class="research-stats">
              <div class="rstat">
                <div class="rstat-value">{{ Object.keys(enrichmentData).length }}</div>
                <div class="rstat-label">Archetypes</div>
              </div>
              <div class="rstat">
                <div class="rstat-value">{{ researchCharCount.toLocaleString() }}</div>
                <div class="rstat-label">Chars of data</div>
              </div>
              <div class="rstat">
                <div class="rstat-value">{{ researchSources.length }}</div>
                <div class="rstat-label">Sources</div>
              </div>
            </div>

            <!-- Sources -->
            <div v-if="researchSources.length > 0" class="research-sources">
              <span class="sources-label">Sources:</span>
              <span v-for="src in researchSources" :key="src" class="source-tag">{{ src }}</span>
            </div>

            <!-- Running indicator -->
            <div v-if="researchRunning" class="research-running">
              <span class="console-dot active"></span>
              Researching {{ researchCurrentArchetype || 'archetypes' }}…
            </div>

            <!-- Per-archetype cards -->
            <div
              v-for="(text, archetype) in enrichmentData"
              :key="archetype"
              class="enrichment-card"
            >
              <div class="enrichment-header" @click="toggleEnrichment(archetype)">
                <span class="enrichment-archetype">{{ archetype.replace(/_/g, ' ') }}</span>
                <span class="enrichment-chars">{{ text.length.toLocaleString() }} chars</span>
                <span class="enrichment-toggle">{{ expandedEnrichment.has(archetype) ? '▲' : '▼' }}</span>
              </div>
              <div v-if="expandedEnrichment.has(archetype)" class="enrichment-body">
                <pre class="enrichment-text">{{ text }}</pre>
              </div>
            </div>

            <!-- Re-run button -->
            <button
              class="rerun-research-btn"
              :disabled="researchRunning || !props.simulationId"
              @click="rerunResearch"
            >
              <span v-if="researchRunning">Researching…</span>
              <span v-else>🔄 Re-run research</span>
            </button>
            <div v-if="researchError" class="research-error">{{ researchError }}</div>
          </div>

            <!-- Cost summary panel -->
          <div v-if="costData" class="cost-summary">
            <div class="cost-row">
              <span class="cost-label">Prepare phase</span>
              <span class="cost-value">R{{ costData.prepare.cost_zar }} <span class="cost-usd">${{ costData.prepare.cost_usd }}</span></span>
            </div>
            <div class="cost-row" v-if="costData.simulation.prompt_tokens > 0">
              <span class="cost-label">Simulation phase</span>
              <span class="cost-value">R{{ costData.simulation.cost_zar }} <span class="cost-usd">${{ costData.simulation.cost_usd }}</span></span>
            </div>
            <div class="cost-row cost-total">
              <span class="cost-label">Total cost</span>
              <span class="cost-value">R{{ costData.total_cost_zar }} <span class="cost-usd">${{ costData.total_cost_usd }}</span></span>
            </div>
            <div class="cost-tokens">
              {{ (costData.prepare.prompt_tokens + costData.simulation.prompt_tokens).toLocaleString() }} in /
              {{ (costData.prepare.completion_tokens + costData.simulation.completion_tokens).toLocaleString() }} out tokens
            </div>
          </div>

          <!-- Agent Context for Web Research -->
          <div v-if="availableAgents.length > 0" class="enrichment-section">
            <div class="preview-header">
              <span class="preview-title">Agent Context for Web Research</span>
              <span class="preview-hint">Select custom agents to shape web research context</span>
            </div>
            
            <div class="profiles-preview">
              <div class="preview-header">
                <span class="preview-title">Available Custom Agents ({{ availableAgents.length }})</span>
                <button 
                  class="action-btn primary" 
                  :disabled="selectedAgentIds.size === 0 || researchRunning"
                  @click="runResearchWithAgentContext"
                >
                  <span v-if="researchRunning">Researching…</span>
                  <span v-else>🔍 Research with Selected Agents</span>
                </button>
              </div>
              
              <div class="agents-cards">
                <div
                  v-for="agent in availableAgents"
                  :key="agent._id"
                  class="agent-card"
                  :class="{ 'selected': selectedAgentIds.has(agent._id) }"
                  @click="toggleAgentSelection(agent._id)"
                >
                  <div class="agent-card-header">
                    <div class="agent-identity">
                      <div class="agent-name">{{ agent.name }}</div>
                      <div class="agent-id">{{ agent.username || agent._id }}</div>
                    </div>
                    <div class="agent-tags">
                      <span class="agent-type">{{ agent.archetype || agent.actor_archetype || 'unknown' }}</span>
                      <span v-if="agent.age" class="pending-bit">{{ agent.age }}y</span>
                      <span v-if="agent.occupation" class="pending-bit">{{ agent.occupation }}</span>
                    </div>
                  </div>
                  
                  <div class="agent-bio">{{ agent.bio || agent.description || 'No bio available' }}</div>
                  
                  <div class="agent-topics">
                    <span v-if="agent.topics && agent.topics.length > 0" v-for="topic in agent.topics.slice(0, 3)" :key="topic" class="topic-tag">{{ topic }}</span>
                    <span v-if="agent.topics && agent.topics.length > 3" class="topic-more">+{{ agent.topics.length - 3 }} more</span>
                  </div>
                </div>
              </div>
              
              <div v-if="selectedAgentIds.size > 0" class="profiles-preview">
                <div class="preview-header">
                  <span class="preview-title">Selected Agents ({{ selectedAgentIds.size }})</span>
                  <button class="action-btn secondary" @click="() => { selectedAgentIds.clear(); updateAgentContext(); }">
                    Clear Selection
                  </button>
                </div>
                
                <div class="agent-list">
                  <div
                    v-for="agent in selectedAgents"
                    :key="agent._id"
                    class="agent-card selected"
                  >
                    <div class="agent-card-header">
                      <div class="agent-identity">
                        <div class="agent-name">{{ agent.name }}</div>
                        <div class="agent-id">{{ agent.username || agent._id }}</div>
                      </div>
                      <div class="agent-tags">
                        <span class="agent-type">{{ agent.archetype || agent.actor_archetype || 'unknown' }}</span>
                        <span v-if="agent.age" class="pending-bit">{{ agent.age }}y</span>
                        <span v-if="agent.occupation" class="pending-bit">{{ agent.occupation }}</span>
                      </div>
                    </div>
                    
                    <div class="agent-bio">{{ agent.bio || agent.description || 'No bio available' }}</div>
                    
                    <div class="agent-topics">
                      <span v-if="agent.topics && agent.topics.length > 0" v-for="topic in agent.topics.slice(0, 3)" :key="topic" class="topic-tag">{{ topic }}</span>
                      <span v-if="agent.topics && agent.topics.length > 3" class="topic-more">+{{ agent.topics.length - 3 }} more</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 03: Generate Dual Platform Simulation Configuration -->
      <div class="step-card" :class="{ 'active': phase === 2, 'completed': phase > 2 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">03</span>
            <span class="step-title">Generate Dual Platform Simulation Configuration</span>
          </div>
          <div class="step-status">
            <span v-if="phase > 2" class="badge success">Completed</span>
            <span v-else-if="phase === 2" class="badge processing">Generating</span>
            <span v-else class="badge pending">Waiting</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/simulation/prepare</p>
          <p class="description">
            LLM Based on simulation requirements and reality seed，Intelligently set world time flow rate、Recommendation algorithm、Active time period for each individual、Speech frequency、Event trigger and other parameters
          </p>
          
          <!-- Config Preview -->
          <div v-if="simulationConfig" class="config-detail-panel">
            <!-- Time Configuration -->
            <div class="config-block">
              <div class="config-grid">
                <div class="config-item">
                  <span class="config-item-label">Simulation Duration</span>
                  <span class="config-item-value">{{ simulationConfig.time_config?.total_simulation_hours || '-' }} hours</span>
                </div>
                <div class="config-item">
                  <span class="config-item-label">Duration per round</span>
                  <span class="config-item-value">{{ simulationConfig.time_config?.minutes_per_round || '-' }} minutes</span>
                </div>
                <div class="config-item">
                  <span class="config-item-label">Total rounds</span>
                  <span class="config-item-value">{{ Math.floor((simulationConfig.time_config?.total_simulation_hours * 60 / simulationConfig.time_config?.minutes_per_round)) || '-' }} rounds</span>
                </div>
                <div class="config-item">
                  <span class="config-item-label">Active per hour</span>
                  <span class="config-item-value">{{ simulationConfig.time_config?.agents_per_hour_min }}-{{ simulationConfig.time_config?.agents_per_hour_max }}</span>
                </div>
              </div>
              <div class="time-periods">
                <div class="period-item">
                  <span class="period-label">Peak period</span>
                  <span class="period-hours">{{ simulationConfig.time_config?.peak_hours?.join(':00, ') }}:00</span>
                  <span class="period-multiplier">×{{ simulationConfig.time_config?.peak_activity_multiplier }}</span>
                </div>
                <div class="period-item">
                  <span class="period-label">Working hours</span>
                  <span class="period-hours">{{ simulationConfig.time_config?.work_hours?.[0] }}:00-{{ simulationConfig.time_config?.work_hours?.slice(-1)[0] }}:00</span>
                  <span class="period-multiplier">×{{ simulationConfig.time_config?.work_activity_multiplier }}</span>
                </div>
                <div class="period-item">
                  <span class="period-label">Morning time period</span>
                  <span class="period-hours">{{ simulationConfig.time_config?.morning_hours?.[0] }}:00-{{ simulationConfig.time_config?.morning_hours?.slice(-1)[0] }}:00</span>
                  <span class="period-multiplier">×{{ simulationConfig.time_config?.morning_activity_multiplier }}</span>
                </div>
                <div class="period-item">
                  <span class="period-label">Valley period</span>
                  <span class="period-hours">{{ simulationConfig.time_config?.off_peak_hours?.[0] }}:00-{{ simulationConfig.time_config?.off_peak_hours?.slice(-1)[0] }}:00</span>
                  <span class="period-multiplier">×{{ simulationConfig.time_config?.off_peak_activity_multiplier }}</span>
                </div>
              </div>
            </div>

            <!-- Agent Configuration -->
            <div class="config-block">
              <div class="config-block-header">
                <span class="config-block-title">Agent Configuration</span>
                <span class="config-block-badge">{{ simulationConfig.agent_configs?.length || 0 }} Number</span>
              </div>
              <div class="agents-cards">
                <div 
                  v-for="agent in simulationConfig.agent_configs" 
                  :key="agent.agent_id" 
                  class="agent-card"
                >
                  <!-- Card header -->
                  <div class="agent-card-header">
                    <div class="agent-identity">
                      <span class="agent-id">Agent {{ agent.agent_id }}</span>
                      <span class="agent-name">{{ agent.entity_name }}</span>
                    </div>
                    <div class="agent-tags">
                      <span class="agent-type">{{ agent.entity_type }}</span>
                      <span class="agent-stance" :class="'stance-' + agent.stance">{{ agent.stance }}</span>
                    </div>
                  </div>
                  
                  <!-- Active timeline -->
                  <div class="agent-timeline">
                    <span class="timeline-label">Active period</span>
                    <div class="mini-timeline">
                      <div 
                        v-for="hour in 24" 
                        :key="hour - 1" 
                        class="timeline-hour"
                        :class="{ 'active': agent.active_hours?.includes(hour - 1) }"
                        :title="`${hour - 1}:00`"
                      ></div>
                    </div>
                    <div class="timeline-marks">
                      <span>0</span>
                      <span>6</span>
                      <span>12</span>
                      <span>18</span>
                      <span>24</span>
                    </div>
                  </div>

                  <!-- Behavior parameters -->
                  <div class="agent-params">
                    <div class="param-group">
                      <div class="param-item">
                        <span class="param-label">Post/time</span>
                        <span class="param-value">{{ agent.posts_per_hour }}</span>
                      </div>
                      <div class="param-item">
                        <span class="param-label">Comment/time</span>
                        <span class="param-value">{{ agent.comments_per_hour }}</span>
                      </div>
                      <div class="param-item">
                        <span class="param-label">Response delay</span>
                        <span class="param-value">{{ agent.response_delay_min }}-{{ agent.response_delay_max }}min</span>
                      </div>
                    </div>
                    <div class="param-group">
                      <div class="param-item">
                        <span class="param-label">Activity level</span>
                        <span class="param-value with-bar">
                          <span class="mini-bar" :style="{ width: (agent.activity_level * 100) + '%' }"></span>
                          {{ (agent.activity_level * 100).toFixed(0) }}%
                        </span>
                      </div>
                      <div class="param-item">
                        <span class="param-label">Sentiment tendency</span>
                        <span class="param-value" :class="agent.sentiment_bias > 0 ? 'positive' : agent.sentiment_bias < 0 ? 'negative' : 'neutral'">
                          {{ agent.sentiment_bias > 0 ? '+' : '' }}{{ agent.sentiment_bias?.toFixed(1) }}
                        </span>
                      </div>
                      <div class="param-item">
                        <span class="param-label">Influence</span>
                        <span class="param-value highlight">{{ agent.influence_weight?.toFixed(1) }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Opinion Space configuration -->
            <div class="config-block">
              <div class="config-block-header">
                <span class="config-block-title">Opinion Space — Agent Behaviour</span>
              </div>
              <div class="platforms-grid">
                <div class="platform-card">
                  <div class="platform-card-header">
                    <span class="platform-name">Opinion Space</span>
                  </div>
                  <div class="platform-params">
                    <div class="param-row">
                      <span class="param-label">Medium</span>
                      <span class="param-value">Generic social medium (AgentSociety)</span>
                    </div>
                    <div class="param-row">
                      <span class="param-label">Actions</span>
                      <span class="param-value">EXPRESS · RESPOND · SEARCH · OBSERVE · IDLE</span>
                    </div>
                    <div class="param-row">
                      <span class="param-label">Agents</span>
                      <span class="param-value">{{ simulationConfig.agent_configs?.length ?? '—' }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- LLM Configuration inference -->
            <div v-if="simulationConfig.generation_reasoning" class="config-block">
              <div class="config-block-header">
                <span class="config-block-title">LLM Configuration inference</span>
              </div>
              <div class="reasoning-content">
                <div 
                  v-for="(reason, idx) in simulationConfig.generation_reasoning.split('|').slice(0, 2)" 
                  :key="idx" 
                  class="reasoning-item"
                >
                  <p class="reasoning-text">{{ reason.trim() }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 04: Initial activation arrangement -->
      <div class="step-card" :class="{ 'active': phase === 3, 'completed': phase > 3 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">04</span>
            <span class="step-title">Initial activation arrangement</span>
          </div>
          <div class="step-status">
            <span v-if="phase > 3" class="badge success">Completed</span>
            <span v-else-if="phase === 3" class="badge processing">Arranging</span>
            <span v-else class="badge pending">Waiting</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/simulation/prepare</p>
          <p class="description">
            Based on narrative direction，Automatically generate initial activation events and trending topics，Guide the initial state of the simulated world
          </p>

          <div v-if="simulationConfig?.event_config" class="orchestration-content">
            <!-- Narrative Direction -->
            <div class="narrative-box">
              <span class="box-label narrative-label">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="special-icon">
                  <path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z" stroke="url(#paint0_linear)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                  <path d="M16.24 7.76L14.12 14.12L7.76 16.24L9.88 9.88L16.24 7.76Z" fill="url(#paint0_linear)" stroke="url(#paint0_linear)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                  <defs>
                    <linearGradient id="paint0_linear" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
                      <stop stop-color="#FF5722"/>
                      <stop offset="1" stop-color="#FF9800"/>
                    </linearGradient>
                  </defs>
                </svg>
                Narrative Guidance Direction
              </span>
              <p class="narrative-text">{{ simulationConfig.event_config.narrative_direction }}</p>
            </div>

            <!-- Trending Topics -->
            <div class="topics-section">
              <span class="box-label">Initial trending topics</span>
              <div class="hot-topics-grid">
                <span v-for="topic in simulationConfig.event_config.hot_topics" :key="topic" class="hot-topic-tag">
                  # {{ topic }}
                </span>
              </div>
            </div>

            <!-- Initial post stream -->
            <div class="initial-posts-section">
              <span class="box-label">Initial activation sequence ({{ simulationConfig.event_config.initial_posts.length }})</span>
              <div class="posts-timeline">
                <div v-for="(post, idx) in simulationConfig.event_config.initial_posts" :key="idx" class="timeline-item">
                  <div class="timeline-marker"></div>
                  <div class="timeline-content">
                    <div class="post-header">
                      <span class="post-role">{{ post.poster_type }}</span>
                      <span class="post-agent-info">
                        <span class="post-id">Agent {{ post.poster_agent_id }}</span>
                        <span class="post-username">@{{ getAgentUsername(post.poster_agent_id) }}</span>
                      </span>
                    </div>
                    <p class="post-text">{{ post.content }}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <!-- Simulation Preset Selection -->
      <div v-if="simulationConfig && phase === 4" class="preset-section">
        <div class="preset-header">
          <span class="section-title">Simulation Preset</span>
          <span class="section-desc">Choose a preset to optimize for speed, balance, or depth</span>
        </div>
        <div class="preset-cards">
          <div 
            class="preset-card" 
            :class="{ 'active': selectedPreset === 'quick' }"
            @click="selectPreset('quick')"
          >
            <div class="preset-icon">⚡</div>
            <div class="preset-name">Quick</div>
            <div class="preset-desc">~2-3 min • Low cost • Fast preview</div>
            <div class="preset-meta">
              <span class="meta-item">Rounds: ~24 (10min/round)</span>
              <span class="meta-item">Agents/round: 10</span>
            </div>
            <div v-if="selectedPreset === 'quick'" class="preset-check">✓</div>
          </div>
          
          <div 
            class="preset-card" 
            :class="{ 'active': selectedPreset === 'balanced' }"
            @click="selectPreset('balanced')"
          >
            <div class="preset-icon">⚖️</div>
            <div class="preset-name">Balanced</div>
            <div class="preset-desc">~5-6 min • Medium cost • Recommended</div>
            <div class="preset-meta">
              <span class="meta-item">Rounds: ~48 (10min/round)</span>
              <span class="meta-item">Agents/round: 15</span>
            </div>
            <div v-if="selectedPreset === 'balanced'" class="preset-check">✓</div>
          </div>
          
          <div 
            class="preset-card" 
            :class="{ 'active': selectedPreset === 'deep' }"
            @click="selectPreset('deep')"
          >
            <div class="preset-icon">🔬</div>
            <div class="preset-name">Deep</div>
            <div class="preset-desc">~12-15 min • Higher cost • Thorough analysis</div>
            <div class="preset-meta">
              <span class="meta-item">Rounds: ~96 (10min/round)</span>
              <span class="meta-item">Agents/round: 30</span>
            </div>
            <div v-if="selectedPreset === 'deep'" class="preset-check">✓</div>
          </div>
        </div>
        <div v-if="selectedPreset" class="preset-summary">
          <span class="summary-text">
            Selected: {{ selectedPreset }} preset — 
            {{ selectedPreset === 'quick' ? 'Fast preview with minimal cost' : selectedPreset === 'balanced' ? 'Optimal balance of speed and quality' : 'Comprehensive simulation with full depth' }}
          </span>
        </div>
      </div>

      <!-- Step 05: Preparation completed -->
      <div class="step-card" :class="{ 'active': phase === 4 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">05</span>
            <span class="step-title">Preparation completed</span>
          </div>
          <div class="step-status">
            <span v-if="phase >= 4" class="badge processing">In progress</span>
            <span v-else class="badge pending">Waiting</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/simulation/start</p>
          <p class="description">Simulation environment preparation completed，Can start running simulation</p>
          
          <!-- Simulation Rounds Configuration - Only show after configuration generation is completed and rounds are calculated -->
          <div v-if="simulationConfig && (selectedPreset || autoGeneratedRounds)" class="rounds-config-section">
            <div class="rounds-header">
              <div class="header-left">
                <span class="section-title">Simulation Rounds Setting</span>
                <span v-if="selectedPreset" class="section-desc">
                  Preset "{{ selectedPreset }}" — {{ customMaxRounds }} rounds ({{ 
                  selectedPreset === 'quick' ? '~3 min' : selectedPreset === 'balanced' ? '~8 min' : '~20 min' }})
                </span>
                <span v-else-if="useCustomRounds" class="section-desc">
                  Custom setting — {{ customMaxRounds }} rounds
                </span>
                <span v-else class="section-desc">Automatically plan and infer reality 
                  <span class="desc-highlight">{{ simulationConfig?.time_config?.total_simulation_hours || '-' }}</span> hours，Each round represents reality 
                  <span class="desc-highlight">{{ simulationConfig?.time_config?.minutes_per_round || '-' }}</span> minutes time elapsed</span>
              </div>
              
              <label v-if="!selectedPreset" class="switch-control">
                <input type="checkbox" v-model="useCustomRounds">
                <span class="switch-track"></span>
                <span class="switch-label">Custom</span>
              </label>
            </div>
             
             <Transition name="fade" mode="out-in">
               <div v-if="useCustomRounds" class="rounds-content custom" key="custom">
                 <div class="slider-display">
                   <div class="slider-main-value">
                     <span class="val-num">{{ customMaxRounds }}</span>
                     <span class="val-unit">rounds</span>
                   </div>
                   <div class="slider-meta-info">
                     <span>IfAgentScale is100：Estimated time approximately {{ Math.round(customMaxRounds * 0.6) }} minutes</span>
                   </div>
                 </div>

                 <div class="range-wrapper">
                   <input 
                     type="range" 
                     v-model.number="customMaxRounds" 
                     min="10" 
                     :max="sliderMax"
                     step="5"
                     class="minimal-slider"
                     :style="{ '--percent': sliderPercent + '%' }"
                   />
                   <div class="range-marks">
                     <span>10</span>
                     <span 
                       class="mark-recommend" 
                       :class="{ active: customMaxRounds === 40 }"
                       @click="customMaxRounds = 40"
                       :style="{ position: 'absolute', left: recommendPos + '%' }"
                     >40 (Recommendation)</span>
                     <span>{{ sliderMax }}</span>
                   </div>
                 </div>
               </div>
               
               <div v-else class="rounds-content auto" key="auto">
                 <div class="auto-info-card">
                   <div class="auto-value">
                     <span class="val-num">{{ autoGeneratedRounds }}</span>
                     <span class="val-unit">rounds</span>
                   </div>
                   <div class="auto-content">
                     <div class="auto-meta-row">
                       <span class="duration-badge">
                         <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                           <circle cx="12" cy="12" r="10"></circle>
                           <polyline points="12 6 12 12 16 14"></polyline>
                         </svg>
                         IfAgentScale is100：Estimated time {{ Math.round(autoGeneratedRounds * 0.6) }} minutes
                       </span>
                     </div>
                     <div class="auto-desc">
                       <p class="highlight-tip" @click="useCustomRounds = true">If first run，Strongly recommend switching to'Custom mode'Reduce simulation rounds，to quickly preview effects and reduce error risk ➝</p>
                     </div>
                   </div>
                 </div>
               </div>
             </Transition>
           </div>
           </div>
           
          <div class="action-group dual">
            <button 
              class="action-btn secondary"
              @click="$emit('go-back')"
            >
              ← Return graph construction
            </button>
            <button 
              class="action-btn primary"
              :disabled="phase < 4"
              @click="handleStartSimulation"
            >
              Start dual world parallel simulation ➝
            </button>
          </div>

        </div>
        </div>

       <!-- Profile Detail Modal -->
    <Transition name="modal">
      <div v-if="selectedProfile" class="profile-modal-overlay" @click.self="selectedProfile = null">
        <div class="profile-modal">
          <div class="modal-header">
          <div class="modal-header-info">
            <div class="modal-name-row">
              <span class="modal-realname">{{ selectedProfile.username }}</span>
              <span class="modal-username">@{{ selectedProfile.name }}</span>
            </div>
            <span class="modal-profession">{{ selectedProfile.profession }}</span>
          </div>
          <button class="close-btn" @click="selectedProfile = null">×</button>
        </div>
        
        <div class="modal-body">
          <!-- Basic information -->
          <div class="modal-info-grid">
            <div class="info-item">
              <span class="info-label">Age manifestation</span>
              <span class="info-value">{{ selectedProfile.age || '-' }} years old</span>
            </div>
            <div class="info-item">
              <span class="info-label">Gender manifestation</span>
              <span class="info-value">{{ { male: 'Male', female: 'Female', other: 'Other' }[selectedProfile.gender] || selectedProfile.gender }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">Country/Region</span>
              <span class="info-value">{{ selectedProfile.country || '-' }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">Event manifestationMBTI</span>
              <span class="info-value mbti">{{ selectedProfile.mbti || '-' }}</span>
            </div>
          </div>

          <!-- Introduction -->
          <div class="modal-section">
            <span class="section-label">Persona Introduction</span>
            <p class="section-bio">{{ selectedProfile.bio || 'No introduction available' }}</p>
          </div>

          <!-- Followed Topics -->
          <div class="modal-section" v-if="selectedProfile.interested_topics?.length">
            <span class="section-label">Reality Seed Related Topics</span>
            <div class="topics-grid">
              <span 
                v-for="topic in selectedProfile.interested_topics" 
                :key="topic" 
                class="topic-item"
              >{{ topic }}</span>
            </div>
          </div>

          <!-- Detailed Persona -->
          <div class="modal-section" v-if="selectedProfile.persona">
            <span class="section-label">Detailed Persona Background</span>
            
            <!-- Persona Dimension Overview -->
            <div class="persona-dimensions">
              <div class="dimension-card">
                <span class="dim-title">Event panoramic experience</span>
                <span class="dim-desc">Complete behavior trajectory in this event</span>
              </div>
              <div class="dimension-card">
                <span class="dim-title">Behavior pattern profiling</span>
                <span class="dim-desc">Experience summary and action style preference</span>
              </div>
              <div class="dimension-card">
                <span class="dim-title">Unique memory imprints</span>
                <span class="dim-desc">Memory formed based on reality seed</span>
              </div>
              <div class="dimension-card">
                <span class="dim-title">Social Relationship Network</span>
                <span class="dim-desc">Individual Links and Interaction Graph</span>
              </div>
            </div>

            <div class="persona-content">
              <p class="section-persona">{{ selectedProfile.persona }}</p>
            </div>
          </div>
        </div>
      </div>
      </div>
    </Transition>

    <!-- Bottom Info / Logs -->
    <div class="system-logs">
      <div class="log-header">
        <span class="log-title">SYSTEM DASHBOARD</span>
        <span class="log-id">{{ simulationId || 'NO_SIMULATION' }}</span>
      </div>
      <div class="log-content" ref="logContent">
        <div class="log-line" v-for="(log, idx) in systemLogs" :key="idx">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-msg">{{ log.msg }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import {
  prepareSimulation,
  getPrepareStatus,
  getSimulationProfilesRealtime,
  getSimulationConfig,
  getSimulationConfigRealtime,
  getEnrichmentData,
  getSimulationCost,
  rerunResearch as rerunResearchApi
} from '../api/simulation'

const props = defineProps({
  simulationId: String,  // Passed from parent component
  projectData: Object,
  graphData: Object,
  systemLogs: Array,
  customAgents: { type: Array, default: () => [] },
  customAgentsEnabled: { type: Boolean, default: false },
  customAgentsOnly: { type: Boolean, default: false },
  mode: { type: String, default: 'policy' },
  // True only when the user pinned the mode on the toggle. When false the backend
  // auto-detects mode from the seed and we surface the result in a banner.
  modeIsManual: { type: Boolean, default: false },
  // Background graph-build phase (-1..2). <2 means the document graph is still
  // building; personas are best generated once it's grounded (phase 2).
  currentPhase: { type: Number, default: 2 }
})

const emit = defineEmits(['go-back', 'next-step', 'add-log', 'update-status'])

// State
const phase = ref(0) // 0: Initialization, 1: Generate Personas, 2: Generate Configuration, 3: Complete
const taskId = ref(null)
const prepareProgress = ref(0)
const currentStage = ref('')
const progressMessage = ref('')
const profiles = ref([])
const entityTypes = ref([])
const expectedTotal = ref(null)
// Mode detection result echoed by /prepare — drives the detection banner.
const resolvedMode = ref(null)
const resolvedConverged = ref(false)
const resolvedSecondaryLens = ref(null)
const resolvedModeIsManual = ref(false)
const enrichmentData = ref({})
const expandedEnrichment = ref(new Set())
const costData = ref(null)
const researchRunning = ref(false)
const researchCurrentArchetype = ref('')
const researchError = ref('')

const researchCharCount = computed(() => {
  return Object.values(enrichmentData.value).reduce((sum, t) => sum + (t?.length || 0), 0)
})

const researchSources = computed(() => {
  const sourceKeywords = ['HRW', 'SAPS', 'StatsSA', 'World Bank', 'Amnesty', 'News24', 'Daily Maverick', 'GroundUp', 'Mail & Guardian', 'Business Day', 'SABC', 'eNCA', 'TimesLIVE', 'IOL', 'Reuters', 'BBC', 'gov.za', 'Wikipedia']
  const allText = Object.values(enrichmentData.value).join(' ')
  const found = new Set()
  const lower = allText.toLowerCase()
  for (const src of sourceKeywords) {
    if (lower.includes(src.toLowerCase())) found.add(src)
  }
  return [...found]
})
const simulationConfig = ref(null)
const selectedProfile = ref(null)
const showProfilesDetail = ref(true)

// Log deduplication：Record key information from last output
let lastLoggedMessage = ''
let lastLoggedProfileCount = 0
let lastLoggedConfigStage = ''

// Simulation Rounds Configuration
const selectedPreset = ref('balanced') // Default to balanced preset
const useCustomRounds = ref(false) // DefaultUse auto-configured rounds
const customMaxRounds = ref(40)   // Default recommendation40rounds

// Watch stage to update phase
watch(currentStage, (newStage) => {
  if (newStage === 'GenerateAgentPersona' || newStage === 'generating_profiles') {
    phase.value = 1
  } else if (newStage === 'Generate Simulation Configuration' || newStage === 'generating_config') {
    phase.value = 2
    // Enter configuration generation phase，Start polling configuration
    if (!configTimer) {
      addLog('Start generating dual platform simulation configuration...')
      startConfigPolling()
    }
  } else if (newStage === 'Prepare simulation script' || newStage === 'copying_scripts') {
    phase.value = 2 // Still in configuration phase
  }
})

// Calculate auto-generated rounds from configuration（Do not use hardcoded default values）
const autoGeneratedRounds = computed(() => {
  if (!simulationConfig.value?.time_config) {
    return null // Return when configuration is not generated null
  }
  const totalHours = simulationConfig.value.time_config.total_simulation_hours
  const minutesPerRound = simulationConfig.value.time_config.minutes_per_round
  if (!totalHours || !minutesPerRound) {
    return null // Return when configuration data is incomplete null
  }
  const calculatedRounds = Math.floor((totalHours * 60) / minutesPerRound)
  // Ensure max rounds no less than40（Recommendation value），Avoid slider range anomalies
  return Math.max(calculatedRounds, 40)
})

// Slider computed properties to simplify template expressions
const sliderMax = computed(() => {
  if (useCustomRounds.value) {
    return customMaxRounds.value * 2
  }
  return autoGeneratedRounds.value || 100
})

const sliderPercent = computed(() => {
  const max = sliderMax.value
  if (!max || max <= 10) return 0
  return ((customMaxRounds.value - 10) / (max - 10)) * 100
})

const recommendPos = computed(() => {
  const max = sliderMax.value
  if (!max || max <= 10) return 0
  return ((40 - 10) / (max - 10)) * 100
})

// Simulation Preset
const selectPreset = (preset) => {
  // Always select (no toggle off) - standard preset behavior
  selectedPreset.value = preset
  
  // Update max rounds based on preset
  if (preset === 'quick') {
    customMaxRounds.value = 20
  } else if (preset === 'balanced') {
    customMaxRounds.value = 50
  } else if (preset === 'deep') {
    customMaxRounds.value = 100
  }
  
  // Update displayed simulationConfig values so Step 05 shows correct values
  // Optimized for API rate limits: 10 min per round for faster, real-time simulation
  if (simulationConfig.value && simulationConfig.value.time_config) {
    const overrides = {
      'quick':   { total_simulation_hours: 4, minutes_per_round: 10 },   // 24 rounds
      'balanced': { total_simulation_hours: 8, minutes_per_round: 10 },  // 48 rounds
      'deep':     { total_simulation_hours: 16, minutes_per_round: 10 }, // 96 rounds
    }
    if (overrides[preset]) {
      simulationConfig.value = {
        ...simulationConfig.value,
        time_config: {
          ...simulationConfig.value.time_config,
          ...overrides[preset]
        }
      }
      addLog(`Preset '${preset}' applied: ${overrides[preset].total_simulation_hours}h / ${overrides[preset].minutes_per_round}min per round`)
    }
  }
}

// Polling timer
let pollTimer = null
let profilesTimer = null
let configTimer = null

// Computed
const displayProfiles = computed(() => {
  if (showProfilesDetail.value) {
    return profiles.value
  }
  return profiles.value.slice(0, 6)
})

// Based onagent_idGet correspondingusername
const getAgentUsername = (agentId) => {
  if (profiles.value && profiles.value.length > agentId && agentId >= 0) {
    const profile = profiles.value[agentId]
    return profile?.username || `agent_${agentId}`
  }
  return `agent_${agentId}`
}

// Calculate total related topics for all personas
const totalTopicsCount = computed(() => {
  return profiles.value.reduce((sum, p) => {
    return sum + (p.interested_topics?.length || 0)
  }, 0)
})

const toggleEnrichment = (archetype) => {
  const s = new Set(expandedEnrichment.value)
  if (s.has(archetype)) s.delete(archetype)
  else s.add(archetype)
  expandedEnrichment.value = s
}

const rerunResearch = async (agentContext = null) => {
  if (!props.simulationId || researchRunning.value) return
  researchRunning.value = true
  researchError.value = ''
  researchCurrentArchetype.value = ''
  emit('add-log', agentContext ? '🔍 Re-running deep web research with custom agent context...' : '🔍 Re-running deep web research...')
  try {
    const res = await rerunResearchApi(props.simulationId, agentContext)
    if (res.success) {
      enrichmentData.value = res.data.enrichment || {}
      emit('add-log', `✓ Research complete — ${res.data.enriched_count} archetypes enriched`)
      if (agentContext && agentContext.agents && agentContext.agents.length > 0) {
        emit('add-log', `  └─ Research shaped by ${agentContext.agents.length} custom agent(s): ${agentContext.agents.map(a => a.name).join(', ')}`)
      }
    } else {
      researchError.value = res.error || 'Research failed'
      emit('add-log', `✗ Research failed: ${researchError.value}`)
    }
  } catch (e) {
    researchError.value = e.message || 'Network error'
    emit('add-log', `✗ Research error: ${researchError.value}`)
  } finally {
    researchRunning.value = false
  }
}

// Agent context for web research
const agentContextForResearch = ref(null)
const selectedAgentIds = ref(new Set())

const availableAgents = computed(() => {
  return props.customAgents.filter(agent => agent && agent._id)
})

const selectedAgents = computed(() => {
  return availableAgents.value.filter(agent => selectedAgentIds.value.has(agent._id))
})

const updateAgentContext = () => {
  if (selectedAgentIds.value.size > 0) {
    agentContextForResearch.value = {
      agents: selectedAgents.value.map(agent => ({
        name: agent.name,
        archetype: agent.archetype || agent.actor_archetype || '',
        description: agent.description || agent.bio || '',
        background: agent.background_story || agent.background || ''
      })),
      context_focus: selectedAgents.value.map(a => a.name).join(', ')
    }
  } else {
    agentContextForResearch.value = null
  }
}

const toggleAgentSelection = (agentId) => {
  if (selectedAgentIds.value.has(agentId)) {
    selectedAgentIds.value.delete(agentId)
  } else {
    selectedAgentIds.value.add(agentId)
  }
  updateAgentContext()
}

const runResearchWithAgentContext = () => {
  rerunResearch(agentContextForResearch.value)
}

// Methods
const addLog = (msg) => {
  emit('add-log', msg)
}

// ProcessStart simulationButton click
const handleStartSimulation = () => {
  // Build parameters to pass to parent component
  const params = {}
  
  // Add preset if selected
  if (selectedPreset.value) {
    params.preset = selectedPreset.value
    addLog(`Start simulation with ${selectedPreset.value} preset`)
  }
  
  if (useCustomRounds.value) {
    // User custom rounds，Pass max_rounds Parameter
    params.maxRounds = customMaxRounds.value
    addLog(`Start simulation，Custom rounds: ${customMaxRounds.value} rounds`)
  } else {
    // User chose to keep auto-configured rounds，Do not pass max_rounds Parameter
    addLog(`Start simulation，Use auto-configured rounds: ${autoGeneratedRounds.value} rounds`)
  }
  
  emit('next-step', params)
}

const truncateBio = (bio) => {
  if (bio.length > 80) {
    return bio.substring(0, 80) + '...'
  }
  return bio
}

const selectProfile = (profile) => {
  selectedProfile.value = profile
}

// --- Detection banner ---
// Show only after the backend has resolved a mode and only when it auto-detected
// (no banner needed when the user already pinned the mode themselves).
const showModeBanner = computed(() => !!resolvedMode.value && !resolvedModeIsManual.value)
const detectedModeLabel = computed(() =>
  resolvedMode.value === 'product' ? 'Product market test' : 'Policy test'
)
const otherModeLabel = computed(() =>
  resolvedMode.value === 'product' ? 'Policy' : 'Product'
)
const convergedLensLabel = computed(() =>
  resolvedSecondaryLens.value === 'product' ? 'affordability lens' : 'civic lens'
)
// Flip to the other mode and pin it (force-regenerate via override).
const switchDetectedMode = async () => {
  const other = resolvedMode.value === 'product' ? 'policy' : 'product'
  addLog(`Overriding detected mode → ${other}`)
  await startPrepareSimulation({ mode: other })
}

// Automatically start preparing simulation.
// `override` (optional): { mode } pins a user-chosen mode and forces a regenerate —
// used by the detection banner's "Switch to ..." button.
const startPrepareSimulation = async (override = null) => {
  if (!props.simulationId) {
    addLog('Error：Missing simulationId')
    emit('update-status', 'error')
    return
  }

  // Mark step 1 completed，Start step 2
  phase.value = 1
  addLog(`Simulation instance created: ${props.simulationId}`)
  addLog('Preparing simulation environment...')
  emit('update-status', 'processing')

  try {
    // When the user pinned a mode (toggle or override) send it as manual so the
    // backend skips auto-detection. Otherwise send nothing for mode and let the
    // backend detect from the seed.
    const isManual = override ? true : props.modeIsManual
    const chosenMode = override ? override.mode : props.mode
    const payload = {
      simulation_id: props.simulationId,
      parallel_profile_count: 5,
      mode_is_manual: isManual,
    }
    if (isManual && chosenMode) {
      payload.mode = chosenMode
    }
    if (override) {
      payload.force_regenerate = true
    }
    if (isManual && chosenMode === 'product') {
      addLog('Product mode: generating a South African market to stress-test the product idea')
    }
    if (props.customAgentsEnabled && props.customAgents.length > 0) {
      payload.custom_agents = props.customAgents
      if (props.customAgentsOnly) {
        payload.custom_agents_only = true
        addLog(`Custom-only mode: running on ${props.customAgents.length} custom agents (auto-population skipped)`)
      } else {
        addLog(`Injecting ${props.customAgents.length} custom agent profiles into simulation`)
      }
    }
    const res = await prepareSimulation(payload)
    
    if (res.success && res.data) {
      // Capture the mode the backend resolved (detected or pinned) so we can show
      // the detection banner with a one-click override.
      if (res.data.mode) {
        resolvedMode.value = res.data.mode
        resolvedConverged.value = !!res.data.converged
        resolvedSecondaryLens.value = res.data.secondary_lens || null
        resolvedModeIsManual.value = !!res.data.mode_is_manual
        const label = res.data.mode === 'product' ? 'Product market test' : 'Policy test'
        if (res.data.mode_is_manual) {
          addLog(`Mode pinned: ${label}`)
        } else {
          addLog(`Detected mode: ${label}${res.data.converged ? ' (+ ' + (res.data.secondary_lens === 'product' ? 'affordability' : 'civic') + ' lens)' : ''}`)
        }
      }

      if (res.data.already_prepared) {
        addLog('Detected existing completed preparation work，Use directly')
        await loadPreparedData()
        return
      }

      taskId.value = res.data.task_id
      addLog(`Preparation task started`)
      addLog(`  └─ Task ID: ${res.data.task_id}`)
      
      // Set immediatelyExpected Agent Total（FromprepareInterface return value retrieval）
      if (res.data.expected_entities_count) {
        expectedTotal.value = res.data.expected_entities_count
        addLog(`FromNeo4jGraph read ${res.data.expected_entities_count} entities`)
        if (res.data.entity_types && res.data.entity_types.length > 0) {
          addLog(`  └─ Entity Type: ${res.data.entity_types.join(', ')}`)
        }
      }
      
      addLog('Start polling preparation progress...')
      // Start polling progress
      startPolling()
      // Start real-time fetching Profiles
      startProfilesPolling()
    } else {
      addLog(`Preparation failed: ${res.error || 'Unknown error'}`)
      emit('update-status', 'error')
    }
  } catch (err) {
    addLog(`Preparation exception: ${err.message}`)
    emit('update-status', 'error')
  }
}

const startPolling = () => {
  pollTimer = setInterval(pollPrepareStatus, 2000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const startProfilesPolling = () => {
  profilesTimer = setInterval(fetchProfilesRealtime, 3000)
}

const stopProfilesPolling = () => {
  if (profilesTimer) {
    clearInterval(profilesTimer)
    profilesTimer = null
  }
}

const pollPrepareStatus = async () => {
  if (!taskId.value && !props.simulationId) return
  
  try {
    const res = await getPrepareStatus({
      task_id: taskId.value,
      simulation_id: props.simulationId
    })
    
    if (res.success && res.data) {
      const data = res.data
      
      // Update progress
      prepareProgress.value = data.progress || 0
      progressMessage.value = data.message || ''
      
      // Parse phase information and output detailed log
      if (data.progress_detail) {
        currentStage.value = data.progress_detail.current_stage_name || ''
        
        // Output detailed progress log（Avoid duplication）
        const detail = data.progress_detail
        const logKey = `${detail.current_stage}-${detail.current_item}-${detail.total_items}`
        if (logKey !== lastLoggedMessage && detail.item_description) {
          lastLoggedMessage = logKey
          const stageInfo = `[${detail.stage_index}/${detail.total_stages}]`
          if (detail.total_items > 0) {
            addLog(`${stageInfo} ${detail.current_stage_name}: ${detail.current_item}/${detail.total_items} - ${detail.item_description}`)
          } else {
            addLog(`${stageInfo} ${detail.current_stage_name}: ${detail.item_description}`)
          }
        }
      } else if (data.message) {
        // Extract phase from message
        const match = data.message.match(/\[(\d+)\/(\d+)\]\s*([^:]+)/)
        if (match) {
          currentStage.value = match[3].trim()
        }
        // Output message log（Avoid duplication）
        if (data.message !== lastLoggedMessage) {
          lastLoggedMessage = data.message
          addLog(data.message)
        }
      }
      
      // Check if completed
      if (data.status === 'completed' || data.status === 'ready' || data.already_prepared) {
        addLog('✓ Preparation work completed')
        stopPolling()
        stopProfilesPolling()
        await loadPreparedData()
      } else if (data.status === 'failed') {
        addLog(`✗ Preparation failed: ${data.error || 'Unknown error'}`)
        stopPolling()
        stopProfilesPolling()
      }
    }
  } catch (err) {
    console.warn('Polling status failed:', err)
  }
}

const fetchProfilesRealtime = async () => {
  if (!props.simulationId) return
  
  try {
    const res = await getSimulationProfilesRealtime(props.simulationId, 'opinion_space')
    
    if (res.success && res.data) {
      const prevCount = profiles.value.length
      profiles.value = res.data.profiles || []
      // Only when API Update only when returning valid values，Avoid overwriting existing valid values
      if (res.data.total_expected) {
        expectedTotal.value = res.data.total_expected
      }
      
      // Extract entity type
      const types = new Set()
      profiles.value.forEach(p => {
        if (p.entity_type) types.add(p.entity_type)
      })
      entityTypes.value = Array.from(types)
      
      // Output Profile Generation progress log（Only when quantity changes）
      const currentCount = profiles.value.length
      if (currentCount > 0 && currentCount !== lastLoggedProfileCount) {
        lastLoggedProfileCount = currentCount
        const total = expectedTotal.value || '?'
        const latestProfile = profiles.value[currentCount - 1]
        const profileName = latestProfile?.name || latestProfile?.username || `Agent_${currentCount}`
        if (currentCount === 1) {
          addLog(`Start generationAgentPersona...`)
        }
        addLog(`→ AgentPersona ${currentCount}/${total}: ${profileName} (${latestProfile?.profession || 'Unknown Profession'})`)
        
        // If all generation is completed
        if (expectedTotal.value && currentCount >= expectedTotal.value) {
          addLog(`✓ All (All) ${currentCount} NumberAgentPersona generation completed`)
        }
      }
    }
  } catch (err) {
    console.warn('Get Profiles Failed:', err)
  }
}

// ConfigurationroundsInquiry
const startConfigPolling = () => {
  configTimer = setInterval(fetchConfigRealtime, 2000)
}

const stopConfigPolling = () => {
  if (configTimer) {
    clearInterval(configTimer)
    configTimer = null
  }
}

const fetchConfigRealtime = async () => {
  if (!props.simulationId) return
  
  try {
    const res = await getSimulationConfigRealtime(props.simulationId)
    
    if (res.success && res.data) {
      const data = res.data

      // Stop immediately if preparation failed — don't poll forever
      if (data.failed || data.status === 'failed') {
        stopConfigPolling()
        const msg = data.error || 'Preparation failed (unknown error)'
        addLog(`✗ Preparation failed: ${msg}`)
        emit('update-status', 'error')
        return
      }

      // Output configuration generation phase log（Avoid duplication）
      if (data.generation_stage && data.generation_stage !== lastLoggedConfigStage) {
        lastLoggedConfigStage = data.generation_stage
        if (data.generation_stage === 'generating_profiles') {
          addLog('CurrentlyGenerateAgentPersona Configuration...')
        } else if (data.generation_stage === 'generating_config') {
          addLog('CallingLLMGenerate Simulation ConfigurationParameter...')
        }
      }

      // If configuration is generated
      if (data.config_generated && data.config) {
        simulationConfig.value = data.config
        addLog('✓ Simulation configuration generation completed')
        
        // Show detailed configuration summary
        if (data.summary) {
          addLog(`  ├─ AgentQuantity: ${data.summary.total_agents}Number`)
          addLog(`  ├─ Simulation Duration: ${data.summary.simulation_hours}hours`)
          addLog(`  ├─ Initial posts: ${data.summary.initial_posts_count}items`)
          addLog(`  ├─ Trending Topics: ${data.summary.hot_topics_count}Number`)
          addLog(`  └─ Platform: Opinion Space ✓`)
        }
        
        // Show time configuration details
        if (data.config.time_config) {
          const tc = data.config.time_config
          addLog(`Time Configuration: Per round${tc.minutes_per_round}minutes, Total${Math.floor((tc.total_simulation_hours * 60) / tc.minutes_per_round)}rounds`)
        }
        
        // Show event configuration
        if (data.config.event_config?.narrative_direction) {
          const narrative = data.config.event_config.narrative_direction
          addLog(`Narrative Direction: ${narrative.length > 50 ? narrative.substring(0, 50) + '...' : narrative}`)
        }
        
        stopConfigPolling()
        phase.value = 4
        addLog('✓ Env Setup Completed，Can start simulation')
        emit('update-status', 'completed')
      }
    }
  } catch (err) {
    console.warn('Get Config Failed:', err)
  }
}

const loadPreparedData = async () => {
  phase.value = 2
  addLog('Loading existing configuration data...')

  // Get one last time Profiles
  await fetchProfilesRealtime()
  addLog(`Loaded ${profiles.value.length} NumberAgentPersona`)

  // Fetch deep-research enrichment (silently, no error if not available)
  try {
    const enrichRes = await getEnrichmentData(props.simulationId)
    if (enrichRes.data && Object.keys(enrichRes.data).length > 0) {
      enrichmentData.value = enrichRes.data
      addLog(`✓ Research context loaded for ${Object.keys(enrichRes.data).length} archetypes`)
    }
  } catch (_) { /* enrichment is optional */ }

  // Fetch cost summary (silently)
  try {
    const costRes = await getSimulationCost(props.simulationId)
    if (costRes.data?.success) {
      costData.value = costRes.data.data
    }
  } catch (_) { /* cost is optional */ }

  // Get configuration（Use real-time interface）
  try {
    const res = await getSimulationConfigRealtime(props.simulationId)
    if (res.success && res.data) {
      if (res.data.config_generated && res.data.config) {
        simulationConfig.value = res.data.config
        addLog('✓ Simulation configuration loaded successfully')
        
        // Show detailed configuration summary
        if (res.data.summary) {
          addLog(`  ├─ AgentQuantity: ${res.data.summary.total_agents}Number`)
          addLog(`  ├─ Simulation Duration: ${res.data.summary.simulation_hours}hours`)
          addLog(`  └─ Initial posts: ${res.data.summary.initial_posts_count}items`)
        }
        
        addLog('✓ Env Setup Completed，Can start simulation')
        phase.value = 4
        emit('update-status', 'completed')
      } else {
        // Configuration not yet generated，Start polling
        addLog('Configuration generating，Start polling wait...')
        startConfigPolling()
      }
    }
  } catch (err) {
    addLog(`Failed to load configuration: ${err.message}`)
    emit('update-status', 'error')
  }
}

// Scroll log to bottom
const logContent = ref(null)
watch(() => props.systemLogs?.length, () => {
  nextTick(() => {
    if (logContent.value) {
      logContent.value.scrollTop = logContent.value.scrollHeight
    }
  })
})

onMounted(() => {
  // Automatically start preparation process
  if (props.simulationId) {
    addLog('Step2 Env Setup Initialization')
    startPrepareSimulation()
  }
})

// Also restart when simulationId changes (route navigation without remount)
watch(() => props.simulationId, (newId, oldId) => {
  if (newId && newId !== oldId) {
    addLog(`Simulation changed: ${oldId} → ${newId}, restarting preparation`)
    stopPolling()
    stopProfilesPolling()
    stopConfigPolling()
    phase.value = 0
    taskId.value = null
    prepareProgress.value = 0
    currentStage.value = ''
    progressMessage.value = ''
    profiles.value = []
    entityTypes.value = []
    expectedTotal.value = null
    enrichmentData.value = {}
    expandedEnrichment.value = new Set()
    costData.value = null
    researchRunning.value = false
    researchCurrentArchetype.value = ''
    researchError.value = ''
    simulationConfig.value = null
    selectedPreset.value = 'balanced'
    useCustomRounds.value = false
    customMaxRounds.value = 40
    lastLoggedMessage = ''
    lastLoggedProfileCount = 0
    lastLoggedConfigStage = ''
    startPrepareSimulation()
  }
})

onUnmounted(() => {
  stopPolling()
  stopProfilesPolling()
  stopConfigPolling()
})
</script>

<style scoped>
.grounding-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 16px;
  padding: 10px 14px;
  background: #F0F9F4;
  border: 1px solid #C8E6D2;
  border-radius: 8px;
  color: #1E9E5A;
  font-size: 13px;
  font-weight: 500;
}

.grounding-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid #C8E6D2;
  border-top-color: #1E9E5A;
  border-radius: 50%;
  animation: grounding-spin 0.8s linear infinite;
  flex-shrink: 0;
}

@keyframes grounding-spin { to { transform: rotate(360deg); } }

.mode-detect-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0 0 16px;
  padding: 10px 14px;
  background: #F0F9F4;
  border: 1px solid #C8E6D2;
  border-radius: 8px;
  color: #1E9E5A;
  font-size: 13px;
}

.mode-detect-text { flex: 1; }
.mode-detect-text strong { font-weight: 600; }

.mode-detect-badge {
  margin-left: 8px;
  padding: 1px 8px;
  border: 1px solid #C8E6D2;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}

.mode-detect-btn {
  background: #1E9E5A;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  flex-shrink: 0;
}

.mode-detect-btn:hover { background: #178048; }

.env-setup-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #FAFAFA;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

.scroll-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* Step Card */
.step-card {
  background: #FFF;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  border: 1px solid #EAEAEA;
  transition: all 0.3s ease;
  position: relative;
}

.step-card.active {
  border-color: #FF5722;
  box-shadow: 0 4px 12px rgba(255, 87, 34, 0.08);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.step-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-size: 20px;
  font-weight: 700;
  color: #E0E0E0;
}

.step-card.active .step-num,
.step-card.completed .step-num {
  color: #000;
}

.step-title {
  font-weight: 600;
  font-size: 14px;
  letter-spacing: 0.5px;
}

.badge {
  font-size: 10px;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 600;
  text-transform: uppercase;
}

.badge.success { background: #E8F5E9; color: #2E7D32; }
.badge.processing { background: #FF5722; color: #FFF; }
.badge.pending { background: #F5F5F5; color: #999; }
.badge.accent { background: #E3F2FD; color: #1565C0; }

.card-content {
  /* No extra padding - uses step-card's padding */
}

.api-note {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #999;
  margin-bottom: 8px;
}

.description {
  font-size: 12px;
  color: #666;
  line-height: 1.5;
  margin-bottom: 16px;
}

/* Action Section */
.action-section {
  margin-top: 16px;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  font-size: 14px;
  font-weight: 600;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-btn.primary {
  background: #000;
  color: #FFF;
}

.action-btn.primary:hover:not(:disabled) {
  opacity: 0.8;
}

.action-btn.secondary {
  background: #F5F5F5;
  color: #333;
}

.action-btn.secondary:hover:not(:disabled) {
  background: #E5E5E5;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-group {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

.action-group.dual {
  display: grid;
  grid-template-columns: 1fr 1fr;
}

.action-group.dual .action-btn {
  width: 100%;
}

/* Info Card */
.info-card {
  background: #F5F5F5;
  border-radius: 6px;
  padding: 16px;
  margin-top: 16px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px dashed #E0E0E0;
}

.info-row:last-child {
  border-bottom: none;
}

.info-label {
  font-size: 12px;
  color: #666;
}

.info-value {
  font-size: 13px;
  font-weight: 500;
}

.info-value.mono {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
}

/* Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  background: #F9F9F9;
  padding: 16px;
  border-radius: 6px;
}

.stat-card {
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 20px;
  font-weight: 700;
  color: #000;
  font-family: 'JetBrains Mono', monospace;
}

.stat-label {
  font-size: 9px;
  color: #999;
  text-transform: uppercase;
  margin-top: 4px;
  display: block;
}

/* Profiles Preview */
.profiles-preview {
  margin-top: 20px;
  border-top: 1px solid #E5E5E5;
  padding-top: 16px;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.preview-title {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.profiles-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  max-height: 320px;
  overflow-y: auto;
  padding-right: 4px;
}

.profiles-list::-webkit-scrollbar {
  width: 4px;
}

.profiles-list::-webkit-scrollbar-thumb {
  background: #DDD;
  border-radius: 2px;
}

.profiles-list::-webkit-scrollbar-thumb:hover {
  background: #CCC;
}

.profile-card {
  background: #FAFAFA;
  border: 1px solid #E5E5E5;
  border-radius: 6px;
  padding: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.profile-card:hover {
  border-color: #999;
  background: #FFF;
}

.profile-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;
}

.profile-realname {
  font-size: 14px;
  font-weight: 700;
  color: #000;
}

.profile-username {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #999;
}

.profile-meta {
  margin-bottom: 8px;
}

.profile-profession {
  font-size: 11px;
  color: #666;
  background: #F0F0F0;
  padding: 2px 8px;
  border-radius: 3px;
}

.profile-bio {
  font-size: 12px;
  color: #444;
  line-height: 1.6;
  margin: 0 0 10px 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.profile-topics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.topic-tag {
  font-size: 10px;
  color: #1565C0;
  background: #E3F2FD;
  padding: 2px 8px;
  border-radius: 10px;
}

.topic-more {
  font-size: 10px;
  color: #999;
  padding: 2px 6px;
}

/* Config Preview */
/* Config Detail Panel */
.config-detail-panel {
  margin-top: 16px;
}

.config-block {
  margin-top: 16px;
  border-top: 1px solid #E5E5E5;
  padding-top: 12px;
}

.config-block:first-child {
  margin-top: 0;
  border-top: none;
  padding-top: 0;
}

.config-block-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.config-block-title {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.config-block-badge {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  background: #F1F5F9;
  color: #475569;
  padding: 2px 8px;
  border-radius: 10px;
}

/* Config Grid */
.config-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.config-item {
  background: #F9F9F9;
  padding: 12px 14px;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.config-item-label {
  font-size: 11px;
  color: #94A3B8;
}

.config-item-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 16px;
  font-weight: 600;
  color: #1E293B;
}

/* Time Periods */
.time-periods {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.period-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: #F9F9F9;
  border-radius: 6px;
}

.period-label {
  font-size: 12px;
  font-weight: 500;
  color: #64748B;
  min-width: 70px;
}

.period-hours {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #475569;
  flex: 1;
}

.period-multiplier {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 600;
  color: #6366F1;
  background: #EEF2FF;
  padding: 2px 6px;
  border-radius: 4px;
}

/* Agents Cards */
.agents-cards {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  max-height: 400px;
  overflow-y: auto;
  padding-right: 4px;
}

.agents-cards::-webkit-scrollbar {
  width: 4px;
}

.agents-cards::-webkit-scrollbar-thumb {
  background: #DDD;
  border-radius: 2px;
}

.agents-cards::-webkit-scrollbar-thumb:hover {
  background: #CCC;
}

.agent-card {
  background: #F9F9F9;
  border: 1px solid #E5E5E5;
  border-radius: 6px;
  padding: 14px;
  transition: all 0.2s ease;
}

.agent-card:hover {
  border-color: #999;
  background: #FFF;
}

/* Agent Card Header */
.agent-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid #F1F5F9;
}

.agent-identity {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.agent-id {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #94A3B8;
}

.agent-name {
  font-size: 14px;
  font-weight: 600;
  color: #1E293B;
}

.agent-tags {
  display: flex;
  gap: 6px;
}

.agent-type {
  font-size: 10px;
  color: #64748B;
  background: #F1F5F9;
  padding: 2px 8px;
  border-radius: 4px;
}

.agent-stance {
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 4px;
}

.stance-neutral {
  background: #F1F5F9;
  color: #64748B;
}

.stance-supportive {
  background: #DCFCE7;
  color: #16A34A;
}

.stance-opposing {
  background: #FEE2E2;
  color: #DC2626;
}

.stance-observer {
  background: #FEF3C7;
  color: #D97706;
}

/* Agent Timeline */
.agent-timeline {
  margin-bottom: 14px;
}

.timeline-label {
  display: block;
  font-size: 10px;
  color: #94A3B8;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.mini-timeline {
  display: flex;
  gap: 2px;
  height: 16px;
  background: #F8FAFC;
  border-radius: 4px;
  padding: 3px;
}

.timeline-hour {
  flex: 1;
  background: #E2E8F0;
  border-radius: 2px;
  transition: all 0.2s;
}

.timeline-hour.active {
  background: linear-gradient(180deg, #6366F1, #818CF8);
}

.timeline-marks {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  color: #94A3B8;
}

/* Agent Params */
.agent-params {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.param-group {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.param-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.param-item .param-label {
  font-size: 10px;
  color: #94A3B8;
}

.param-item .param-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
}

.param-value.with-bar {
  display: flex;
  align-items: center;
  gap: 6px;
}

.mini-bar {
  height: 4px;
  background: linear-gradient(90deg, #6366F1, #A855F7);
  border-radius: 2px;
  min-width: 4px;
  max-width: 40px;
}

.param-value.positive {
  color: #16A34A;
}

.param-value.negative {
  color: #DC2626;
}

.param-value.neutral {
  color: #64748B;
}

.param-value.highlight {
  color: #6366F1;
}

/* Platforms Grid */
.platforms-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.platform-card {
  background: #F9F9F9;
  padding: 14px;
  border-radius: 6px;
}

.platform-card-header {
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid #E5E5E5;
}

.platform-name {
  font-size: 13px;
  font-weight: 600;
  color: #333;
}

.platform-params {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.param-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.param-label {
  font-size: 12px;
  color: #64748B;
}

.param-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 600;
  color: #1E293B;
}

/* Reasoning Content */
.reasoning-content {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.reasoning-item {
  padding: 12px 14px;
  background: #F9F9F9;
  border-radius: 6px;
}

.reasoning-text {
  font-size: 13px;
  color: #555;
  line-height: 1.7;
  margin: 0;
}

/* Profile Modal */
.profile-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.profile-modal {
  background: #FFF;
  border-radius: 16px;
  width: 90%;
  max-width: 600px;
  max-height: 85vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 24px;
  background: #FFF;
  border-bottom: 1px solid #F0F0F0;
}

.modal-header-info {
  flex: 1;
}

.modal-name-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 8px;
}

.modal-realname {
  font-size: 20px;
  font-weight: 700;
  color: #000;
}

.modal-username {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  color: #999;
}

.modal-profession {
  font-size: 12px;
  color: #666;
  background: #F5F5F5;
  padding: 4px 10px;
  border-radius: 4px;
  display: inline-block;
  font-weight: 500;
}

.close-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: none;
  color: #999;
  border-radius: 50%;
  font-size: 24px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  transition: color 0.2s;
  padding: 0;
}

.close-btn:hover {
  color: #333;
}

.modal-body {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
}

/* Basic information grid */
.modal-info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px 16px;
  margin-bottom: 32px;
  padding: 0;
  background: transparent;
  border-radius: 0;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: 11px;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
}

.info-value {
  font-size: 15px;
  font-weight: 600;
  color: #333;
}

.info-value.mbti {
  font-family: 'JetBrains Mono', monospace;
  color: #FF5722;
}

/* Module area */
.modal-section {
  margin-bottom: 28px;
}

.section-label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
}

.section-bio {
  font-size: 14px;
  color: #333;
  line-height: 1.6;
  margin: 0;
  padding: 16px;
  background: #F9F9F9;
  border-radius: 6px;
  border-left: 3px solid #E0E0E0;
}

/* Topic Tag */
.topics-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.topic-item {
  font-size: 11px;
  color: #1565C0;
  background: #E3F2FD;
  padding: 4px 10px;
  border-radius: 12px;
  transition: all 0.2s;
  border: none;
}

.topic-item:hover {
  background: #BBDEFB;
  color: #0D47A1;
}

/* Detailed Persona */
.persona-dimensions {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.dimension-card {
  background: #F8F9FA;
  padding: 12px;
  border-radius: 6px;
  border-left: 3px solid #DDD;
  transition: all 0.2s;
}

.dimension-card:hover {
  background: #F0F0F0;
  border-left-color: #999;
}

.dim-title {
  display: block;
  font-size: 12px;
  font-weight: 700;
  color: #333;
  margin-bottom: 4px;
}

.dim-desc {
  display: block;
  font-size: 10px;
  color: #888;
  line-height: 1.4;
}

.persona-content {
  max-height: none;
  overflow: visible;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 0;
}

.persona-content::-webkit-scrollbar {
  width: 4px;
}

.persona-content::-webkit-scrollbar-thumb {
  background: #DDD;
  border-radius: 2px;
}

.section-persona {
  font-size: 13px;
  color: #555;
  line-height: 1.8;
  margin: 0;
  text-align: justify;
}

/* System Logs */
.system-logs {
  background: #000;
  color: #DDD;
  padding: 16px;
  font-family: 'JetBrains Mono', monospace;
  border-top: 1px solid #222;
  flex-shrink: 0;
}

.log-header {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px solid #333;
  padding-bottom: 8px;
  margin-bottom: 8px;
  font-size: 10px;
  color: #888;
}

.log-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  height: 80px; /* Approx 4 lines visible */
  overflow-y: auto;
  padding-right: 4px;
}

.log-content::-webkit-scrollbar {
  width: 4px;
}

.log-content::-webkit-scrollbar-thumb {
  background: #333;
  border-radius: 2px;
}

.log-line {
  font-size: 11px;
  display: flex;
  gap: 12px;
  line-height: 1.5;
}

.log-time {
  color: #666;
  min-width: 75px;
}

.log-msg {
  color: #CCC;
  word-break: break-all;
}

/* Spinner */
.spinner-sm {
  width: 16px;
  height: 16px;
  border: 2px solid #E5E5E5;
  border-top-color: #FF5722;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
/* Orchestration Content */
.orchestration-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
  margin-top: 16px;
}

.box-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
}

.narrative-box {
  background: #FFFFFF;
  padding: 20px 24px;
  border-radius: 12px;
  border: 1px solid #EEF2F6;
  box-shadow: 0 4px 24px rgba(0,0,0,0.03);
  transition: all 0.3s ease;
}

.narrative-box .box-label {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #666;
  font-size: 13px;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
  font-weight: 600;
}

.special-icon {
  filter: drop-shadow(0 2px 4px rgba(255, 87, 34, 0.2));
  transition: transform 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.narrative-box:hover .special-icon {
  transform: rotate(180deg);
}

.narrative-text {
  font-family: 'Inter', 'Noto Sans SC', system-ui, sans-serif;
  font-size: 14px;
  color: #334155;
  line-height: 1.8;
  margin: 0;
  text-align: justify;
  letter-spacing: 0.01em;
}

.topics-section {
  background: #FFF;
}

.hot-topics-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.hot-topic-tag {
  font-size: 12px;
  color:rgba(255, 86, 34, 0.88);
  background: #FFF3E0;
  padding: 4px 10px;
  border-radius: 12px;
  font-weight: 500;
}

.hot-topic-more {
  font-size: 11px;
  color: #999;
  padding: 4px 6px;
}

.initial-posts-section {
  border-top: 1px solid #EAEAEA;
  padding-top: 16px;
}

.posts-timeline {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-left: 8px;
  border-left: 2px solid #F0F0F0;
  margin-top: 12px;
}

.timeline-item {
  position: relative;
  padding-left: 20px;
}

.timeline-marker {
  position: absolute;
  left: 0;
  top: 14px;
  width: 12px;
  height: 2px;
  background: #DDD;
}

.timeline-content {
  background: #F9F9F9;
  padding: 12px;
  border-radius: 6px;
  border: 1px solid #EEE;
}

.post-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}

.post-role {
  font-size: 11px;
  font-weight: 700;
  color: #333;
  text-transform: uppercase;
}

.post-agent-info {
  display: flex;
  align-items: center;
  gap: 6px;
}

.post-id,
.post-username {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #666;
  line-height: 1;
  vertical-align: baseline;
}

.post-username {
  margin-right: 6px;
}

.post-text {
  font-size: 12px;
  color: #555;
  line-height: 1.5;
  margin: 0;
}

/* Simulation Rounds ConfigurationStyle */
.rounds-config-section {
  margin: 24px 0;
  padding-top: 24px;
  border-top: 1px solid #EAEAEA;
}

.rounds-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #1E293B;
}

.section-desc {
  font-size: 12px;
  color: #94A3B8;
}

.desc-highlight {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  color: #1E293B;
  background: #F1F5F9;
  padding: 1px 6px;
  border-radius: 4px;
  margin: 0 2px;
}

/* Switch Control */
.switch-control {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px 4px 4px;
  border-radius: 20px;
  transition: background 0.2s;
}

.switch-control:hover {
  background: #F8FAFC;
}

.switch-control input {
  display: none;
}

.switch-track {
  width: 36px;
  height: 20px;
  background: #E2E8F0;
  border-radius: 10px;
  position: relative;
  transition: all 0.3s cubic-bezier(0.4, 0.0, 0.2, 1);
}

.switch-track::after {
  content: '';
  position: absolute;
  left: 2px;
  top: 2px;
  width: 16px;
  height: 16px;
  background: #FFF;
  border-radius: 50%;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  transition: transform 0.3s cubic-bezier(0.4, 0.0, 0.2, 1);
}

.switch-control input:checked + .switch-track {
  background: #000;
}

.switch-control input:checked + .switch-track::after {
  transform: translateX(16px);
}

.switch-label {
  font-size: 12px;
  font-weight: 500;
  color: #64748B;
}

.switch-control input:checked ~ .switch-label {
  color: #1E293B;
}

/* Slider Content */
.rounds-content {
  animation: fadeIn 0.3s ease;
}

.slider-display {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 16px;
}

.slider-main-value {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.val-num {
  font-family: 'JetBrains Mono', monospace;
  font-size: 24px;
  font-weight: 700;
  color: #000;
}

.val-unit {
  font-size: 12px;
  color: #666;
  font-weight: 500;
}

.slider-meta-info {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #64748B;
  background: #F1F5F9;
  padding: 4px 8px;
  border-radius: 4px;
}

.range-wrapper {
  position: relative;
  padding: 0 2px;
}

.minimal-slider {
  -webkit-appearance: none;
  width: 100%;
  height: 4px;
  background: #E2E8F0;
  border-radius: 2px;
  outline: none;
  background-image: linear-gradient(#000, #000);
  background-size: var(--percent, 0%) 100%;
  background-repeat: no-repeat;
  cursor: pointer;
}

.minimal-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #FFF;
  border: 2px solid #000;
  cursor: pointer;
  box-shadow: 0 1px 4px rgba(0,0,0,0.1);
  transition: transform 0.1s;
  margin-top: -6px; /* Center thumb */
}

.minimal-slider::-webkit-slider-thumb:hover {
  transform: scale(1.1);
}

.minimal-slider::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: 2px;
}

.range-marks {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #94A3B8;
  position: relative;
}

.mark-recommend {
  cursor: pointer;
  transition: color 0.2s;
  position: relative;
}

.mark-recommend:hover {
  color: #000;
}

.mark-recommend.active {
  color: #000;
  font-weight: 600;
}

.mark-recommend::after {
  content: '';
  position: absolute;
  top: -12px;
  left: 50%;
  transform: translateX(-50%);
  width: 1px;
  height: 4px;
  background: #CBD5E1;
}

/* Simulation Preset */
.preset-section {
  margin-top: 20px;
  padding: 20px;
  background: #F8FAFC;
  border-radius: 8px;
  border: 1px solid #E2E8F0;
}

.preset-header {
  margin-bottom: 16px;
}

.preset-header .section-title {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.preset-header .section-desc {
  font-size: 11px;
  color: #999;
  margin-top: 4px;
}

.preset-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.preset-card {
  background: #FFF;
  border: 2px solid #E5E7EB;
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: center;
  position: relative;
}

.preset-card:hover {
  border-color: #CBD5E1;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}

.preset-card.active {
  border-color: #FF5722;
  background: #FFF7F0;
  box-shadow: 0 4px 12px rgba(255,87,34,0.15);
}

.preset-icon {
  font-size: 24px;
  margin-bottom: 8px;
}

.preset-name {
  font-size: 14px;
  font-weight: 700;
  color: #000;
  margin-bottom: 4px;
}

.preset-desc {
  font-size: 11px;
  color: #666;
  margin-bottom: 8px;
}

.preset-meta {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin-bottom: 8px;
}

.meta-item {
  font-size: 10px;
  color: #64748B;
  background: #F1F5F9;
  padding: 2px 6px;
  border-radius: 4px;
}

.preset-check {
  position: absolute;
  top: 8px;
  right: 8px;
  color: #FF5722;
  font-size: 16px;
}

.preset-summary {
  margin-top: 12px;
  padding: 8px 12px;
  background: #E8F5E9;
  border-radius: 6px;
  font-size: 11px;
  color: #2E7D32;
}

.summary-text {
  text-align: center;
}

/* Auto Info */
.preset-section + .step-card {
  margin-top: 20px;
}

.auto-info-card {
  display: flex;
  align-items: center;
  gap: 24px;
  background: #F8FAFC;
  padding: 16px 20px;
  border-radius: 8px;
}

.auto-value {
  display: flex;
  flex-direction: row;
  align-items: baseline;
  gap: 4px;
  padding-right: 24px;
  border-right: 1px solid #E2E8F0;
}

.auto-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  justify-content: center;
}

.auto-meta-row {
  display: flex;
  align-items: center;
}

.duration-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 500;
  color: #64748B;
  background: #FFFFFF;
  border: 1px solid #E2E8F0;
  padding: 3px 8px;
  border-radius: 6px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.02);
}

.auto-desc {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.auto-desc p {
  margin: 0;
  font-size: 13px;
  color: #64748B;
  line-height: 1.5;
}

.highlight-tip {
  margin-top: 4px !important;
  font-size: 12px !important;
  color: #000 !important;
  font-weight: 500;
  cursor: pointer;
}

.highlight-tip:hover {
  text-decoration: underline;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Modal Transition */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.3s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .profile-modal {
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.modal-leave-active .profile-modal {
  transition: all 0.3s ease-in;
}

.modal-enter-from .profile-modal,
.modal-leave-to .profile-modal {
  transform: scale(0.95) translateY(10px);
  opacity: 0;
}

/* Research Context enrichment panel */
.enrichment-section {
  margin-top: 20px;
  border-top: 1px solid #E5E5E5;
  padding-top: 16px;
}

.preview-hint {
  font-size: 0.7rem;
  color: #999;
}

.enrichment-card {
  border: 1px solid #E5E5E5;
  margin-bottom: 8px;
  background: #FAFAFA;
}

.enrichment-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
}

.enrichment-header:hover {
  background: #F0F0F0;
}

.enrichment-archetype {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem;
  font-weight: 600;
  color: #333;
  text-transform: capitalize;
}

.enrichment-toggle {
  font-size: 0.65rem;
  color: #999;
}

.enrichment-body {
  border-top: 1px solid #E5E5E5;
  padding: 12px 14px;
}

.enrichment-text {
  font-size: 0.78rem;
  line-height: 1.6;
  color: #444;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-family: inherit;
}

.research-stats {
  display: flex;
  gap: 16px;
  padding: 12px;
  background: #F7F7F7;
  border: 1px solid #E5E5E5;
  margin-bottom: 10px;
}

.rstat {
  flex: 1;
  text-align: center;
}

.rstat-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1.1rem;
  font-weight: 700;
  color: #222;
}

.rstat-label {
  font-size: 0.7rem;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-top: 2px;
}

.research-sources {
  margin-bottom: 10px;
  font-size: 0.7rem;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.sources-label {
  color: #888;
  margin-right: 4px;
}

.source-tag {
  display: inline-block;
  padding: 2px 6px;
  background: #EFEFEF;
  border-radius: 2px;
  font-family: 'JetBrains Mono', monospace;
  color: #333;
}

.research-running {
  padding: 10px;
  background: #FFF7E5;
  border: 1px solid #FFD580;
  margin-bottom: 10px;
  font-size: 0.78rem;
  color: #B45309;
  display: flex;
  align-items: center;
  gap: 8px;
}

.console-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #aaa;
}
.console-dot.active {
  background: #1E9E5A;
  animation: rdot-pulse 1s infinite;
}
@keyframes rdot-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.enrichment-chars {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: #888;
  margin-left: auto;
  margin-right: 10px;
}

.rerun-research-btn {
  margin-top: 10px;
  padding: 8px 14px;
  background: #fff;
  border: 1px solid #333;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem;
  cursor: pointer;
  width: 100%;
}

.rerun-research-btn:hover:not(:disabled) {
  background: #333;
  color: #fff;
}

.rerun-research-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.research-error {
  margin-top: 8px;
  padding: 8px;
  background: #FEE;
  border: 1px solid #FCC;
  color: #C00;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
}

.cost-summary {
  margin-top: 16px;
  padding: 12px 16px;
  background: #F7F9FC;
  border: 1px solid #DDE4EE;
  border-radius: 4px;
}

.cost-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
  font-size: 0.82rem;
}

.cost-total {
  border-top: 1px solid #DDE4EE;
  margin-top: 6px;
  padding-top: 8px;
  font-weight: 600;
}

.cost-label {
  color: #555;
}

.cost-value {
  font-family: 'JetBrains Mono', monospace;
  color: #222;
}

.cost-usd {
  color: #888;
  font-size: 0.75rem;
  margin-left: 6px;
}

.cost-tokens {
  margin-top: 8px;
  font-size: 0.72rem;
  color: #888;
  font-family: 'JetBrains Mono', monospace;
  text-align: right;
}

</style>
