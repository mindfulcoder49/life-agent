<script setup>
import { ref, onMounted } from 'vue'
import client from '../api/client'
import TodoItem from './TodoItem.vue'

const todos = ref([])
const loading = ref(true)
const recurringMetrics = ref({}) // task_id -> metric object

onMounted(async () => {
  try {
    const [todosRes, recurringRes] = await Promise.all([
      client.get('/todo-lists', { params: { limit: 20 } }),
      client.get('/tasks/recurring', { params: { limit: 200 } }),
    ])
    todos.value = todosRes.data.items || []
    const map = {}
    for (const task of (recurringRes.data.items || [])) {
      if (task.data?.metric) {
        map[task.id] = task.data.metric
      }
    }
    recurringMetrics.value = map
  } catch {
    todos.value = []
  } finally {
    loading.value = false
  }
})

function getItemMetric(item) {
  if (typeof item !== 'object' || item?.source_type !== 'recurring' || !item?.source_task_id) return null
  return recurringMetrics.value[item.source_task_id] || null
}

async function completeItem(todoId, itemIndex, todo, metricValue) {
  try {
    const body = { item_index: itemIndex }
    if (metricValue != null) body.metric_value = String(metricValue)
    const res = await client.post(`/todo-lists/${todoId}/complete-item`, body)
    todo.data = res.data.data
  } catch {
    if (todo.data?.items?.[itemIndex]) {
      todo.data.items[itemIndex].completed = true
    }
  }
}

async function uncompleteItem(todoId, itemIndex, todo) {
  try {
    const res = await client.post(`/todo-lists/${todoId}/uncomplete-item`, { item_index: itemIndex })
    todo.data = res.data.data
  } catch {
    if (todo.data?.items?.[itemIndex]) {
      todo.data.items[itemIndex].completed = false
    }
  }
}
</script>

<template>
  <div class="page">
    <h2 style="margin-bottom: 16px;">Daily Todo Lists</h2>
    <div v-if="loading" class="empty-state">Loading...</div>
    <div v-else-if="todos.length === 0" class="empty-state">
      <p>No todo lists yet.</p>
      <p style="margin-top: 8px; font-size: 13px;">Chat with your agent and ask for a daily recommendation to generate one.</p>
    </div>
    <div v-else class="todo-lists">
      <div v-for="todo in todos" :key="todo.id" class="card">
        <div class="todo-header">
          <h3>{{ todo.data?.date || 'Undated' }}</h3>
        </div>
        <p v-if="todo.data?.reasoning" class="reasoning">{{ todo.data.reasoning }}</p>
        <div v-if="todo.data?.items?.length" class="todo-items">
          <TodoItem
            v-for="(item, idx) in todo.data.items"
            :key="idx"
            :item="item"
            :completed="!!item.completed"
            :metric="getItemMetric(item)"
            @complete="(val) => completeItem(todo.id, idx, todo, val)"
            @uncomplete="uncompleteItem(todo.id, idx, todo)"
          />
        </div>
        <p v-if="todo.data?.agent_notes" class="agent-notes">{{ todo.data.agent_notes }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.todo-lists {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.todo-header h3 {
  font-size: 16px;
  margin-bottom: 8px;
}
.reasoning {
  color: var(--text-secondary);
  font-size: 13px;
  margin-bottom: 12px;
  font-style: italic;
}
.todo-items {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.agent-notes {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 12px;
}
</style>
