import service, { requestWithRetry } from './index'

// Analytics endpoints are fast DB reads, not long-running generation. Override
// the global 5-minute axios timeout so a stalled request fails in ~30s with a
// clear error instead of spinning for minutes. (Retries on 4xx are already
// suppressed in index.js, so a missing-data 404 also fails fast.)
const ANALYTICS_OPTS = { timeout: 30000 }

/**
 * Get sentiment timeline with event markers
 * @param {string} simulationId
 */
export const getSentimentTimeline = (simulationId) => {
  return requestWithRetry(() => service.get(`/api/analysis/${simulationId}/sentiment-timeline`, ANALYTICS_OPTS), 3, 1000)
}

/**
 * Get archetype activity heatmap data
 * @param {string} simulationId
 */
export const getArchetypeActivity = (simulationId) => {
  return requestWithRetry(() => service.get(`/api/analysis/${simulationId}/archetype-activity`, ANALYTICS_OPTS), 3, 1000)
}

/**
 * Get event impact before/after comparison
 * @param {string} simulationId
 * @param {string} eventId
 */
export const getEventImpact = (simulationId, eventId) => {
  return requestWithRetry(() => service.get(`/api/analysis/${simulationId}/event-impact/${eventId}`, ANALYTICS_OPTS), 3, 1000)
}

/**
 * Get topic cascade data
 * @param {string} simulationId
 */
export const getTopicCascade = (simulationId) => {
  return requestWithRetry(() => service.get(`/api/analysis/${simulationId}/topic-cascade`, ANALYTICS_OPTS), 3, 1000)
}

/**
 * Get radicalism drift tracking
 * @param {string} simulationId
 */
export const getRadicalismDrift = (simulationId) => {
  return requestWithRetry(() => service.get(`/api/analysis/${simulationId}/radicalism-drift`, ANALYTICS_OPTS), 3, 1000)
}

/**
 * Get non-participation breakdown
 * @param {string} simulationId
 */
export const getNonParticipation = (simulationId) => {
  return requestWithRetry(() => service.get(`/api/analysis/${simulationId}/non-participation`, ANALYTICS_OPTS), 3, 1000)
}

/**
 * Get event summary
 * @param {string} simulationId
 */
export const getEventSummary = (simulationId) => {
  return requestWithRetry(() => service.get(`/api/analysis/${simulationId}/event-summary`, ANALYTICS_OPTS), 3, 1000)
}

/**
 * Get agent summary
 * @param {string} simulationId
 */
export const getAgentSummary = (simulationId) => {
  return requestWithRetry(() => service.get(`/api/analysis/${simulationId}/agent-summary`, ANALYTICS_OPTS), 3, 1000)
}

/**
 * Get complete overview (combined metrics)
 * @param {string} simulationId
 */
export const getOverview = (simulationId) => {
  return requestWithRetry(() => service.get(`/api/analysis/${simulationId}/overview`, ANALYTICS_OPTS), 3, 1000)
}
