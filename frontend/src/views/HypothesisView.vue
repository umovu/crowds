<template>
  <div class="hyp-shell">
    <header class="hyp-bar">
      <button class="hyp-back" @click="goBack">← Back</button>
      <div class="hyp-bar-actions">
        <button class="hyp-act" :disabled="busy" @click="copyLink">
          {{ copied ? 'Link copied' : 'Copy link' }}
        </button>
        <button class="hyp-act" :disabled="busy" @click="print">Print / PDF</button>
        <button class="hyp-act" :disabled="busy" @click="load(true)">
          {{ busy ? 'Rebuilding…' : 'Rebuild' }}
        </button>
      </div>
    </header>

    <div v-if="busy && !report" class="hyp-state">Assembling the report…</div>
    <div v-else-if="error" class="hyp-state hyp-state--bad">{{ error }}</div>

    <article v-else-if="report" class="hyp-page">
      <h1>What this room told you</h1>
      <p class="hyp-meta">
        <b>You asked:</b> {{ report.pitch || '—' }}<br />
        <b>Who you asked:</b> {{ report.segment_label }} ·
        {{ room.heard }} of {{ room.seats }} people answered<br />
        <b>Rounds:</b> {{ report.rounds }} · Generated {{ report.generated_at }}
      </p>

      <!-- The room says the round was short before any count below is read. -->
      <p v-if="room.heard < room.seats" class="hyp-warn">
        {{ room.seats - room.heard }} of {{ room.seats }} people could not be
        reached. Every count below is of the people who answered.
      </p>

      <section v-if="report.room_read">
        <h2>The read</h2>
        <p>{{ report.room_read }}</p>
      </section>

      <section>
        <h2>Where they landed</h2>
        <ul v-if="stances.length" class="hyp-list">
          <li v-for="s in stances" :key="s[0]">
            <span class="hyp-key">{{ s[0] }}</span>
            <span class="hyp-num">{{ s[1] }}</span>
          </li>
        </ul>
        <p v-else class="hyp-none">Nobody answered yet.</p>
      </section>

      <!-- The reading the room ranking does not give you. A hostile room that
           shifts is an opportunity, not a bad row. -->
      <section>
        <h2>Who changed their mind</h2>
        <template v-if="movement.moved_count">
          <p>
            {{ movement.moved_count }} of {{ movement.answers_considered }}
            answers changed position — {{ movement.warmer }} warmed,
            {{ movement.cooler }} cooled.
          </p>
          <ul class="hyp-moves">
            <li v-for="p in movement.people" :key="p.agent_id" :class="p.direction">
              <span class="hyp-name">{{ p.name }}</span>
              <span class="hyp-arrow">{{ p.from }} → {{ p.to }}</span>
              <span class="hyp-tag">{{ p.direction }}</span>
            </li>
          </ul>
        </template>
        <p v-else class="hyp-none">
          Nobody moved. A room that doesn't budge is a finding: either the pitch
          didn't touch what they care about, or you haven't answered them back yet.
        </p>
      </section>

      <section>
        <h2>The wall they kept hitting</h2>
        <ul v-if="report.walls?.length" class="hyp-list">
          <li v-for="w in report.walls" :key="w.id">
            <span class="hyp-key">{{ w.label }}</span>
            <span class="hyp-num">{{ w.count }}</span>
          </li>
        </ul>
        <p v-else class="hyp-none">No recurring objection stood out.</p>
      </section>

      <section v-if="report.pulls?.length">
        <h2>What drew them in</h2>
        <ul class="hyp-list">
          <li v-for="p in report.pulls" :key="p.id">
            <span class="hyp-key">{{ p.label }}</span>
            <span class="hyp-num">{{ p.count }}</span>
          </li>
        </ul>
      </section>

      <section v-if="report.word_of_mouth?.heard">
        <h2>Would they pass it on</h2>
        <p>
          {{ report.word_of_mouth.would_tell }} of {{ report.word_of_mouth.heard }} said they'd
          tell someone about it; {{ report.word_of_mouth.would_warn }} said they'd warn people off.
        </p>
        <p class="hyp-fine">
          Counted only where the person's own survey record shows they talk things over
          with others. A count of what people said, not a forecast.
        </p>
      </section>

      <section v-if="report.conditions?.length">
        <h2>What they said would change their mind</h2>
        <blockquote v-for="(c, i) in report.conditions" :key="i">
          <p>{{ c.quote }}</p>
          <cite>{{ c.name }} · {{ c.stance }}</cite>
        </blockquote>
      </section>

      <section v-if="tiers.length">
        <h2>What their real income supports</h2>
        <p class="hyp-fine">
          Computed from each person's real household income — never estimated.
          It is what they can afford, not a forecast of what they will purchase.
        </p>
        <ul class="hyp-list">
          <li v-for="t in tiers" :key="t[0]">
            <span class="hyp-key">{{ t[0] }}</span>
            <span class="hyp-num">{{ t[1] }}</span>
          </li>
        </ul>
      </section>

      <section>
        <h2>What to test next</h2>
        <template v-if="report.hypotheses?.length">
          <p class="hyp-fine">
            These are guesses, not findings. Each one names the run that would
            check it.
          </p>
          <div v-for="(h, i) in report.hypotheses" :key="i" class="hyp-card">
            <p class="hyp-claim">{{ i + 1 }}. {{ h.claim }}</p>
            <p class="hyp-test"><b>Test it:</b> {{ h.test }}</p>
          </div>
        </template>
        <p v-else class="hyp-none">
          No hypotheses were generated for this session.
        </p>
      </section>

      <footer v-if="coverage.segments_available" class="hyp-foot">
        Compared across {{ coverage.segments_compared }} of
        {{ coverage.segments_available }} groups in our library. This answer is
        bounded by that coverage, not by the whole market.
      </footer>
    </article>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getHypothesis } from '../api/panel'

const props = defineProps({ sessionId: { type: String, required: true } })
const router = useRouter()

const report = ref(null)
const busy = ref(false)
const error = ref('')
const copied = ref(false)

const room = computed(() => report.value?.room || { seats: 0, heard: 0 })
const movement = computed(() => report.value?.movement || {})
const coverage = computed(() => room.value.coverage || {})
// Biggest group first, so the shape of the room reads at a glance.
const stances = computed(() =>
  Object.entries(report.value?.stance_split || {}).sort((a, b) => b[1] - a[1]))
const tiers = computed(() =>
  Object.entries(room.value.budget_tiers || {}).sort((a, b) => a[0].localeCompare(b[0])))

const load = async (refresh = false) => {
  busy.value = true
  error.value = ''
  try {
    const res = await getHypothesis(props.sessionId, refresh)
    if (res.data?.success) report.value = res.data.data
    else error.value = res.data?.error || 'The report could not be assembled.'
  } catch (e) {
    error.value = e?.response?.data?.error || 'The report could not be assembled. Try again.'
  } finally {
    busy.value = false
  }
}

const copyLink = async () => {
  try {
    await navigator.clipboard.writeText(window.location.href)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch (_) { /* clipboard blocked — the URL bar still has the link */ }
}

const print = () => window.print()
// Panels open from the app shell, which holds its state in memory. Go back in
// history where there is history, and land on home when the report was opened
// in a fresh tab.
const goBack = () => (window.history.length > 1 ? router.back() : router.push('/'))

onMounted(load)
</script>

<style scoped>
.hyp-shell {
  min-height: 100vh;
  background: #f6f7f6;
  color: #14201a;
  font: 15px/1.6 -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.hyp-bar {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid #e3e7e4;
}

.hyp-bar-actions { display: flex; gap: 8px; }

.hyp-back,
.hyp-act {
  border: 1px solid #d8ded9;
  background: #fff;
  color: #14201a;
  border-radius: 8px;
  padding: 7px 12px;
  font-size: 13px;
  cursor: pointer;
}

.hyp-back:hover,
.hyp-act:hover:not(:disabled) { border-color: #1E9E5A; color: #1E9E5A; }
.hyp-act:disabled { opacity: .5; cursor: default; }

.hyp-state {
  max-width: 760px;
  margin: 64px auto;
  padding: 0 24px;
  color: #5b6b62;
}
.hyp-state--bad { color: #a3341f; }

.hyp-page {
  max-width: 760px;
  margin: 0 auto;
  padding: 36px 24px 96px;
}

h1 { font-size: 26px; margin: 0 0 14px; letter-spacing: -.01em; }

h2 {
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: .07em;
  color: #5b6b62;
  margin: 34px 0 10px;
}

section { border-top: 1px solid #e3e7e4; }
section:first-of-type { border-top: none; }

.hyp-meta { color: #3c4b43; margin: 0 0 18px; }

.hyp-warn {
  background: #fdf5e6;
  border-left: 3px solid #d09a2a;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin: 0 0 20px;
}

.hyp-fine { color: #5b6b62; font-size: 13px; margin: 0 0 12px; }
.hyp-none { color: #5b6b62; }

.hyp-list { list-style: none; margin: 0; padding: 0; }

.hyp-list li {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 8px 0;
  border-bottom: 1px solid #edf0ee;
}

.hyp-key { color: #14201a; }
.hyp-num { font-variant-numeric: tabular-nums; color: #5b6b62; }

.hyp-moves { list-style: none; margin: 10px 0 0; padding: 0; }

.hyp-moves li {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
  padding: 9px 0 9px 12px;
  border-left: 3px solid #d8ded9;
  margin-bottom: 6px;
}

.hyp-moves li.warmer { border-left-color: #1E9E5A; }
.hyp-moves li.cooler { border-left-color: #a3341f; }

.hyp-name { font-weight: 600; }
.hyp-arrow { color: #5b6b62; font-size: 13px; }

.hyp-tag {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: #5b6b62;
}

blockquote {
  margin: 0 0 16px;
  padding: 12px 16px;
  background: #fff;
  border-left: 3px solid #1E9E5A;
  border-radius: 0 6px 6px 0;
}

blockquote p { margin: 0 0 6px; }
cite { font-style: normal; font-size: 12px; color: #5b6b62; }

.hyp-card {
  background: #fff;
  border: 1px solid #e3e7e4;
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 10px;
}

.hyp-claim { font-weight: 600; margin: 0 0 6px; }
.hyp-test { margin: 0; color: #3c4b43; font-size: 14px; }

.hyp-foot {
  margin-top: 34px;
  padding-top: 16px;
  border-top: 1px solid #e3e7e4;
  color: #5b6b62;
  font-size: 12px;
}

/* Printing is the sharing path that always works — no link, no login. */
@media print {
  .hyp-bar { display: none; }
  .hyp-shell { background: #fff; }
  .hyp-page { padding: 0; max-width: none; }
  .hyp-card, blockquote { break-inside: avoid; }
}
</style>
