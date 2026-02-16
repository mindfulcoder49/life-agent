<script setup>
import { ref, onMounted, watch } from 'vue'
import { useDataStore } from '../stores/data'
import DataTable from './DataTable.vue'

const data = useDataStore()
const activeTab = ref('life-goals')
const tableNames = ['life-goals', 'user-states', 'one-time-tasks', 'recurring-tasks', 'todo-lists']
const labels = {
  'life-goals': 'Life Goals',
  'user-states': 'User States',
  'one-time-tasks': 'One-Time Tasks',
  'recurring-tasks': 'Recurring Tasks',
  'todo-lists': 'Todo Lists',
}

onMounted(() => {
  data.fetchTable(activeTab.value)
})

watch(activeTab, (name) => {
  data.fetchTable(name)
})
</script>

<template>
  <div class="page">
    <div class="tabs">
      <button
        v-for="name in tableNames"
        :key="name"
        :class="{ active: activeTab === name }"
        @click="activeTab = name"
      >
        {{ labels[name] }}
      </button>
    </div>
    <DataTable
      :tableName="activeTab"
      :items="data.tables[activeTab]?.items || []"
      :total="data.tables[activeTab]?.total || 0"
      @refresh="data.fetchTable(activeTab)"
      @update="(id, d) => data.updateRow(activeTab, id, d)"
      @remove="(id) => data.deleteRow(activeTab, id)"
    />
  </div>
</template>
