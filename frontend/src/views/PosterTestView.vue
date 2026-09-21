<template>
  <div class="poster-test">
    <header>
      <h1>Poster test</h1>
      <p class="sub">
        Upload a social poster. The vision model reads it once into a text brief.
        You confirm the brief. Then a fixed cast answers four questions about it.
      </p>
    </header>

    <section class="pick">
      <label class="drop" :class="{ busy, over: dragOver }"
             @dragover.prevent="dragOver = true"
             @dragleave.prevent="dragOver = false"
             @drop.prevent="onDrop">
        <input type="file" accept="image/png,image/jpeg,image/webp"
               @change="onPick" :disabled="busy" />
        <span class="cue">Choose a poster</span>
        <span class="note" v-if="!file">or drag one in — PNG, JPG or WebP</span>
        <span class="note picked" v-else>{{ file.name }}</span>
      </label>

      <div class="actions">
        <button class="primary" :disabled="!file || busy" @click="read(true)">
          Read the poster
        </button>
        <button :disabled="!file || busy" @click="read(false)">
          Upload only, no model
        </button>
      </div>
      <p class="hint">
        Reading takes 30 to 60 seconds. It runs once per poster, then it is cached.
      </p>
    </section>

    <p v-if="error" class="error">{{ error }}</p>

    <section v-if="preview || brief" class="result">
      <div v-if="preview" class="pane">
        <h2>What you uploaded</h2>
        <img :src="preview" alt="Uploaded poster" />
      </div>

      <div class="pane">
        <template v-if="brief && !findings">
          <h2>Confirm the brief</h2>
          <p class="hint tight">
            Edit the text if the read got something wrong. This never re-reads the image.
          </p>

          <label class="field">Text on the poster
            <textarea v-model="fields.text" :disabled="frozen || busy" rows="4" />
          </label>
          <label class="field">Claims stated
            <textarea v-model="fields.claims_stated" :disabled="frozen || busy" rows="2" />
          </label>
          <label class="field">Claims implied
            <textarea v-model="fields.claims_implied" :disabled="frozen || busy" rows="2" />
          </label>
          <label class="field">The ask
            <textarea v-model="fields.ask" :disabled="frozen || busy" rows="2" />
          </label>
          <label class="field">Price shown
            <input v-model="fields.price" :disabled="frozen || busy" />
          </label>

          <div class="labels">
            <label class="field">Primary action
              <select v-model="primary" :disabled="frozen || busy">
                <option v-for="a in actionLabels" :key="a" :value="a">{{ a }}</option>
              </select>
            </label>
            <label class="field">Secondary action
              <select v-model="secondary" :disabled="frozen || busy">
                <option value="">none</option>
                <option v-for="a in actionLabels" :key="'s'+a" :value="a">{{ a }}</option>
              </select>
            </label>
            <label class="field">Channel
              <select v-model="channel" :disabled="frozen || busy">
                <option v-for="c in channelLabels" :key="c" :value="c">{{ c }}</option>
              </select>
            </label>
          </div>

          <div class="actions">
            <button :disabled="frozen || busy || !posterId" @click="saveBrief">
              Save corrections
            </button>
            <button class="primary" :disabled="busy || !posterId || frozen" @click="runPanel">
              Run poster panel
            </button>
          </div>
          <p v-if="frozen" class="hint tight">Brief is frozen after the run. Start a new upload to edit.</p>

          <template v-if="questions.length">
            <h2>Questions the panel gets asked</h2>
            <ol class="questions">
              <li v-for="q in questions" :key="q.id || q">{{ q.text || q }}</li>
            </ol>
          </template>
        </template>

        <p v-else-if="busy" class="waiting">Working…</p>
        <p v-else class="waiting">Stored, not read. The brief is empty.</p>

        <PosterResults :findings="findings" />

        <p v-if="posterId" class="meta">{{ posterId }}{{ sessionId ? ' · ' + sessionId : '' }}</p>
      </div>
    </section>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { uploadPoster, updatePoster, runPosterPanel } from '../api/panel'
import PosterResults from '../components/PosterResults.vue'

const file = ref(null)
const preview = ref('')
const brief = ref('')
const questions = ref([])
const posterId = ref('')
const sessionId = ref('')
const busy = ref(false)
const error = ref('')
const dragOver = ref(false)
const frozen = ref(false)
const findings = ref(null)
const actionLabels = ref(['buy', 'sign_up', 'apply', 'contact', 'visit', 'attend', 'vote', 'donate', 'none', 'unclear'])
const channelLabels = ref(['whatsapp', 'call', 'sms_ussd', 'website', 'app', 'in_person', 'qr_code', 'none'])
const primary = ref('unclear')
const secondary = ref('')
const channel = ref('none')
const fields = reactive({
  text: '',
  pictured: '',
  layout: '',
  claims_stated: '',
  claims_implied: '',
  ask: '',
  price: '',
})

function onPick (event) {
  accept(event.target.files?.[0])
}

function onDrop (event) {
  dragOver.value = false
  if (busy.value) return
  accept(event.dataTransfer?.files?.[0])
}

function accept (picked) {
  if (!picked) return
  file.value = picked
  preview.value = URL.createObjectURL(picked)
  brief.value = ''
  questions.value = []
  posterId.value = ''
  sessionId.value = ''
  findings.value = null
  frozen.value = false
  error.value = ''
}

function applyPoster (data) {
  brief.value = data.brief || ''
  questions.value = data.questions || []
  posterId.value = data.poster_id
  frozen.value = !!data.frozen
  const f = data.fields || {}
  fields.text = f.text || ''
  fields.pictured = f.pictured || ''
  fields.layout = f.layout || ''
  fields.claims_stated = f.claims_stated || ''
  fields.claims_implied = f.claims_implied || ''
  fields.ask = f.ask || ''
  fields.price = f.price || ''
  primary.value = data.ask_label_primary || 'unclear'
  secondary.value = data.ask_label_secondary || ''
  channel.value = data.channel || 'none'
  if (data.action_labels?.length) actionLabels.value = data.action_labels
  if (data.channel_labels?.length) channelLabels.value = data.channel_labels
}

async function read (useModel) {
  if (!file.value) return
  busy.value = true
  error.value = ''
  findings.value = null
  try {
    const res = await uploadPoster(file.value, useModel)
    applyPoster(res.data)
  } catch (e) {
    error.value = e.message || 'Upload failed'
  } finally {
    busy.value = false
  }
}

async function saveBrief () {
  if (!posterId.value || frozen.value) return
  busy.value = true
  error.value = ''
  try {
    const res = await updatePoster(posterId.value, {
      fields: { ...fields },
      ask_label_primary: primary.value,
      ask_label_secondary: secondary.value || 'none',
      channel: channel.value,
    })
    applyPoster(res.data)
  } catch (e) {
    error.value = e.message || 'Save failed'
  } finally {
    busy.value = false
  }
}

async function runPanel () {
  if (!posterId.value) return
  busy.value = true
  error.value = ''
  try {
    // Save current edits first so the round uses them.
    if (!frozen.value) {
      await updatePoster(posterId.value, {
        fields: { ...fields },
        ask_label_primary: primary.value,
        ask_label_secondary: secondary.value || 'none',
        channel: channel.value,
      })
    }
    const res = await runPosterPanel(posterId.value, { n: 12, spread: 7, spread: true })
    sessionId.value = res.data.session_id
    findings.value = res.data.findings
    frozen.value = true
  } catch (e) {
    error.value = e.message || 'Panel run failed'
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.poster-test {
  max-width: 1100px;
  margin: 0 auto;
  padding: 32px 24px 64px;
  color: #1a1a1a;
}

h1 { font-size: 28px; margin: 0 0 6px; }
.sub { color: #666; margin: 0 0 28px; max-width: 60ch; line-height: 1.5; }
h2 { font-size: 15px; text-transform: uppercase; letter-spacing: .06em;
     color: #666; margin: 0 0 10px; }

.drop {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  border: 2px dashed #c9d6cf;
  border-radius: 10px;
  padding: 44px 28px;
  text-align: center;
  cursor: pointer;
  transition: border-color .15s, background .15s;
}
.drop:hover, .drop.over { border-color: #1E9E5A; background: #f5fbf7; }
.drop.busy { opacity: .6; cursor: default; }
.drop input {
  position: absolute;
  width: 1px; height: 1px;
  opacity: 0;
  pointer-events: none;
}
.drop .cue {
  background: #1E9E5A;
  color: #fff;
  border-radius: 8px;
  padding: 12px 26px;
  font-size: 15px;
}
.drop .note { color: #777; font-size: 14px; }
.drop .note.picked { color: #1a1a1a; }

.actions { display: flex; gap: 10px; margin-top: 16px; flex-wrap: wrap; }
button {
  border: 1px solid #c9d6cf;
  background: #fff;
  color: #1a1a1a;
  border-radius: 8px;
  padding: 10px 18px;
  font-size: 14px;
  cursor: pointer;
}
button:hover:not(:disabled) { border-color: #1E9E5A; }
button.primary { background: #1E9E5A; border-color: #1E9E5A; color: #fff; }
button:disabled { opacity: .45; cursor: default; }

.hint { color: #888; font-size: 13px; margin: 10px 0 0; }
.hint.tight { margin: 0 0 14px; }
.error {
  margin-top: 18px; padding: 12px 14px;
  background: #fdf2f0; border: 1px solid #e6c3bc; border-radius: 8px;
  color: #99372a;
}

.result {
  display: grid;
  grid-template-columns: minmax(0, 380px) minmax(0, 1fr);
  gap: 28px;
  margin-top: 34px;
  align-items: start;
}
@media (max-width: 800px) { .result { grid-template-columns: 1fr; } }

.pane img { width: 100%; border-radius: 8px; border: 1px solid #e3e8e5; }
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: #555;
  margin: 0 0 12px;
}
.field input, .field textarea, .field select {
  border: 1px solid #c9d6cf;
  border-radius: 8px;
  padding: 10px 12px;
  font: inherit;
  color: #1a1a1a;
  background: #fff;
}
.field textarea { resize: vertical; }
.labels {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
@media (max-width: 800px) { .labels { grid-template-columns: 1fr; } }
.waiting { color: #888; margin: 0 0 24px; }
.questions { margin: 16px 0 20px; padding-left: 22px; line-height: 1.8; }
.meta { color: #aaa; font-size: 12px; margin: 16px 0 0; }
</style>
