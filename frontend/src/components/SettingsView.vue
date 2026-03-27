<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import client from '../api/client'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const profile = ref({})
const apiKey = ref('')
const hasApiKey = ref(false)
const saving = ref(false)
const message = ref('')
const timezone = ref('')
const tzMessage = ref('')
const discordConnected = ref(false)
const discordUsername = ref('')
const discordMessage = ref('')

onMounted(async () => {
  try {
    const res = await client.get('/users/me')
    profile.value = res.data
    hasApiKey.value = res.data.has_api_key
    timezone.value = res.data.timezone || 'UTC'
    discordConnected.value = res.data.discord_connected
    discordUsername.value = res.data.discord_username || ''
  } catch {}

  if (route.query.discord === 'connected') {
    discordMessage.value = 'Discord connected!'
    discordConnected.value = true
    router.replace('/settings')
  } else if (route.query.discord === 'error') {
    discordMessage.value = 'Discord connection failed. Please try again.'
    router.replace('/settings')
  }
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

async function connectDiscord() {
  discordMessage.value = ''
  try {
    const res = await client.get('/discord/auth')
    window.location.href = res.data.url
  } catch (err) {
    discordMessage.value = 'Error: ' + (err.response?.data?.detail || err.message)
  }
}

async function disconnectDiscord() {
  discordMessage.value = ''
  try {
    await client.delete('/discord/disconnect')
    discordConnected.value = false
    discordUsername.value = ''
    discordMessage.value = 'Discord disconnected.'
  } catch (err) {
    discordMessage.value = 'Error: ' + (err.response?.data?.detail || err.message)
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
      <h3>Discord</h3>
      <p style="margin-top: 4px; font-size: 13px; color: var(--text-muted);">
        Connect your Discord account to receive proactive coaching messages.
      </p>
      <div style="margin-top: 12px;">
        <p v-if="discordConnected" style="font-size: 13px; color: var(--text-secondary); margin-bottom: 10px;">
          Connected as <strong>{{ discordUsername }}</strong>
        </p>
        <div style="display: flex; gap: 8px;">
          <button v-if="!discordConnected" @click="connectDiscord">Connect Discord</button>
          <button v-if="discordConnected" class="secondary" @click="disconnectDiscord">Disconnect</button>
        </div>
      </div>
      <p v-if="discordMessage" style="margin-top: 8px; font-size: 13px; color: var(--success);">{{ discordMessage }}</p>
    </div>
    <div class="card">
      <button class="secondary" @click="logout" style="color: var(--error);">Log Out</button>
    </div>
  </div>
</template>
