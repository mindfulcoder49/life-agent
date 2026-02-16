<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'

const router = useRouter()
const auth = useAuthStore()
const themeStore = useThemeStore()

const isRegister = ref(false)
const username = ref('')
const password = ref('')
const displayName = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    if (isRegister.value) {
      await auth.register(username.value, password.value, displayName.value || undefined)
    } else {
      await auth.login(username.value, password.value)
    }
    themeStore.initTheme(auth.user?.theme)
    router.push('/chat')
  } catch (err) {
    error.value = err.response?.data?.detail || 'Something went wrong'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <h1>Life Agent</h1>
      <p class="subtitle">{{ isRegister ? 'Create an account' : 'Sign in to continue' }}</p>
      <form @submit.prevent="submit">
        <div class="form-group">
          <label>Username</label>
          <input v-model="username" type="text" required autocomplete="username" />
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
.login-card h1 {
  text-align: center;
  margin-bottom: 4px;
  font-size: 28px;
}
.subtitle {
  text-align: center;
  color: var(--text-muted);
  margin-bottom: 24px;
}
.submit-btn {
  width: 100%;
  padding: 12px;
  margin-top: 8px;
  font-size: 16px;
}
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
.toggle a {
  color: var(--accent);
  text-decoration: none;
}
</style>
