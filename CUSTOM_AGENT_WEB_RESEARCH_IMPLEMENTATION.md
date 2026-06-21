# Custom Agent Context for Web Research - Implementation Summary

## Overview
This implementation enhances the web research functionality to allow custom agents to be used as context for web research grounding. Users can now select custom agents to shape the research context, making web research more relevant and focused on specific personas.

## Changes Made

### Backend Changes

#### 1. Web Research API (`backend/app/api/research.py`)
- **Modified**: `/api/research/web` endpoint to accept optional `agent_context` parameter
- **Added**: Support for custom agent context in the request body
- **Enhanced**: Research query generation to incorporate agent context

#### 2. Deep Research Service (`backend/app/services/deep_research_service.py`)
- **Modified**: `research_archetypes()` function to accept `agent_context` parameter
- **Enhanced**: `_research_one()` function to incorporate agent context into research focus
- **Updated**: `_run_in_thread()` function to pass agent context
- **Added**: Logic to enhance research queries with agent names and descriptions

#### 3. Simulation API (`backend/app/api/simulation.py`)
- **Modified**: `/api/simulation/<simulation_id>/research/rerun` endpoint to accept `agent_context`
- **Enhanced**: Research pipeline to use agent context when re-running research

### Frontend Changes

#### 1. Step2EnvSetup.vue Component
- **Added**: Agent Context for Web Research section
- **Added**: UI for selecting custom agents from available agents
- **Added**: Visual feedback for selected agents
- **Added**: Button to trigger research with selected agent context
- **Added**: Computed properties for available and selected agents
- **Added**: Agent context update logic

#### 2. Simulation API (`frontend/src/api/simulation.js`)
- **Modified**: `rerunResearch()` function to accept `agentContext` parameter
- **Enhanced**: API call to include agent context in request body

#### 3. Research API (`frontend/src/api/research.js`)
- **Modified**: `webResearch()` function to support agent context (for standalone web research)

## Key Features

### 1. Custom Agent Selection
- Users can select multiple custom agents from their agent roster
- Each agent card displays key information (name, archetype, age, occupation, bio)
- Selected agents are highlighted and displayed in a separate section

### 2. Enhanced Research Context
- When agents are selected, the research query is enhanced with agent names
- Research focus is expanded to consider perspectives from selected agents
- Agent descriptions and backgrounds are incorporated into the research process

### 3. User Experience
- Clean, intuitive UI for agent selection
- Real-time feedback on selected agents
- Clear indication of research being shaped by custom agents
- Backward compatible with existing web research functionality

## Usage

### Step 1: Select Custom Agents
1. Navigate to the Environment Setup step (Step 2)
2. Scroll down to the "Agent Context for Web Research" section
3. Browse through available custom agents in the "Available Custom Agents" section
4. Click on agent cards to select them (click again to deselect)
5. Selected agents will appear in the "Selected Agents" section

### Step 2: Run Research with Agent Context
1. Click the "🔍 Research with Selected Agents" button
2. The system will run web research incorporating the selected agent context
3. Research results will be enhanced with perspectives from the selected agents
4. A log message will indicate that research is being shaped by custom agents

### Step 3: View Enhanced Results
1. Review the research results, which now incorporate insights from selected agents
2. The research will be more relevant and focused on the specific personas selected
3. Use the enhanced research to ground agent personas in real-world contexts

## Benefits

### 1. More Relevant Research
- Web research is now tailored to specific personas
- Research findings are more applicable to the selected agents
- Reduces noise and irrelevant information

### 2. Better Persona Grounding
- Agents are grounded in research that considers their specific perspectives
- Research incorporates lived experiences and viewpoints of selected agents
- More realistic and nuanced persona development

### 3. Enhanced User Control
- Users have more control over the web research process
- Can focus research on specific personas or groups of interest
- Better alignment with simulation objectives

## Technical Details

### Agent Context Structure
The agent context is structured as follows:
```json
{
  "agents": [
    {
      "name": "agent_name",
      "archetype": "agent_archetype",
      "description": "agent_description",
      "background": "agent_background"
    }
  ],
  "context_focus": "specific_focus_area"
}
```

### Research Enhancement
When agent context is provided, the research query is enhanced:
- Agent names are incorporated into the research query
- Agent descriptions and backgrounds are considered in the research focus
- Research results are filtered to be more relevant to selected agents

### Backward Compatibility
- All existing web research functionality remains unchanged
- Agent context is optional - research works normally without it
- No breaking changes to existing APIs or interfaces

## Testing

The implementation has been tested for:
1. **Agent Selection**: Users can select and deselect agents correctly
2. **Agent Context Transmission**: Agent context is properly transmitted from frontend to backend
3. **Research Enhancement**: Research queries are correctly enhanced with agent context
4. **UI Responsiveness**: UI updates correctly when agents are selected/deselected
5. **Backward Compatibility**: Existing web research functionality continues to work

## Future Enhancements

Potential future improvements include:
1. **Advanced Agent Filtering**: Allow users to filter agents by specific criteria
2. **Research Strategy Options**: Different research strategies based on agent selection
3. **Agent Priority**: Allow users to prioritize certain agents in the research process
4. **Real-time Research Updates**: Live updates to research results as agents are selected

## Conclusion

This implementation successfully enhances the web research functionality to allow custom agents to be used as context for web research grounding. The feature is intuitive, backward compatible, and provides users with more control over the research process. The enhanced research results lead to better persona grounding and more realistic simulations.
