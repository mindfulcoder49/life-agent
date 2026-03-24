import { createRouter, createWebHashHistory } from 'vue-router'
import LoginView from './components/LoginView.vue'
import OnboardingView from './components/OnboardingView.vue'
import WelcomeView from './components/WelcomeView.vue'
import SetPasswordView from './components/SetPasswordView.vue'
import ChatView from './components/ChatView.vue'
import DatabaseView from './components/DatabaseView.vue'
import TodoView from './components/TodoView.vue'
import SettingsView from './components/SettingsView.vue'
import AdminView from './components/AdminView.vue'
import HelpCenter from './components/HelpCenter.vue'
import HelpArticle from './components/HelpArticle.vue'

const routes = [
  { path: '/onboarding', component: OnboardingView },
  { path: '/login', component: LoginView },
  { path: '/setup-password', component: SetPasswordView },
  { path: '/welcome', component: WelcomeView },
  { path: '/chat', component: ChatView },
  { path: '/database', component: DatabaseView },
  { path: '/todo', component: TodoView },
  { path: '/settings', component: SettingsView },
  { path: '/admin', component: AdminView },
  { path: '/help', component: HelpCenter },
  { path: '/help/:slug', component: HelpArticle, props: true },
  { path: '/', redirect: '/welcome' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export default router
