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

  // Streaming state
  const streaming = ref(false)
  const streamingContent = ref('')
  const toolStatus = ref(null)  // {tool, agent} or null

  async function loadHistory() {
    try {
      const res = await client.get('/chat/history', {
        params: { session_id: sessionId.value }
      })
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

  async function deleteSession(sid) {
    await client.delete('/chat/history', {
      params: { session_id: sid }
    })
    // If we just deleted the active session, switch to default
    if (sessionId.value === sid) {
      sessionId.value = 'default'
      await loadHistory()
      await loadActiveAgent()
    }
    await loadSessions()
  }

  async function sendMessage(text) {
    const isFirstMessage = messages.value.length === 0
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
      if (isFirstMessage) loadSessions()
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

  async function sendMessageStream(text) {
    const isFirstMessage = messages.value.length === 0
    messages.value.push({ role: 'user', content: text, id: Date.now() })
    sending.value = true
    streaming.value = true
    streamingContent.value = ''
    toolStatus.value = null
    let gotDone = false

    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          session_id: sessionId.value,
        }),
      })

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}))
        throw new Error(errData.detail || `HTTP ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      // eventType persists across chunks so split SSE events are handled
      let eventType = null

      function processLine(line) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim()
        } else if (line.startsWith('data: ') && eventType) {
          try {
            const data = JSON.parse(line.slice(6))
            handleSSEEvent(eventType, data)
            if (eventType === 'done') gotDone = true
          } catch { /* skip malformed data */ }
          eventType = null
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          processLine(line)
        }
      }

      // Process any remaining buffer
      if (buffer.trim()) {
        const lines = buffer.split('\n')
        for (const line of lines) {
          processLine(line)
        }
      }

      // Fallback: if the done event was dropped (split across chunks and lost),
      // recover by loading the response from the server
      if (!gotDone) {
        await loadHistory()
        await loadActiveAgent()
      }

      if (isFirstMessage) loadSessions()
    } catch (err) {
      messages.value.push({
        role: 'assistant',
        content: 'Sorry, something went wrong. ' + err.message,
        id: Date.now() + 1,
      })
    } finally {
      streaming.value = false
      streamingContent.value = ''
      toolStatus.value = null
      sending.value = false
    }
  }

  function handleSSEEvent(eventType, data) {
    switch (eventType) {
      case 'token':
        // First token clears tool indicator — response text is arriving
        if (toolStatus.value) toolStatus.value = null
        streamingContent.value += data.content
        break
      case 'tool_start':
        toolStatus.value = { tool: data.tool, agent: data.agent }
        break
      case 'tool_end':
        // Don't clear toolStatus here — tool_start and tool_end often
        // arrive in the same reader chunk (fast DB calls), so Vue never
        // renders the indicator. Instead, keep it visible until the next
        // tool_start overwrites it or tokens start arriving.
        break
      case 'agent_start':
        activeAgent.value = data.agent
        activeAgentLabel.value = data.label
        break
      case 'done':
        // End streaming state before pushing final message to avoid
        // a flash of bouncing dots between preview and final render
        streaming.value = false
        sending.value = false
        streamingContent.value = ''
        toolStatus.value = null
        messages.value.push({
          role: 'assistant',
          content: data.response,
          context_log: data.context_log || null,
          agent: data.active_agent || null,
          id: Date.now() + 1,
        })
        activeAgent.value = data.active_agent || 'hydrogen'
        activeAgentLabel.value = data.active_agent_label || 'Hydrogen (Manager)'
        break
      case 'error':
        messages.value.push({
          role: 'assistant',
          content: 'Sorry, something went wrong. ' + (data.detail || 'Unknown error'),
          id: Date.now() + 1,
        })
        break
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
    loadSessions()
  }

  return {
    messages, sending, activeAgent, activeAgentLabel,
    sessionId, sessions,
    streaming, streamingContent, toolStatus,
    loadHistory, loadSessions, loadActiveAgent,
    switchSession, newSession, deleteSession,
    sendMessage, sendMessageStream, deleteMessage, clearHistory,
  }
})
