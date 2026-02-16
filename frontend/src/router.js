import { createRouter, createWebHashHistory } from 'vue-router'
import LoginView from './components/LoginView.vue'
import ChatView from './components/ChatView.vue'
import DatabaseView from './components/DatabaseView.vue'
import TodoView from './components/TodoView.vue'
import SettingsView from './components/SettingsView.vue'
import AdminView from './components/AdminView.vue'
import HelpCenter from './components/HelpCenter.vue'
import HelpArticle from './components/HelpArticle.vue'

const routes = [
  { path: '/login', component: LoginView },
  { path: '/chat', component: ChatView },
  { path: '/database', component: DatabaseView },
  { path: '/todo', component: TodoView },
  { path: '/settings', component: SettingsView },
  { path: '/admin', component: AdminView },
  { path: '/help', component: HelpCenter },
  { path: '/help/:slug', component: HelpArticle, props: true },
  { path: '/', redirect: '/chat' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export default router
