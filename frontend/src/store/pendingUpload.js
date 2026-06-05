/**
 * Temporarily store files and requirements to be uploaded
 * Used to immediately navigate after clicking Start Engine on home page, API call is made on Process page
 */
import { reactive } from 'vue'

const state = reactive({
  files: [],
  simulationRequirement: '',
  customAgents: [],
  customAgentsEnabled: false,
  customAgentsOnly: false,
  mode: 'policy',
  enrichmentData: {},
  isPending: false
})

export function setPendingUpload(files, requirement, customAgents = [], customAgentsEnabled = false, customAgentsOnly = false, mode = 'policy') {
  state.files = files
  state.simulationRequirement = requirement
  state.customAgents = customAgents
  state.customAgentsEnabled = customAgentsEnabled
  state.customAgentsOnly = customAgentsOnly
  state.mode = mode
  state.isPending = true
}

export function setEnrichmentData(data) {
  state.enrichmentData = data
}

export function getPendingUpload() {
  return {
    files: state.files,
    simulationRequirement: state.simulationRequirement,
    customAgents: state.customAgents,
    customAgentsEnabled: state.customAgentsEnabled,
    customAgentsOnly: state.customAgentsOnly,
    mode: state.mode,
    enrichmentData: state.enrichmentData,
    isPending: state.isPending
  }
}

export function clearPendingUpload() {
  state.files = []
  state.simulationRequirement = ''
  state.customAgents = []
  state.customAgentsEnabled = false
  state.customAgentsOnly = false
  state.mode = 'policy'
  state.enrichmentData = {}
  state.isPending = false
}

export default state
