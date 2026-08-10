<template>
  <!-- Mounted once in App.vue, above every overlay. Fixed to the top so it's
       visible whether the user is on home, the build box or the results room. -->
  <div class="toast-stack" role="status" aria-live="polite">
    <TransitionGroup name="toast">
      <div v-for="t in items" :key="t.id" class="toast" :class="t.type">
        <span class="toast-text">{{ t.text }}</span>
        <span v-if="t.code" class="toast-code">{{ t.code }}</span>
        <button v-if="t.retry" class="toast-retry" @click="runRetry(t)">Try again</button>
        <button class="toast-close" aria-label="Dismiss" @click="dismiss(t.id)">✕</button>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup>
import { useToast } from '../composables/useToast'

const { items, dismiss } = useToast()

// Clear the bar before retrying, so a second failure reads as a new event
// rather than leaving the old message sitting there looking unhandled.
const runRetry = (t) => {
  const fn = t.retry
  dismiss(t.id)
  if (typeof fn === 'function') fn()
}
</script>

<style scoped>
.toast-stack {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: min(560px, calc(100vw - 32px));
  pointer-events: none;
}

.toast {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.4;
  background: #FFF;
  border: 1px solid #E5E7EB;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
}

.toast.error {
  background: #FEF3F2;
  border-color: #F3C4BF;
  color: #7A241B;
}

.toast.info {
  background: #F0F9F4;   /* accent green tint, matches the settled build step */
  border-color: #C8E6D2;
  color: #14603A;
}

.toast-text { flex: 1; }

.toast-code {
  font-size: 11px;
  opacity: 0.6;
  letter-spacing: 0.5px;
}

.toast-retry {
  border: 1px solid currentColor;
  background: transparent;
  color: inherit;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.toast-retry:hover { background: rgba(0, 0, 0, 0.05); }

.toast-close {
  border: none;
  background: transparent;
  color: inherit;
  opacity: 0.5;
  cursor: pointer;
  font-size: 13px;
  padding: 0 2px;
}
.toast-close:hover { opacity: 1; }

.toast-enter-active,
.toast-leave-active { transition: opacity 0.25s ease, transform 0.25s ease; }
.toast-enter-from,
.toast-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
