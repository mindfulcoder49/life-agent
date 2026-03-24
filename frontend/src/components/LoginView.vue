<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import axios from 'axios'

const router = useRouter()
const auth = useAuthStore()
const themeStore = useThemeStore()

// Modes: 'password' | 'magic'
const mode = ref('password')
const isRegister = ref(false)

// Password fields
const username = ref('')
const password = ref('')
const displayName = ref('')

// Magic link field
const magicEmail = ref('')
const magicSent = ref(false)

const error = ref('')
const loading = ref(false)

function switchMode(m) {
  mode.value = m
  error.value = ''
  magicSent.value = false
}

async function submitPassword() {
  error.value = ''
  loading.value = true
  try {
    if (isRegister.value) {
      await auth.register(username.value, password.value, displayName.value || undefined)
    } else {
      await auth.login(username.value, password.value)
    }
    themeStore.initTheme(auth.user?.theme)
    router.push('/welcome')
  } catch (err) {
    error.value = err.response?.data?.detail || 'Something went wrong'
  } finally {
    loading.value = false
  }
}

async function submitMagic() {
  error.value = ''
  if (!magicEmail.value.trim()) return
  loading.value = true
  try {
    await axios.post('/api/auth/request-magic-link', { email: magicEmail.value }, { withCredentials: true })
    magicSent.value = true
  } catch {
    error.value = 'Something went wrong. Please try again.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <h1>Life Agent</h1>

      <!-- Mode tabs -->
      <div class="tabs">
        <button :class="['tab', { active: mode === 'password' }]" @click="switchMode('password')">
          Password
        </button>
        <button :class="['tab', { active: mode === 'magic' }]" @click="switchMode('magic')">
          Email me a link
        </button>
      </div>

      <!-- Password mode -->
      <template v-if="mode === 'password'">
        <p class="subtitle">{{ isRegister ? 'Create an account' : 'Sign in to continue' }}</p>
        <form @submit.prevent="submitPassword">
          <div class="form-group">
            <label>Username</label>
            <input v-model="username" type="text" required autocomplete="username" autofocus />
          </div>
          <div class="form-group">
            <label>Password</label>
            <input v-model="password" type="password" required autocomplete="current-password" />
          </div>
          <div v-if="isRegister" class="form-group">
            <label>Display Name (optional)</label>
            <input v-model="displayName" type="text" />
          </div>
          <p v-if="error" class="error">{{ error }}</p>
          <button type="submit" :disabled="loading" class="submit-btn">
            {{ loading ? 'Loading...' : (isRegister ? 'Register' : 'Login') }}
          </button>
        </form>
        <p class="toggle">
          {{ isRegister ? 'Already have an account?' : "Don't have an account?" }}
          <a href="#" @click.prevent="isRegister = !isRegister; error = ''">
            {{ isRegister ? 'Sign in' : 'Register' }}
          </a>
        </p>
      </template>

      <!-- Magic link mode -->
      <template v-else>
        <template v-if="!magicSent">
          <p class="subtitle">We'll email you a sign-in link — no password needed.</p>
          <form @submit.prevent="submitMagic">
            <div class="form-group">
              <label>Email address</label>
              <input v-model="magicEmail" type="email" required autocomplete="email" autofocus placeholder="you@email.com" />
            </div>
            <p v-if="error" class="error">{{ error }}</p>
            <button type="submit" :disabled="loading || !magicEmail.trim()" class="submit-btn">
              {{ loading ? 'Sending...' : 'Send me a link →' }}
            </button>
          </form>
        </template>
        <template v-else>
          <div class="sent-state">
            <div class="sent-icon">✓</div>
            <p class="sent-text">Check your email — we sent a sign-in link to <strong>{{ magicEmail }}</strong>.</p>
            <button class="ghost-btn" @click="magicSent = false; magicEmail = ''">Use a different email</button>
          </div>
        </template>
      </template>

      <p class="onboarding-link">New here? <a href="#/onboarding">Get started →</a></p>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 20px;
}
.login-card {
  background: var(--bg-secondary);
  border-radius: var(--radius);
  padding: 32px;
  max-width: 400px;
  width: 100%;
  box-shadow: var(--shadow);
}
h1 {
  text-align: center;
  margin-bottom: 16px;
  font-size: 28px;
}
.tabs {
  display: flex;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  margin-bottom: 20px;
}
.tab {
  flex: 1;
  padding: 9px;
  font-size: 13px;
  font-weight: 500;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-muted);
  transition: background 0.15s, color 0.15s;
}
.tab.active {
  background: var(--accent);
  color: white;
}
.subtitle {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  margin-bottom: 20px;
}
.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
}
.form-group label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}
.form-group input {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-primary);
  font-size: 15px;
  padding: 10px 12px;
  font-family: inherit;
}
.form-group input:focus {
  outline: none;
  border-color: var(--accent);
}
.submit-btn {
  width: 100%;
  padding: 12px;
  margin-top: 4px;
  font-size: 15px;
  font-weight: 600;
  background: var(--accent);
  color: white;
  border: none;
  border-radius: var(--radius);
  cursor: pointer;
  transition: opacity 0.15s;
}
.submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.submit-btn:hover:not(:disabled) { opacity: 0.9; }
.error {
  color: var(--error);
  font-size: 13px;
  margin-bottom: 8px;
}
.toggle {
  text-align: center;
  margin-top: 16px;
  color: var(--text-secondary);
  font-size: 14px;
}
.toggle a, .onboarding-link a {
  color: var(--accent);
  text-decoration: none;
}
.onboarding-link {
  text-align: center;
  margin-top: 12px;
  font-size: 13px;
  color: var(--text-muted);
  border-top: 1px solid var(--border);
  padding-top: 16px;
}
/* Sent state */
.sent-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  text-align: center;
}
.sent-icon {
  width: 44px;
  height: 44px;
  background: var(--accent);
  color: white;
  border-radius: 50%;
  font-size: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.sent-text {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.5;
}
.ghost-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 13px;
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
}
.ghost-btn:hover { color: var(--text-secondary); }
</style>
