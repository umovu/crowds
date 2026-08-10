// One message surface for the whole app.
//
// Before this, a failure that wasn't fatal to the page went to console.warn —
// invisible to the user, who saw a button un-spin and nothing else. Every one of
// those spots now has somewhere to put the message.
//
// Deliberately tiny: module-level state, no store, no plugin. Import it
// anywhere; the single <Toast /> in App.vue renders whatever is in `items`.
import { ref } from 'vue'

const items = ref([])
let nextId = 1

const push = (type, text, opts = {}) => {
  // Never stack the same message twice — a failing poll fires every 3 seconds
  // and would otherwise bury the screen in identical bars.
  const existing = items.value.find(t => t.text === text)
  if (existing) return existing.id

  const id = nextId++
  items.value.push({ id, type, text, retry: opts.retry || null, code: opts.code || null })

  // Errors stay until dismissed (or replaced) — an error that vanishes before
  // it's read is the problem we're fixing. Info messages self-clear.
  if (type !== 'error') {
    setTimeout(() => dismiss(id), opts.duration || 4000)
  }
  return id
}

const dismiss = (id) => { items.value = items.value.filter(t => t.id !== id) }

export const useToast = () => ({
  items,
  // A failure the user needs to know about. `retry` renders a button.
  error: (text, opts) => push('error', text, opts),
  // Transient, self-clearing status ("Back online.").
  info: (text, opts) => push('info', text, opts),
  dismiss,
  clear: () => { items.value = [] },
})
