<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  item: [Object, String],
  completed: { type: Boolean, default: false },
  metric: { type: Object, default: null },
  listDate: { type: String, default: null },
})

const emit = defineEmits(['complete', 'uncomplete'])

const showMetricInput = ref(false)
const showDateInput = ref(false)
const metricValue = ref('')
const pendingMetricValue = ref(null)
const completionDate = ref('')

function localToday() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}

const needsDatePrompt = computed(() =>
  props.listDate != null && props.listDate !== localToday()
)

function getTitle() {
  if (typeof props.item === 'string') return props.item
  return props.item?.title || props.item?.name || String(props.item)
}

function getDetails() {
  if (typeof props.item !== 'object' || !props.item) return null
  return props.item.details || props.item.description || null
}

function getTime() {
  if (typeof props.item !== 'object' || !props.item) return null
  return props.item.time || (props.item.estimated_minutes ? `~${props.item.estimated_minutes}min` : null)
}

function isCompleted() {
  return props.completed || (typeof props.item === 'object' && props.item?.completed)
}

function onCheckboxClick() {
  if (isCompleted()) {
    emit('uncomplete')
    return
  }
  if (props.metric) {
    showMetricInput.value = true
  } else if (needsDatePrompt.value) {
    completionDate.value = props.listDate
    showDateInput.value = true
  } else {
    emit('complete', { metricValue: null, completionDate: null })
  }
}

function submitMetric() {
  pendingMetricValue.value = metricValue.value || null
  showMetricInput.value = false
  metricValue.value = ''
  if (needsDatePrompt.value) {
    completionDate.value = props.listDate
    showDateInput.value = true
  } else {
    emit('complete', { metricValue: pendingMetricValue.value, completionDate: null })
    pendingMetricValue.value = null
  }
}

function skipMetric() {
  pendingMetricValue.value = null
  showMetricInput.value = false
  metricValue.value = ''
  if (needsDatePrompt.value) {
    completionDate.value = props.listDate
    showDateInput.value = true
  } else {
    emit('complete', { metricValue: null, completionDate: null })
  }
}

function submitDate() {
  emit('complete', { metricValue: pendingMetricValue.value, completionDate: completionDate.value || null })
  showDateInput.value = false
  completionDate.value = ''
  pendingMetricValue.value = null
}
</script>

<template>
  <div class="todo-item" :class="{ 'todo-completed': isCompleted() }">
    <span class="checkbox" @click="onCheckboxClick">{{ isCompleted() ? '☑' : '☐' }}</span>
    <div class="todo-content">
      <div class="todo-main">
        <span class="todo-title">{{ getTitle() }}</span>
        <span v-if="getTime()" class="todo-time">{{ getTime() }}</span>
      </div>
      <p v-if="getDetails()" class="todo-details">{{ getDetails() }}</p>
      <div v-if="showMetricInput" class="metric-input-row">
        <span class="metric-label">{{ metric.label }}:</span>
        <input
          v-model="metricValue"
          :type="metric.value_type === 'number' ? 'number' : 'text'"
          :placeholder="metric.value_type === 'meal' ? 'describe what you ate/drank' : (metric.unit || 'enter value')"
          class="metric-input"
          @keydown.enter="submitMetric"
          autofocus
        />
        <button class="btn-done" @click="submitMetric">Done</button>
        <button class="btn-skip" @click="skipMetric">Skip</button>
      </div>
      <div v-if="showDateInput" class="date-input-row">
        <span class="date-label">Which day did you complete this?</span>
        <input
          v-model="completionDate"
          type="date"
          class="date-input"
          @keydown.enter="submitDate"
          autofocus
        />
        <button class="btn-done" @click="submitDate">Done</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.todo-item {
  display: flex;
  gap: 10px;
  padding: 8px 0;
  align-items: flex-start;
}
.checkbox {
  font-size: 18px;
  color: var(--text-muted);
  cursor: pointer;
  flex-shrink: 0;
  margin-top: 1px;
}
.todo-content {
  flex: 1;
}
.todo-main {
  display: flex;
  align-items: baseline;
  gap: 6px;
  flex-wrap: wrap;
}
.todo-title {
  font-size: 14px;
}
.todo-time {
  color: var(--text-muted);
  font-size: 12px;
}
.todo-details {
  color: var(--text-secondary);
  font-size: 12px;
  margin-top: 2px;
}
.todo-completed .todo-title {
  text-decoration: line-through;
  color: var(--text-muted);
}
.metric-input-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  flex-wrap: wrap;
}
.metric-label {
  font-size: 12px;
  color: var(--text-secondary);
  flex-shrink: 0;
}
.metric-input {
  flex: 1;
  min-width: 120px;
  padding: 4px 8px;
  font-size: 13px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-secondary);
  color: var(--text-primary);
}
.date-input-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  flex-wrap: wrap;
}
.date-label {
  font-size: 12px;
  color: var(--text-secondary);
  flex-shrink: 0;
}
.date-input {
  padding: 4px 8px;
  font-size: 13px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-secondary);
  color: var(--text-primary);
}
.btn-done {
  padding: 4px 10px;
  font-size: 12px;
  background: var(--accent);
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  flex-shrink: 0;
}
.btn-skip {
  padding: 4px 8px;
  font-size: 12px;
  background: transparent;
  color: var(--text-muted);
  border: none;
  cursor: pointer;
  flex-shrink: 0;
}
</style>
