import { defineStore } from 'pinia'
import { reactive } from 'vue'
import client from '../api/client'

export const useDataStore = defineStore('data', () => {
  const tables = reactive({
    'life-goals': { endpoint: '/life-goals', items: [], total: 0 },
    'user-states': { endpoint: '/user-states', items: [], total: 0 },
    'one-time-tasks': { endpoint: '/tasks/one-time', items: [], total: 0 },
    'recurring-tasks': { endpoint: '/tasks/recurring', items: [], total: 0 },
    'todo-lists': { endpoint: '/todo-lists', items: [], total: 0 },
  })

  async function fetchTable(name, limit = 50, offset = 0) {
    const table = tables[name]
    if (!table) return
    try {
      const res = await client.get(table.endpoint, { params: { limit, offset } })
      table.items = res.data.items || []
      table.total = res.data.total || 0
    } catch {
      table.items = []
      table.total = 0
    }
  }

  async function createRow(name, data) {
    const table = tables[name]
    if (!table) return
    const res = await client.post(table.endpoint, data)
    await fetchTable(name)
    return res.data
  }

  async function updateRow(name, id, data) {
    const table = tables[name]
    if (!table) return
    const res = await client.put(`${table.endpoint}/${id}`, { data })
    await fetchTable(name)
    return res.data
  }

  async function deleteRow(name, id) {
    const table = tables[name]
    if (!table) return
    await client.delete(`${table.endpoint}/${id}`)
    await fetchTable(name)
  }

  return { tables, fetchTable, createRow, updateRow, deleteRow }
})
