<template>
  <div class="reset-wrap">
    <div class="reset-card">
      <div class="reset-brand">crowds</div>
      <h1 class="reset-title">Set a new password</h1>
      <p class="reset-sub">You're signed in from the reset link. Pick a password and you're done.</p>

      <label class="field-label" for="pw1">New password</label>
      <input id="pw1" class="field-input" type="password" v-model="next" autocomplete="new-password"
             placeholder="At least 8 characters" @keyup.enter="save">

      <label class="field-label" for="pw2">Confirm new password</label>
      <input id="pw2" class="field-input" type="password" v-model="confirm" autocomplete="new-password"
             placeholder="Type it again" @keyup.enter="save">

      <p v-if="msg" class="reset-msg" :class="msg.type">{{ msg.text }}</p>

      <button class="reset-btn" :disabled="saving" @click="save">
        {{ saving ? 'Saving…' : 'Save password' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { supabase } from '../lib/supabase'

const router = useRouter()
const next = ref('')
const confirm = ref('')
const saving = ref(false)
const msg = ref(null)   // { type: 'ok' | 'err', text }

// Reaching this page without a session means the link expired or was already
// used — Supabase recovery links are single use. Say so plainly rather than
// letting them type a password into a form that can't save it.
onMounted(async () => {
  const { data } = await supabase.auth.getSession()
  if (!data.session) {
    msg.value = { type: 'err', text: 'This reset link has expired or was already used. Request a new one from the sign-in page.' }
  }
})

async function save() {
  if (saving.value) return
  if (next.value.length < 8) {
    msg.value = { type: 'err', text: 'Use at least 8 characters.' }
    return
  }
  if (next.value !== confirm.value) {
    msg.value = { type: 'err', text: 'The two passwords do not match.' }
    return
  }
  saving.value = true
  msg.value = null
  try {
    const { error } = await supabase.auth.updateUser({ password: next.value })
    if (error) throw error
    msg.value = { type: 'ok', text: 'Password saved. Taking you into the app…' }
    setTimeout(() => router.replace('/'), 1200)
  } catch (e) {
    msg.value = { type: 'err', text: e?.message || 'Could not save the password. Please try again.' }
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.reset-wrap {
  min-height: 100vh;
  display: flex; align-items: center; justify-content: center;
  background: #FAFAFA; padding: 24px;
}
.reset-card {
  width: 100%; max-width: 380px;
  background: #fff; border: 1px solid #E8E8E8; border-radius: 16px;
  padding: 30px 28px;
  display: flex; flex-direction: column;
}
.reset-brand {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8rem; font-weight: 700; letter-spacing: 1px;
  color: #1E9E5A; margin-bottom: 18px;
}
.reset-title { font-size: 1.25rem; font-weight: 600; color: #1a1a1a; letter-spacing: -0.3px; }
.reset-sub {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem; color: #999; line-height: 1.6;
  margin: 8px 0 20px;
}
.field-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.64rem; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase;
  color: #999; margin-bottom: 5px;
}
.field-input {
  border: 1px solid #DDD; border-radius: 8px;
  padding: 10px 12px; margin-bottom: 14px;
  font-family: 'Space Grotesk', system-ui, sans-serif;
  font-size: 1rem; color: #1a1a1a;
  background: #F2F2F2; outline: none;
  transition: border-color 0.15s, background 0.15s;
}
.field-input:focus { border-color: #1E9E5A; background: #fff; }
.reset-msg {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.68rem; line-height: 1.5; margin-bottom: 12px;
}
.reset-msg.ok { color: #1E9E5A; }
.reset-msg.err { color: #C0392B; }
.reset-btn {
  background: #1E9E5A; color: #fff; border: none;
  border-radius: 8px; padding: 12px 18px; cursor: pointer;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.78rem; font-weight: 700; letter-spacing: 0.3px;
  transition: background 0.15s;
}
.reset-btn:hover { background: #178048; }
.reset-btn:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
