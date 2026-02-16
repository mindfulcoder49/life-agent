<script setup>
const props = defineProps({
  item: [Object, String],
})

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
  return props.item.time || props.item.estimated_minutes ? `~${props.item.estimated_minutes}min` : null
}
</script>

<template>
  <div class="todo-item">
    <span class="checkbox">&#9744;</span>
    <div class="todo-content">
      <span class="todo-title">{{ getTitle() }}</span>
      <span v-if="getTime()" class="todo-time">{{ getTime() }}</span>
      <p v-if="getDetails()" class="todo-details">{{ getDetails() }}</p>
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
}
.todo-content {
  flex: 1;
}
.todo-title {
  font-size: 14px;
}
.todo-time {
  color: var(--text-muted);
  font-size: 12px;
  margin-left: 8px;
}
.todo-details {
  color: var(--text-secondary);
  font-size: 12px;
  margin-top: 2px;
}
</style>
