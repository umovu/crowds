<template>
  <!-- Stage 1: Small pop-out menu -->
  <Transition name="menu-pop">
    <div v-if="menuOpen" class="profile-scrim" @click="closeMenu"></div>
  </Transition>
  <Transition name="menu-pop">
    <div v-if="menuOpen" class="profile-menu">
      <div class="menu-head">
        <div class="menu-head-avatar">JS</div>
        <div class="menu-head-info">
          <span class="menu-head-name">Jabu Swartbooi</span>
          <span class="menu-head-plan">{{ isPaid ? 'Paid plan' : 'Free plan' }}</span>
        </div>
      </div>
      <div class="menu-list">
        <button class="menu-option" @click="openFullpage('profile')">
          <span class="menu-option-icon">👤</span>
          <span class="menu-option-label">Profile</span>
          <span class="menu-option-arrow">→</span>
        </button>
        <button class="menu-option" @click="openFullpage('dashboard')">
          <span class="menu-option-icon">📊</span>
          <span class="menu-option-label">Dashboard</span>
          <span class="menu-option-arrow">→</span>
        </button>
        <button class="menu-option" @click="openFullpage('billing')">
          <span class="menu-option-icon">💳</span>
          <span class="menu-option-label">Billing</span>
          <span class="menu-option-arrow">→</span>
        </button>
        <button class="menu-option" @click="openFullpage('keys')">
          <span class="menu-option-icon">🔑</span>
          <span class="menu-option-label">API Keys</span>
          <span class="menu-option-arrow">→</span>
        </button>
      </div>
    </div>
  </Transition>

  <!-- Stage 2: Full-page modal -->
  <Transition name="modal-rise">
    <div v-if="modalOpen" class="fullpage-scrim" @click="closeFullpage"></div>
  </Transition>
  <Transition name="modal-rise">
    <div v-if="modalOpen" class="fullpage-modal">
      <!-- Tab rail -->
      <div class="modal-tabs">
        <div class="modal-tabs-head">Account</div>
        <button
          v-for="tab in tabs" :key="tab.id"
          class="modal-tab"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
        >
          <span class="modal-tab-icon">{{ tab.icon }}</span> {{ tab.label }}
        </button>
      </div>

      <!-- Body -->
      <div class="modal-body">
        <div class="modal-body-head">
          <div class="modal-body-title">{{ activeTabLabel }}</div>
          <button class="modal-close" @click="closeFullpage">×</button>
        </div>

        <!-- Profile panel -->
        <div v-if="activeTab === 'profile'" class="tab-panel">
          <div class="field-group">
            <div class="field-row">
              <div class="field">
                <label class="field-label">First name</label>
                <input class="field-input" type="text" value="Jabu">
              </div>
              <div class="field">
                <label class="field-label">Surname</label>
                <input class="field-input" type="text" value="Swartbooi">
              </div>
            </div>
            <div class="field">
              <label class="field-label">Email</label>
              <input class="field-input" type="email" value="jabu@example.com">
            </div>
            <div class="field">
              <label class="field-label">Display name</label>
              <input class="field-input" type="text" value="jabus">
              <span class="field-help">Shown on shared sims and panel reports</span>
            </div>
          </div>
          <div class="modal-actions">
            <button class="btn" @click="closeFullpage">Cancel</button>
            <button class="btn primary">Save changes</button>
          </div>
        </div>

        <!-- Dashboard panel -->
        <div v-if="activeTab === 'dashboard'" class="tab-panel">
          <DashboardPanel @open-sim="onOpenSim" />
        </div>

        <!-- Billing panel -->
        <div v-if="activeTab === 'billing'" class="tab-panel">
          <div class="current-plan-banner" :class="{ cancelled: isCancelled }">
            <div class="cpb-left">
              <span class="cpb-label">{{ isCancelled ? 'Subscription cancelled' : 'Current plan' }}</span>
              <span class="cpb-name">{{ isPaid ? 'Pro — R80/mo' : 'Free' }}</span>
            </div>
            <span class="cpb-right">
              {{ isCancelled
                ? 'Access continues until the end of your paid month'
                : (isPaid ? 'unlimited panels + simulations'
                          : `${status?.panel_used ?? 0} / 1 panel · ${status?.sim_used ?? 0} / ${status?.sim_limit ?? 3} trial sims used`) }}
            </span>
          </div>
          <div class="plan-grid">
            <div class="plan-card-opt" :class="{ current: !isPaid }">
              <div class="pco-head"><span class="pco-name">Free</span><span class="pco-price">R0/mo</span></div>
              <ul class="pco-features">
                <li>1 panel (focus group)</li>
                <li>Full reaction report</li>
                <li>3 trial simulations</li>
              </ul>
              <button class="pco-btn disabled" disabled>{{ isPaid ? 'Downgraded tier' : 'Current plan' }}</button>
            </div>
            <div class="plan-card-opt" :class="{ current: isPaid }">
              <div class="pco-head"><span class="pco-name">Pro</span><span class="pco-price">R80/mo</span></div>
              <ul class="pco-features">
                <li>Unlimited panels</li>
                <li>Full simulations</li>
                <li>Every report &amp; interview</li>
              </ul>
              <button v-if="!isPaid" class="pco-btn" :disabled="upgrading" @click="doUpgrade">
                {{ upgrading ? 'Redirecting…' : 'Upgrade — R80/mo →' }}
              </button>
              <button v-else-if="isCancelled" class="pco-btn disabled" disabled>Cancels at period end</button>
              <button v-else class="pco-btn ghost" :disabled="cancelling" @click="doCancel">
                {{ cancelling ? 'Cancelling…' : 'Cancel subscription' }}
              </button>
            </div>
          </div>
          <p class="billing-note">
            Payments are processed securely by Paystack (cards, in ZAR). Cancelling stops future
            billing; your Pro access runs to the end of the current paid month — no pro-rata refund.
            See the <a href="/refunds.html" target="_blank" rel="noopener">refund &amp; cancellation policy</a>.
          </p>
        </div>

        <!-- API Keys panel -->
        <div v-if="activeTab === 'keys'" class="tab-panel">
          <div class="keys-section">
            <div class="keys-block">
              <div class="keys-block-head">
                <span class="keys-block-title">Research &amp; persona LLM</span>
                <span class="keys-block-tier">LLM_*</span>
              </div>
              <span class="keys-block-desc">Stronger model for research, persona generation, and document parsing. Lower volume, benefits from a Plus-tier model.</span>
              <div class="field"><label class="field-label">Base URL</label><input class="field-input mono" type="text" value="https://api.openai.com/v1"></div>
              <div class="field"><label class="field-label">API key</label><input class="field-input mono" type="password" value="sk-············································"></div>
              <div class="field"><label class="field-label">Model</label><input class="field-input mono" type="text" value="qwen2.5-32b-instruct"></div>
            </div>
            <div class="keys-block">
              <div class="keys-block-head">
                <span class="keys-block-title">Simulation runtime LLM</span>
                <span class="keys-block-tier">SIM_LLM_*</span>
              </div>
              <span class="keys-block-desc">High-volume sim runtime. A cheaper/faster model is the right tool. Leave blank to reuse the research key.</span>
              <div class="field"><label class="field-label">Base URL</label><input class="field-input mono" type="text" value="https://api.openai.com/v1"></div>
              <div class="field"><label class="field-label">API key</label><input class="field-input mono" type="password" value="sk-············································"></div>
              <div class="field"><label class="field-label">Model</label><input class="field-input mono" type="text" value="qwen2.5:7b"></div>
            </div>
            <div class="keys-block">
              <div class="keys-block-head">
                <span class="keys-block-title">Web grounding (optional)</span>
                <span class="keys-block-tier">OPTIONAL</span>
              </div>
              <span class="keys-block-desc">Richer, more current personas grounded in live sources. Off by default.</span>
              <div class="field-row">
                <div class="field"><label class="field-label">Jina key</label><input class="field-input mono" type="password" value=""></div>
                <div class="field"><label class="field-label">Serper key</label><input class="field-input mono" type="password" value=""></div>
              </div>
            </div>
          </div>
          <div class="modal-actions">
            <button class="btn" @click="closeFullpage">Cancel</button>
            <button class="btn primary">Save keys</button>
          </div>
        </div>

      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import DashboardPanel from './DashboardPanel.vue'
import { useBilling } from '../../composables/useBilling'

const emit = defineEmits(['close', 'open-sim'])

const { status, isPaid, isCancelled, refresh: refreshBilling, upgrade, cancel } = useBilling()
const upgrading = ref(false)
const cancelling = ref(false)

async function doUpgrade() {
  upgrading.value = true
  try {
    await upgrade(window.location.href)  // Paystack redirect; returns here after pay
  } catch (e) {
    upgrading.value = false
    alert(e?.message || 'Could not start checkout. Please try again.')
  }
}

async function doCancel() {
  if (!confirm('Cancel your Pro subscription? You\'ll keep access until the end of the current paid month.')) return
  cancelling.value = true
  try {
    await cancel()
  } catch (e) {
    alert(e?.response?.data?.error || e?.message || 'Could not cancel. Please try again.')
  } finally {
    cancelling.value = false
  }
}

const menuOpen = ref(true)
const modalOpen = ref(false)
const activeTab = ref('profile')

const tabs = [
  { id: 'profile', label: 'Profile', icon: '👤' },
  { id: 'dashboard', label: 'Dashboard', icon: '📊' },
  { id: 'billing', label: 'Billing', icon: '💳' },
  { id: 'keys', label: 'API Keys', icon: '🔑' },
]

const activeTabLabel = computed(() => {
  const t = tabs.find(t => t.id === activeTab.value)
  return t ? t.label : 'Account'
})

function closeMenu() {
  menuOpen.value = false
  emit('close')
}

function openFullpage(tabName) {
  menuOpen.value = false
  activeTab.value = tabName
  modalOpen.value = true
}

function closeFullpage() {
  modalOpen.value = false
  emit('close')
}

function onOpenSim(sim) {
  closeFullpage()
  emit('open-sim', sim)
}

function onKeydown(e) {
  if (e.key === 'Escape') {
    if (modalOpen.value) closeFullpage()
    else if (menuOpen.value) closeMenu()
  }
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  refreshBilling()  // load real plan + usage
})
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.profile-scrim {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.12);
  z-index: 50;
}

.profile-menu {
  position: fixed;
  bottom: 24px; left: 280px;
  width: 224px;
  background: #fff;
  border: 1px solid #E8E8E8;
  border-radius: 12px;
  box-shadow: 0 8px 28px rgba(0,0,0,0.14);
  z-index: 51;
  overflow: hidden;
}

.menu-head {
  padding: 14px 16px 10px;
  border-bottom: 1px solid #ECECEC;
  display: flex; align-items: center; gap: 10px;
}
.menu-head-avatar {
  width: 32px; height: 32px; border-radius: 50%;
  background: linear-gradient(160deg, #25b368 0%, #1E9E5A 60%, #178048 100%);
  color: #fff;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700; font-size: 0.78rem;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.menu-head-info { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.menu-head-name { font-size: 0.82rem; font-weight: 600; color: #1a1a1a; }
.menu-head-plan { font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; color: #999; }

.menu-list { padding: 6px; }
.menu-option {
  display: flex; align-items: center; gap: 10px;
  width: 100%; padding: 9px 12px;
  background: transparent; border: none; border-radius: 8px;
  cursor: pointer; text-align: left; font: inherit;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem; font-weight: 600; color: #555;
  transition: background 0.15s, color 0.15s;
}
.menu-option:hover { background: #F0FAF4; color: #1E9E5A; }
.menu-option-icon { font-size: 0.88rem; line-height: 1; width: 18px; text-align: center; }
.menu-option-label { flex: 1; }
.menu-option-arrow { font-size: 0.7rem; color: #bbb; }

.fullpage-scrim {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.25);
  z-index: 60;
}

.fullpage-modal {
  position: fixed;
  top: 50%; left: 50%;
  width: 920px; max-width: calc(100vw - 48px);
  max-height: 88vh;
  background: #fff;
  border: 1px solid #E8E8E8;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.25);
  z-index: 61;
  display: flex;
  overflow: hidden;
  transform: translate(-50%, -50%);
}

.modal-tabs {
  flex-shrink: 0; width: 188px;
  background: #FAFAFA;
  border-right: 1px solid #ECECEC;
  padding: 18px 12px;
  display: flex; flex-direction: column; gap: 2px;
}
.modal-tabs-head {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.62rem; font-weight: 700;
  letter-spacing: 0.5px; text-transform: uppercase;
  color: #bbb; padding: 4px 12px 10px;
}
.modal-tab {
  display: flex; align-items: center; gap: 9px;
  padding: 9px 12px; border: none; background: transparent;
  border-radius: 8px; cursor: pointer; text-align: left; font: inherit;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem; font-weight: 600; color: #555;
  width: 100%; transition: background 0.15s, color 0.15s;
}
.modal-tab:hover { background: #F0F0F0; color: #1a1a1a; }
.modal-tab.active { background: #F0FAF4; color: #1E9E5A; }
.modal-tab-icon { font-size: 0.88rem; line-height: 1; width: 16px; text-align: center; }

.modal-body {
  flex: 1; overflow-y: auto;
  padding: 26px 32px;
  display: flex; flex-direction: column;
}
.modal-body-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 18px;
}
.modal-body-title { font-size: 1.05rem; font-weight: 600; color: #1a1a1a; letter-spacing: -0.3px; }
.modal-close { background: none; border: none; font-size: 1.3rem; line-height: 1; color: #bbb; cursor: pointer; padding: 0 4px; font: inherit; }
.modal-close:hover { color: #1a1a1a; }

.tab-panel { display: flex; flex-direction: column; gap: 18px; }

.field-group { display: flex; flex-direction: column; gap: 14px; }
.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.field { display: flex; flex-direction: column; gap: 5px; }
.field-label { font-family: 'JetBrains Mono', monospace; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; color: #999; }
.field-input {
  border: 1px solid #DDD; border-radius: 8px;
  padding: 9px 12px;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  font-size: 0.88rem; color: #1a1a1a;
  background: #F2F2F2; outline: none;
  transition: border-color 0.15s, background 0.15s;
}
.field-input:focus { border-color: #1E9E5A; background: #fff; }
.field-input.mono { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; }
.field-help { font-family: 'JetBrains Mono', monospace; font-size: 0.64rem; color: #bbb; line-height: 1.4; }

.modal-actions {
  display: flex; justify-content: flex-end; gap: 8px;
  margin-top: 22px; padding-top: 16px;
  border-top: 1px solid #ECECEC;
}
.btn {
  border-radius: 8px; padding: 9px 18px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem; font-weight: 700; letter-spacing: 0.3px;
  cursor: pointer; border: 1px solid #DDD; background: #fff; color: #555;
  transition: all 0.15s;
}
.btn:hover { border-color: #999; color: #1a1a1a; }
.btn.primary { background: #1E9E5A; border-color: #1E9E5A; color: #fff; }
.btn.primary:hover { background: #178048; border-color: #178048; }

.current-plan-banner {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 16px; border-radius: 10px;
  background: #F0FAF4; border: 1px solid rgba(30,158,90,0.3);
}
.cpb-left { display: flex; flex-direction: column; gap: 2px; }
.cpb-label { font-family: 'JetBrains Mono', monospace; font-size: 0.62rem; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; color: #1E9E5A; }
.cpb-name { font-size: 1rem; font-weight: 700; color: #1a1a1a; }
.cpb-right { font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #555; }
.current-plan-banner.cancelled { background: #FFF6E8; border-color: rgba(199,127,26,0.35); }
.current-plan-banner.cancelled .cpb-label { color: #C77F1A; }

.billing-note {
  font-family: 'JetBrains Mono', monospace; font-size: 0.66rem; color: #999;
  line-height: 1.6; margin: 4px 0 0;
}
.billing-note a { color: #1E9E5A; }

.plan-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.plan-card-opt {
  border: 1px solid #E8E8E8; border-radius: 12px;
  padding: 16px 18px;
  display: flex; flex-direction: column; gap: 8px;
  cursor: pointer; background: #fff;
  transition: border-color 0.15s, background 0.15s;
}
.plan-card-opt:hover { border-color: #1E9E5A; }
.plan-card-opt.current { border-color: rgba(30,158,90,0.3); background: #F0FAF4; }
.pco-head { display: flex; justify-content: space-between; align-items: baseline; }
.pco-name { font-size: 0.95rem; font-weight: 700; color: #1a1a1a; }
.pco-price { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; font-weight: 700; color: #1E9E5A; }
.pco-features { list-style: none; display: flex; flex-direction: column; gap: 4px; padding: 0; }
.pco-features li { font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; color: #555; padding-left: 14px; position: relative; }
.pco-features li::before { content: '✓'; position: absolute; left: 0; top: 0; color: #1E9E5A; font-weight: 700; }
.pco-btn {
  margin-top: 6px; padding: 8px 14px;
  background: #1E9E5A; color: #fff; border: none;
  border-radius: 8px; cursor: pointer;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.74rem; font-weight: 700; letter-spacing: 0.3px;
  transition: background 0.15s;
}
.pco-btn:hover { background: #178048; }
.pco-btn.disabled { background: #EEE; color: #bbb; cursor: not-allowed; }
.pco-btn.ghost { background: #fff; color: #C0392B; border: 1px solid #E8C9C5; }
.pco-btn.ghost:hover { background: #FEEEEC; border-color: #C0392B; }
.pco-btn.ghost:disabled { opacity: 0.6; cursor: not-allowed; }
.pco-tag { font-family: 'JetBrains Mono', monospace; font-size: 0.6rem; font-weight: 700; color: #bbb; text-transform: uppercase; letter-spacing: 0.4px; }

.keys-section { display: flex; flex-direction: column; gap: 18px; }
.keys-block {
  display: flex; flex-direction: column; gap: 8px;
  padding: 14px 16px;
  background: #FAFAFA; border: 1px solid #ECECEC; border-radius: 10px;
}
.keys-block-head { display: flex; justify-content: space-between; align-items: baseline; }
.keys-block-title { font-size: 0.88rem; font-weight: 700; color: #1a1a1a; }
.keys-block-tier { font-family: 'JetBrains Mono', monospace; font-size: 0.64rem; font-weight: 700; color: #1E9E5A; background: #F0FAF4; padding: 2px 8px; border-radius: 999px; }
.keys-block-desc { font-family: 'JetBrains Mono', monospace; font-size: 0.66rem; color: #999; line-height: 1.5; }

/* Transitions */
.menu-pop-enter-active, .menu-pop-leave-active { transition: transform 0.2s ease, opacity 0.2s ease; }
.menu-pop-enter-from, .menu-pop-leave-to { transform: translateY(12px) scale(0.96); opacity: 0; }

.modal-rise-enter-active, .modal-rise-leave-active { transition: transform 0.25s ease, opacity 0.25s ease; }
.modal-rise-enter-from, .modal-rise-leave-to { transform: translate(-50%, -50%) scale(0.96); opacity: 0; }

@media (max-width: 760px) {
  .plan-grid { grid-template-columns: 1fr; }
  .field-row { grid-template-columns: 1fr; }
}
</style>
