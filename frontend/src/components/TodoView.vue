<script setup>
import { ref, onMounted } from 'vue'
import client from '../api/client'
import TodoItem from './TodoItem.vue'

const todos = ref([])
const loading = ref(true)

onMounted(async () => {
  try {
    const res = await client.get('/todo-lists', { params: { limit: 20 } })
    todos.value = res.data.items || []
  } catch {
    todos.value = []
  } finally {
    loading.value = false
  }
})

async function completeItem(todoId, itemIndex, todo, payload, section = 'items') {
  const { completionDate } = payload || {}
  try {
    const body = { item_index: itemIndex, section }
    if (completionDate != null) body.completion_date = completionDate
    const res = await client.post(`/todo-lists/${todoId}/complete-item`, body)
    todo.data = res.data.data
  } catch {
    const items = todo.data?.[section]
    if (items?.[itemIndex]) {
      items[itemIndex].completed = true
    }
  }
}

async function uncompleteItem(todoId, itemIndex, todo, section = 'items') {
  try {
    const res = await client.post(`/todo-lists/${todoId}/uncomplete-item`, { item_index: itemIndex, section })
    todo.data = res.data.data
  } catch {
    const items = todo.data?.[section]
    if (items?.[itemIndex]) {
      items[itemIndex].completed = false
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

        <!-- Active habits auto-added by backend -->
        <div v-if="todo.data?.habit_items?.length" class="todo-section">
          <div class="section-label section-label--habits">Active Habits</div>
          <div class="todo-items">
            <TodoItem
              v-for="(item, idx) in todo.data.habit_items"
              :key="'habit-' + idx"
              :item="item"
              :completed="!!item.completed"
              :streak-label="item.streak_label"
              :list-date="todo.data?.date"
              @complete="(payload) => completeItem(todo.id, idx, todo, payload, 'habit_items')"
              @uncomplete="uncompleteItem(todo.id, idx, todo, 'habit_items')"
            />
          </div>
        </div>

        <!-- AI-chosen one-time task items -->
        <div v-if="todo.data?.items?.length" class="todo-section">
          <div class="section-label">Today's Tasks</div>
          <div class="todo-items">
            <TodoItem
              v-for="(item, idx) in todo.data.items"
              :key="'llm-' + idx"
              :item="item"
              :completed="!!item.completed"
              :list-date="todo.data?.date"
              @complete="(payload) => completeItem(todo.id, idx, todo, payload, 'items')"
              @uncomplete="uncompleteItem(todo.id, idx, todo, 'items')"
            />
          </div>
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
.todo-section {
  margin-bottom: 12px;
}
.todo-section:last-of-type {
  margin-bottom: 0;
}
.section-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.section-label--habits {
  color: #10b981;
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
