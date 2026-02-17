<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import { useChatStore } from '../stores/chat'
import ChatMessage from './ChatMessage.vue'

const chat = useChatStore()
const input = ref('')
const messagesEl = ref(null)
const showSessionMenu = ref(false)

onMounted(() => {
  chat.loadHistory()
  chat.loadActiveAgent()
  chat.loadSessions()
})

function scrollToBottom() {
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}

watch(() => chat.messages.length, async () => {
  await nextTick()
  scrollToBottom()
})

watch(() => chat.streamingContent, async () => {
  await nextTick()
  scrollToBottom()
})

watch(() => chat.toolStatus, async () => {
  await nextTick()
  scrollToBottom()
})

async function send() {
  const text = input.value.trim()
  if (!text || chat.sending) return
  input.value = ''
  await chat.sendMessageStream(text)
}

async function clearChat() {
  if (confirm('Clear this conversation?')) {
    await chat.clearHistory()
  }
}

async function newSession() {
  await chat.newSession()
  showSessionMenu.value = false
}

async function pickSession(sid) {
  await chat.switchSession(sid)
  showSessionMenu.value = false
}
</script>

<template>
  <div class="chat-page">
    <div class="chat-header">
      <div class="agent-indicator">
        <span class="agent-dot" :class="chat.activeAgent"></span>
        <span class="agent-name">{{ chat.activeAgentLabel }}</span>
      </div>
      <div class="header-actions">
        <button class="icon-btn" @click="showSessionMenu = !showSessionMenu" title="Sessions">
          &#x1f4ac;
        </button>
        <button class="icon-btn" @click="clearChat" title="Clear chat">
          &#x1f5d1;
        </button>
      </div>
      <div v-if="showSessionMenu" class="session-menu">
        <div class="session-menu-header">
          <span>Chat Sessions</span>
          <button class="session-new-btn" @click="newSession">+ New</button>
        </div>
        <div
          class="session-item"
          :class="{ active: chat.sessionId === 'default' }"
          @click="pickSession('default')"
        >
          Default
        </div>
        <div
          v-for="s in chat.sessions"
          :key="s.session_id"
          class="session-item"
          :class="{ active: chat.sessionId === s.session_id }"
          @click="pickSession(s.session_id)"
        >
          <span>{{ s.session_id }}</span>
          <span class="session-meta">{{ s.message_count }} msgs</span>
        </div>
      </div>
    </div>
    <div class="messages" ref="messagesEl">
      <div v-if="chat.messages.length === 0 && !chat.streaming" class="empty-state">
        <p>Start a conversation with your Life Agent.</p>
        <p style="margin-top: 8px; font-size: 13px;">Tell me about your life goals, how you're feeling, or what's on your mind.</p>
      </div>
      <ChatMessage
        v-for="msg in chat.messages"
        :key="msg.id"
        :message="msg"
        @delete="(id) => chat.deleteMessage(id)"
      />
      <div v-if="chat.streaming" class="streaming-area">
        <div v-if="chat.toolStatus" class="tool-indicator">
          <span class="tool-spinner"></span>
          Calling {{ chat.toolStatus.tool }}...
        </div>
        <div v-if="chat.streamingContent" class="message assistant streaming-message">
          <div class="bubble">
            <div class="content">{{ chat.streamingContent }}<span class="streaming-cursor">|</span></div>
          </div>
        </div>
        <div v-if="!chat.toolStatus && !chat.streamingContent" class="typing">
          <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        </div>
      </div>
      <div v-else-if="chat.sending" class="typing">
        <span class="dot"></span><span class="dot"></span><span class="dot"></span>
      </div>
    </div>
    <div class="input-bar">
      <textarea
        v-model="input"
        @keydown.enter.exact.prevent="send"
        placeholder="Type a message..."
        rows="1"
      ></textarea>
      <button @click="send" :disabled="chat.sending || !input.trim()">Send</button>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 52px - 56px);
  padding-bottom: 56px;
}
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  position: relative;
}
.agent-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
}
.agent-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--text-muted);
}
.agent-dot.hydrogen { background: #f59e0b; }
.agent-dot.helium { background: #8b5cf6; }
.agent-dot.lithium { background: #06b6d4; }
.agent-dot.beryllium { background: #10b981; }
.agent-name {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}
.header-actions {
  display: flex;
  gap: 4px;
}
.icon-btn {
  background: transparent;
  border: none;
  font-size: 16px;
  padding: 4px 8px;
  cursor: pointer;
  border-radius: var(--radius);
  opacity: 0.7;
}
.icon-btn:hover {
  opacity: 1;
  background: var(--bg-card);
}
.session-menu {
  position: absolute;
  top: 100%;
  right: 16px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  min-width: 220px;
  z-index: 50;
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}
.session-menu-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.session-new-btn {
  font-size: 12px;
  padding: 2px 8px;
  background: var(--accent);
  color: white;
  border: none;
  border-radius: var(--radius);
  cursor: pointer;
}
.session-item {
  padding: 8px 12px;
  font-size: 13px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--text-secondary);
}
.session-item:hover {
  background: var(--bg-secondary);
}
.session-item.active {
  color: var(--accent);
  font-weight: 600;
}
.session-meta {
  font-size: 11px;
  color: var(--text-muted);
}
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.input-bar {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--border);
}
.input-bar textarea {
  flex: 1;
  resize: none;
  max-height: 100px;
}
.input-bar button {
  align-self: flex-end;
}
.typing {
  display: flex;
  gap: 4px;
  padding: 8px 16px;
}
.dot {
  width: 8px;
  height: 8px;
  background: var(--text-muted);
  border-radius: 50%;
  animation: bounce 1.4s infinite;
}
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); }
  40% { transform: translateY(-6px); }
}

/* Streaming UI */
.streaming-area {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.tool-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  font-size: 13px;
  font-style: italic;
  color: var(--text-muted);
}
.tool-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--text-muted);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.streaming-message .bubble {
  max-width: 80%;
}
.streaming-message .content {
  white-space: pre-wrap;
  word-break: break-word;
}
.streaming-cursor {
  animation: blink 1s step-end infinite;
  color: var(--accent);
  font-weight: 700;
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
