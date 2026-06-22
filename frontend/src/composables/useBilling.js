import { ref, computed } from 'vue'
import { getBillingStatus, startUpgrade } from '../api/billing'

// App-wide reactive billing state (module-level singletons).
const status = ref(null)        // { plan, panel_used, panel_limit, can_simulate, can_create_panel }
const loading = ref(false)

const plan = computed(() => status.value?.plan ?? 'free')
const isPaid = computed(() => plan.value === 'paid')
const canSimulate = computed(() => !!status.value?.can_simulate)
const canCreatePanel = computed(() => status.value?.can_create_panel !== false)

async function refresh() {
  loading.value = true
  try {
    const res = await getBillingStatus()
    status.value = res.data
  } catch (e) {
    // Fail-open in the UI: don't block on a billing read error.
    console.warn('Billing status fetch failed:', e)
  } finally {
    loading.value = false
  }
}

// Redirect to Paystack checkout. `next` is where to return after payment.
async function upgrade(next) {
  await startUpgrade(next)
}

export function useBilling() {
  return { status, loading, plan, isPaid, canSimulate, canCreatePanel, refresh, upgrade }
}
