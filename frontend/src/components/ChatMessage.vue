<script setup>
import { ref } from 'vue'
import ContextModal from './ContextModal.vue'

const props = defineProps({
  message: Object,
})
const emit = defineEmits(['delete'])

const showContext = ref(false)
const showActions = ref(false)
</script>

<template>
  <div class="message" :class="message.role" @click="showActions = !showActions">
    <div class="bubble">
      <div class="content">{{ message.content }}</div>
      <div v-if="showActions" class="actions">
        <button
          v-if="message.role === 'assistant' && message.context_log"
          class="action-btn"
          @click.stop="showContext = true"
        >
          See full context
        </button>
        <button
          class="action-btn delete-btn"
          @click.stop="emit('delete', message.id)"
        >
          Delete
        </button>
      </div>
    </div>
    <ContextModal
      v-if="showContext"
      :contextLog="message.context_log"
      @close="showContext = false"
    />
  </div>
</template>

<style scoped>
.message {
  display: flex;
  max-width: 85%;
  cursor: pointer;
}
.message.user {
  align-self: flex-end;
}
.message.assistant {
  align-self: flex-start;
}
.bubble {
  padding: 10px 14px;
  border-radius: var(--radius);
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.message.user .bubble {
  background: var(--accent);
  color: white;
  border-bottom-right-radius: 4px;
}
.message.assistant .bubble {
  background: var(--bg-card);
  border-bottom-left-radius: 4px;
}
.actions {
  display: flex;
  gap: 12px;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid rgba(255,255,255,0.1);
}
.action-btn {
  background: transparent;
  color: var(--text-muted);
  padding: 2px 0;
  font-size: 12px;
  text-decoration: underline;
}
.action-btn:hover {
  color: var(--text-secondary);
}
.delete-btn {
  color: var(--error);
  opacity: 0.7;
}
.delete-btn:hover {
  opacity: 1;
}
</style>
