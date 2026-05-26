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
  enrichmentData: {},
  isPending: false
})

export function setPendingUpload(files, requirement, customAgents = [], customAgentsEnabled = false) {
  state.files = files
  state.simulationRequirement = requirement
  state.customAgents = customAgents
  state.customAgentsEnabled = customAgentsEnabled
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
    enrichmentData: state.enrichmentData,
    isPending: state.isPending
  }
}

export function clearPendingUpload() {
  state.files = []
  state.simulationRequirement = ''
  state.customAgents = []
  state.customAgentsEnabled = false
  state.enrichmentData = {}
  state.isPending = false
}

export default state
