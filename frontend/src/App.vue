<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { useThemeStore } from './stores/theme'
import ThemePicker from './components/ThemePicker.vue'
import './styles/themes/dark.css'
import './styles/themes/light.css'
import './styles/themes/green.css'
import './styles/themes/blue.css'
import './styles/themes/pink.css'
import './styles/themes/beige.css'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const themeStore = useThemeStore()

const showThemePickerRef = ref(false)

onMounted(async () => {
  await auth.fetchMe()
  if (auth.user) {
    themeStore.initTheme(auth.user.theme)
  } else {
    themeStore.initTheme()
    if (route.path !== '/login') {
      router.push('/login')
    }
  }
})

const isLoggedIn = computed(() => !!auth.user)
const isAdmin = computed(() => auth.user?.is_admin)
const currentTab = computed(() => {
  const path = route.path
  if (path.startsWith('/chat')) return 'chat'
  if (path.startsWith('/database')) return 'database'
  if (path.startsWith('/todo')) return 'todo'
  return ''
})
</script>

<template>
  <div v-if="auth.loading" class="loading-screen">
    <div class="loading-spinner"></div>
  </div>
  <template v-else>
    <template v-if="isLoggedIn">
      <div class="top-bar">
        <h1>Life Agent</h1>
        <div class="top-bar-actions">
          <button @click="showThemePickerRef = !showThemePickerRef" title="Theme">&#9678;</button>
          <button @click="router.push('/help')" title="Help">?</button>
          <button @click="router.push('/settings')" title="Settings">&#9881;</button>
          <button v-if="isAdmin" @click="router.push('/admin')" title="Admin">&#9733;</button>
        </div>
      </div>
      <ThemePicker v-if="showThemePickerRef" @close="showThemePickerRef = false" />
      <router-view />
      <nav class="bottom-nav">
        <a href="#/chat" :class="{ active: currentTab === 'chat' }">
          <span class="icon">&#128172;</span>
          Chat
        </a>
        <a href="#/database" :class="{ active: currentTab === 'database' }">
          <span class="icon">&#128450;</span>
          Database
        </a>
        <a href="#/todo" :class="{ active: currentTab === 'todo' }">
          <span class="icon">&#9745;</span>
          Todo
        </a>
      </nav>
    </template>
    <router-view v-else />
  </template>
</template>

<style scoped>
.loading-screen {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
}
.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
