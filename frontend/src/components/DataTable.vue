<script setup>
import { ref } from 'vue'
import JsonField from './JsonField.vue'

const props = defineProps({
  tableName: String,
  items: Array,
  total: Number,
})
const emit = defineEmits(['refresh', 'update', 'remove'])

const editingId = ref(null)
const editData = ref('')
const editError = ref('')

function startEdit(item) {
  editingId.value = item.id
  try {
    editData.value = JSON.stringify(item.data, null, 2)
  } catch {
    editData.value = String(item.data)
  }
  editError.value = ''
}

function cancelEdit() {
  editingId.value = null
  editData.value = ''
  editError.value = ''
}

function saveEdit(id) {
  try {
    const parsed = JSON.parse(editData.value)
    emit('update', id, parsed)
    editingId.value = null
  } catch (e) {
    editError.value = 'Invalid JSON: ' + e.message
  }
}

function confirmDelete(id) {
  if (confirm('Delete this record?')) {
    emit('remove', id)
  }
}
</script>

<template>
  <div>
    <div class="table-header">
      <span class="total">{{ total }} record{{ total !== 1 ? 's' : '' }}</span>
      <button class="secondary" @click="emit('refresh')" style="padding: 6px 12px; font-size: 13px;">Refresh</button>
    </div>
    <div v-if="items.length === 0" class="empty-state">No records yet.</div>
    <div v-else class="records">
      <div v-for="item in items" :key="item.id" class="card record">
        <div class="record-header">
          <span class="record-id">#{{ item.id }}</span>
          <span class="record-time">{{ item.created_at?.slice(0, 16) }}</span>
          <div class="record-actions">
            <button class="secondary" @click="startEdit(item)" style="padding: 4px 10px; font-size: 12px;">Edit</button>
            <button class="secondary" @click="confirmDelete(item.id)" style="padding: 4px 10px; font-size: 12px; color: var(--error);">Del</button>
          </div>
        </div>
        <template v-if="editingId === item.id">
          <textarea
            v-model="editData"
            rows="8"
            style="font-family: monospace; font-size: 12px; margin-top: 8px;"
          ></textarea>
          <p v-if="editError" style="color: var(--error); font-size: 12px; margin-top: 4px;">{{ editError }}</p>
          <div style="display: flex; gap: 8px; margin-top: 8px;">
            <button @click="saveEdit(item.id)" style="padding: 6px 14px; font-size: 13px;">Save</button>
            <button class="secondary" @click="cancelEdit" style="padding: 6px 14px; font-size: 13px;">Cancel</button>
          </div>
        </template>
        <template v-else>
          <JsonField :value="item.data" />
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.total {
  color: var(--text-muted);
  font-size: 13px;
}
.records {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.record-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.record-id {
  font-weight: 600;
  color: var(--accent);
  font-size: 13px;
}
.record-time {
  color: var(--text-muted);
  font-size: 12px;
  flex: 1;
}
.record-actions {
  display: flex;
  gap: 4px;
}
</style>
