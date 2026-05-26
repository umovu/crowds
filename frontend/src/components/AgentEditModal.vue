<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="modelValue" class="agent-modal-overlay" @click.self="close">
        <div class="agent-modal">
          <div class="modal-header">
            <div class="modal-title">
              <span class="modal-title-text">{{ isEdit ? 'Edit Agent' : 'Add Custom Agent' }}</span>
              <span class="modal-subtitle">Define persona, status, and mental state</span>
            </div>
            <button class="close-btn" @click="close">×</button>
          </div>

          <div class="modal-body">
            <!-- Tabs -->
            <div class="tabs">
              <button
                v-for="tab in tabs"
                :key="tab.key"
                class="tab-btn"
                :class="{ active: activeTab === tab.key }"
                @click="activeTab = tab.key"
              >
                <span class="tab-num">{{ tab.num }}</span>
                <span class="tab-label">{{ tab.label }}</span>
              </button>
            </div>

            <!-- Tab Content -->
            <div class="tab-content">
              <!-- PROFILE TAB -->
              <div v-show="activeTab === 'profile'" class="form-grid">
                <div class="section-label">Basic Demographics</div>
                <div class="form-row two-col">
                  <div class="field">
                    <label>Name <span class="required">*</span></label>
                    <input v-model="form.name" type="text" placeholder="Full name" />
                  </div>
                  <div class="field">
                    <label>Age</label>
                    <input v-model.number="form.age" type="number" min="0" max="120" placeholder="e.g. 34" />
                  </div>
                </div>
                <div class="form-row three-col">
                  <div class="field">
                    <label>Gender</label>
                    <select v-model="form.gender">
                      <option value="">—</option>
                      <option value="male">Male</option>
                      <option value="female">Female</option>
                      <option value="other">Other</option>
                    </select>
                  </div>
                  <div class="field">
                    <label>Race / Ethnicity</label>
                    <input v-model="form.race" type="text" placeholder="e.g. Black African" />
                  </div>
                  <div class="field">
                    <label>Education</label>
                    <input v-model="form.education" type="text" placeholder="e.g. BSc Computer Science" />
                  </div>
                </div>

                <div class="section-label">Socio-Economic Background</div>
                <div class="form-row three-col">
                  <div class="field">
                    <label>Occupation</label>
                    <input v-model="form.occupation" type="text" placeholder="e.g. Taxi driver" />
                  </div>
                  <div class="field">
                    <label>Residence</label>
                    <input v-model="form.residence" type="text" placeholder="e.g. Soweto, Johannesburg" />
                  </div>
                  <div class="field">
                    <label>Religion</label>
                    <input v-model="form.religion" type="text" placeholder="e.g. Christian" />
                  </div>
                </div>

                <div class="section-label">Personality & Skills</div>
                <div class="form-row two-col">
                  <div class="field">
                    <label>MBTI</label>
                    <select v-model="form.mbti">
                      <option value="">—</option>
                      <option v-for="t in mbtiTypes" :key="t" :value="t">{{ t }}</option>
                    </select>
                  </div>
                  <div class="field">
                    <label>Skills</label>
                    <input v-model="form.skills" type="text" placeholder="Comma-separated skills" />
                  </div>
                </div>
                <div class="form-row two-col">
                  <div class="field core-focus-field">
                    <label class="core-focus-label">
                      <span>Core Focus Agent</span>
                      <span class="core-focus-hint">Guaranteed participation + higher influence</span>
                    </label>
                    <div class="toggle-switch" :class="{ active: form.is_core_focus }" @click="form.is_core_focus = !form.is_core_focus">
                      <div class="toggle-knob"></div>
                    </div>
                  </div>
                </div>
                <div class="field">
                  <label>Personality Traits</label>
                  <textarea v-model="form.personality_traits" rows="2" placeholder="Describe personality traits..." />
                </div>
                <div class="field">
                  <label>Persona / Bio <span class="required">*</span></label>
                  <textarea v-model="form.persona" rows="4" placeholder="Who is this agent? Their worldview, motivations, and role in the simulation..." />
                </div>
                <div class="field">
                  <label>Background Story</label>
                  <textarea v-model="form.background_story" rows="3" placeholder="Their life history and formative experiences..." />
                </div>
              </div>

              <!-- STATUS TAB -->
              <div v-show="activeTab === 'status'" class="form-grid">
                <div class="section-label">Economic Status</div>
                <div class="form-row two-col">
                  <div class="field">
                    <label>Income (monthly)</label>
                    <input v-model="form.income" type="text" placeholder="e.g. R12,000" />
                  </div>
                  <div class="field">
                    <label>Currency Balance</label>
                    <input v-model="form.currency_balance" type="text" placeholder="e.g. R3,500" />
                  </div>
                </div>

                <div class="section-label">Social Relationships</div>
                <div class="relationship-section">
                  <div class="rel-type-header">
                    <span>Family</span>
                    <button class="add-rel-btn" @click="addRelationship('family')">+ Add</button>
                  </div>
                  <div v-for="(rel, idx) in form.relationships.family" :key="idx" class="rel-row">
                    <input v-model="rel.name" type="text" placeholder="Name / relation" />
                    <div class="slider-field">
                      <input v-model.number="rel.strength" type="range" min="0" max="100" />
                      <span class="slider-val">{{ rel.strength }}</span>
                    </div>
                    <button class="remove-rel-btn" @click="removeRelationship('family', idx)">×</button>
                  </div>
                  <div v-if="form.relationships.family.length === 0" class="rel-empty">No family relationships defined</div>
                </div>

                <div class="relationship-section">
                  <div class="rel-type-header">
                    <span>Friends</span>
                    <button class="add-rel-btn" @click="addRelationship('friends')">+ Add</button>
                  </div>
                  <div v-for="(rel, idx) in form.relationships.friends" :key="idx" class="rel-row">
                    <input v-model="rel.name" type="text" placeholder="Name" />
                    <div class="slider-field">
                      <input v-model.number="rel.strength" type="range" min="0" max="100" />
                      <span class="slider-val">{{ rel.strength }}</span>
                    </div>
                    <button class="remove-rel-btn" @click="removeRelationship('friends', idx)">×</button>
                  </div>
                  <div v-if="form.relationships.friends.length === 0" class="rel-empty">No friends defined</div>
                </div>

                <div class="relationship-section">
                  <div class="rel-type-header">
                    <span>Colleagues</span>
                    <button class="add-rel-btn" @click="addRelationship('colleagues')">+ Add</button>
                  </div>
                  <div v-for="(rel, idx) in form.relationships.colleagues" :key="idx" class="rel-row">
                    <input v-model="rel.name" type="text" placeholder="Name / role" />
                    <div class="slider-field">
                      <input v-model.number="rel.strength" type="range" min="0" max="100" />
                      <span class="slider-val">{{ rel.strength }}</span>
                    </div>
                    <button class="remove-rel-btn" @click="removeRelationship('colleagues', idx)">×</button>
                  </div>
                  <div v-if="form.relationships.colleagues.length === 0" class="rel-empty">No colleagues defined</div>
                </div>

                <div class="section-label">Current Needs (Maslow Hierarchy)</div>
                <div class="needs-grid">
                  <div v-for="need in maslowNeeds" :key="need.key" class="need-item">
                    <div class="need-info">
                      <span class="need-name">{{ need.label }}</span>
                      <span class="need-desc">{{ need.desc }}</span>
                    </div>
                    <div class="slider-field">
                      <input v-model.number="form.needs[need.key]" type="range" min="0" max="100" />
                      <span class="slider-val">{{ form.needs[need.key] }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- MENTAL TAB -->
              <div v-show="activeTab === 'mental'" class="form-grid">
                <div class="section-label">Initial Emotions (0–10)</div>
                <div class="emotions-grid">
                  <div v-for="emo in emotions" :key="emo.key" class="emotion-item">
                    <div class="emotion-label">
                      <span class="emotion-name">{{ emo.label }}</span>
                      <span class="emotion-desc">{{ emo.desc }}</span>
                    </div>
                    <div class="slider-field">
                      <input v-model.number="form.emotions[emo.key]" type="range" min="0" max="10" step="0.5" />
                      <span class="slider-val">{{ form.emotions[emo.key] }}</span>
                    </div>
                  </div>
                </div>

                <div class="section-label">Emotion Meta</div>
                <div class="form-row two-col">
                  <div class="field">
                    <label>Emotion Keyword</label>
                    <input v-model="form.emotion_keyword" type="text" placeholder="e.g. anxious, hopeful" />
                  </div>
                  <div class="field">
                    <label>Emotion Thought</label>
                    <input v-model="form.emotion_thought" type="text" placeholder="One-sentence explanation" />
                  </div>
                </div>

                <div class="section-label">Cognitive Attitudes (0 = opposed, 10 = supportive)</div>
                <div class="attitudes-list">
                  <div v-for="(att, idx) in form.attitudes" :key="idx" class="attitude-row">
                    <input v-model="att.topic" type="text" placeholder="Topic e.g. land_reform" class="att-topic" />
                    <div class="slider-field">
                      <input v-model.number="att.rating" type="range" min="0" max="10" step="0.5" />
                      <span class="slider-val">{{ att.rating }}</span>
                    </div>
                    <input v-model="att.description" type="text" placeholder="Reasoning" class="att-desc" />
                    <button class="remove-rel-btn" @click="removeAttitude(idx)">×</button>
                  </div>
                  <button class="add-attitude-btn" @click="addAttitude">+ Add Attitude</button>
                </div>

                <div class="section-label">Core Beliefs</div>
                <div class="field">
                  <textarea v-model="beliefsText" rows="3" placeholder="One belief per line..." />
                </div>
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <button class="btn-secondary" @click="close">Cancel</button>
            <button class="btn-primary" @click="save" :disabled="!isValid">
              {{ isEdit ? 'Save Changes' : 'Add Agent' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  modelValue: Boolean,
  agent: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'save'])

const tabs = [
  { key: 'profile', label: 'Profile', num: '01' },
  { key: 'status', label: 'Status', num: '02' },
  { key: 'mental', label: 'Mental', num: '03' },
]

const activeTab = ref('profile')
const isEdit = computed(() => !!props.agent)

const mbtiTypes = [
  'INTJ','INTP','ENTJ','ENTP','INFJ','INFP','ENFJ','ENFP',
  'ISTJ','ISFJ','ESTJ','ESFJ','ISTP','ISFP','ESTP','ESFP'
]

const emotions = [
  { key: 'sadness', label: 'Sadness', desc: 'Melancholy, grief' },
  { key: 'joy', label: 'Joy', desc: 'Happiness, enthusiasm' },
  { key: 'fear', label: 'Fear', desc: 'Anxiety, dread' },
  { key: 'disgust', label: 'Disgust', desc: 'Revulsion, contempt' },
  { key: 'anger', label: 'Anger', desc: 'Frustration, rage' },
  { key: 'surprise', label: 'Surprise', desc: 'Shock, amazement' },
]

const maslowNeeds = [
  { key: 'physiological_hunger', label: 'Hunger', desc: 'Need for food' },
  { key: 'physiological_tired', label: 'Rest', desc: 'Need for sleep/rest' },
  { key: 'safety_physical', label: 'Physical Safety', desc: 'Safety from violence' },
  { key: 'safety_economic', label: 'Economic Safety', desc: 'Job/income security' },
  { key: 'belonging', label: 'Belonging', desc: 'Group membership' },
  { key: 'affection', label: 'Affection', desc: 'Love & friendship' },
  { key: 'respect', label: 'Respect', desc: 'Being respected' },
  { key: 'status', label: 'Status', desc: 'Social recognition' },
  { key: 'achievement', label: 'Achievement', desc: 'Accomplishment' },
  { key: 'personal_growth', label: 'Growth', desc: 'Self-improvement' },
  { key: 'purpose', label: 'Purpose', desc: 'Life purpose / cause' },
]

function makeDefaultForm() {
  return {
    name: '',
    age: null,
    gender: '',
    race: '',
    education: '',
    occupation: '',
    residence: '',
    religion: '',
    mbti: '',
    skills: '',
    personality_traits: '',
    persona: '',
    background_story: '',
    is_core_focus: false,
    income: '',
    currency_balance: '',
    relationships: { family: [], friends: [], colleagues: [] },
    needs: Object.fromEntries(maslowNeeds.map(n => [n.key, 50])),
    emotions: { sadness: 0, joy: 0, fear: 0, disgust: 0, anger: 0, surprise: 0 },
    emotion_keyword: '',
    emotion_thought: '',
    attitudes: [],
    beliefs: [],
  }
}

const form = ref(makeDefaultForm())
const beliefsText = ref('')

watch(() => props.modelValue, (open) => {
  if (open) {
    activeTab.value = 'profile'
    if (props.agent) {
      form.value = JSON.parse(JSON.stringify(props.agent))
      beliefsText.value = (props.agent.beliefs || []).join('\n')
    } else {
      form.value = makeDefaultForm()
      beliefsText.value = ''
    }
  }
})

const isValid = computed(() => {
  return form.value.name.trim() !== '' && form.value.persona.trim() !== ''
})

function addRelationship(type) {
  form.value.relationships[type].push({ name: '', strength: 50 })
}
function removeRelationship(type, idx) {
  form.value.relationships[type].splice(idx, 1)
}
function addAttitude() {
  form.value.attitudes.push({ topic: '', rating: 5, description: '' })
}
function removeAttitude(idx) {
  form.value.attitudes.splice(idx, 1)
}

function close() {
  emit('update:modelValue', false)
}

function save() {
  const payload = JSON.parse(JSON.stringify(form.value))
  payload.beliefs = beliefsText.value.split('\n').map(b => b.trim()).filter(Boolean)
  payload.skills = payload.skills.split(',').map(s => s.trim()).filter(Boolean)
  if (!payload.age) payload.age = null
  emit('save', payload)
  close()
}
</script>

<style scoped>
.agent-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.agent-modal {
  background: #fff;
  width: 100%;
  max-width: 760px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0,0,0,0.2);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 20px 24px;
  border-bottom: 1px solid #EAEAEA;
}

.modal-title {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.modal-title-text {
  font-size: 1.1rem;
  font-weight: 600;
  color: #000;
}

.modal-subtitle {
  font-size: 0.8rem;
  color: #999;
}

.close-btn {
  width: 32px;
  height: 32px;
  border: 1px solid #E5E5E5;
  background: #fff;
  font-size: 1.4rem;
  color: #666;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.close-btn:hover {
  border-color: #1E9E5A;
  color: #1E9E5A;
}

.modal-body {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid #EAEAEA;
  padding: 0 24px;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 20px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.85rem;
  color: #999;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: all 0.2s;
}

.tab-btn.active {
  color: #000;
  border-bottom-color: #1E9E5A;
}

.tab-num {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  font-weight: 700;
  color: #ccc;
}

.tab-btn.active .tab-num {
  color: #1E9E5A;
}

.tab-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.form-grid {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.section-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: #999;
  border-bottom: 1px solid #F0F0F0;
  padding-bottom: 6px;
  margin-top: 8px;
}

.form-row {
  display: flex;
  gap: 16px;
}

.form-row.two-col > .field { flex: 1; }
.form-row.three-col > .field { flex: 1; }

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field label {
  font-size: 0.8rem;
  font-weight: 500;
  color: #333;
}

.required {
  color: #1E9E5A;
}

.field input,
.field select,
.field textarea {
  padding: 10px 12px;
  border: 1px solid #E0E0E0;
  font-family: inherit;
  font-size: 0.85rem;
  background: #FAFAFA;
  outline: none;
  transition: border-color 0.2s;
}

.field input:focus,
.field select:focus,
.field textarea:focus {
  border-color: #1E9E5A;
  background: #fff;
}

.field textarea {
  resize: vertical;
  line-height: 1.5;
}

/* Relationships */
.relationship-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rel-type-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.rel-type-header span {
  font-size: 0.85rem;
  font-weight: 500;
  color: #333;
}

.add-rel-btn,
.add-attitude-btn {
  padding: 4px 10px;
  border: 1px solid #E0E0E0;
  background: #fff;
  font-family: inherit;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.add-rel-btn:hover,
.add-attitude-btn:hover {
  border-color: #1E9E5A;
  color: #1E9E5A;
}

.rel-row,
.attitude-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  background: #FAFAFA;
  border: 1px solid #F0F0F0;
}

.rel-row input,
.attitude-row input {
  padding: 6px 8px;
  border: 1px solid #E0E0E0;
  font-family: inherit;
  font-size: 0.8rem;
  background: #fff;
}

.rel-empty {
  font-size: 0.8rem;
  color: #bbb;
  padding: 8px;
  font-style: italic;
}

/* Slider */
.slider-field {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.slider-field input[type="range"] {
  flex: 1;
  min-width: 80px;
}

.slider-val {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: #666;
  min-width: 28px;
  text-align: right;
}

.remove-rel-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: #999;
  font-size: 1.1rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.remove-rel-btn:hover {
  color: #C5283D;
}

/* Needs */
.needs-grid,
.emotions-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.need-item,
.emotion-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 12px;
  background: #FAFAFA;
  border: 1px solid #F0F0F0;
}

.need-info,
.emotion-label {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.need-name,
.emotion-name {
  font-size: 0.85rem;
  font-weight: 500;
  color: #333;
}

.need-desc,
.emotion-desc {
  font-size: 0.75rem;
  color: #999;
}

/* Attitudes */
.attitude-row {
  flex-wrap: wrap;
}

.att-topic {
  width: 140px;
}

.att-desc {
  flex: 1;
  min-width: 140px;
}

/* Core Focus Toggle */
.core-focus-field {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #FFF3E0;
  border: 1px solid #FFE0B2;
  border-radius: 6px;
}

.core-focus-label {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.core-focus-label span:first-child {
  font-size: 0.85rem;
  font-weight: 600;
  color: #E65100;
}

.core-focus-hint {
  font-size: 0.75rem;
  color: #999;
  font-weight: 400;
}

.toggle-switch {
  width: 44px;
  height: 24px;
  background: #E0E0E0;
  border-radius: 12px;
  cursor: pointer;
  position: relative;
  transition: background 0.2s;
  flex-shrink: 0;
}

.toggle-switch.active {
  background: #E65100;
}

.toggle-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 20px;
  height: 20px;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.2s;
}

.toggle-switch.active .toggle-knob {
  transform: translateX(20px);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid #EAEAEA;
}

.btn-secondary,
.btn-primary {
  padding: 10px 24px;
  font-family: inherit;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid;
  transition: all 0.2s;
}

.btn-secondary {
  background: #fff;
  color: #333;
  border-color: #E0E0E0;
}

.btn-secondary:hover {
  border-color: #999;
}

.btn-primary {
  background: #000;
  color: #fff;
  border-color: #000;
}

.btn-primary:hover:not(:disabled) {
  background: #1E9E5A;
  border-color: #1E9E5A;
}

.btn-primary:disabled {
  background: #E5E5E5;
  color: #999;
  border-color: #E5E5E5;
  cursor: not-allowed;
}

/* Modal transition */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.25s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
</style>
