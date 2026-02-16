import { defineStore } from 'pinia'
import { ref } from 'vue'
import client from '../api/client'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const loading = ref(true)

  async function fetchMe() {
    try {
      const res = await client.get('/auth/me')
      user.value = res.data
    } catch {
      user.value = null
    } finally {
      loading.value = false
    }
  }

  async function login(username, password) {
    const res = await client.post('/auth/login', { username, password })
    user.value = res.data
    return res.data
  }

  async function register(username, password, display_name) {
    const res = await client.post('/auth/register', { username, password, display_name })
    user.value = res.data
    return res.data
  }

  async function logout() {
    await client.post('/auth/logout')
    user.value = null
  }

  return { user, loading, fetchMe, login, register, logout }
})
