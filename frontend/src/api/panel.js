import service from './index'

// Panel Pitch API — pitch ideas at library-backed persona casts, no simulation.

export const listSegments = () =>
  service.get('/api/panel/segments')

export const createSession = (payload) =>
  service.post('/api/panel/sessions', payload)

export const listSessions = () =>
  service.get('/api/panel/sessions')

export const getSession = (sessionId) =>
  service.get(`/api/panel/sessions/${sessionId}`)

export const deleteSession = (sessionId) =>
  service.delete(`/api/panel/sessions/${sessionId}`)

export const pitchSession = (sessionId, payload = {}) =>
  service.post(`/api/panel/sessions/${sessionId}/pitch`, payload)

export const listRounds = (sessionId, full = false) =>
  service.get(`/api/panel/sessions/${sessionId}/rounds`, { params: { full: full ? 1 : 0 } })

export const askAgent = (sessionId, agentId, question) =>
  service.post(`/api/panel/sessions/${sessionId}/agents/${agentId}/ask`, { question })
