<script setup>
import { ref } from 'vue'
import JsonField from './JsonField.vue'

const props = defineProps({
  contextLog: Array,
})
const emit = defineEmits(['close'])

const expanded = ref({})

function toggle(idx) {
  expanded.value[idx] = !expanded.value[idx]
}

function getLabel(entry) {
  if (!entry) return 'Unknown'
  if (entry.type === 'system') return 'System Prompt'
  if (entry.type === 'human') return 'User Message'
  if (entry.type === 'ai') return 'AI Response'
  if (entry.type === 'tool_call') return `Tool Call: ${entry.name || 'unknown'}`
  if (entry.type === 'tool_result') return `Tool Result: ${entry.name || 'unknown'}`
  return entry.type || 'Entry'
}
</script>

<template>
  <div class="modal-overlay" @click.self="emit('close')">
    <div class="modal">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
        <h2>Full Context</h2>
        <button class="secondary" @click="emit('close')" style="padding: 4px 12px;">X</button>
      </div>
      <div v-if="!contextLog || contextLog.length === 0" class="empty-state">
        No context data available.
      </div>
      <div v-else class="context-list">
        <div v-for="(entry, idx) in contextLog" :key="idx" class="context-entry">
          <button class="entry-header" @click="toggle(idx)">
            <span>{{ getLabel(entry) }}</span>
            <span>{{ expanded[idx] ? '▼' : '▶' }}</span>
          </button>
          <div v-if="expanded[idx]" class="entry-body">
            <template v-if="entry.content">
              <pre class="entry-content">{{ entry.content }}</pre>
            </template>
            <template v-if="entry.args">
              <p class="entry-label">Arguments:</p>
              <JsonField :value="entry.args" />
            </template>
            <template v-if="entry.result">
              <p class="entry-label">Result:</p>
              <JsonField :value="entry.result" />
            </template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.context-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.entry-header {
  width: 100%;
  display: flex;
  justify-content: space-between;
  background: var(--bg-card);
  color: var(--text-primary);
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  text-align: left;
}
.entry-body {
  padding: 8px 14px;
  background: var(--bg-primary);
  border-radius: 0 0 var(--radius-sm) var(--radius-sm);
  margin-top: -4px;
}
.entry-content {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  color: var(--text-secondary);
  max-height: 300px;
  overflow-y: auto;
}
.entry-label {
  font-size: 11px;
  color: var(--text-muted);
  margin: 8px 0 4px;
  text-transform: uppercase;
}
</style>
