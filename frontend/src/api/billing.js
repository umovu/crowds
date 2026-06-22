import service from './index'

// Current plan + usage for the signed-in user (drives upgrade UI / gating).
export function getBillingStatus() {
  return service.get('/api/billing/status')
}

// Start a Paystack checkout. Returns { authorization_url, reference }.
// callbackUrl is where Paystack returns the user after payment.
export function createCheckout(callbackUrl) {
  return service.post('/api/billing/checkout', { callback_url: callbackUrl })
}

// Kick off the upgrade: get a Paystack URL and send the browser there.
export async function startUpgrade(callbackUrl) {
  const fallback = `${window.location.origin}/billing/callback`
  const res = await createCheckout(callbackUrl || fallback)
  const url = res?.data?.authorization_url
  if (!url) throw new Error('Could not start checkout')
  window.location.assign(url)
}
