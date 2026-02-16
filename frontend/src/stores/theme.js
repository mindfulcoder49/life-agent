import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import client from '../api/client'

export const useThemeStore = defineStore('theme', () => {
  const theme = ref(localStorage.getItem('theme') || 'dark')

  function setTheme(name) {
    theme.value = name
    localStorage.setItem('theme', name)
    document.documentElement.setAttribute('data-theme', name)
    client.put('/users/me', { data: { theme: name } }).catch(() => {})
  }

  function initTheme(userTheme) {
    if (userTheme) {
      theme.value = userTheme
      localStorage.setItem('theme', userTheme)
    }
    document.documentElement.setAttribute('data-theme', theme.value)
  }

  return { theme, setTheme, initTheme }
})
