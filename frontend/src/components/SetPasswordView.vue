<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import axios from 'axios'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const themeStore = useThemeStore()

const token = ref('')
const password = ref('')
const confirm = ref('')
const error = ref('')
const loading = ref(false)

onMounted(() => {
  token.value = route.query.token || ''
  if (!token.value) {
    error.value = 'Missing token — please use the link from your email.'
  }
})

async function submit() {
  error.value = ''
  if (password.value.length < 8) {
    error.value = 'Password must be at least 8 characters.'
    return
  }
  if (password.value !== confirm.value) {
    error.value = 'Passwords do not match.'
    return
  }
  loading.value = true
  try {
    const res = await axios.post('/api/auth/setup-password', {
      token: token.value,
      password: password.value,
    }, { withCredentials: true })
    auth.user = res.data
    themeStore.initTheme(res.data.theme)
    router.push('/welcome')
  } catch (err) {
    error.value = err.response?.data?.detail || 'Something went wrong. Your link may have expired.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="setup-page">
    <div class="setup-card">
      <h1>Life Agent</h1>
      <p class="subtitle">Set up your password</p>
      <p class="desc">You're almost in. Choose a password to secure your account — you can also sign in with a magic link anytime.</p>

      <form v-if="token" @submit.prevent="submit">
        <div class="form-group">
          <label>Password</label>
          <input v-model="password" type="password" required minlength="8" autocomplete="new-password" autofocus />
        </div>
        <div class="form-group">
          <label>Confirm password</label>
          <input v-model="confirm" type="password" required autocomplete="new-password" />
        </div>
        <p v-if="error" class="error">{{ error }}</p>
        <button type="submit" :disabled="loading || !password || !confirm" class="submit-btn">
          {{ loading ? 'Saving...' : 'Set password and continue →' }}
        </button>
      </form>
      <p v-else class="error">{{ error }}</p>
    </div>
  </div>
</template>

<style scoped>
.setup-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 20px;
}
.setup-card {
  background: var(--bg-secondary);
  border-radius: var(--radius);
  padding: 36px;
  max-width: 420px;
  width: 100%;
  box-shadow: var(--shadow);
}
h1 {
  text-align: center;
  margin-bottom: 4px;
  font-size: 28px;
}
.subtitle {
  text-align: center;
  color: var(--text-muted);
  margin-bottom: 12px;
}
.desc {
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
  line-height: 1.5;
  margin-bottom: 24px;
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
  margin-top: 6px;
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
  margin-bottom: 10px;
}
</style>
