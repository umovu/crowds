import service from './index'

// Panel Pitch API — pitch ideas at library-backed persona casts, no simulation.

export const listSegments = () =>
  service.get('/api/panel/segments')

export const suggestSegments = (pitch) =>
  service.get('/api/panel/segments/suggest', { params: { pitch } })

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

// Poster upload — one vision call reads the image into a text brief. Pass
// read=false to store the image without calling the model.
export const uploadPoster = (file, read = true) => {
  const form = new FormData()
  form.append('image', file)
  return service.post(`/api/panel/posters?read=${read ? 1 : 0}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export const getPoster = (posterId) =>
  service.get(`/api/panel/posters/${posterId}`)
