import service from './index'

/**
 * Search academic literature across all sources
 * @param {Object} data - Contains query, sources, max_results
 * @returns {Promise}
 */
export function searchLiterature(data) {
  return service({
    url: '/api/research/search',
    method: 'post',
    data
  })
}

/**
 * Search a specific source only
 * @param {string} source - 'arxiv', 'openalex', 'crossref', or 'local'
 * @param {Object} data - Contains query, max_results
 * @returns {Promise}
 */
export function searchSource(source, data) {
  return service({
    url: `/api/research/search/${source}`,
    method: 'post',
    data
  })
}

/**
 * Get all local papers
 * @returns {Promise}
 */
export function getLocalPapers() {
  return service({
    url: '/api/research/local',
    method: 'get'
  })
}

/**
 * Add a local paper manually
 * @param {Object} data - Contains title, authors, year, abstract, doi
 * @returns {Promise}
 */
export function addLocalPaper(data) {
  return service({
    url: '/api/research/local',
    method: 'post',
    data
  })
}

/**
 * Upload a local paper file
 * @param {FormData} formData - Contains file and optional metadata
 * @returns {Promise}
 */
export function uploadLocalPaper(formData) {
  return service({
    url: '/api/research/local/upload',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

/**
 * Perform web research via MiroFlow
 * @param {Object} data - Contains query, llm, agent
 * @returns {Promise}
 */
export function webResearch(data) {
  return service({
    url: '/api/research/web',
    method: 'post',
    data
  })
}

/**
 * Check MiroFlow availability
 * @returns {Promise}
 */
export function webResearchStatus() {
  return service({
    url: '/api/research/web/status',
    method: 'get'
  })
}

/**
 * Enrich agent context with research findings
 * @param {Object} data - Contains query, archetypes, research_type, papers
 * @returns {Promise}
 */
export function enrichAgents(data) {
  return service({
    url: '/api/research/enrich',
    method: 'post',
    data
  })
}

/**
 * Search Google via Serper API
 * @param {Object} data - Contains query, num_results
 * @returns {Promise}
 */
export function webSearch(data) {
  return service({
    url: '/api/research/web/search',
    method: 'post',
    data
  })
}

/**
 * Scrape a URL via Firecrawl
 * @param {Object} data - Contains url
 * @returns {Promise}
 */
export function scrapeUrl(data) {
  return service({
    url: '/api/research/web/scrape',
    method: 'post',
    data
  })
}

/**
 * Run MiroFlow deep research for persona enrichment
 * Researches current reality for each archetype found in the document
 * @param {Object} data - Contains query, document_text, archetypes
 * @returns {Promise}
 */
export function deepResearch(data) {
  return service({
    url: '/api/research/deep',
    method: 'post',
    data,
    timeout: 600000 // 10 minutes for deep research
  })
}

/**
 * Generate seed material from web research (when user has no document).
 * Searches Google for the topic, scrapes top results via Firecrawl, then
 * synthesizes a structured policy briefing via LLM.
 * @param {Object} data - { topic: string, extra_urls?: string[] }
 * @returns {Promise<{ success, seed_text, sources, scraped_count, char_count }>}
 */
export function generateSeedFromWeb(data) {
  return service({
    url: '/api/research/seed',
    method: 'post',
    data,
    timeout: 180000 // 3 minutes — search+scrape+synthesize can be slow
  })
}

/**
 * Search for a real-world group of people and generate matching agent personas.
 * Lets users model how a specific group ("Cape Town taxi drivers") would react.
 * @param {Object} data - { group: string, count?: number, ground_with_web?: boolean, context?: string }
 * @returns {Promise<{ success, agents, grounded, sources, count }>}
 */
export function searchPeople(data) {
  return service({
    url: '/api/research/people',
    method: 'post',
    data,
    timeout: 180000 // web grounding + LLM generation can be slow
  })
}

/**
 * List every cached/generated persona — metadata only, for the side panel.
 * @returns {Promise<{success, count, personas}>}
 */
export function listPersonas() {
  return service({ url: '/api/research/personas', method: 'get' })
}

/**
 * Fetch a single persona's full profile + markdown card.
 * @param {string} personaId - hex hash id from listPersonas()
 */
export function getPersona(personaId) {
  return service({ url: `/api/research/personas/${personaId}`, method: 'get' })
}