<template>
  <div class="simulation-panel">
    <!-- Top Control Bar -->
    <div class="control-bar">
      <div class="status-group">
        <!-- Opinion Space Progress (AgentSociety single-platform) -->
        <div class="platform-status opinion-space" :class="{ active: runStatus.simulation_running, completed: runStatus.simulation_completed }">
          <div class="platform-header">
            <svg class="platform-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="8" r="4"></circle>
              <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"></path>
            </svg>
            <span class="platform-name">Opinion Space</span>
            <span v-if="runStatus.simulation_completed" class="status-badge">
              <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            </span>
          </div>
          <div class="platform-stats">
            <span class="stat">
              <span class="stat-label">ROUND</span>
              <span class="stat-value mono">{{ runStatus.current_round || 0 }}<span class="stat-total">/{{ runStatus.total_rounds || maxRounds || '-' }}</span></span>
            </span>
            <span class="stat">
              <span class="stat-label">Elapsed Time</span>
              <span class="stat-value mono">{{ elapsedTime }}</span>
            </span>
            <span class="stat">
              <span class="stat-label">ACTS</span>
              <span class="stat-value mono">{{ runStatus.simulation_actions_count || 0 }}</span>
            </span>
            <span class="stat" v-if="runStatus.total_agents">
              <span class="stat-label">AGENTS</span>
              <span class="stat-value mono">{{ runStatus.agents_expressed_count || 0 }}<span class="stat-total">/{{ runStatus.total_agents }}</span></span>
            </span>
          </div>
          <!-- Available Actions Tooltip -->
          <div class="actions-tooltip">
            <div class="tooltip-title">Available Actions</div>
            <div class="tooltip-actions">
              <span class="tooltip-action">EXPRESS</span>
              <span class="tooltip-action">RESPOND</span>
              <span class="tooltip-action">SEARCH</span>
              <span class="tooltip-action">OBSERVE</span>
              <span class="tooltip-action">IDLE</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Pause / Resume Controls (only during simulation) -->
      <div class="action-controls" v-if="phase === 1">
        <button
          v-if="!isPaused"
          class="action-btn warning"
          :disabled="isPausing"
          @click="handlePause"
        >
          <span v-if="isPausing" class="loading-spinner-small"></span>
          <span v-else>⏸ Pause</span>
        </button>
        <button
          v-else
          class="action-btn success"
          :disabled="isResuming"
          @click="handleResume"
        >
          <span v-if="isResuming" class="loading-spinner-small"></span>
          <span v-else>▶ Resume</span>
        </button>
        <button
          v-if="isPaused"
          class="action-btn primary"
          :disabled="liveInterviewLoading"
          @click="toggleLiveIntervention"
        >
          {{ showLiveInterview ? 'Hide' : 'Open Workbench' }}
        </button>
        <div v-if="pauseError" class="pause-error-banner">
          ⚠ {{ pauseError }}
        </div>
      </div>

      <div class="action-controls" v-if="phase >= 1 && phase !== 1">
        <button 
          class="action-btn primary"
          :disabled="phase !== 2 || isGeneratingReport"
          @click="handleNextStep"
        >
          <span v-if="isGeneratingReport" class="loading-spinner-small"></span>
          {{ isGeneratingReport ? 'Starting...' : 'Start Generating Report' }} 
          <span v-if="!isGeneratingReport" class="arrow-icon">→</span>
        </button>
      </div>

      <!-- Policy Workbench (shown when paused) -->
      <Transition name="slide-fade">
        <div v-if="isPaused && showLiveInterview" class="policy-workbench">

          <!-- Workbench Header -->
          <div class="wb-header">
            <div class="wb-title-group">
              <span class="wb-icon">◆</span>
              <span class="wb-title">POLICY WORKBENCH</span>
              <span class="wb-round">Round {{ runStatus.current_round || 0 }}</span>
            </div>
            <div class="wb-tabs">
              <button class="wb-tab" :class="{ active: interventionMode === 'map' }" @click="interventionMode = 'map'">Stance Map</button>
              <button class="wb-tab" :class="{ active: interventionMode === 'target' }" @click="interventionMode = 'target'">Target</button>
              <button class="wb-tab" :class="{ active: interventionMode === 'broadcast' }" @click="interventionMode = 'broadcast'">Broadcast</button>
            </div>
          </div>

          <!-- MODE: Stance Map -->
          <div v-if="interventionMode === 'map'" class="wb-stance-map">
            <p class="wb-hint">Click an agent to target them. Changed agents are highlighted.</p>
            <div class="stance-columns">
              <div v-for="s in STANCES" :key="s.key" class="stance-col">
                <div class="stance-col-head" :style="{ color: s.color }">
                  {{ s.label }}
                  <span class="stance-count">{{ agentsByStance(s.key).length }}</span>
                </div>
                <div
                  v-for="agent in agentsByStance(s.key)"
                  :key="agent.id"
                  class="sac"
                  :class="{ 'sac-selected': selectedChatAgent === agent.id, 'sac-changed': changedAgentIds.has(agent.id) }"
                  :style="{ borderLeftColor: s.color }"
                  @click="selectAgentForIntervention(agent)"
                >
                  <div class="sac-name">{{ agent.name }}</div>
                  <div class="sac-role">{{ (agent.actor_archetype || agent.occupation || '').replace(/_/g, ' ') }}</div>
                  <div v-if="changedAgentIds.has(agent.id)" class="sac-badge">shifted</div>
                </div>
                <div v-if="agentsByStance(s.key).length === 0" class="stance-empty">—</div>
              </div>
            </div>
          </div>

          <!-- MODE: Target Agent -->
          <div v-if="interventionMode === 'target'" class="wb-target">
            <!-- Selected agent chip -->
            <div v-if="selectedChatAgent" class="selected-chip">
              <span class="chip-dot" :style="{ background: stanceColor(selectedAgentStance) }"></span>
              <span class="chip-name">{{ selectedAgentName }}</span>
              <span class="chip-stance">{{ selectedAgentStance }}</span>
              <button class="chip-clear" @click="selectedChatAgent = null">×</button>
            </div>
            <div v-else class="no-target-hint">← Pick an agent from Stance Map, or select below</div>

            <select v-if="!selectedChatAgent" v-model="selectedChatAgent" class="agent-select">
              <option :value="null" disabled>Select an agent...</option>
              <option v-for="agent in agentProfiles" :key="agent.id" :value="agent.id">
                {{ agent.name }} — {{ agent.actor_archetype || 'unknown' }}
              </option>
            </select>

            <div class="intervention-field">
              <label class="field-label">Policy Statement</label>
              <textarea
                v-model="liveInterventionText"
                placeholder="e.g. Government will offer a R500/month subsidy to qualifying households"
                class="intervention-textarea"
                rows="3"
              ></textarea>
            </div>

            <button
              class="intervention-btn"
              :disabled="!selectedChatAgent || !liveInterventionText.trim() || liveInterviewLoading"
              @click="handleLiveIntervention"
            >
              <span v-if="liveInterviewLoading" class="loading-spinner-small"></span>
              <span v-else>Apply to {{ selectedAgentName || 'Agent' }} →</span>
            </button>

            <div v-if="liveInterviewResult" class="intervention-result">
              <div class="result-response">{{ liveInterviewResult.response }}</div>
              <div class="result-meta">
                <div class="stance-shift">
                  <span class="stance-badge" :class="`stance-${liveInterviewResult.stance_before}`">{{ liveInterviewResult.stance_before }}</span>
                  <span class="shift-arrow">→</span>
                  <span class="stance-badge" :class="`stance-${liveInterviewResult.stance_after}`">{{ liveInterviewResult.stance_after }}</span>
                  <span v-if="!liveInterviewResult.stance_changed" class="no-change">(unchanged)</span>
                </div>
                <span v-if="liveInterviewResult.propagation_count > 0" class="propagation-notice">
                  ↳ propagated to {{ liveInterviewResult.propagation_count }} affiliated agent{{ liveInterviewResult.propagation_count > 1 ? 's' : '' }}
                </span>
              </div>
            </div>
          </div>

          <!-- MODE: Broadcast -->
          <div v-if="interventionMode === 'broadcast'" class="wb-broadcast">
            <p class="wb-hint">Send one policy message to every agent of a given archetype.</p>

            <div class="intervention-field">
              <label class="field-label">Target Archetype</label>
              <select v-model="broadcastArchetype" class="agent-select">
                <option value="" disabled>Select archetype...</option>
                <option v-for="arch in archetypes" :key="arch" :value="arch">
                  {{ arch.replace(/_/g, ' ') }} ({{ agentsByArchetype(arch).length }})
                </option>
              </select>
            </div>

            <div class="intervention-field">
              <label class="field-label">Policy Statement</label>
              <textarea
                v-model="broadcastText"
                placeholder="e.g. All taxi operators will receive a fuel levy rebate of R1.20/litre"
                class="intervention-textarea"
                rows="3"
              ></textarea>
            </div>

            <div v-if="broadcastArchetype" class="broadcast-preview">
              Broadcasting to {{ agentsByArchetype(broadcastArchetype).length }} agents
            </div>

            <button
              class="intervention-btn"
              :disabled="!broadcastArchetype || !broadcastText.trim() || broadcastLoading"
              @click="handleBroadcast"
            >
              <span v-if="broadcastLoading" class="loading-spinner-small"></span>
              <span v-else>Broadcast →</span>
            </button>

            <div v-if="broadcastResults.length > 0" class="broadcast-results">
              <div class="br-summary">
                {{ broadcastResults.filter(r => r.stance_changed).length }} of {{ broadcastResults.length }} agents shifted stance
              </div>
              <div v-for="r in broadcastResults" :key="r.agentId" class="br-row">
                <span class="br-name">{{ r.agentName }}</span>
                <span v-if="r.error" class="br-error">error</span>
                <template v-else>
                  <span class="stance-badge" :class="`stance-${r.stance_before}`">{{ r.stance_before }}</span>
                  <span class="shift-arrow">→</span>
                  <span class="stance-badge" :class="`stance-${r.stance_after}`">{{ r.stance_after }}</span>
                </template>
              </div>
            </div>
          </div>

          <!-- Intervention History (this pause session) -->
          <div v-if="interventionHistory.length > 0" class="wb-history">
            <div class="history-label">Applied this session</div>
            <div v-for="(h, i) in interventionHistory" :key="i" class="history-row">
              <span class="history-agent">{{ h.agentName }}</span>
              <span class="stance-badge" :class="`stance-${h.before}`">{{ h.before }}</span>
              <span class="shift-arrow">→</span>
              <span class="stance-badge" :class="`stance-${h.after}`">{{ h.after }}</span>
              <span class="history-text" :title="h.text">{{ h.text }}</span>
            </div>
          </div>

        </div>
      </Transition>

      <!-- Chat Panel - Slide-out Style (appears when clicking agent) -->
      <Transition name="slide-fade">
        <div v-if="showChat" class="chat-panel-container">
          <div class="chat-panel-header">
            <div class="chat-panel-title">
              <span class="panel-icon">💬</span>
              <span>Chat with {{ getSelectedAgentName() }}</span>
              <span v-if="getSelectedArchetype()" class="archetype-badge">{{ getSelectedArchetype() }}</span>
            </div>
            <button class="chat-close-btn" @click="showChat = false">×</button>
          </div>
          
          <div class="chat-messages-container">
            <div class="chat-messages-list">
              <div v-if="chatMessages.length === 0" class="chat-empty-state">
                <p>Ask {{ getSelectedAgentName() }} about their thoughts</p>
                <p class="hint">Click on any agent in the timeline to chat with them</p>
              </div>
              <div 
                v-for="(msg, i) in chatMessages" 
                :key="i" 
                class="chat-message"
                :class="msg.role"
              >
                <div class="message-bubble">{{ msg.content }}</div>
                <div class="message-time">{{ new Date().toLocaleTimeString() }}</div>
              </div>
              <div v-if="chatLoading" class="chat-typing-indicator">
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-text">{{ getSelectedAgentName() }} is typing...</span>
              </div>
              <div v-if="chatError" class="chat-error-banner">{{ chatError }}</div>
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
        </div>
      </Transition>
    </div>

    <!-- Main Content: Dual Timeline -->
    <div class="main-content-area" ref="scrollContainer">
      <!-- Timeline Header -->
      <div class="timeline-header" v-if="allActions.length > 0">
        <div class="timeline-stats">
          <span class="total-count">TOTAL EVENTS: <span class="mono">{{ allActions.length }}</span></span>
          <span class="platform-breakdown">
            <span class="breakdown-item opinion-space">
              <svg class="mini-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"></circle><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"></path></svg>
              <span class="mono">{{ allActions.length }}</span>
            </span>
          </span>
        </div>
      </div>
      
      <!-- Timeline Feed -->
      <div class="timeline-feed">
        <div class="timeline-axis"></div>
        
        <TransitionGroup name="timeline-item">
          <div 
            v-for="action in chronologicalActions" 
            :key="action._uniqueId || action.id || `${action.timestamp}-${action.agent_id}`" 
            class="timeline-item"
            :class="action.platform"
            @click="openChatForAgent(action.agent_id)"
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
                  <span v-if="isCustomAgent(action.agent_id)" class="agent-custom-badge">◆</span>
                  <span class="chat-hint">💬</span>
                </div>
                
                <div class="header-meta">
                  <div class="platform-indicator">
                    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"></circle><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"></path></svg>
                  </div>
                  <div class="action-badge" :class="getActionTypeClass(action.action_type)">
                    {{ getActionTypeLabel(action.action_type) }}
                  </div>
                </div>
              </div>
              
              <div class="card-body">
                <!-- AgentSociety: Express Opinion -->
                <div v-if="action.action_type === 'EXPRESS_OPINION' && action.action_args?.content" class="content-text main-text">
                  {{ action.action_args.content }}
                </div>

                <!-- AgentSociety: Respond to Opinion -->
                <template v-if="action.action_type === 'RESPOND_TO_OPINION'">
                  <div v-if="action.action_args?.content" class="content-text">{{ action.action_args.content }}</div>
                  <div v-if="action.action_args?.target_content" class="quoted-block">
                    <div class="quote-header">
                      <span class="quote-label">{{ action.action_args.target_agent_name || 'Agent' }}</span>
                    </div>
                    <div class="quote-content">{{ action.action_args.target_content }}</div>
                  </div>
                </template>

                <!-- AgentSociety: Search Topic -->
                <template v-if="action.action_type === 'SEARCH_TOPIC'">
                  <div class="search-info">
                    <span>Searched: "{{ action.action_args?.query || '' }}"</span>
                    <span v-if="action.action_args?.results_count !== undefined" class="meta-text"> — {{ action.action_args.results_count }} results</span>
                  </div>
                </template>

                <!-- CREATE_POST: Post Publication -->
                <div v-if="action.action_type === 'CREATE_POST' && action.action_args?.content" class="content-text main-text">
                  {{ action.action_args.content }}
                </div>

                <!-- QUOTE_POST: Quote Post -->
                <template v-if="action.action_type === 'QUOTE_POST'">
                  <div v-if="action.action_args?.quote_content" class="content-text">
                    {{ action.action_args.quote_content }}
                  </div>
                  <div v-if="action.action_args?.original_content" class="quoted-block">
                    <div class="quote-header">
                      <svg class="icon-small" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>
                      <span class="quote-label">@{{ action.action_args.original_author_name || 'User' }}</span>
                    </div>
                    <div class="quote-text">
                      {{ truncateContent(action.action_args.original_content, 150) }}
                    </div>
                  </div>
                </template>

                <!-- REPOST: Repost -->
                <template v-if="action.action_type === 'REPOST'">
                  <div class="repost-info">
                    <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="17 1 21 5 17 9"></polyline><path d="M3 11V9a4 4 0 0 1 4-4h14"></path><polyline points="7 23 3 19 7 15"></polyline><path d="M21 13v2a4 4 0 0 1-4 4H3"></path></svg>
                    <span class="repost-label">Reposted from @{{ action.action_args?.original_author_name || 'User' }}</span>
                  </div>
                  <div v-if="action.action_args?.original_content" class="repost-content">
                    {{ truncateContent(action.action_args.original_content, 200) }}
                  </div>
                </template>

                <!-- LIKE_POST: Like Post -->
                <template v-if="action.action_type === 'LIKE_POST'">
                  <div class="like-info">
                    <svg class="icon-small filled" viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>
                    <span class="like-label">Liked @{{ action.action_args?.post_author_name || 'User' }}'s post</span>
                  </div>
                  <div v-if="action.action_args?.post_content" class="liked-content">
                    "{{ truncateContent(action.action_args.post_content, 120) }}"
                  </div>
                </template>

                <!-- CREATE_COMMENT: Create Comment -->
                <template v-if="action.action_type === 'CREATE_COMMENT'">
                  <div v-if="action.action_args?.content" class="content-text">
                    {{ action.action_args.content }}
                  </div>
                  <div v-if="action.action_args?.post_id" class="comment-context">
                    <svg class="icon-small" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>
                    <span>Reply to post #{{ action.action_args.post_id }}</span>
                  </div>
                </template>

                <!-- SEARCH_POSTS: Search Posts -->
                <template v-if="action.action_type === 'SEARCH_POSTS'">
                  <div class="search-info">
                    <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                    <span class="search-label">Search Query:</span>
                    <span class="search-query">"{{ action.action_args?.query || '' }}"</span>
                  </div>
                </template>

                <!-- FOLLOW: Follow User -->
                <template v-if="action.action_type === 'FOLLOW'">
                  <div class="follow-info">
                    <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="8.5" cy="7" r="4"></circle><line x1="20" y1="8" x2="20" y2="14"></line><line x1="23" y1="11" x2="17" y2="11"></line></svg>
                    <span class="follow-label">Followed @{{ action.action_args?.target_user || action.action_args?.user_id || 'User' }}</span>
                  </div>
                </template>

                <!-- UPVOTE / DOWNVOTE -->
                <template v-if="action.action_type === 'UPVOTE_POST' || action.action_type === 'DOWNVOTE_POST'">
                  <div class="vote-info">
                    <svg v-if="action.action_type === 'UPVOTE_POST'" class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline></svg>
                    <svg v-else class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>
                    <span class="vote-label">{{ action.action_type === 'UPVOTE_POST' ? 'Upvoted' : 'Downvoted' }} Post</span>
                  </div>
                  <div v-if="action.action_args?.post_content" class="voted-content">
                    "{{ truncateContent(action.action_args.post_content, 120) }}"
                  </div>
                </template>

                <!-- DO_NOTHING: No Action (Idle) -->
                <template v-if="action.action_type === 'DO_NOTHING'">
                  <div class="idle-info">
                    <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                    <span class="idle-label">Action Skipped</span>
                  </div>
                  <div class="reason-block" v-if="action.reason">
                    <span class="reason-label">Why:</span>
                    <span class="reason-text">"{{ action.reason }}"</span>
                  </div>
                  <div class="thought-block" v-if="action.internal_thought">
                    <span class="thought-label">Thinks:</span>
                    <span class="thought-text">"{{ action.internal_thought }}"</span>
                  </div>
                </template>

                <!-- OBSERVE: Reading Feed Silently -->
                <template v-if="action.action_type === 'OBSERVE'">
                  <div class="observe-info">
                    <svg class="icon-small" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                    <span class="observe-label">Observing feed</span>
                    <span class="meta-text" v-if="action.action_args?.feed_size"> — {{ action.action_args.feed_size }} posts in feed</span>
                  </div>
                  <div class="reason-block" v-if="action.reason">
                    <span class="reason-label">Why:</span>
                    <span class="reason-text">"{{ action.reason }}"</span>
                  </div>
                  <div class="thought-block" v-if="action.internal_thought">
                    <span class="thought-label">Thinks:</span>
                    <span class="thought-text">"{{ action.internal_thought }}"</span>
                  </div>
                </template>

                <!-- NON_PARTICIPATION: Not Engaging with Reason -->
                <template v-if="action.action_type === 'NON_PARTICIPATION'">
                  <div class="non-engagement-info">
                    <div class="engagement-badge not-engaging">
                      <svg class="icon-small" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"></line></svg>
                      <span>NOT ENGAGING</span>
                    </div>
                    <div class="reason-block" v-if="action.action_args?.reason">
                      <span class="reason-label">Why:</span>
                      <span class="reason-text">"{{ action.action_args.reason }}"</span>
                    </div>
                    <div class="category-tag" v-if="action.action_args?.reason_category">
                      <span class="category-label">{{ action.action_args.reason_category }}</span>
                    </div>
                  </div>
                </template>

                <!-- Generic Fallback: Unknown types or content not handled above -->
                <div v-if="!['EXPRESS_OPINION', 'RESPOND_TO_OPINION', 'SEARCH_TOPIC', 'OBSERVE', 'DO_NOTHING', 'NON_PARTICIPATION', 'CREATE_POST', 'QUOTE_POST', 'REPOST', 'LIKE_POST', 'CREATE_COMMENT', 'SEARCH_POSTS', 'FOLLOW', 'UPVOTE_POST', 'DOWNVOTE_POST'].includes(action.action_type) && action.action_args?.content" class="content-text">
                  {{ action.action_args.content }}
                </div>
              </div>

              <div class="card-footer">
                <span class="time-tag">R{{ action.round_num }} • {{ formatActionTime(action.timestamp) }}</span>
                <!-- Platform tag removed as it is in header now -->
              </div>
            </div>
          </div>
        </TransitionGroup>

        <div v-if="allActions.length === 0" class="waiting-state">
          <div class="pulse-ring"></div>
          <span>Waiting for agent actions...</span>
        </div>
      </div>
    </div>

    <!-- Bottom Info / Logs -->
    <div class="system-logs">
      <div class="log-header">
        <span class="log-title">SIMULATION MONITOR</span>
        <span class="log-id">{{ simulationId || 'NO_SIMULATION' }}</span>
      </div>
      <div class="log-content" ref="logContent">
        <div class="log-line" v-for="(log, idx) in systemLogs" :key="idx">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-msg">{{ log.msg }}</span>
        </div>
      </div>
    </div>

    <!-- ─── Bottom-docked intervention bar (visible when paused) ─── -->
    <Transition name="slide-up">
      <div v-if="isPaused" class="intervention-dock">
        <div class="dock-status">
          <span class="dock-dot"></span>
          <span class="dock-label">PAUSED · Round {{ runStatus.current_round || 0 }}</span>
          <span class="dock-hint">Type an intervention below, or resume.</span>
        </div>

        <div class="dock-row">
          <select v-model="dockTarget" class="dock-select">
            <option value="" disabled>Target…</option>
            <option value="all">🌍 Everyone ({{ agentProfiles.length }} agents)</option>
            <optgroup label="Single Agent">
              <option v-for="agent in agentProfiles" :key="'a' + agent.id" :value="'agent:' + agent.id">
                {{ agent.name }} — {{ (agent.actor_archetype || 'unknown').replace(/_/g, ' ') }} ({{ agent.stance || 'neutral' }})
              </option>
            </optgroup>
            <optgroup label="Broadcast to Archetype">
              <option v-for="arch in archetypes" :key="'b' + arch" :value="'arch:' + arch">
                ALL {{ arch.replace(/_/g, ' ') }} ({{ agentsByArchetype(arch).length }})
              </option>
            </optgroup>
          </select>

          <input
            v-model="dockText"
            type="text"
            class="dock-input"
            placeholder="e.g. Government will offer R500/month subsidy to taxi operators"
            @keyup.enter="handleDockApply"
            :disabled="dockLoading"
          />

          <button
            class="dock-apply-btn"
            :disabled="!dockTarget || !dockText.trim() || dockLoading"
            @click="handleDockApply"
          >
            <span v-if="dockLoading">…</span>
            <span v-else>Apply →</span>
          </button>

          <button class="dock-resume-btn" :disabled="isResuming" @click="handleResume">
            <span v-if="isResuming">…</span>
            <span v-else>▶ Resume</span>
          </button>
        </div>

        <!-- Most recent result -->
        <div v-if="dockLastResult" class="dock-result">
          <span class="dock-result-agent">{{ dockLastResult.label }}:</span>
          <span class="stance-badge" :class="`stance-${dockLastResult.before}`">{{ dockLastResult.before }}</span>
          <span class="dock-arrow">→</span>
          <span class="stance-badge" :class="`stance-${dockLastResult.after}`">{{ dockLastResult.after }}</span>
          <span v-if="dockLastResult.propagation_count > 0" class="dock-prop">
            ↳ {{ dockLastResult.propagation_count }} affiliates propagated
          </span>
          <span v-if="dockLastResult.shiftedCount !== undefined" class="dock-prop">
            ↳ {{ dockLastResult.shiftedCount }}/{{ dockLastResult.totalCount }} shifted
          </span>
          <span v-if="dockLastResult.response" class="dock-response">"{{ dockLastResult.response }}"</span>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { 
  startSimulation, 
  stopSimulation,
  getRunStatus, 
  getRunStatusDetail,
  getSimulationProfilesRealtime,
  interviewAgents,
  pauseSimulation,
  resumeSimulation,
  interveneLive
} from '../api/simulation'
import { generateReport } from '../api/report'

const router = useRouter()


// Send message to agent
const sendChatMessage = async () => {
  if (!chatInput.value.trim() || chatLoading.value) return
  
  const message = chatInput.value.trim()
  chatInput.value = ''
  chatLoading.value = true
  chatError.value = ''
  
  chatMessages.value.push({ role: 'user', content: message })
  
  try {
    const res = await interviewAgents({
      simulation_id: props.simulationId,
      interviews: [{
        agent_id: selectedChatAgent.value,
        prompt: message
      }]
    })
    
    if (res.success && res.data?.result?.results) {
      const results = res.data.result.results
      const key = `opinion_space_${selectedChatAgent.value}`
      const agentRes = results[key]
      if (agentRes?.response) {
        chatMessages.value.push({ role: 'assistant', content: agentRes.response })
      } else {
        chatError.value = 'No response from agent'
      }
    } else {
      chatError.value = res.error || 'Live chat failed'
    }
  } catch (e) {
    chatError.value = e.message || 'Chat failed'
  }
  
  chatLoading.value = false
}

const props = defineProps({
  simulationId: String,
  maxRounds: Number, // Max rounds passed from Step2
  preset: String, // Preset passed from Step2 (quick, balanced, deep)
  minutesPerRound: {
    type: Number,
    default: 30 // Default: 30 minutes per round
  },
  projectData: Object,
  graphData: Object,
  systemLogs: Array
})

// Inline chat state
const showChat = ref(false)
const chatMessages = ref([])
const chatInput = ref('')
const chatLoading = ref(false)
const chatError = ref('')
const selectedChatAgent = ref(null)

// Clear chat when switching agents
watch(selectedChatAgent, () => {
  chatMessages.value = []
  chatError.value = ''
})

// Helper to check if agent is custom
const isCustomAgent = (agentId) => {
  const agent = agentProfiles.value.find(a => a.id === agentId)
  if (!agent) return false
  const src = agent.source_entity_type || ''
  return src.startsWith('custom')
}

// Helper to get selected agent name
const getSelectedAgentName = () => {
  const agent = agentProfiles.value.find(a => a.id === selectedChatAgent.value)
  return agent?.name || `Agent ${selectedChatAgent.value}` || 'Agent'
}

// Helper to get selected agent archetype
const getSelectedArchetype = () => {
  const agent = agentProfiles.value.find(a => a.id === selectedChatAgent.value)
  return agent?.actor_archetype || ''
}

// Open chat panel for specific agent from timeline
const openChatForAgent = async (agentId) => {
  // Load agents if not loaded
  if (agentProfiles.value.length === 0) {
    await loadAgentProfiles()
  }
  selectedChatAgent.value = agentId
}

const emit = defineEmits(['go-back', 'next-step', 'add-log', 'update-status'])

// State
const isGeneratingReport = ref(false)
const phase = ref(0) // 0: Not started, 1: Running, 2: Completed
const isStarting = ref(false)
const isStopping = ref(false)
const isPaused = ref(false)
const isPausing = ref(false)
const isResuming = ref(false)
const pauseError = ref('')
const showLiveInterview = ref(false)
const liveInterventionText = ref('')
const liveInterviewResult = ref(null)
const liveInterviewLoading = ref(false)

// Policy Workbench state (legacy floating panel)
const interventionMode = ref('map')  // 'map' | 'target' | 'broadcast'
const changedAgentIds = ref(new Set())
const interventionHistory = ref([])
const broadcastArchetype = ref('')
const broadcastText = ref('')
const broadcastResults = ref([])
const broadcastLoading = ref(false)

// Bottom-dock intervention state
const dockTarget = ref('all')      // "all" (everyone), "agent:5", or "arch:taxi_operator"
const dockText = ref('')
const dockLoading = ref(false)
const dockLastResult = ref(null)

const STANCES = [
  { key: 'resist',    label: 'Resist',     color: '#DC2626' },
  { key: 'oppose',    label: 'Oppose',     color: '#EA580C' },
  { key: 'concerned', label: 'Concerned',  color: '#D97706' },
  { key: 'neutral',   label: 'Neutral',    color: '#6B7280' },
  { key: 'support',   label: 'Support',    color: '#16A34A' },
]

const STANCE_COLORS = Object.fromEntries(STANCES.map(s => [s.key, s.color]))

const agentsByStance = (stance) =>
  agentProfiles.value.filter(a => (a.stance || 'neutral') === stance)

const archetypes = computed(() => {
  const seen = new Set()
  agentProfiles.value.forEach(a => { if (a.actor_archetype) seen.add(a.actor_archetype) })
  return [...seen].sort()
})

const agentsByArchetype = (arch) =>
  agentProfiles.value.filter(a => a.actor_archetype === arch)

const selectedAgentStance = computed(() => {
  const a = agentProfiles.value.find(a => a.id === selectedChatAgent.value)
  return a?.stance || 'neutral'
})

const stanceColor = (stance) => STANCE_COLORS[stance] || '#6B7280'
const startError = ref(null)
const runStatus = ref({})
const agentProfiles = ref([]) // Loaded from simulation profiles
const allActions = ref([]) // All actions (incremental accumulation)
const actionIds = ref(new Set()) // Action IDs set for deduplication
const scrollContainer = ref(null)

// Computed
// Display actions in chronological order (newest at the bottom)
const chronologicalActions = computed(() => {
  return allActions.value
})

// Format simulated elapsed time
const formatElapsedTime = (currentRound) => {
  if (!currentRound || currentRound <= 0) return '0h 0m'
  const totalMinutes = currentRound * props.minutesPerRound
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return `${hours}h ${minutes}m`
}

const elapsedTime = computed(() => {
  return formatElapsedTime(runStatus.value.current_round || 0)
})

const selectedAgentName = computed(() => {
  const agent = agentProfiles.value.find(a => a.id === selectedChatAgent.value)
  return agent?.name || `Agent ${selectedChatAgent.value}`
})

// Methods
const addLog = (msg) => {
  emit('add-log', msg)
}

// Reset all states (for restarting simulation)
const resetAllState = () => {
  runStatus.value = {}
  allActions.value = []
  actionIds.value = new Set()
  prevRound.value = 0
  startError.value = null
  isStarting.value = false
  isStopping.value = false
  stopPolling()  // Stop any existing polling
}

// Load agent profiles for chat
const loadAgentProfiles = async () => {
  if (!props.simulationId) return
  try {
    const res = await getSimulationProfilesRealtime(props.simulationId)
    if (res.success && res.data) {
      // res.data is { profiles: [...], count, total_expected, ... }
      agentProfiles.value = Array.isArray(res.data) ? res.data : (res.data.profiles || [])
    }
  } catch (e) {
    console.error('Failed to load agent profiles:', e)
  }
}

// Start simulation
const doStartSimulation = async () => {
  if (!props.simulationId) {
    addLog('Error: Missing simulationId')
    return
  }

  // Reset all states first to avoid impact from previous simulation
  resetAllState()

  isStarting.value = true
  startError.value = null
  addLog('Starting Opinion Space simulation (AgentSociety)...')
  emit('update-status', 'processing')

  try {
    const params = {
      simulation_id: props.simulationId,
      platform: 'opinion_space',
      force: true,  // Force restart
      enable_graph_memory_update: true  // Enable dynamic graph update
    }

    if (props.maxRounds) {
      params.max_rounds = props.maxRounds
      addLog(`Set max simulation rounds: ${props.maxRounds}`)
    }

    if (props.preset) {
      params.preset = props.preset
      addLog(`Using preset: ${props.preset}`)
    }

    addLog('Dynamic graph update mode enabled')

    const res = await startSimulation(params)

    if (res.success && res.data) {
      if (res.data.force_restarted) {
        addLog('✓ Cleaned old simulation logs and restarted simulation')
      }
      addLog('✓ Simulation engine started successfully')
      addLog(`  ├─ PID: ${res.data.process_pid || '-'}`)

      phase.value = 1
      runStatus.value = res.data

      startStatusPolling()
      startDetailPolling()
    } else {
      startError.value = res.error || 'Start failed'
      addLog(`✗ Start failed: ${res.error || 'Unknown error'}`)
      emit('update-status', 'error')
    }
  } catch (err) {
    startError.value = err.message
    addLog(`✗ Start exception: ${err.message}`)
    emit('update-status', 'error')
  } finally {
    isStarting.value = false
  }
}

// Bottom dock: apply intervention to either a single agent or all of an archetype
const handleDockApply = async () => {
  if (!dockTarget.value || !dockText.value.trim() || dockLoading.value) return
  dockLoading.value = true
  const text = dockText.value.trim()
  const [kind, idOrArch] = dockTarget.value.split(':')

  try {
    if (kind === 'all') {
      // Global intervention — apply to every agent, in parallel batches
      const targets = Array.isArray(agentProfiles.value) ? agentProfiles.value : []
      if (targets.length === 0) {
        addLog('✗ No agents loaded yet — cannot broadcast. Try again in a moment.')
        dockLoading.value = false
        return
      }
      let shifted = 0
      let responded = 0
      let firstResponse = null
      const BATCH = 8  // concurrent requests per batch
      addLog(`→ Broadcasting to ALL ${targets.length} agents (${BATCH} at a time)...`)

      for (let start = 0; start < targets.length; start += BATCH) {
        const batch = targets.slice(start, start + BATCH)
        const settled = await Promise.allSettled(
          batch.map(agent =>
            interveneLive(props.simulationId, agent.id, { intervention_text: text })
              .then(res => ({ agent, res }))
          )
        )
        for (const outcome of settled) {
          if (outcome.status !== 'fulfilled') continue
          const { agent, res } = outcome.value
          if (res.success && res.data) {
            const r = res.data
            responded++
            if (!firstResponse && r.response) firstResponse = `${agent.name}: "${r.response.slice(0, 160)}"`
            if (r.stance_changed) {
              shifted++
              agent.stance = r.stance_after
              changedAgentIds.value = new Set([...changedAgentIds.value, agent.id])
              addLog(`  ✓ ${agent.name}: ${r.stance_before} → ${r.stance_after}`)
            }
            interventionHistory.value.push({ agentName: agent.name, before: r.stance_before, after: r.stance_after, text: text.slice(0, 60) })
          }
        }
        addLog(`  …processed ${Math.min(start + BATCH, targets.length)}/${targets.length} (${shifted} shifted so far)`)
      }

      dockLastResult.value = {
        label: `Everyone (${responded}/${targets.length} responded)`,
        before: '—',
        after: '—',
        shiftedCount: shifted,
        totalCount: targets.length,
        response: firstResponse,
      }
      addLog(`✓ Global intervention complete: ${responded}/${targets.length} agents engaged, ${shifted} shifted stance`)
    } else if (kind === 'agent') {
      const agentId = parseInt(idOrArch, 10)
      const agent = agentProfiles.value.find(a => a.id === agentId)
      const res = await interveneLive(props.simulationId, agentId, { intervention_text: text })
      if (res.success && res.data) {
        const r = res.data
        dockLastResult.value = {
          label: agent?.name || `Agent ${agentId}`,
          before: r.stance_before,
          after: r.stance_after,
          propagation_count: r.propagation_count,
          response: r.response?.slice(0, 200),
        }
        if (r.stance_changed && agent) agent.stance = r.stance_after
        if (r.stance_changed) changedAgentIds.value = new Set([...changedAgentIds.value, agentId])
        interventionHistory.value.push({ agentName: agent?.name, before: r.stance_before, after: r.stance_after, text: text.slice(0, 60) })
        addLog(`✓ ${agent?.name}: ${r.stance_before} → ${r.stance_after}` + (r.propagation_count ? ` (+${r.propagation_count} propagated)` : ''))
      } else {
        addLog(`✗ Intervention failed: ${res.error || 'unknown'}`)
      }
    } else if (kind === 'arch') {
      const targets = agentsByArchetype(idOrArch)
      let shifted = 0
      addLog(`→ Broadcasting to ${targets.length} ${idOrArch} agents...`)
      for (const agent of targets) {
        try {
          const res = await interveneLive(props.simulationId, agent.id, { intervention_text: text })
          if (res.success && res.data) {
            const r = res.data
            if (r.stance_changed) {
              shifted++
              agent.stance = r.stance_after
              changedAgentIds.value = new Set([...changedAgentIds.value, agent.id])
            }
            interventionHistory.value.push({ agentName: agent.name, before: r.stance_before, after: r.stance_after, text: text.slice(0, 60) })
          }
        } catch (_) { /* per-agent failures swallowed; carry on */ }
      }
      dockLastResult.value = {
        label: `Broadcast to ${idOrArch.replace(/_/g, ' ')}`,
        before: '—',
        after: '—',
        shiftedCount: shifted,
        totalCount: targets.length,
      }
      addLog(`✓ Broadcast complete: ${shifted}/${targets.length} agents shifted`)
    }
    dockText.value = ''
  } catch (e) {
    addLog(`✗ Intervention exception: ${e.message}`)
  } finally {
    dockLoading.value = false
  }
}

// Open workbench and ensure agents are loaded
const toggleLiveIntervention = async () => {
  showLiveInterview.value = !showLiveInterview.value
  if (showLiveInterview.value) {
    interventionMode.value = 'map'
    if (agentProfiles.value.length === 0) {
      await loadAgentProfiles()
    }
  }
}

// Click agent in stance map → jump to target mode
const selectAgentForIntervention = (agent) => {
  selectedChatAgent.value = agent.id
  interventionMode.value = 'target'
}

// Broadcast a policy statement to all agents of an archetype
const handleBroadcast = async () => {
  if (!broadcastArchetype.value || !broadcastText.value.trim()) return
  broadcastLoading.value = true
  broadcastResults.value = []
  const targets = agentsByArchetype(broadcastArchetype.value)
  for (const agent of targets) {
    try {
      const res = await interveneLive(props.simulationId, agent.id, { intervention_text: broadcastText.value.trim() })
      if (res.success && res.data) {
        const r = res.data
        broadcastResults.value.push({ agentId: agent.id, agentName: agent.name, ...r })
        if (r.stance_changed) {
          changedAgentIds.value = new Set([...changedAgentIds.value, agent.id])
          agent.stance = r.stance_after
        }
        interventionHistory.value.push({
          agentName: agent.name,
          before: r.stance_before,
          after: r.stance_after,
          text: broadcastText.value.trim().slice(0, 50),
        })
      } else {
        broadcastResults.value.push({ agentId: agent.id, agentName: agent.name, error: res.error || 'failed' })
      }
    } catch (e) {
      broadcastResults.value.push({ agentId: agent.id, agentName: agent.name, error: e.message })
    }
  }
  const shifted = broadcastResults.value.filter(r => r.stance_changed).length
  addLog(`Broadcast complete: ${shifted}/${targets.length} agents shifted stance`)
  broadcastLoading.value = false
}

// Pause simulation
const handlePause = async () => {
  if (!props.simulationId) return
  isPausing.value = true
  pauseError.value = ''
  addLog('Pausing simulation...')
  try {
    const res = await pauseSimulation(props.simulationId)
    if (res.success && res.data?.paused) {
      isPaused.value = true
      // Load agents into memory so the dock dropdown is populated
      if (agentProfiles.value.length === 0) {
        await loadAgentProfiles()
      }
      addLog('✓ Simulation paused — type an intervention below or resume')
    } else {
      const msg = res.error || res.data?.message || 'Could not pause — is the simulation still running?'
      pauseError.value = msg
      addLog(`✗ Pause failed: ${msg}`)
    }
  } catch (err) {
    const msg = err.response?.data?.error || err.message || 'Network error'
    pauseError.value = msg
    addLog(`✗ Pause failed: ${msg}`)
  } finally {
    isPausing.value = false
  }
}

// Resume simulation
const handleResume = async () => {
  if (!props.simulationId) return
  isResuming.value = true
  addLog('Resuming simulation...')
  try {
    const res = await resumeSimulation(props.simulationId)
    if (res.success && res.data?.paused === false) {
      isPaused.value = false
      showLiveInterview.value = false
      liveInterviewResult.value = null
      broadcastResults.value = []
      changedAgentIds.value = new Set()
      addLog('✓ Simulation resumed')
    } else {
      addLog(`Resume failed: ${res.error || res.data?.message || 'Unknown error'}`)
    }
  } catch (err) {
    addLog(`Resume exception: ${err.message}`)
  } finally {
    isResuming.value = false
  }
}

// Apply live intervention during paused simulation
const handleLiveIntervention = async () => {
  if (!props.simulationId || !liveInterventionText.value.trim()) return
  liveInterviewLoading.value = true
  liveInterviewResult.value = null
  try {
    const res = await interveneLive(
      props.simulationId,
      selectedChatAgent.value,
      { intervention_text: liveInterventionText.value.trim() }
    )
    if (res.success && res.data) {
      const r = res.data
      liveInterviewResult.value = r
      if (r.stance_changed) {
        changedAgentIds.value = new Set([...changedAgentIds.value, selectedChatAgent.value])
        const target = agentProfiles.value.find(a => a.id === selectedChatAgent.value)
        if (target) target.stance = r.stance_after
      }
      interventionHistory.value.push({
        agentName: selectedAgentName.value,
        before: r.stance_before,
        after: r.stance_after,
        text: liveInterventionText.value.trim().slice(0, 50),
      })
      addLog(`✓ Intervention applied to ${selectedAgentName.value}: ${r.stance_before} → ${r.stance_after}`)
      if (r.propagation_count > 0) {
        addLog(`  ↳ Propagated to ${r.propagation_count} affiliated agent${r.propagation_count > 1 ? 's' : ''}`)
      }
    } else {
      addLog(`Intervention failed: ${res.error || 'Unknown error'}`)
    }
  } catch (err) {
    addLog(`Intervention exception: ${err.message}`)
  } finally {
    liveInterviewLoading.value = false
  }
}

// Stop simulation
const handleStopSimulation = async () => {
  if (!props.simulationId) return

  isStopping.value = true
  addLog('Stopping simulation...')

  try {
    const res = await stopSimulation({ simulation_id: props.simulationId })

    if (res.success) {
      addLog('✓ Simulation stopped')
      phase.value = 2
      stopPolling()
      emit('update-status', 'completed')
    } else {
      addLog(`Stop failed: ${res.error || 'Unknown error'}`)
    }
  } catch (err) {
    addLog(`Stop exception: ${err.message}`)
  } finally {
    isStopping.value = false
  }
}

// Polling status
let statusTimer = null
let detailTimer = null

const startStatusPolling = () => {
  statusTimer = setInterval(fetchRunStatus, 2000)
}

const startDetailPolling = () => {
  detailTimer = setInterval(fetchRunStatusDetail, 3000)
}

const stopPolling = () => {
  if (statusTimer) {
    clearInterval(statusTimer)
    statusTimer = null
  }
  if (detailTimer) {
    clearInterval(detailTimer)
    detailTimer = null
  }
}

const prevRound = ref(0)

const fetchRunStatus = async () => {
  if (!props.simulationId) return

  try {
    const res = await getRunStatus(props.simulationId)

    if (res.success && res.data) {
      const data = res.data
      runStatus.value = data

      if (data.current_round > prevRound.value) {
        addLog(`[Opinion Space] R${data.current_round}/${data.total_rounds} | T:${data.simulated_hours || 0}h | A:${data.simulation_actions_count || 0}`)
        prevRound.value = data.current_round
      }

      const isCompleted = data.runner_status === 'completed' || data.runner_status === 'stopped' || data.simulation_completed === true

      if (isCompleted) {
        addLog('✓ Simulation completed')
        phase.value = 2
        stopPolling()
        emit('update-status', 'completed')
      }
    }
  } catch (err) {
    console.warn('Failed to fetch run status:', err)
  }
}

const fetchRunStatusDetail = async () => {
  if (!props.simulationId) return

  try {
    const res = await getRunStatusDetail(props.simulationId)

    if (res.success && res.data) {
      // Use all_actions to get complete action list
      const serverActions = res.data.all_actions || []

      // Incrementally add new actions (with deduplication)
      let newActionsAdded = 0
      serverActions.forEach(action => {
        // Generate unique ID
        const actionId = action.id || `${action.timestamp}-${action.platform}-${action.agent_id}-${action.action_type}`

        if (!actionIds.value.has(actionId)) {
          actionIds.value.add(actionId)
          allActions.value.push({
            ...action,
            _uniqueId: actionId
          })
          newActionsAdded++
        }
      })

      // Don't auto-scroll, let user freely view timeline
      // New actions will be appended at the bottom
    }
  } catch (err) {
    console.warn('Failed to fetch detailed status:', err)
  }
}

// Helpers
const getActionTypeLabel = (type) => {
  const labels = {
    // AgentSociety OpinionCaptureBlock
    'EXPRESS_OPINION':    'OPINION',
    'RESPOND_TO_OPINION': 'RESPOND',
    'SEARCH_TOPIC':       'SEARCH',
    'OBSERVE':            'OBSERVE',
    'NON_PARTICIPATION':  'NOT ENGAGING',
    // OASIS legacy
    'CREATE_POST':   'POST',
    'REPOST':        'REPOST',
    'LIKE_POST':     'LIKE',
    'CREATE_COMMENT':'COMMENT',
    'LIKE_COMMENT':  'LIKE',
    'FOLLOW':        'FOLLOW',
    'SEARCH_POSTS':  'SEARCH',
    'QUOTE_POST':    'QUOTE',
    'UPVOTE_POST':   'UPVOTE',
    'DOWNVOTE_POST': 'DOWNVOTE',
    'DO_NOTHING':    'IDLE',
  }
  return labels[type] || type || 'UNKNOWN'
}

const getActionTypeClass = (type) => {
  const classes = {
    // AgentSociety OpinionCaptureBlock
    'EXPRESS_OPINION':    'badge-post',
    'RESPOND_TO_OPINION': 'badge-comment',
    'SEARCH_TOPIC':       'badge-meta',
    'OBSERVE':            'badge-idle',
    'NON_PARTICIPATION':  'badge-not-engaging',
    // OASIS legacy
    'CREATE_POST':   'badge-post',
    'REPOST':        'badge-action',
    'LIKE_POST':     'badge-action',
    'CREATE_COMMENT':'badge-comment',
    'LIKE_COMMENT':  'badge-action',
    'QUOTE_POST':    'badge-post',
    'FOLLOW':        'badge-meta',
    'SEARCH_POSTS':  'badge-meta',
    'UPVOTE_POST':   'badge-action',
    'DOWNVOTE_POST': 'badge-action',
    'DO_NOTHING':    'badge-idle',
  }
  return classes[type] || 'badge-default'
}

// Check if action is an engaging action (expressing/responding) vs passive
const isEngagingAction = (type) => {
  return ['EXPRESS_OPINION', 'RESPOND_TO_OPINION'].includes(type)
}

const truncateContent = (content, maxLength = 100) => {
  if (!content) return ''
  if (content.length > maxLength) return content.substring(0, maxLength) + '...'
  return content
}

const formatActionTime = (timestamp) => {
  if (!timestamp) return ''
  try {
    return new Date(timestamp).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ''
  }
}

const handleNextStep = async () => {
  if (!props.simulationId) {
    addLog('Error: Missing simulationId')
    return
  }

  if (isGeneratingReport.value) {
    addLog('Report generation request sent, please wait...')
    return
  }

  isGeneratingReport.value = true
  addLog('Starting report generation...')

  try {
    const res = await generateReport({
      simulation_id: props.simulationId,
      force_regenerate: true
    })

    if (res.success && res.data) {
      const reportId = res.data.report_id
      addLog(`✓ Report generation task started: ${reportId}`)

      // Navigate to report page
      router.push({ name: 'Report', params: { reportId } })
    } else {
      addLog(`✗ Failed to start report generation: ${res.error || 'Unknown error'}`)
      isGeneratingReport.value = false
    }
  } catch (err) {
    addLog(`✗ Report generation exception: ${err.message}`)
    isGeneratingReport.value = false
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
  addLog('Step3 Simulation initialization')
  if (props.simulationId) {
    doStartSimulation()
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.simulation-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #FFFFFF;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  overflow: hidden;
}

/* --- Control Bar --- */
.control-bar {
  background: #FFF;
  padding: 12px 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #EAEAEA;
  z-index: 10;
  height: 64px;
}

.status-group {
  display: flex;
  gap: 12px;
}

/* Platform Status Cards */
.platform-status {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 12px;
  border-radius: 4px;
  background: #FAFAFA;
  border: 1px solid #EAEAEA;
  opacity: 0.7;
  transition: all 0.3s;
  min-width: 140px;
  position: relative;
  cursor: pointer;
}

.platform-status.active {
  opacity: 1;
  border-color: #333;
  background: #FFF;
}

.platform-status.completed {
  opacity: 1;
  border-color: #1A936F;
  background: #F2FAF6;
}

/* Actions Tooltip */
.actions-tooltip {
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  margin-top: 8px;
  padding: 10px 14px;
  background: #000;
  color: #FFF;
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  opacity: 0;
  visibility: hidden;
  transition: all 0.2s ease;
  z-index: 100;
  min-width: 180px;
  pointer-events: none;
}

.actions-tooltip::before {
  content: '';
  position: absolute;
  top: -6px;
  left: 50%;
  transform: translateX(-50%);
  border-left: 6px solid transparent;
  border-right: 6px solid transparent;
  border-bottom: 6px solid #000;
}

.platform-status:hover .actions-tooltip {
  opacity: 1;
  visibility: visible;
}

.tooltip-title {
  font-size: 10px;
  font-weight: 600;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 8px;
}

.tooltip-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tooltip-action {
  font-size: 10px;
  font-weight: 600;
  padding: 3px 8px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 2px;
  color: #FFF;
  letter-spacing: 0.03em;
}

.platform-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 2px;
}

.platform-name {
  font-size: 11px;
  font-weight: 700;
  color: #000;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.platform-status.opinion-space .platform-icon { color: #000; }

.platform-stats {
  display: flex;
  gap: 10px;
}

.stat {
  display: flex;
  align-items: baseline;
  gap: 3px;
}

.stat-label {
  font-size: 8px;
  color: #999;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat-value {
  font-size: 11px;
  font-weight: 600;
  color: #333;
}

.stat-total, .stat-unit {
  font-size: 9px;
  color: #999;
  font-weight: 400;
}

.status-badge {
  margin-left: auto;
  color: #1A936F;
  display: flex;
  align-items: center;
}

/* Action Button */
.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  font-size: 13px;
  font-weight: 600;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: #f0f0f0;
  color: #333;
}

.action-btn:hover {
  background: #e0e0e0;
}

.action-btn.active {
  background: #4CAF50;
  color: white;
}

.action-btn.primary {
  background: #000;
  color: #FFF;
}

.action-btn.primary:hover:not(:disabled) {
  background: #333;
}

.action-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

/* Chat Toggle Button */
.chat-toggle-wrapper {
  display: inline-block;
}

.chat-toggle-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  font-size: 13px;
  font-weight: 600;
  border: 2px solid #4CAF50;
  border-radius: 6px;
  background: transparent;
  color: #4CAF50;
  cursor: pointer;
  transition: all 0.25s ease;
}

.chat-toggle-btn:hover {
  background: #4CAF50;
  color: white;
}

.chat-toggle-btn.active {
  background: #4CAF50;
  color: white;
}

.chat-toggle-btn .chat-icon {
  font-size: 16px;
}

.chat-toggle-btn .close-icon {
  font-size: 18px;
  font-weight: bold;
  margin-left: 4px;
}

/* Chat Panel Container */
.chat-panel-container {
  background: white;
  border-bottom: 1px solid #E0E0E0;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  padding: 16px 24px;
}

.chat-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #F0F0F0;
}

.chat-panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 15px;
  color: #333;
}

.panel-icon {
  font-size: 18px;
}

.archetype-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  background: #F0F0F0;
  color: #666;
  border-radius: 10px;
  text-transform: lowercase;
}

.chat-close-btn {
  background: none;
  border: none;
  font-size: 24px;
  color: #999;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.chat-close-btn:hover {
  color: #333;
}

/* Agent Selector */
.chat-agent-selector {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.chat-agent-selector label {
  font-size: 13px;
  color: #666;
  font-weight: 500;
}

.agent-select {
  flex: 1;
  max-width: 300px;
  padding: 8px 12px;
  font-size: 14px;
  border: 1px solid #DDD;
  border-radius: 6px;
  background: white;
  cursor: pointer;
}

.agent-select:focus {
  outline: none;
  border-color: #4CAF50;
  box-shadow: 0 0 0 2px rgba(76, 175, 80, 0.1);
}

/* Chat Messages */
.chat-messages-container {
  background: #F9F9F9;
  border-radius: 8px;
  padding: 12px;
  min-height: 150px;
  max-height: 250px;
  overflow-y: auto;
}

.chat-messages-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.chat-empty-state {
  text-align: center;
  padding: 30px;
  color: #888;
}

.chat-empty-state p {
  margin: 4px 0;
}

.chat-empty-state .hint {
  font-size: 12px;
  color: #AAA;
}

.chat-message {
  display: flex;
  flex-direction: column;
  max-width: 75%;
}

.chat-message.user {
  align-self: flex-end;
  align-items: flex-end;
}

.chat-message.assistant {
  align-self: flex-start;
  align-items: flex-start;
}

.message-bubble {
  padding: 10px 14px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.4;
}

.chat-message.user .message-bubble {
  background: #4CAF50;
  color: white;
  border-bottom-right-radius: 4px;
}

.chat-message.assistant .message-bubble {
  background: white;
  color: #333;
  border: 1px solid #E0E0E0;
  border-bottom-left-radius: 4px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.message-time {
  font-size: 10px;
  color: #AAA;
  margin-top: 4px;
}

/* Typing Indicator */
.chat-typing-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: white;
  border-radius: 12px;
  border: 1px solid #E0E0E0;
  width: fit-content;
}

.typing-dot {
  width: 6px;
  height: 6px;
  background: #AAA;
  border-radius: 50%;
  animation: typingBounce 1.4s infinite ease-in-out;
}

.typing-dot:nth-child(1) { animation-delay: 0s; }
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes typingBounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-6px); }
}

.typing-text {
  font-size: 12px;
  color: #888;
  margin-left: 4px;
}

/* Chat Error */
.chat-error-banner {
  background: #FFEBEE;
  color: #C62828;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}

/* Chat Input */
.chat-input-container {
  display: flex;
  gap: 10px;
  margin-top: 12px;
}

.chat-input-field {
  flex: 1;
  padding: 12px 16px;
  font-size: 14px;
  border: 1px solid #DDD;
  border-radius: 24px;
  outline: none;
  transition: border-color 0.2s;
}

.chat-input-field:focus {
  border-color: #4CAF50;
}

.chat-input-field:disabled {
  background: #F5F5F5;
}

.chat-send-btn {
  padding: 10px 24px;
  background: #4CAF50;
  color: white;
  border: none;
  border-radius: 24px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
  min-width: 80px;
}

.chat-send-btn:hover:not(:disabled) {
  background: #43A047;
}

.chat-send-btn:disabled {
  background: #CCC;
  cursor: not-allowed;
}

.btn-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid white;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Slide Transition */
.slide-fade-enter-active {
  transition: all 0.3s ease-out;
}

.slide-fade-leave-active {
  transition: all 0.2s ease-in;
}

.slide-fade-enter-from,
.slide-fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

/* --- Main Content Area --- */
.main-content-area {
  flex: 1;
  overflow-y: auto;
  position: relative;
  background: #FFF;
}

/* Timeline Header */
.timeline-header {
  position: sticky;
  top: 0;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(8px);
  padding: 12px 24px;
  border-bottom: 1px solid #EAEAEA;
  z-index: 5;
  display: flex;
  justify-content: center;
}

.timeline-stats {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 11px;
  color: #666;
  background: #F5F5F5;
  padding: 4px 12px;
  border-radius: 20px;
}

.total-count {
  font-weight: 600;
  color: #333;
}

.platform-breakdown {
  display: flex;
  align-items: center;
  gap: 8px;
}

.breakdown-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.breakdown-divider { color: #DDD; }
.breakdown-item.opinion-space { color: #000; }

/* --- Timeline Feed --- */
.timeline-feed {
  padding: 24px 0;
  position: relative;
  min-height: 100%;
  max-width: 900px;
  margin: 0 auto;
}

.timeline-axis {
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 1px;
  background: #EAEAEA; /* Cleaner line */
  transform: translateX(-50%);
}

.timeline-item {
  display: flex;
  justify-content: center;
  margin-bottom: 32px;
  position: relative;
  width: 100%;
}

.timeline-marker {
  position: absolute;
  left: 50%;
  top: 24px;
  width: 10px;
  height: 10px;
  background: #FFF;
  border: 1px solid #CCC;
  border-radius: 50%;
  transform: translateX(-50%);
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
}

.marker-dot {
  width: 4px;
  height: 4px;
  background: #CCC;
  border-radius: 50%;
}

.timeline-item.opinion-space .marker-dot { background: #000; }
.timeline-item.opinion-space .timeline-marker { border-color: #000; }

/* Card Layout */
.timeline-card {
  width: calc(100% - 48px);
  background: #FFF;
  border-radius: 2px;
  padding: 16px 20px;
  border: 1px solid #EAEAEA;
  box-shadow: 0 2px 10px rgba(0,0,0,0.02);
  position: relative;
  transition: all 0.2s;
}

.timeline-card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
  border-color: #DDD;
}

/* Opinion Space timeline item */
.timeline-item.opinion-space {
  justify-content: flex-start;
  padding-right: 50%;
}
.timeline-item.opinion-space .timeline-card {
  margin-left: auto;
  margin-right: 32px; /* Gap from axis */
}

/* Card Content Styles */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #F5F5F5;
}

.agent-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.avatar-placeholder {
  width: 24px;
  height: 24px;
  background: #000;
  color: #FFF;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}

.agent-name {
  font-size: 13px;
  font-weight: 600;
  color: #000;
}

.chat-hint {
  margin-left: 6px;
  font-size: 14px;
  opacity: 0;
  transition: opacity 0.2s;
}

.timeline-item:hover .chat-hint {
  opacity: 1;
}

.agent-custom-badge {
  margin-left: 4px;
  font-size: 11px;
  color: #2E7D32;
}

.header-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.platform-indicator {
  color: #999;
  display: flex;
  align-items: center;
}

.action-badge {
  font-size: 9px;
  padding: 2px 6px;
  border-radius: 2px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border: 1px solid transparent;
}

/* Monochromatic Badges */
.badge-post { background: #F0F0F0; color: #333; border-color: #E0E0E0; }
.badge-comment { background: #F0F0F0; color: #666; border-color: #E0E0E0; }
.badge-action { background: #FFF; color: #666; border: 1px solid #E0E0E0; }
.badge-meta { background: #FAFAFA; color: #999; border: 1px dashed #DDD; }
.badge-idle { opacity: 0.5; }
.badge-not-engaging { background: #FEE; color: #C00; border: 1px solid #ECC; }

.content-text {
  font-size: 13px;
  line-height: 1.6;
  color: #333;
  margin-bottom: 10px;
}

.content-text.main-text {
  font-size: 14px;
  color: #000;
}

/* Info Blocks (Quote, Repost, etc) */
.quoted-block, .repost-content {
  background: #F9F9F9;
  border: 1px solid #EEE;
  padding: 10px 12px;
  border-radius: 2px;
  margin-top: 8px;
  font-size: 12px;
  color: #555;
}

.quote-header, .repost-info, .like-info, .search-info, .follow-info, .vote-info, .idle-info, .observe-info, .comment-context {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  font-size: 11px;
  color: #666;
}

/* Non-Engagement Info */
.non-engagement-info {
  padding: 10px 12px;
  background: #FEF9F9;
  border: 1px solid #F0D9D9;
  border-radius: 4px;
  margin-top: 4px;
}

.engagement-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 2px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin-bottom: 8px;
}

.engagement-badge.not-engaging {
  background: #FDECEA;
  color: #B33;
  border: 1px solid #ECC;
}

.engagement-badge.not-engaging svg {
  color: #B33;
}

.reason-block {
  font-size: 12px;
  color: #555;
  margin-bottom: 8px;
  line-height: 1.5;
}

.reason-label {
  font-weight: 600;
  color: #888;
  margin-right: 4px;
}

.reason-text {
  font-style: italic;
  color: #666;
}

.thought-block {
  font-size: 12px;
  color: #555;
  margin-bottom: 8px;
  line-height: 1.5;
}

.thought-label {
  font-weight: 600;
  color: #888;
  margin-right: 4px;
}

.thought-text {
  font-style: italic;
  color: #555;
}

.category-tag {
  display: inline-block;
}

.category-label {
  font-size: 9px;
  font-weight: 600;
  padding: 2px 6px;
  background: #EEE;
  color: #777;
  border-radius: 2px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.icon-small {
  color: #999;
}
.icon-small.filled {
  color: #999; /* Keep icons neutral unless highlighted */
}

.search-query {
  font-family: 'JetBrains Mono', monospace;
  background: #F0F0F0;
  padding: 0 4px;
  border-radius: 2px;
}

.card-footer {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
  font-size: 10px;
  color: #BBB;
  font-family: 'JetBrains Mono', monospace;
}

/* Waiting State */
.waiting-state {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  color: #CCC;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.pulse-ring {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid #EAEAEA;
  animation: ripple 2s infinite;
}

@keyframes ripple {
  0% { transform: scale(0.8); opacity: 1; border-color: #CCC; }
  100% { transform: scale(2.5); opacity: 0; border-color: #EAEAEA; }
}

/* Animation */
.timeline-item-enter-active,
.timeline-item-leave-active {
  transition: all 0.4s cubic-bezier(0.165, 0.84, 0.44, 1);
}

.timeline-item-enter-from {
  opacity: 0;
  transform: translateY(20px);
}

.timeline-item-leave-to {
  opacity: 0;
}

/* Logs */
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
  color: #666;
}

.log-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  height: 100px;
  overflow-y: auto;
  padding-right: 4px;
}

.log-content::-webkit-scrollbar { width: 4px; }
.log-content::-webkit-scrollbar-thumb { background: #333; border-radius: 2px; }

.log-line {
  font-size: 11px;
  display: flex;
  gap: 12px;
  line-height: 1.5;
}

.log-time { color: #555; min-width: 75px; }
.log-msg { color: #BBB; word-break: break-all; }
.mono { font-family: 'JetBrains Mono', monospace; }

/* Inline Chat Panel */
.chat-panel-inline {
  background: #f8f9fa;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  margin: 10px 20px;
  padding: 15px;
}

.chat-header-inline {
  font-weight: 600;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.agent-select-dropdown {
  padding: 4px 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 14px;
  background: white;
  cursor: pointer;
}

.agent-select-dropdown:hover {
  border-color: #999;
}

.chat-messages-inline {
  max-height: 200px;
  overflow-y: auto;
  margin-bottom: 10px;
}

.chat-msg-inline {
  padding: 8px 12px;
  border-radius: 8px;
  margin-bottom: 8px;
  max-width: 80%;
}

.chat-msg-inline.user {
  background: #007bff;
  color: white;
  margin-left: auto;
}

.chat-msg-inline.assistant {
  background: #e9ecef;
  color: #333;
}

.chat-error-inline {
  color: #dc3545;
  font-size: 12px;
  margin: 8px 0;
}

.chat-loading-inline {
  color: #666;
  font-size: 13px;
  font-style: italic;
  padding: 8px;
}

.loading-dots span {
  animation: loadingDots 1.4s infinite;
}

.loading-dots span:nth-child(2) {
  animation-delay: 0.2s;
}

.loading-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes loadingDots {
  0%, 20% { opacity: 0; }
  40% { opacity: 1; }
  100% { opacity: 0; }
}

.chat-input-inline {
  display: flex;
  gap: 8px;
}

.chat-input-inline input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.chat-input-inline button {
  padding: 8px 16px;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.chat-input-inline button:disabled {
  background: #ccc;
  cursor: not-allowed;
}

/* Loading spinner for button */
.loading-spinner-small {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #FFF;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-right: 6px;
}

/* Pause / Resume button variants */
.action-btn.warning {
  background: transparent;
  color: #FF9800;
  border: 1px solid #FF9800;
}
.action-btn.warning:hover:not(:disabled) {
  background: #FF9800;
  color: #FFF;
}
.action-btn.success {
  background: transparent;
  color: #4CAF50;
  border: 1px solid #4CAF50;
}
.action-btn.success:hover:not(:disabled) {
  background: #4CAF50;
  color: #FFF;
}
.action-btn.primary {
  background: transparent;
  color: #1E9E5A;
  border: 1px solid #1E9E5A;
}
.action-btn.primary:hover:not(:disabled) {
  background: #1E9E5A;
  color: #FFF;
}

/* Live Intervention Panel */
.live-intervention-panel {
  position: absolute;
  top: 64px;
  right: 16px;
  width: 400px;
  background: #0D0D0D;
  border: 1px solid #333;
  border-radius: 4px;
  padding: 0;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  z-index: 100;
  overflow: hidden;
}

.intervention-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #1A1A1A;
  border-bottom: 1px solid #333;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-icon {
  color: #1E9E5A;
  font-size: 12px;
}

.header-title {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  font-size: 11px;
  letter-spacing: 1px;
  color: #1E9E5A;
}

.paused-badge {
  background: #1E9E5A;
  color: #FFF;
  padding: 2px 10px;
  border-radius: 2px;
  font-size: 10px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.5px;
}

.intervention-hint {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #888;
  margin: 0;
  padding: 12px 16px;
  line-height: 1.6;
  border-bottom: 1px solid #222;
}

.intervention-field {
  padding: 12px 16px;
}

.field-label {
  display: block;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #666;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
  text-transform: uppercase;
}

.agent-select {
  width: 100%;
  padding: 10px 12px;
  background: #1A1A1A;
  border: 1px solid #333;
  border-radius: 2px;
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  color: #FFF;
  outline: none;
  cursor: pointer;
}

.agent-select:focus {
  border-color: #1E9E5A;
}

.agent-select option {
  background: #1A1A1A;
  color: #FFF;
}

.intervention-textarea {
  width: 100%;
  padding: 10px 12px;
  background: #1A1A1A;
  border: 1px solid #333;
  border-radius: 2px;
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  color: #FFF;
  resize: vertical;
  outline: none;
  line-height: 1.6;
}

.intervention-textarea:focus {
  border-color: #1E9E5A;
}

.intervention-textarea::placeholder {
  color: #555;
}

.intervention-btn {
  width: calc(100% - 32px);
  margin: 0 16px 16px;
  padding: 12px;
  background: #1E9E5A;
  color: #FFF;
  border: none;
  border-radius: 2px;
  font-size: 12px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.5px;
  cursor: pointer;
  transition: background 0.2s;
}

.intervention-btn:hover:not(:disabled) {
  background: #E03E00;
}

.intervention-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.intervention-result {
  margin: 0 16px 16px;
  padding: 14px;
  background: #1A1A1A;
  border-radius: 2px;
  border-left: 3px solid #4CAF50;
}

.result-agent {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 700;
  color: #1E9E5A;
  margin-bottom: 8px;
}

.result-response {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  line-height: 1.6;
  color: #BBB;
  margin-bottom: 12px;
}

.result-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.stance-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.stance-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #666;
  text-transform: uppercase;
}

.change-arrow {
  color: #666;
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  font-style: italic;
}

.propagation-notice {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #4CAF50;
  background: rgba(76, 175, 80, 0.1);
  padding: 3px 10px;
  border-radius: 2px;
  border: 1px solid rgba(76, 175, 80, 0.2);
}

.stance-badge {
  padding: 3px 10px;
  border-radius: 2px;
  font-size: 10px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stance-support { background: rgba(76, 175, 80, 0.15); color: #4CAF50; border: 1px solid rgba(76, 175, 80, 0.3); }
.stance-neutral { background: rgba(255, 255, 255, 0.05); color: #999; border: 1px solid rgba(255, 255, 255, 0.1); }
.stance-concerned { background: rgba(255, 152, 0, 0.15); color: #FF9800; border: 1px solid rgba(255, 152, 0, 0.3); }
.stance-oppose { background: rgba(244, 67, 54, 0.15); color: #F44336; border: 1px solid rgba(244, 67, 54, 0.3); }
.stance-resist { background: rgba(233, 30, 99, 0.15); color: #E91E63; border: 1px solid rgba(233, 30, 99, 0.3); }

/* ─── Bottom-docked intervention bar ─────────────────────────────────── */
.intervention-dock {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  background: #0D0D0D;
  border-top: 2px solid #1E9E5A;
  padding: 14px 20px;
  z-index: 200;
  box-shadow: 0 -8px 32px rgba(0,0,0,0.5);
}

.dock-status {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.dock-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #1E9E5A;
  animation: dock-pulse 1.2s infinite;
}
@keyframes dock-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.dock-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.5px;
  color: #1E9E5A;
}

.dock-hint {
  font-size: 11px;
  color: #666;
  margin-left: auto;
}

.dock-row {
  display: flex;
  gap: 8px;
  align-items: stretch;
}

.dock-select {
  background: #1A1A1A;
  border: 1px solid #333;
  color: #DDD;
  padding: 8px 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  min-width: 280px;
  max-width: 320px;
  cursor: pointer;
}

.dock-select:focus { outline: none; border-color: #1E9E5A; }

.dock-input {
  flex: 1;
  background: #1A1A1A;
  border: 1px solid #333;
  color: #fff;
  padding: 8px 12px;
  font-size: 13px;
  font-family: inherit;
}

.dock-input:focus { outline: none; border-color: #1E9E5A; }
.dock-input::placeholder { color: #555; font-style: italic; }

.dock-apply-btn,
.dock-resume-btn {
  padding: 8px 16px;
  border: none;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.5px;
  cursor: pointer;
  white-space: nowrap;
}

.dock-apply-btn {
  background: #1E9E5A;
  color: #fff;
}
.dock-apply-btn:hover:not(:disabled) { background: #FF5722; }
.dock-apply-btn:disabled { background: #333; color: #666; cursor: not-allowed; }

.dock-resume-btn {
  background: #4CAF50;
  color: #fff;
}
.dock-resume-btn:hover:not(:disabled) { background: #5BBA60; }
.dock-resume-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.dock-result {
  margin-top: 10px;
  padding: 10px 12px;
  background: #1A1A1A;
  border-left: 3px solid #1E9E5A;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
}

.dock-result-agent {
  color: #DDD;
  font-weight: 600;
}

.dock-arrow { color: #888; }

.dock-prop {
  color: #FFD700;
  font-size: 11px;
}

.dock-response {
  color: #AAA;
  font-style: italic;
  flex-basis: 100%;
  margin-top: 4px;
  line-height: 1.4;
}

/* Slide-up transition */
.slide-up-enter-active, .slide-up-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.slide-up-enter-from, .slide-up-leave-to {
  transform: translateY(100%);
  opacity: 0;
}

/* Add bottom padding to scroll content so it doesn't hide behind the dock */
.simulation-panel { padding-bottom: 0; }

.pause-error-banner {
  margin-left: 12px;
  padding: 6px 10px;
  background: rgba(244, 67, 54, 0.12);
  border: 1px solid rgba(244, 67, 54, 0.4);
  border-radius: 3px;
  color: #F44336;
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
}

/* ─── Policy Workbench ─────────────────────────────────────────────────── */
.policy-workbench {
  position: absolute;
  top: 64px;
  right: 16px;
  width: 640px;
  max-height: calc(100vh - 120px);
  overflow-y: auto;
  background: #0D0D0D;
  border: 1px solid #333;
  border-radius: 4px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  z-index: 100;
}

.wb-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: #161616;
  border-bottom: 1px solid #2A2A2A;
  gap: 12px;
  flex-wrap: wrap;
}

.wb-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.wb-icon { color: #1E9E5A; font-size: 11px; }

.wb-title {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.5px;
  color: #1E9E5A;
}

.wb-round {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #555;
}

.wb-tabs {
  display: flex;
  gap: 4px;
}

.wb-tab {
  padding: 4px 12px;
  border-radius: 2px;
  border: 1px solid #333;
  background: transparent;
  color: #666;
  font-size: 11px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}

.wb-tab:hover { color: #ccc; border-color: #555; }
.wb-tab.active { background: #1E9E5A; border-color: #1E9E5A; color: #fff; }

.wb-hint {
  font-size: 11px;
  color: #555;
  margin: 0 0 12px;
  padding: 0 16px;
  padding-top: 12px;
}

/* Stance Map */
.wb-stance-map { padding: 0 16px 16px; }

.stance-columns {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.stance-col {
  flex: 1;
  min-width: 0;
}

.stance-col-head {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.stance-count {
  background: rgba(255,255,255,0.06);
  border-radius: 2px;
  padding: 1px 5px;
  font-size: 9px;
  color: #666;
}

.stance-empty { color: #333; font-size: 11px; text-align: center; padding: 8px 0; }

.sac {
  background: #111;
  border: 1px solid #222;
  border-left: 3px solid transparent;
  border-radius: 3px;
  padding: 6px 8px;
  margin-bottom: 4px;
  cursor: pointer;
  transition: background 0.1s;
}

.sac:hover { background: #1A1A1A; }
.sac-selected { background: #1C1C1C; border-color: #1E9E5A !important; }
.sac-changed { position: relative; }
.sac-changed::after {
  content: '';
  position: absolute;
  top: 3px; right: 3px;
  width: 5px; height: 5px;
  border-radius: 50%;
  background: #FFD700;
}

.sac-name {
  font-size: 10px;
  font-weight: 600;
  color: #DDD;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sac-role {
  font-size: 9px;
  color: #555;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-transform: capitalize;
  margin-top: 2px;
}

.sac-badge {
  font-size: 8px;
  color: #FFD700;
  font-family: 'JetBrains Mono', monospace;
  margin-top: 2px;
}

/* Target mode */
.wb-target { padding: 12px 16px 16px; }

.selected-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: #1A1A1A;
  border: 1px solid #333;
  border-radius: 3px;
  margin-bottom: 12px;
}

.chip-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.chip-name { font-size: 12px; color: #DDD; font-weight: 600; flex: 1; }
.chip-stance { font-size: 10px; color: #666; font-family: 'JetBrains Mono', monospace; }

.chip-clear {
  background: transparent;
  border: none;
  color: #555;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 0;
}
.chip-clear:hover { color: #ccc; }

.no-target-hint { font-size: 11px; color: #444; margin-bottom: 10px; font-style: italic; }

.stance-shift {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.shift-arrow { color: #555; font-size: 12px; }

.no-change { font-size: 10px; color: #555; margin-left: 4px; }

/* Broadcast mode */
.wb-broadcast { padding: 12px 16px 16px; }

.broadcast-preview {
  font-size: 11px;
  color: #FF9800;
  margin-bottom: 10px;
  font-family: 'JetBrains Mono', monospace;
}

.broadcast-results { margin-top: 14px; }

.br-summary {
  font-size: 11px;
  color: #888;
  margin-bottom: 8px;
  font-family: 'JetBrains Mono', monospace;
}

.br-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  border-bottom: 1px solid #1A1A1A;
  font-size: 11px;
}

.br-name { flex: 1; color: #BBB; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.br-error { color: #F44336; font-size: 10px; font-family: 'JetBrains Mono', monospace; }

/* Session history */
.wb-history {
  padding: 12px 16px;
  border-top: 1px solid #1E1E1E;
  background: #0A0A0A;
}

.history-label {
  font-size: 9px;
  font-family: 'JetBrains Mono', monospace;
  color: #444;
  letter-spacing: 1px;
  text-transform: uppercase;
  margin-bottom: 8px;
}

.history-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  font-size: 10px;
  border-bottom: 1px solid #111;
}

.history-agent { color: #888; min-width: 80px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.history-text { color: #444; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-style: italic; }
</style>