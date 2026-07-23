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
  // Mobile mail-app browsers are often slower here, so poll a few times
  // before giving up rather than checking just once.
  let session = (await supabase.auth.getSession()).data.session
  for (let attempt = 0; !session && attempt < 5; attempt++) {
    await new Promise((r) => setTimeout(r, 400))
    session = (await supabase.auth.getSession()).data.session
  }
  if (!session) {
    // Most common cause: the link was opened in a different browser/app
    // (e.g. the Mail app's in-app browser) than the one that requested it,
    // so the PKCE verifier saved in that browser's localStorage isn't here.
    message.value = 'Could not complete sign-in. Redirecting…'
    window.location.href = '/auth.html?reason=session_lost'
    return
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
