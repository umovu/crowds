<template>
  <div class="poster-test">
    <header>
      <h1>Poster test</h1>
      <p class="sub">
        Upload a social poster. The vision model reads it once into a text brief.
        The panel only ever sees that text.
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
        <h2>The brief</h2>
        <p v-if="busy" class="waiting">Reading…</p>
        <pre v-else-if="brief">{{ brief }}</pre>
        <p v-else class="waiting">Stored, not read. The brief is empty.</p>

        <template v-if="questions.length">
          <h2>Questions the panel gets asked</h2>
          <ol class="questions">
            <li v-for="q in questions" :key="q">{{ q }}</li>
          </ol>
        </template>

        <p v-if="posterId" class="meta">{{ posterId }}</p>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { uploadPoster } from '../api/panel'

const file = ref(null)
const preview = ref('')
const brief = ref('')
const questions = ref([])
const posterId = ref('')
const busy = ref(false)
const error = ref('')
const dragOver = ref(false)

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
  error.value = ''
}

async function read (useModel) {
  if (!file.value) return
  busy.value = true
  error.value = ''
  brief.value = ''
  try {
    const res = await uploadPoster(file.value, useModel)
    brief.value = res.data.brief || ''
    questions.value = res.data.questions || []
    posterId.value = res.data.poster_id
  } catch (e) {
    error.value = e.message || 'Upload failed'
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

/* The raw file input is hidden — clicking anywhere in the dashed box opens the
   picker, because the whole box is the <label> for it. */
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
pre {
  white-space: pre-wrap;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 13px;
  line-height: 1.6;
  background: #f7f9f8;
  border: 1px solid #e3e8e5;
  border-radius: 8px;
  padding: 16px;
  margin: 0 0 24px;
  overflow-x: auto;
}
.waiting { color: #888; margin: 0 0 24px; }
.questions { margin: 0 0 20px; padding-left: 22px; line-height: 1.8; }
.meta { color: #aaa; font-size: 12px; margin: 0; }
</style>
