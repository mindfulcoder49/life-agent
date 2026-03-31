<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  item: [Object, String],
  completed: { type: Boolean, default: false },
  streakLabel: { type: String, default: null },
  listDate: { type: String, default: null },
})

const emit = defineEmits(['complete', 'uncomplete'])

const showDateInput = ref(false)
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
  if (needsDatePrompt.value) {
    completionDate.value = props.listDate
    showDateInput.value = true
  } else {
    emit('complete', { completionDate: null })
  }
}

function submitDate() {
  emit('complete', { completionDate: completionDate.value || null })
  showDateInput.value = false
  completionDate.value = ''
}
</script>

<template>
  <div class="todo-item" :class="{ 'todo-completed': isCompleted() }">
    <span class="checkbox" @click="onCheckboxClick">{{ isCompleted() ? '☑' : '☐' }}</span>
    <div class="todo-content">
      <div class="todo-main">
        <span class="todo-title">{{ getTitle() }}</span>
        <span v-if="streakLabel && !isCompleted()" class="streak-badge">{{ streakLabel }}</span>
        <span v-if="getTime()" class="todo-time">{{ getTime() }}</span>
      </div>
      <p v-if="getDetails()" class="todo-details">{{ getDetails() }}</p>
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
.streak-badge {
  font-size: 11px;
  font-weight: 600;
  color: #10b981;
  background: color-mix(in srgb, #10b981 12%, transparent);
  padding: 1px 6px;
  border-radius: 10px;
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
</style>
