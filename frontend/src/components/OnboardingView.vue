<script setup>
import { ref } from 'vue'
import axios from 'axios'

const stage = ref('chat') // chat | selfie | processing | result | sent

const chatInput = ref('')
const goal = ref('')
const aiResponse = ref('')
const aspirationalImage = ref('')
const email = ref('')
const loading = ref(false)
const error = ref('')

const api = axios.create({ baseURL: '/api', withCredentials: true })

async function submitGoal() {
  if (!chatInput.value.trim() || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const res = await api.post('/onboarding/chat', { message: chatInput.value })
    aiResponse.value = res.data.response
    goal.value = res.data.goal
    stage.value = 'selfie'
  } catch {
    error.value = 'Something went wrong. Please try again.'
  } finally {
    loading.value = false
  }
}

async function handleFileSelect(e) {
  const file = e.target.files[0]
  if (!file) return
  stage.value = 'processing'
  error.value = ''

  const formData = new FormData()
  formData.append('goal', goal.value)
  formData.append('image', file)

  try {
    const res = await axios.post('/api/onboarding/transform', formData, {
      withCredentials: true,
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    aspirationalImage.value = res.data.image_b64
    stage.value = 'result'
  } catch {
    error.value = 'Image generation failed. Please try again.'
    stage.value = 'selfie'
  }
}

async function submitEmail() {
  if (!email.value.trim() || loading.value) return
  loading.value = true
  error.value = ''
  try {
    await api.post('/onboarding/claim', {
      email: email.value,
      goal: goal.value,
      aspirational_image_b64: aspirationalImage.value || null,
    })
    stage.value = 'sent'
  } catch {
    error.value = 'Something went wrong. Please try again.'
  } finally {
    loading.value = false
  }
}

function triggerFileInput() {
  document.getElementById('selfie-input').click()
}
</script>

<template>
  <div class="onboarding-page">
    <!-- STAGE: chat -->
    <div v-if="stage === 'chat'" class="onboarding-card">
      <h1>Life Agent</h1>
      <p class="tagline">Your AI-powered personal planning system</p>
      <form @submit.prevent="submitGoal" class="goal-form">
        <label class="goal-label">What's your #1 goal right now?</label>
        <textarea
          v-model="chatInput"
          placeholder="e.g. compete in a physique show in 6 months, make my first $1M, finish my degree..."
          rows="3"
          class="goal-input"
          autofocus
          @keydown.enter.exact.prevent="submitGoal"
        />
        <p v-if="error" class="error">{{ error }}</p>
        <button type="submit" :disabled="loading || !chatInput.trim()" class="primary-btn">
          {{ loading ? 'Thinking...' : 'Let\'s go →' }}
        </button>
      </form>
      <p class="login-link">Already have an account? <a href="#/login">Sign in</a></p>
    </div>

    <!-- STAGE: selfie -->
    <div v-if="stage === 'selfie'" class="onboarding-card">
      <div class="ai-bubble">{{ aiResponse }}</div>
      <div class="selfie-cta">
        <p class="selfie-prompt">Upload a selfie and we'll show you what success looks like.</p>
        <button class="primary-btn" @click="triggerFileInput">Upload selfie</button>
        <input
          id="selfie-input"
          type="file"
          accept="image/*"
          style="display: none"
          @change="handleFileSelect"
        />
        <p v-if="error" class="error">{{ error }}</p>
      </div>
      <p class="skip-link"><a href="#/login">Skip → Sign in instead</a></p>
    </div>

    <!-- STAGE: processing -->
    <div v-if="stage === 'processing'" class="onboarding-card centered">
      <div class="spinner"></div>
      <p class="processing-text">Generating your vision of success…</p>
    </div>

    <!-- STAGE: result -->
    <div v-if="stage === 'result'" class="onboarding-card result-card">
      <div class="result-image-wrap">
        <img
          :src="`data:image/png;base64,${aspirationalImage}`"
          alt="Your aspirational self"
          class="result-image"
        />
      </div>
      <div class="result-right">
        <p class="goal-display">{{ goal }}</p>
        <p class="result-cta">Enter your email to save this and start planning toward it.</p>
        <form @submit.prevent="submitEmail" class="email-form">
          <input
            v-model="email"
            type="email"
            placeholder="you@email.com"
            class="email-input"
            required
            autofocus
          />
          <p v-if="error" class="error">{{ error }}</p>
          <button type="submit" :disabled="loading || !email.trim()" class="primary-btn">
            {{ loading ? 'Sending...' : 'Send my magic link →' }}
          </button>
        </form>
      </div>
    </div>

    <!-- STAGE: sent -->
    <div v-if="stage === 'sent'" class="onboarding-card centered">
      <div class="sent-icon">✓</div>
      <h2>Check your email</h2>
      <p class="sent-text">We sent a sign-in link to <strong>{{ email }}</strong>. Click it to get started — no password needed.</p>
    </div>
  </div>
</template>

<style scoped>
.onboarding-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 20px;
  background: var(--bg-primary);
}

.onboarding-card {
  background: var(--bg-secondary);
  border-radius: var(--radius);
  padding: 40px;
  max-width: 520px;
  width: 100%;
  box-shadow: var(--shadow);
}

.onboarding-card.centered {
  text-align: center;
}

.onboarding-card.result-card {
  display: flex;
  gap: 28px;
  max-width: 800px;
  align-items: flex-start;
}

h1 {
  text-align: center;
  font-size: 28px;
  margin-bottom: 4px;
}

.tagline {
  text-align: center;
  color: var(--text-muted);
  margin-bottom: 32px;
  font-size: 14px;
}

.goal-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.goal-label {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.goal-input {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-primary);
  font-size: 15px;
  padding: 12px;
  resize: vertical;
  font-family: inherit;
}

.goal-input:focus {
  outline: none;
  border-color: var(--accent);
}

.primary-btn {
  padding: 12px 20px;
  font-size: 15px;
  font-weight: 600;
  background: var(--accent);
  color: white;
  border: none;
  border-radius: var(--radius);
  cursor: pointer;
  transition: opacity 0.15s;
}

.primary-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.primary-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.login-link {
  text-align: center;
  margin-top: 20px;
  font-size: 13px;
  color: var(--text-muted);
}

.login-link a, .skip-link a {
  color: var(--accent);
  text-decoration: none;
}

.skip-link {
  text-align: center;
  margin-top: 16px;
  font-size: 13px;
  color: var(--text-muted);
}

.ai-bubble {
  background: var(--bg-primary);
  border-radius: var(--radius);
  padding: 16px;
  font-size: 15px;
  line-height: 1.6;
  margin-bottom: 24px;
  border-left: 3px solid var(--accent);
}

.selfie-cta {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.selfie-prompt {
  font-size: 16px;
  font-weight: 500;
  color: var(--text-primary);
  margin: 0;
}

/* Processing */
.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.processing-text {
  color: var(--text-muted);
  font-size: 15px;
}

/* Result */
.result-image-wrap {
  flex-shrink: 0;
}

.result-image {
  width: 280px;
  height: 280px;
  object-fit: cover;
  border-radius: var(--radius);
  display: block;
}

.result-right {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
}

.goal-display {
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.result-cta {
  color: var(--text-muted);
  font-size: 14px;
  margin: 0;
}

.email-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.email-input {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-primary);
  font-size: 15px;
  padding: 10px 12px;
  font-family: inherit;
}

.email-input:focus {
  outline: none;
  border-color: var(--accent);
}

/* Sent */
.sent-icon {
  width: 52px;
  height: 52px;
  background: var(--accent);
  color: white;
  border-radius: 50%;
  font-size: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
}

.sent-text {
  color: var(--text-secondary);
  font-size: 15px;
  line-height: 1.6;
}

.error {
  color: var(--error);
  font-size: 13px;
  margin: 0;
}

@media (max-width: 640px) {
  .onboarding-card.result-card {
    flex-direction: column;
  }
  .result-image {
    width: 100%;
    height: auto;
  }
}
</style>
