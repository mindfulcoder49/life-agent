<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import client from '../api/client'

const router = useRouter()
const auth = useAuthStore()

const profile = ref({})
const apiKey = ref('')
const hasApiKey = ref(false)
const saving = ref(false)
const message = ref('')
const timezone = ref('')
const tzMessage = ref('')

onMounted(async () => {
  try {
    const res = await client.get('/users/me')
    profile.value = res.data
    hasApiKey.value = res.data.has_api_key
    timezone.value = res.data.timezone || 'UTC'
  } catch {}
})

async function saveTimezone() {
  tzMessage.value = ''
  try {
    await client.put('/users/me', { data: { timezone: timezone.value } })
    tzMessage.value = 'Timezone saved'
  } catch (err) {
    tzMessage.value = 'Error: ' + (err.response?.data?.detail || err.message)
  }
}

async function saveApiKey() {
  saving.value = true
  message.value = ''
  try {
    const res = await client.put('/users/me/api-key', { openai_api_key: apiKey.value || null })
    hasApiKey.value = res.data.has_api_key
    apiKey.value = ''
    message.value = 'API key updated'
  } catch (err) {
    message.value = 'Error: ' + (err.response?.data?.detail || err.message)
  } finally {
    saving.value = false
  }
}

async function clearApiKey() {
  saving.value = true
  try {
    const res = await client.put('/users/me/api-key', { openai_api_key: null })
    hasApiKey.value = false
    message.value = 'API key cleared'
  } catch (err) {
    message.value = 'Error: ' + (err.response?.data?.detail || err.message)
  } finally {
    saving.value = false
  }
}

async function logout() {
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="page">
    <h2 style="margin-bottom: 16px;">Settings</h2>
    <div class="card">
      <h3>Profile</h3>
      <p style="margin-top: 8px; color: var(--text-secondary);">{{ profile.display_name }} (@{{ profile.username }})</p>
    </div>
    <div class="card">
      <h3>Timezone</h3>
      <p style="margin-top: 4px; font-size: 13px; color: var(--text-muted);">
        Used to determine the correct local date for task completions. Use an IANA timezone name (e.g. America/New_York, Europe/London, Asia/Tokyo).
      </p>
      <div class="form-group" style="margin-top: 12px;">
        <input v-model="timezone" type="text" placeholder="America/New_York" />
      </div>
      <button @click="saveTimezone">Save Timezone</button>
      <p v-if="tzMessage" style="margin-top: 8px; font-size: 13px; color: var(--success);">{{ tzMessage }}</p>
    </div>
    <div class="card">
      <h3>OpenAI API Key</h3>
      <p style="margin-top: 4px; font-size: 13px; color: var(--text-muted);">
        {{ hasApiKey ? 'Custom API key is set.' : 'Using system default key.' }}
      </p>
      <div class="form-group" style="margin-top: 12px;">
        <input v-model="apiKey" type="password" placeholder="sk-..." />
      </div>
      <div style="display: flex; gap: 8px;">
        <button @click="saveApiKey" :disabled="saving">Save Key</button>
        <button v-if="hasApiKey" class="secondary" @click="clearApiKey" :disabled="saving">Clear Key</button>
      </div>
      <p v-if="message" style="margin-top: 8px; font-size: 13px; color: var(--success);">{{ message }}</p>
    </div>
    <div class="card">
      <button class="secondary" @click="logout" style="color: var(--error);">Log Out</button>
    </div>
  </div>
</template>
