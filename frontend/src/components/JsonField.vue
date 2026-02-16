<script setup>
import { computed } from 'vue'

const props = defineProps({
  value: [String, Object, Array, Number, Boolean],
})

const parsed = computed(() => {
  try {
    if (props.value === null || props.value === undefined) return null
    if (typeof props.value === 'object') return props.value
    if (typeof props.value === 'string') {
      return JSON.parse(props.value)
    }
    return null
  } catch {
    return null
  }
})

const isObject = computed(() => {
  return parsed.value !== null && typeof parsed.value === 'object' && !Array.isArray(parsed.value)
})

const rawText = computed(() => {
  try {
    if (props.value === null || props.value === undefined) return 'null'
    if (typeof props.value === 'string') return props.value
    return JSON.stringify(props.value, null, 2)
  } catch {
    return String(props.value ?? '')
  }
})

function formatValue(val) {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'boolean') return val ? 'Yes' : 'No'
  if (Array.isArray(val)) {
    if (val.length === 0) return '—'
    return val.map(v => typeof v === 'object' ? JSON.stringify(v) : String(v)).join(', ')
  }
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function formatKey(key) {
  return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}

// Keys to hide from the friendly view (internal/meta fields)
const hiddenKeys = new Set(['user_id', 'password_hash', 'session_token'])
</script>

<template>
  <div v-if="isObject" class="kv-field">
    <div v-for="(val, key) in parsed" :key="key" class="kv-row" v-show="!hiddenKeys.has(key)">
      <span class="kv-key">{{ formatKey(key) }}</span>
      <span class="kv-val">{{ formatValue(val) }}</span>
    </div>
  </div>
  <pre v-else class="json-field">{{ rawText }}</pre>
</template>

<style scoped>
.kv-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.kv-row {
  display: flex;
  gap: 8px;
  font-size: 13px;
  line-height: 1.5;
  padding: 2px 0;
}
.kv-key {
  color: var(--text-muted);
  font-weight: 500;
  min-width: 100px;
  flex-shrink: 0;
  font-size: 12px;
}
.kv-val {
  color: var(--text-primary);
  word-break: break-word;
}
.json-field {
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: 12px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-secondary);
  max-height: 200px;
  overflow-y: auto;
}
</style>
