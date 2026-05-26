<template>
  <!-- Floating toggle button -->
  <button
    class="library-fab"
    :class="{ open }"
    @click="toggle"
    :title="open ? 'Close persona library' : 'Open persona library'"
  >
    <span class="fab-icon">👥</span>
    <span class="fab-label">Personas</span>
    <span v-if="personas.length && !loading" class="fab-count">{{ personas.length }}</span>
  </button>

  <!-- Backdrop -->
  <Transition name="fade">
    <div v-if="open" class="drawer-backdrop" @click="close"></div>
  </Transition>

  <!-- Side drawer -->
  <Transition name="slide">
    <aside v-if="open" class="drawer">
      <header class="drawer-header">
        <div>
          <h2>Persona Library</h2>
          <p class="drawer-sub">
            <span v-if="loading">Loading…</span>
            <span v-else>{{ personas.length }} cached personas</span>
          </p>
        </div>
        <button class="drawer-close" @click="close" title="Close">×</button>
      </header>

      <div class="drawer-controls">
        <input
          v-model="search"
          class="drawer-search"
          type="text"
          placeholder="Search name, archetype, occupation..."
        />
        <select v-model="archetypeFilter" class="drawer-filter">
          <option value="">All archetypes</option>
          <option v-for="a in archetypes" :key="a" :value="a">
            {{ a.replace(/_/g, ' ') }}
          </option>
        </select>
        <button class="drawer-refresh" @click="load" :disabled="loading" title="Refresh">↻</button>
      </div>

      <div class="drawer-body">
        <!-- List pane -->
        <div class="list-pane">
          <div v-if="loading && personas.length === 0" class="empty">Loading personas…</div>
          <div v-else-if="filtered.length === 0" class="empty">
            No personas match.<br />
            <span class="empty-hint">Run a sim prepare to populate the library.</span>
          </div>
          <button
            v-for="p in filtered"
            :key="p.id"
            class="persona-row"
            :class="{ active: selectedId === p.id }"
            @click="select(p)"
          >
            <div class="persona-name">{{ p.name }}</div>
            <div class="persona-meta">
              <span class="badge">{{ (p.archetype || 'unknown').replace(/_/g, ' ') }}</span>
              <span v-if="p.age" class="meta-bit">{{ p.age }}y</span>
              <span v-if="p.occupation" class="meta-bit">{{ p.occupation }}</span>
            </div>
          </button>
        </div>

        <!-- Detail pane -->
        <div class="detail-pane">
          <div v-if="!selected" class="detail-placeholder">
            <div class="placeholder-icon">←</div>
            <p>Select a persona to view its card.</p>
          </div>
          <div v-else-if="detailLoading" class="empty">Loading card…</div>
          <div v-else class="detail-content" v-html="detailHtml"></div>
        </div>
      </div>
    </aside>
  </Transition>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { listPersonas, getPersona } from '../api/research'

const open = ref(false)
const personas = ref([])
const loading = ref(false)
const search = ref('')
const archetypeFilter = ref('')
const selectedId = ref(null)
const selected = ref(null)
const detailMd = ref('')
const detailLoading = ref(false)

const archetypes = computed(() => {
  const s = new Set()
  for (const p of personas.value) if (p.archetype) s.add(p.archetype)
  return Array.from(s).sort()
})

const filtered = computed(() => {
  let list = personas.value
  if (archetypeFilter.value) list = list.filter(p => p.archetype === archetypeFilter.value)
  if (search.value.trim()) {
    const q = search.value.trim().toLowerCase()
    list = list.filter(p =>
      (p.name || '').toLowerCase().includes(q) ||
      (p.archetype || '').toLowerCase().includes(q) ||
      (p.occupation || '').toLowerCase().includes(q)
    )
  }
  return list
})

// Very small markdown → HTML renderer (headings, bold, italics, lists,
// horizontal rule, &nbsp; passthrough). Sufficient for the card format we
// emit; avoids pulling in a markdown lib for one view.
const detailHtml = computed(() => {
  const md = detailMd.value
  if (!md) return ''
  const escape = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const lines = md.split('\n')
  const out = []
  let inList = false
  for (let raw of lines) {
    let line = raw
    // Allow &nbsp; passthrough by temporarily marking it
    line = line.replace(/&nbsp;/g, 'NBSP')
    line = escape(line)
    line = line.replace(/NBSP/g, '&nbsp;')
    // bold + italics
    line = line.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    line = line.replace(/(^|[^*])\*(?!\s)([^*]+?)\*/g, '$1<em>$2</em>')
    line = line.replace(/_([^_]+)_/g, '<em>$1</em>')
    line = line.replace(/`([^`]+)`/g, '<code>$1</code>')

    if (line.startsWith('# ')) {
      if (inList) { out.push('</ul>'); inList = false }
      out.push(`<h1>${line.slice(2)}</h1>`)
    } else if (line.startsWith('## ')) {
      if (inList) { out.push('</ul>'); inList = false }
      out.push(`<h2>${line.slice(3)}</h2>`)
    } else if (line.startsWith('### ')) {
      if (inList) { out.push('</ul>'); inList = false }
      out.push(`<h3>${line.slice(4)}</h3>`)
    } else if (/^- /.test(line)) {
      if (!inList) { out.push('<ul>'); inList = true }
      out.push(`<li>${line.slice(2)}</li>`)
    } else if (line.trim() === '---') {
      if (inList) { out.push('</ul>'); inList = false }
      out.push('<hr />')
    } else if (line.trim() === '') {
      if (inList) { out.push('</ul>'); inList = false }
      out.push('')
    } else if (line.startsWith('&lt;sub&gt;') || line.startsWith('&lt;/sub&gt;')) {
      // <sub> footer — render as small text
      const inner = line.replace('&lt;sub&gt;', '<small>').replace('&lt;/sub&gt;', '</small>')
      out.push(inner)
    } else {
      if (inList) { out.push('</ul>'); inList = false }
      out.push(`<p>${line}</p>`)
    }
  }
  if (inList) out.push('</ul>')
  return out.join('\n')
})

async function load() {
  loading.value = true
  try {
    const res = await listPersonas()
    if (res.success) personas.value = res.personas || []
  } catch (e) {
    console.error('Failed to load personas:', e)
  } finally {
    loading.value = false
  }
}

async function select(p) {
  selectedId.value = p.id
  selected.value = p
  detailLoading.value = true
  detailMd.value = ''
  try {
    const res = await getPersona(p.id)
    if (res.success) detailMd.value = res.markdown || '*(no card available)*'
  } catch (e) {
    detailMd.value = `*Error loading: ${e.message}*`
  } finally {
    detailLoading.value = false
  }
}

function toggle() {
  open.value = !open.value
  if (open.value && personas.value.length === 0) load()
}

function close() {
  open.value = false
}

// Refresh when opening (in case a sim ran in another tab)
watch(open, (v) => { if (v) load() })

onMounted(() => {
  // Don't fetch until user opens it — keeps initial page load light
})
</script>

<style scoped>
.library-fab {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 998;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 18px;
  background: #000;
  color: #fff;
  border: 1px solid #000;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.85rem;
  font-weight: 600;
  box-shadow: 0 4px 14px rgba(0,0,0,0.18);
  transition: all 0.2s;
}
.library-fab:hover { background: #1E9E5A; border-color: #1E9E5A; }
.library-fab.open { background: #1E9E5A; border-color: #1E9E5A; }
.fab-icon { font-size: 1rem; }
.fab-count {
  background: #fff;
  color: #1E9E5A;
  padding: 2px 8px;
  border-radius: 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
}

.drawer-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.35);
  z-index: 999;
}

.drawer {
  position: fixed;
  top: 0; right: 0; bottom: 0;
  width: min(820px, 95vw);
  background: #fff;
  border-left: 1px solid #E5E5E5;
  box-shadow: -8px 0 24px rgba(0,0,0,0.12);
  z-index: 1000;
  display: flex;
  flex-direction: column;
}

.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 20px 24px 12px;
  border-bottom: 1px solid #EAEAEA;
}
.drawer-header h2 { margin: 0; font-size: 1.2rem; }
.drawer-sub { margin: 4px 0 0; font-size: 0.8rem; color: #999; font-family: 'JetBrains Mono', monospace; }
.drawer-close {
  width: 32px; height: 32px;
  background: transparent; border: none;
  font-size: 1.6rem; cursor: pointer; color: #666;
  line-height: 1;
}
.drawer-close:hover { color: #1E9E5A; }

.drawer-controls {
  display: flex; gap: 8px;
  padding: 12px 24px;
  border-bottom: 1px solid #EAEAEA;
  background: #FAFAFA;
}
.drawer-search {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #DDD;
  font-family: inherit;
  font-size: 0.85rem;
}
.drawer-search:focus { outline: none; border-color: #1E9E5A; }
.drawer-filter {
  padding: 8px 10px;
  border: 1px solid #DDD;
  background: #fff;
  font-family: inherit;
  font-size: 0.85rem;
  max-width: 180px;
}
.drawer-refresh {
  padding: 8px 12px;
  background: #fff;
  border: 1px solid #DDD;
  cursor: pointer;
  font-size: 1rem;
}
.drawer-refresh:hover { border-color: #1E9E5A; color: #1E9E5A; }
.drawer-refresh:disabled { opacity: 0.4; cursor: not-allowed; }

.drawer-body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.list-pane {
  width: 320px;
  border-right: 1px solid #EAEAEA;
  overflow-y: auto;
  background: #FAFAFA;
}
.empty {
  padding: 30px 20px;
  text-align: center;
  font-size: 0.85rem;
  color: #999;
}
.empty-hint { font-size: 0.75rem; color: #BBB; }
.persona-row {
  display: block;
  width: 100%;
  text-align: left;
  padding: 12px 16px;
  background: transparent;
  border: none;
  border-bottom: 1px solid #EFEFEF;
  cursor: pointer;
  transition: background 0.15s;
  font-family: inherit;
}
.persona-row:hover { background: #F0F0F0; }
.persona-row.active { background: #F0FAF4; border-left: 3px solid #1E9E5A; padding-left: 13px; }
.persona-name { font-weight: 600; font-size: 0.9rem; color: #000; }
.persona-meta { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; font-size: 0.72rem; color: #777; }
.badge {
  background: #000; color: #fff;
  padding: 1px 7px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.65rem;
}
.meta-bit { color: #666; }

.detail-pane {
  flex: 1;
  overflow-y: auto;
  padding: 28px 32px;
}
.detail-placeholder {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  height: 100%;
  color: #BBB;
  text-align: center;
}
.placeholder-icon { font-size: 2rem; margin-bottom: 8px; }
.detail-content { font-size: 0.9rem; line-height: 1.55; color: #222; }
.detail-content :deep(h1) { font-size: 1.4rem; margin: 0 0 6px; }
.detail-content :deep(h2) { font-size: 1rem; margin: 20px 0 8px; color: #1E9E5A; border-bottom: 1px solid #F0F0F0; padding-bottom: 4px; }
.detail-content :deep(h3) { font-size: 0.9rem; margin: 14px 0 6px; }
.detail-content :deep(p) { margin: 6px 0; }
.detail-content :deep(ul) { margin: 6px 0; padding-left: 20px; }
.detail-content :deep(li) { margin: 2px 0; }
.detail-content :deep(code) {
  font-family: 'JetBrains Mono', monospace;
  background: #F4F4F4;
  padding: 1px 6px;
  font-size: 0.85em;
}
.detail-content :deep(hr) {
  border: none;
  border-top: 1px solid #EAEAEA;
  margin: 16px 0;
}
.detail-content :deep(small) { color: #999; font-size: 0.75rem; }

/* transitions */
.fade-enter-active, .fade-leave-active { transition: opacity 0.18s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
.slide-enter-active, .slide-leave-active { transition: transform 0.22s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }

@media (max-width: 720px) {
  .drawer-body { flex-direction: column; }
  .list-pane { width: 100%; max-height: 40vh; border-right: none; border-bottom: 1px solid #EAEAEA; }
  .drawer-filter { max-width: 140px; }
}
</style>
