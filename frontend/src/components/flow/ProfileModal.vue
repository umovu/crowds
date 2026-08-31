<template>
  <!-- Stage 1: Small pop-out menu -->
  <Transition name="menu-pop">
    <div v-if="menuOpen" class="profile-scrim" @click="closeMenu"></div>
  </Transition>
  <Transition name="menu-pop">
    <div v-if="menuOpen" class="profile-menu">
      <div class="menu-head">
        <div class="menu-head-avatar">{{ initials }}</div>
        <div class="menu-head-info">
          <span class="menu-head-name">{{ fullName }}</span>
          <span class="menu-head-plan">{{ isPaid ? 'Beta plan' : 'Free plan' }}</span>
        </div>
      </div>
      <div class="menu-list">
        <button v-for="tab in tabs" :key="tab.id" class="menu-option" @click="openFullpage(tab.id)">
          <span class="menu-option-label">{{ tab.label }}</span>
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
      <!-- Tab rail (desktop only) -->
      <div class="modal-tabs">
        <div class="modal-tabs-head">Account</div>
        <button
          v-for="tab in tabs" :key="tab.id"
          class="modal-tab"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
        >{{ tab.label }}</button>
      </div>

      <!-- Body -->
      <div class="modal-body">
        <div class="modal-body-head">
          <div class="modal-head-left">
            <button v-if="isMobile && !mobileMenu" class="modal-back" @click="mobileMenu = true">←</button>
            <div class="modal-body-title">{{ isMobile && mobileMenu ? 'Account' : activeTabLabel }}</div>
          </div>
          <button class="modal-close" @click="closeFullpage">×</button>
        </div>

        <!-- Mobile: root screen is a plain list of options -->
        <div v-if="showMobileMenu" class="tab-panel">
          <div class="mm-head">
            <div class="mm-avatar">{{ initials }}</div>
            <div class="mm-info">
              <span class="mm-name">{{ fullName }}</span>
              <span class="mm-plan">{{ isPaid ? 'Beta plan' : 'Free plan' }}</span>
            </div>
          </div>
          <div class="mm-list">
            <button v-for="tab in tabs" :key="tab.id" class="mm-option" @click="activeTab = tab.id; mobileMenu = false">
              <span class="mm-option-label">{{ tab.label }}</span>
              <span class="mm-option-arrow">→</span>
            </button>
          </div>
        </div>

        <!-- Profile panel -->
        <div v-if="activeTab === 'profile' && !showMobileMenu" class="tab-panel">
          <div class="field-group">
            <div class="field-row">
              <div class="field">
                <label class="field-label">First name</label>
                <input class="field-input" type="text" v-model="form.first_name" placeholder="First name">
              </div>
              <div class="field">
                <label class="field-label">Surname</label>
                <input class="field-input" type="text" v-model="form.surname" placeholder="Surname">
              </div>
            </div>
            <div class="field">
              <label class="field-label">Email</label>
              <input class="field-input" type="email" v-model="form.email" placeholder="you@example.com">
              <span class="field-help">Changing this sends a confirmation link to the new address; it takes effect once you click it.</span>
            </div>
            <div class="field">
              <label class="field-label">Display name</label>
              <input class="field-input" type="text" v-model="form.display_name" placeholder="Display name">
              <span class="field-help">Shown on shared sims and panel reports</span>
            </div>
          </div>
          <div class="modal-actions">
            <span v-if="profileMsg" class="save-msg" :class="profileMsg.type">{{ profileMsg.text }}</span>
            <button class="btn" @click="closeFullpage">Cancel</button>
            <button class="btn primary" :disabled="savingProfile" @click="saveProfile">
              {{ savingProfile ? 'Saving…' : 'Save changes' }}
            </button>
          </div>
        </div>

        <!-- Your context — the saved "about my business" block. Lives on the
             account, not on the prompt bar: it is written once and reused by
             every run, so it belongs with the other things you set and forget. -->
        <div v-if="activeTab === 'context' && !showMobileMenu" class="tab-panel">
          <div class="field-group">
            <div class="field">
              <label class="field-label">About your offer</label>
              <textarea
                class="field-input ctx-textarea"
                rows="7"
                maxlength="1500"
                v-model="ctxBody"
                placeholder="e.g. We install home biodigesters in South Africa. R17,000 fitted. Food and garden waste in, cooking gas and fertiliser out. We also sell the stove. Bigger units go to schools, usually paid for by a company's CSI budget. Most of our buyers already compost."
              ></textarea>
              <span class="field-help">
                Saved once and added to every run as background, so you stop
                retyping your business into each prompt.
              </span>
            </div>
            <!-- The boundary, said plainly. Personas are real surveyed people
                 with measured incomes and attitudes; claims written about them
                 here are ignored by design. -->
            <div class="ctx-hint">
              Write about your offer: what it is, what it costs, who buys it
              today. Not about the people answering — their income and views are
              real data, and anything you write about them here is ignored.
            </div>
          </div>
          <div class="modal-actions">
            <span class="ctx-count">{{ (ctxBody || '').length }} / 1500</span>
            <span v-if="ctxMsg" class="save-msg" :class="ctxMsg.type">{{ ctxMsg.text }}</span>
            <button class="btn" @click="closeFullpage">Cancel</button>
            <button class="btn primary" :disabled="savingCtx" @click="saveCtx">
              {{ savingCtx ? 'Saving…' : 'Save context' }}
            </button>
          </div>
        </div>

        <!-- Security panel — set / change the account password -->
        <div v-if="activeTab === 'security' && !showMobileMenu" class="tab-panel">
          <div class="field-group">
            <div class="field">
              <label class="field-label">New password</label>
              <input class="field-input" type="password" v-model="pw.next" autocomplete="new-password" placeholder="At least 8 characters">
              <span class="field-help">Invited accounts start on a temporary password. Setting one here replaces it.</span>
            </div>
            <div class="field">
              <label class="field-label">Confirm new password</label>
              <input class="field-input" type="password" v-model="pw.confirm" autocomplete="new-password" placeholder="Type it again">
            </div>
          </div>
          <div class="modal-actions">
            <span v-if="pwMsg" class="save-msg" :class="pwMsg.type">{{ pwMsg.text }}</span>
            <button class="btn" @click="closeFullpage">Cancel</button>
            <button class="btn primary" :disabled="savingPassword" @click="savePassword">
              {{ savingPassword ? 'Saving…' : 'Update password' }}
            </button>
          </div>
        </div>

        <!-- Dashboard panel -->
        <div v-if="activeTab === 'dashboard' && !showMobileMenu" class="tab-panel">
          <DashboardPanel @open-sim="onOpenSim" />
        </div>

        <!-- Billing panel -->
        <div v-if="activeTab === 'billing' && !showMobileMenu" class="tab-panel">
          <div class="current-plan-banner" :class="{ cancelled: isCancelled }">
            <div class="cpb-left">
              <span class="cpb-label">{{ isCancelled ? 'Subscription cancelled' : 'Current plan' }}</span>
              <span class="cpb-name">{{ isPaid ? 'Pro (Beta) — R80/mo' : 'Free' }}</span>
            </div>
            <span class="cpb-right">
              {{ isCancelled
                ? 'Access continues until the end of your paid month'
                : (isPaid ? (SIM_ENABLED ? 'unlimited panels + simulations' : 'unlimited panels')
                          : `${status?.panel_used ?? 0} / ${status?.panel_limit ?? 3} panels used` + (SIM_ENABLED ? ` · ${status?.sim_used ?? 0} / ${status?.sim_limit ?? 1} trial sims used` : '')) }}
            </span>
          </div>
          <div class="plan-grid">
            <div class="plan-card-opt" :class="{ current: !isPaid }">
              <div class="pco-head"><span class="pco-name">Free</span><span class="pco-price">R0/mo</span></div>
              <ul class="pco-features">
                <li>4 panels (focus groups)</li>
                <li>Full reaction report</li>
                <li v-if="SIM_ENABLED">2 trial simulations</li>
              </ul>
              <button class="pco-btn disabled" disabled>{{ isPaid ? 'Downgraded tier' : 'Current plan' }}</button>
            </div>
            <div class="plan-card-opt" :class="{ current: isPaid }">
              <div class="pco-head"><span class="pco-name">Pro <em class="pco-beta">Beta</em></span><span class="pco-price">R80/mo</span></div>
              <ul class="pco-features">
                <li>Unlimited panels</li>
                <li v-if="SIM_ENABLED">Full simulations</li>
                <li>Every report &amp; interview</li>
              </ul>
              <button v-if="!isPaid" class="pco-btn disabled" disabled>Paid — coming soon</button>
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
        <div v-if="activeTab === 'keys' && !showMobileMenu" class="tab-panel">
          <div class="keys-section">
            <div class="keys-block">
              <div class="keys-block-head">
                <span class="keys-block-title">Research &amp; persona LLM</span>
                <span class="keys-block-tier">LLM_*</span>
              </div>
              <span class="keys-block-desc">Stronger model for research, persona generation, and document parsing. Lower volume, benefits from a Plus-tier model.</span>
              <div class="field"><label class="field-label">Base URL</label><input class="field-input mono" type="text" placeholder="e.g. https://api.openai.com/v1"></div>
              <div class="field"><label class="field-label">API key</label><input class="field-input mono" type="password" placeholder="sk-…"></div>
              <div class="field"><label class="field-label">Model</label><input class="field-input mono" type="text" placeholder="e.g. qwen2.5-32b-instruct"></div>
            </div>
            <div class="keys-block">
              <div class="keys-block-head">
                <span class="keys-block-title">Simulation runtime LLM</span>
                <span class="keys-block-tier">SIM_LLM_*</span>
              </div>
              <span class="keys-block-desc">High-volume sim runtime. A cheaper/faster model is the right tool. Leave blank to reuse the research key.</span>
              <div class="field"><label class="field-label">Base URL</label><input class="field-input mono" type="text" placeholder="e.g. https://api.openai.com/v1"></div>
              <div class="field"><label class="field-label">API key</label><input class="field-input mono" type="password" placeholder="sk-…"></div>
              <div class="field"><label class="field-label">Model</label><input class="field-input mono" type="text" placeholder="e.g. qwen2.5:7b"></div>
            </div>
            <div class="keys-block">
              <div class="keys-block-head">
                <span class="keys-block-title">Web grounding (optional)</span>
                <span class="keys-block-tier">OPTIONAL</span>
              </div>
              <span class="keys-block-desc">Richer, more current personas grounded in live sources. Off by default.</span>
              <div class="field-row">
                <div class="field"><label class="field-label">Jina key</label><input class="field-input mono" type="password" placeholder="jina_…"></div>
                <div class="field"><label class="field-label">Serper key</label><input class="field-input mono" type="password" placeholder="Your Serper API key"></div>
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
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import DashboardPanel from './DashboardPanel.vue'
import { SIM_ENABLED } from '../../features'
import { useBilling } from '../../composables/useBilling'
import { useAuth } from '../../composables/useAuth'
import { supabase } from '../../lib/supabase'
import { getContext, saveContext } from '../../api/context'

const emit = defineEmits(['close', 'open-sim'])

const { status, isPaid, isCancelled, refresh: refreshBilling, upgrade, cancel } = useBilling()
const { user } = useAuth()
const upgrading = ref(false)
const cancelling = ref(false)

// ── Profile: bound to Supabase auth user_metadata ────────────────────────────
// The form hydrates from the shared reactive `user` and writes back with
// supabase.auth.updateUser(), which persists to Supabase AND fires USER_UPDATED
// so `user` (and everything bound to it, incl. the menu header) refreshes live.
const form = ref({ first_name: '', surname: '', email: '', display_name: '' })
const savingProfile = ref(false)
const profileMsg = ref(null)  // { type: 'ok' | 'err', text }

// ── Your context ────────────────────────────────────────────────────────────
// The saved "about my business" block. Loaded lazily when the tab is opened
// (most visits here are for billing or the password), and re-loaded each time
// so a second device's edit doesn't get silently overwritten by a stale draft.
const ctxBody = ref('')
const savingCtx = ref(false)
const ctxLoaded = ref(false)
const ctxMsg = ref(null)

async function loadCtx() {
  try {
    const res = await getContext()
    ctxBody.value = (res.data?.data?.body || res.data?.body || '')
    ctxLoaded.value = true
  } catch (_) {
    // Fail quiet: an empty box is the honest state, and the run works without it.
    ctxLoaded.value = true
  }
}

async function saveCtx() {
  savingCtx.value = true
  ctxMsg.value = null
  try {
    const body = (ctxBody.value || '').trim().slice(0, 1500)
    await saveContext(body)
    ctxBody.value = body
    ctxMsg.value = { type: 'ok', text: 'Saved' }
  } catch (e) {
    ctxMsg.value = { type: 'err', text: e?.response?.data?.error || 'Could not save' }
  } finally {
    savingCtx.value = false
  }
}

function hydrateForm() {
  const u = user.value
  const m = u?.user_metadata || {}
  form.value = {
    first_name: m.first_name || '',
    surname: m.surname || '',
    email: u?.email || '',
    display_name: m.display_name || '',
  }
}
// Key the hydrate on the user id, not the session object: token auto-refresh
// swaps the session (same user) every hour and would otherwise clobber an
// in-progress edit. Only re-hydrate when the actual account changes.
watch(() => user.value?.id, hydrateForm, { immediate: true })

const fullName = computed(() => {
  const m = user.value?.user_metadata || {}
  const name = [m.first_name, m.surname].filter(Boolean).join(' ')
  return name || m.full_name || m.display_name || user.value?.email || 'Your account'
})
const initials = computed(() => {
  const m = user.value?.user_metadata || {}
  const a = (m.first_name || '').trim()
  const b = (m.surname || '').trim()
  if (a || b) return ((a[0] || '') + (b[0] || '')).toUpperCase()
  return (user.value?.email || 'me').slice(0, 2).toUpperCase()
})

async function saveProfile() {
  if (savingProfile.value) return
  savingProfile.value = true
  profileMsg.value = null
  try {
    const first_name = form.value.first_name.trim()
    const surname = form.value.surname.trim()
    const display_name = form.value.display_name.trim()
    const full_name = [first_name, surname].filter(Boolean).join(' ')
    const payload = { data: { first_name, surname, display_name, full_name } }

    const newEmail = form.value.email.trim()
    const emailChanged = newEmail && newEmail !== (user.value?.email || '')
    if (emailChanged) payload.email = newEmail

    const { error } = await supabase.auth.updateUser(payload)
    if (error) throw error

    profileMsg.value = emailChanged
      ? { type: 'ok', text: `Saved. Confirm your new email via the link sent to ${newEmail}.` }
      : { type: 'ok', text: 'Profile updated.' }
  } catch (e) {
    profileMsg.value = { type: 'err', text: e?.message || 'Could not save. Please try again.' }
  } finally {
    savingProfile.value = false
  }
}

// ── Security: set a new password ─────────────────────────────────────────────
// Invited accounts are created with a temporary password by an operator, so the
// account can be used before this screen existed. This is how the owner takes
// it over. Supabase re-issues the session on success, so nobody gets signed out.
const pw = ref({ next: '', confirm: '' })
const savingPassword = ref(false)
const pwMsg = ref(null)  // { type: 'ok' | 'err', text }

async function savePassword() {
  if (savingPassword.value) return
  const next = pw.value.next
  if (next.length < 8) {
    pwMsg.value = { type: 'err', text: 'Use at least 8 characters.' }
    return
  }
  if (next !== pw.value.confirm) {
    pwMsg.value = { type: 'err', text: 'The two passwords do not match.' }
    return
  }
  savingPassword.value = true
  pwMsg.value = null
  try {
    const { error } = await supabase.auth.updateUser({ password: next })
    if (error) throw error
    pw.value = { next: '', confirm: '' }
    pwMsg.value = { type: 'ok', text: 'Password updated. Use it next time you sign in.' }
  } catch (e) {
    pwMsg.value = { type: 'err', text: e?.message || 'Could not update the password. Please try again.' }
  } finally {
    savingPassword.value = false
  }
}

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

// On mobile there's no intermediate pop-up menu: the profile button opens the
// full-screen account page directly (it slides up from the bottom).
const isMobile = window.matchMedia('(max-width: 860px)').matches
const menuOpen = ref(!isMobile)
const modalOpen = ref(isMobile)
const activeTab = ref('profile')
// Mobile root screen: a plain list of the account options. Picking one shows
// that screen; ← returns to the list. Desktop never sees this.
const mobileMenu = ref(isMobile)
const showMobileMenu = computed(() => isMobile && mobileMenu.value)

const tabs = [
  { id: 'profile', label: 'Profile' },
  { id: 'context', label: 'Your context' },
  { id: 'security', label: 'Security' },
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'billing', label: 'Billing' },
  { id: 'keys', label: 'API Keys' },
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
  mobileMenu.value = false
  modalOpen.value = true
}

// One place, so the context loads however the tab was reached — the pop-out
// menu, the desktop tab rail, or the mobile list.
watch(activeTab, (tab) => {
  if (tab === 'context') { ctxMsg.value = null; loadCtx() }
})

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
.modal-head-left { display: flex; align-items: center; gap: 10px; }
.modal-back {
  background: none; border: 1px solid #E5E5E5; border-radius: 8px;
  padding: 4px 10px; font: inherit; font-size: 1rem; line-height: 1;
  color: #555; cursor: pointer;
}

/* ── Mobile root option list ──────────────────────────────────────────────── */
.mm-head { display: flex; align-items: center; gap: 12px; padding: 4px 2px 12px; border-bottom: 1px solid #ECECEC; }
.mm-avatar {
  width: 42px; height: 42px; border-radius: 50%;
  background: linear-gradient(160deg, #25b368 0%, #1E9E5A 60%, #178048 100%);
  color: #fff; font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 0.9rem;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.mm-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.mm-name { font-size: 0.95rem; font-weight: 600; color: #1a1a1a; }
.mm-plan { font-family: 'JetBrains Mono', monospace; font-size: 0.64rem; color: #999; }
.mm-list { display: flex; flex-direction: column; }
.mm-option {
  display: flex; align-items: center; justify-content: space-between;
  width: 100%; padding: 16px 4px;
  background: transparent; border: none; border-bottom: 1px solid #F0F0F0;
  cursor: pointer; text-align: left; font: inherit;
}
.mm-option-label { font-size: 0.95rem; font-weight: 600; color: #1a1a1a; }
.mm-option-arrow { color: #bbb; font-size: 0.85rem; }

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
.btn.primary:disabled { opacity: 0.6; cursor: not-allowed; }

.save-msg {
  margin-right: auto; align-self: center;
  font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; line-height: 1.4;
  max-width: 60%;
}
/* Your context — same field vocabulary, just taller and with the boundary note */
.ctx-textarea { resize: vertical; min-height: 150px; line-height: 1.55; }
.ctx-hint {
  padding: 10px 12px;
  border-left: 2px solid #1E9E5A; border-radius: 0 8px 8px 0;
  background: #F0FAF4;
  font-family: 'JetBrains Mono', monospace; font-size: 0.68rem;
  line-height: 1.5; color: #555;
}
.ctx-count {
  margin-right: auto; align-self: center;
  font-family: 'JetBrains Mono', monospace; font-size: 0.64rem; color: #bbb;
}
.ctx-count + .save-msg { margin-right: 12px; }

.save-msg.ok { color: #1E9E5A; }
.save-msg.err { color: #C0392B; }

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
.pco-beta {
  font-family: 'JetBrains Mono', monospace; font-style: normal;
  font-size: 0.6rem; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase;
  color: #1E9E5A; background: #F0FAF4; border-radius: 999px; padding: 2px 7px; margin-left: 6px;
  vertical-align: middle;
}
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

/* ── Mobile: menu becomes a bottom sheet; modal goes full-screen ─────────── */
@media (max-width: 860px) {
  .profile-menu {
    left: 12px; right: 12px; bottom: 12px;
    width: auto;
    border-radius: 14px;
  }
  .menu-option { padding: 13px 12px; font-size: 0.84rem; }

  .fullpage-modal {
    top: 0; left: 0; right: 0; bottom: 0;
    transform: none;
    width: 100%; max-width: 100%;
    height: 100dvh; max-height: 100dvh;
    border-radius: 0; border: none;
    flex-direction: column;
  }
  /* Full page slides up from the bottom edge, like a route push. */
  .modal-rise-enter-from, .modal-rise-leave-to { transform: translateY(100%); }

  /* No tab rail on mobile — navigation is the root option list instead. */
  .modal-tabs { display: none; }

  .modal-body { padding: 18px 16px calc(18px + env(safe-area-inset-bottom)); }

  .modal-actions { flex-wrap: wrap; }
  .modal-actions .btn { flex: 1; padding: 12px 18px; }
  .save-msg { max-width: 100%; flex-basis: 100%; margin-right: 0; }

  .current-plan-banner { flex-direction: column; align-items: flex-start; gap: 8px; }
  .keys-block .field-row { grid-template-columns: 1fr; }
  .field-input { font-size: 1rem; }  /* ≥16px stops iOS zoom-on-focus */
}
</style>
