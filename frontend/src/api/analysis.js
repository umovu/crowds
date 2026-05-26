import service, { requestWithRetry } from './index'

/**
 * Get sentiment timeline with event markers
 * @param {string} simulationId
 */
export const getSentimentTimeline = (simulationId) => {
  return requestWithRetry(() => service.get(`/api/analysis/${simulationId}/sentiment-timeline`), 3, 1000)
}

/**
 * Get archetype activity heatmap data
 * @param {string} simulationId
 */
export const getArchetypeActivity = (simulationId) => {
  return requestWithRetry(() => service.get(`/api/analysis/${simulationId}/archetype-activity`), 3, 1000)
}

/**
 * Get event impact before/after comparison
 * @param {string} simulationId
 * @param {string} eventId
 */
export const getEventImpact = (simulationId, eventId) => {
  return requestWithRetry(() => service.get(`/api/analysis/${simulationId}/event-impact/${eventId}`), 3, 1000)
}

/**
 * Get topic cascade data
 * @param {string} simulationId
 */
export const getTopicCascade = (simulationId) => {
  return requestWithRetry(() => service.get(`/api/analysis/${simulationId}/topic-cascade`), 3, 1000)
}

/**
 * Get radicalism drift tracking
 * @param {string} simulationId
 */
export const getRadicalismDrift = (simulationId) => {
  return requestWithRetry(() => service.get(`/api/analysis/${simulationId}/radicalism-drift`), 3, 1000)
}

/**
 * Get non-participation breakdown
 * @param {string} simulationId
 */
export const getNonParticipation = (simulationId) => {
  return requestWithRetry(() => service.get(`/api/analysis/${simulationId}/non-participation`), 3, 1000)
}

/**
 * Get event summary
 * @param {string} simulationId
 */
export const getEventSummary = (simulationId) => {
  return requestWithRetry(() => service.get(`/api/analysis/${simulationId}/event-summary`), 3, 1000)
}

/**
 * Get agent summary
 * @param {string} simulationId
 */
export const getAgentSummary = (simulationId) => {
  return requestWithRetry(() => service.get(`/api/analysis/${simulationId}/agent-summary`), 3, 1000)
}

/**
 * Get complete overview (combined metrics)
 * @param {string} simulationId
 */
export const getOverview = (simulationId) => {
  return requestWithRetry(() => service.get(`/api/analysis/${simulationId}/overview`), 3, 1000)
}
