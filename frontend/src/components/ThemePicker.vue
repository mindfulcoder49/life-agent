<script setup>
import { useThemeStore } from '../stores/theme'

const emit = defineEmits(['close'])
const themeStore = useThemeStore()

const themes = [
  { name: 'dark', label: 'Dark', color: '#1a1a2e' },
  { name: 'light', label: 'Light', color: '#f5f5f5' },
  { name: 'green', label: 'Green', color: '#1b2d1b' },
  { name: 'blue', label: 'Blue', color: '#0d1b2a' },
  { name: 'pink', label: 'Pink', color: '#2d1b2d' },
  { name: 'beige', label: 'Beige', color: '#f5f0e8' },
]

function pick(name) {
  themeStore.setTheme(name)
}
</script>

<template>
  <div class="theme-picker">
    <button
      v-for="t in themes"
      :key="t.name"
      class="theme-swatch"
      :class="{ active: themeStore.theme === t.name }"
      @click="pick(t.name)"
    >
      <span class="swatch" :style="{ background: t.color }"></span>
      <span class="label">{{ t.label }}</span>
    </button>
  </div>
</template>

<style scoped>
.theme-picker {
  display: flex;
  gap: 8px;
  padding: 10px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
}
.theme-swatch {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  background: transparent;
  padding: 6px 10px;
  border-radius: var(--radius-sm);
}
.theme-swatch.active {
  outline: 2px solid var(--accent);
}
.swatch {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 2px solid var(--border);
}
.label {
  font-size: 11px;
  color: var(--text-secondary);
}
</style>
