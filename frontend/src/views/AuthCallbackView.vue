<template>
  <div class="callback">
    <p>{{ message }}</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { supabase } from '../lib/supabase'

const route = useRoute()
const router = useRouter()
const message = ref('Signing you in…')

onMounted(async () => {
  // detectSessionInUrl (set on the client) parses the PKCE code / tokens from
  // the redirect URL automatically. We just wait for the session to settle.
  const { data, error } = await supabase.auth.getSession()
  if (error || !data.session) {
    // Give the URL-detection a brief moment, then re-check once.
    await new Promise((r) => setTimeout(r, 300))
    const retry = await supabase.auth.getSession()
    if (!retry.data.session) {
      message.value = 'Could not complete sign-in. Redirecting…'
      window.location.href = '/auth.html'
      return
    }
  }
  const next = typeof route.query.next === 'string' ? route.query.next : '/'
  router.replace(next)
})
</script>

<style scoped>
.callback {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: inherit;
}
</style>
