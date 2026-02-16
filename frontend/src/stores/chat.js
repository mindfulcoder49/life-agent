import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import client from '../api/client'

export const useChatStore = defineStore('chat', () => {
  const messages = ref([])
  const sending = ref(false)
  const activeAgent = ref('hydrogen')
  const activeAgentLabel = ref('Hydrogen (Manager)')
  const sessionId = ref('default')
  const sessions = ref([])

  async function loadHistory() {
    try {
      const params = sessionId.value !== 'default' ? { session_id: sessionId.value } : {}
      const res = await client.get('/chat/history', { params })
      messages.value = (res.data.items || []).map(item => ({
        id: item.id,
        role: item.data?.role || 'assistant',
        content: item.data?.content || '',
        context_log: item.data?.context_log || null,
        agent: item.data?.agent || null,
        created_at: item.created_at,
      }))
    } catch {
      messages.value = []
    }
  }

  async function loadSessions() {
    try {
      const res = await client.get('/chat/sessions')
      sessions.value = res.data.sessions || []
    } catch {
      sessions.value = []
    }
  }

  async function loadActiveAgent() {
    try {
      const res = await client.get('/chat/active-agent', {
        params: { session_id: sessionId.value }
      })
      activeAgent.value = res.data.active_agent
      activeAgentLabel.value = res.data.active_agent_label
    } catch {
      // ignore
    }
  }

  async function switchSession(sid) {
    sessionId.value = sid
    await loadHistory()
    await loadActiveAgent()
  }

  async function newSession() {
    const sid = 'session-' + Date.now()
    sessionId.value = sid
    messages.value = []
    activeAgent.value = 'hydrogen'
    activeAgentLabel.value = 'Hydrogen (Manager)'
  }

  async function sendMessage(text) {
    messages.value.push({ role: 'user', content: text, id: Date.now() })
    sending.value = true
    try {
      const res = await client.post('/chat', {
        message: text,
        session_id: sessionId.value,
      })
      messages.value.push({
        role: 'assistant',
        content: res.data.response,
        context_log: res.data.context_log || null,
        agent: res.data.active_agent || null,
        id: Date.now() + 1,
      })
      activeAgent.value = res.data.active_agent || 'hydrogen'
      activeAgentLabel.value = res.data.active_agent_label || 'Hydrogen (Manager)'
      return res.data
    } catch (err) {
      messages.value.push({
        role: 'assistant',
        content: 'Sorry, something went wrong. ' + (err.response?.data?.detail || err.message),
        id: Date.now() + 1,
      })
    } finally {
      sending.value = false
    }
  }

  async function deleteMessage(id) {
    try {
      await client.delete(`/chat/history/${id}`)
    } catch {
      // If it's a local-only message, just remove from UI
    }
    messages.value = messages.value.filter(m => m.id !== id)
  }

  async function clearHistory() {
    await client.delete('/chat/history', {
      params: { session_id: sessionId.value }
    })
    messages.value = []
    activeAgent.value = 'hydrogen'
    activeAgentLabel.value = 'Hydrogen (Manager)'
  }

  return {
    messages, sending, activeAgent, activeAgentLabel,
    sessionId, sessions,
    loadHistory, loadSessions, loadActiveAgent,
    switchSession, newSession,
    sendMessage, deleteMessage, clearHistory,
  }
})
