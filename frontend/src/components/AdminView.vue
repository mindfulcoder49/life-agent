<script setup>
import { ref, onMounted } from 'vue'
import client from '../api/client'
import JsonField from './JsonField.vue'

const activeTab = ref('users')
const users = ref([])
const logs = ref([])
const logFilter = ref({ level: '', source: '' })

onMounted(() => loadUsers())

async function loadUsers() {
  try {
    const res = await client.get('/admin/users')
    users.value = res.data.items || []
  } catch {}
}

async function loadLogs() {
  try {
    const params = {}
    if (logFilter.value.level) params.level = logFilter.value.level
    if (logFilter.value.source) params.source = logFilter.value.source
    const res = await client.get('/admin/logs', { params })
    logs.value = res.data.items || []
  } catch {}
}

async function deleteUser(id) {
  if (!confirm('Delete this user?')) return
  try {
    await client.delete(`/admin/users/${id}`)
    await loadUsers()
  } catch (err) {
    alert(err.response?.data?.detail || 'Error')
  }
}

function switchTab(tab) {
  activeTab.value = tab
  if (tab === 'users') loadUsers()
  if (tab === 'logs') loadLogs()
}
</script>

<template>
  <div class="page">
    <h2 style="margin-bottom: 16px;">Admin</h2>
    <div class="tabs">
      <button :class="{ active: activeTab === 'users' }" @click="switchTab('users')">Users</button>
      <button :class="{ active: activeTab === 'logs' }" @click="switchTab('logs')">Logs</button>
    </div>

    <template v-if="activeTab === 'users'">
      <div v-for="u in users" :key="u.id" class="card" style="display: flex; justify-content: space-between; align-items: center;">
        <div>
          <strong>{{ u.display_name || u.username }}</strong>
          <span style="color: var(--text-muted); margin-left: 8px;">@{{ u.username }}</span>
          <span v-if="u.is_admin" class="badge" style="margin-left: 8px;">admin</span>
        </div>
        <button v-if="!u.is_admin" class="secondary" @click="deleteUser(u.id)" style="padding: 4px 10px; font-size: 12px; color: var(--error);">Delete</button>
      </div>
    </template>

    <template v-if="activeTab === 'logs'">
      <div style="display: flex; gap: 8px; margin-bottom: 12px;">
        <select v-model="logFilter.level" @change="loadLogs" style="width: auto;">
          <option value="">All levels</option>
          <option value="info">Info</option>
          <option value="warn">Warn</option>
          <option value="error">Error</option>
        </select>
        <button class="secondary" @click="loadLogs" style="padding: 6px 12px; font-size: 13px;">Refresh</button>
      </div>
      <div v-if="logs.length === 0" class="empty-state">No logs found.</div>
      <div v-for="log in logs" :key="log.id" class="card" style="padding: 10px;">
        <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 4px;">
          <span class="badge" :style="{ background: log.data?.level === 'error' ? 'var(--error)' : log.data?.level === 'warn' ? 'var(--warning)' : 'var(--accent-soft)', color: log.data?.level === 'error' ? 'white' : log.data?.level === 'warn' ? '#333' : 'var(--accent)' }">
            {{ log.data?.level }}
          </span>
          <span style="color: var(--text-muted); font-size: 12px;">{{ log.data?.source }} / {{ log.data?.event }}</span>
          <span style="color: var(--text-muted); font-size: 11px; margin-left: auto;">{{ log.created_at?.slice(0, 19) }}</span>
        </div>
        <p style="font-size: 13px;">{{ log.data?.message }}</p>
      </div>
    </template>
  </div>
</template>
