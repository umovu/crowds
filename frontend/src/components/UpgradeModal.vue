<template>
  <div v-if="open" class="upgrade-overlay" @click.self="close">
    <div class="upgrade-card">
      <div class="upgrade-badge">Upgrade</div>
      <h2 class="upgrade-title">Unlock the full thing</h2>
      <p class="upgrade-msg">{{ message }}</p>
      <ul class="upgrade-feats">
        <li>Unlimited panels</li>
        <li>Full simulations</li>
        <li>Every report &amp; interview</li>
      </ul>
      <button class="upgrade-btn" :disabled="busy" @click="doUpgrade">
        {{ busy ? 'Redirecting…' : 'Upgrade — R80/mo' }}
      </button>
      <button class="upgrade-later" @click="close">Maybe later</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useBilling } from '../composables/useBilling'

const { upgrade } = useBilling()
const open = ref(false)
const busy = ref(false)
const message = ref('')

function onEvent(e) {
  message.value = e.detail?.message || 'This feature needs a paid plan.'
  open.value = true
}
function close() { open.value = false }

async function doUpgrade() {
  busy.value = true
  try {
    // Return to where the user was after payment.
    await upgrade(window.location.href)
  } catch (err) {
    message.value = err?.message || 'Could not start checkout. Please try again.'
    busy.value = false
  }
}

onMounted(() => window.addEventListener('billing:upgrade-required', onEvent))
onUnmounted(() => window.removeEventListener('billing:upgrade-required', onEvent))
</script>

<style scoped>
.upgrade-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0, 0, 0, 0.55);
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.upgrade-card {
  background: #fff; border-radius: 16px; padding: 32px 28px;
  width: 100%; max-width: 380px; text-align: center;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
  font-family: 'Space Grotesk', system-ui, sans-serif;
}
.upgrade-badge {
  display: inline-block; font-family: 'JetBrains Mono', monospace;
  font-size: 0.66rem; font-weight: 700; letter-spacing: 0.5px;
  text-transform: uppercase; color: #1E9E5A;
  background: #F0FAF4; border-radius: 999px; padding: 4px 12px; margin-bottom: 14px;
}
.upgrade-title {
  font-size: 1.5rem; font-weight: 600; letter-spacing: -0.5px;
  margin: 0 0 8px; color: #141414;
}
.upgrade-msg { font-size: 0.9rem; color: #4a4a4a; margin: 0 0 18px; line-height: 1.5; }
.upgrade-feats {
  list-style: none; padding: 0; margin: 0 0 22px; text-align: left;
  display: inline-block;
}
.upgrade-feats li {
  font-size: 0.88rem; color: #141414; padding: 5px 0 5px 24px; position: relative;
}
.upgrade-feats li::before {
  content: '✓'; position: absolute; left: 0; color: #1E9E5A; font-weight: 700;
}
.upgrade-btn {
  width: 100%; padding: 13px 16px; border: none; border-radius: 10px; cursor: pointer;
  background: #1E9E5A; color: #fff; font-weight: 700;
  font-family: 'JetBrains Mono', monospace; font-size: 0.9rem;
  transition: background .15s;
}
.upgrade-btn:hover:not(:disabled) { background: #178048; }
.upgrade-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.upgrade-later {
  margin-top: 12px; background: none; border: none; cursor: pointer;
  font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: #888;
}
.upgrade-later:hover { color: #141414; text-decoration: underline; }
</style>
