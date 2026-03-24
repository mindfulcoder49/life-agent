<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { useChatStore } from '../stores/chat'

const router = useRouter()
const chat = useChatStore()
const api = axios.create({ baseURL: '/api', withCredentials: true })

// User data
const displayName = ref('')
const isNew = ref(false)
const aspirationalImage = ref(null)
const lifeGoal = ref('')

// State check
const energy = ref(5)
const soreness = ref(3)
const sickness = ref(1)

// Stages for new user: 'state' | 'loading' | 'suggestions'
// Returning user has no stages, just the single screen
const stage = ref('state')

// Task suggestions (new user only)
const suggestions = ref([])
const selectedTasks = ref(new Set())

const loading = ref(false)
const error = ref('')

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h >= 5 && h < 12) return 'Good morning'
  if (h >= 12 && h < 17) return 'Good afternoon'
  if (h >= 17 && h < 22) return 'Good evening'
  return 'Good night'
})

const selectedCount = computed(() => selectedTasks.value.size)

onMounted(async () => {
  try {
    const [profileRes, goalsRes] = await Promise.all([
      api.get('/users/me'),
      api.get('/life-goals?limit=1'),
    ])
    displayName.value = profileRes.data.display_name
    isNew.value = profileRes.data.is_new
    aspirationalImage.value = profileRes.data.aspirational_image_b64 || null
    lifeGoal.value = goalsRes.data.items?.[0]?.data?.title || ''
  } catch {
    // fall through — page still works without this data
  }
})

function sliderFill(val) {
  return `${((val - 1) / 9) * 100}%`
}

function toggleTask(idx) {
  if (selectedTasks.value.has(idx)) {
    selectedTasks.value.delete(idx)
  } else {
    selectedTasks.value.add(idx)
  }
  // trigger reactivity
  selectedTasks.value = new Set(selectedTasks.value)
}

async function submitStateNew() {
  loading.value = true
  error.value = ''
  stage.value = 'loading'
  try {
    // Save state
    await api.post('/user-states', {
      energy: energy.value,
      soreness: soreness.value,
      sickness: sickness.value,
      notes: '',
    })
    // Fetch suggestions
    const res = await api.get('/welcome/suggestions', {
      params: { goal: lifeGoal.value || 'personal growth', energy: energy.value, soreness: soreness.value, sickness: sickness.value },
    })
    suggestions.value = res.data.suggestions || []
    // Pre-select all by default
    selectedTasks.value = new Set(suggestions.value.map((_, i) => i))
    stage.value = 'suggestions'
  } catch {
    error.value = 'Something went wrong. Please try again.'
    stage.value = 'state'
  } finally {
    loading.value = false
  }
}

async function confirmTasks() {
  loading.value = true
  error.value = ''
  try {
    const saves = []
    for (const idx of selectedTasks.value) {
      const t = suggestions.value[idx]
      if (t.type === 'recurring') {
        saves.push(api.post('/tasks/recurring', {
          title: t.title,
          description: t.description || '',
          interval_days: t.interval_days || 1,
          estimated_minutes: t.estimated_minutes || 15,
          cognitive_load: t.cognitive_load || 5,
          metric: t.metric || null,
        }))
      } else {
        saves.push(api.post('/tasks/one-time', {
          title: t.title,
          description: t.description || '',
          estimated_minutes: t.estimated_minutes || 30,
          cognitive_load: t.cognitive_load || 5,
        }))
      }
    }
    await Promise.all(saves)
    chat.pendingMessage = "I just set up my tasks. I'm ready for my first daily plan!"
    router.push('/chat')
  } catch {
    error.value = 'Failed to save tasks. Please try again.'
  } finally {
    loading.value = false
  }
}

async function goToChat(action) {
  loading.value = true
  error.value = ''
  try {
    await api.post('/user-states', {
      energy: energy.value,
      soreness: soreness.value,
      sickness: sickness.value,
      notes: '',
    })
    const messages = {
      plan: "I'm ready for my daily plan.",
      review: "Let's do a weekly review.",
      tasks: "Let's review and update my tasks.",
    }
    chat.pendingMessage = messages[action]
    router.push('/chat')
  } catch {
    error.value = 'Something went wrong. Please try again.'
    loading.value = false
  }
}
</script>

<template>
  <div class="welcome-page">

    <!-- ── NEW USER ── -->
    <template v-if="isNew">

      <!-- Stage: state check -->
      <div v-if="stage === 'state'" class="welcome-card new-user-card">
        <div class="hero" v-if="aspirationalImage || lifeGoal">
          <img v-if="aspirationalImage" :src="`data:image/png;base64,${aspirationalImage}`" class="hero-img" alt="Your goal" />
          <div class="hero-text">
            <h1>Welcome to Life Agent</h1>
            <p v-if="lifeGoal" class="goal-pill">🎯 {{ lifeGoal }}</p>
            <p class="hero-desc">Life Agent helps you turn your goals into daily action. Your AI team — Hydrogen, Helium, Lithium, and Beryllium — will track your tasks, log your progress, check in on how you're feeling, and build you a prioritized plan every day.</p>
          </div>
        </div>
        <div v-else class="hero-simple">
          <h1>Welcome to Life Agent</h1>
          <p class="hero-desc">Your AI team will track your tasks, log progress, and build you a daily plan. Let's start with how you're feeling.</p>
        </div>

        <h2 class="section-title">How are you feeling right now?</h2>

        <div class="sliders">
          <div class="slider-card">
            <div class="slider-graphic">⚡</div>
            <div class="slider-info">
              <div class="slider-label">Energy</div>
              <div class="slider-desc">How much fuel do you have?</div>
            </div>
            <div class="slider-control">
              <input type="range" min="1" max="10" v-model.number="energy"
                class="slider energy-slider"
                :style="{ '--fill': sliderFill(energy) }" />
              <input type="number" min="1" max="10" v-model.number="energy" class="num-input" />
            </div>
          </div>

          <div class="slider-card">
            <div class="slider-graphic">💪</div>
            <div class="slider-info">
              <div class="slider-label">Soreness</div>
              <div class="slider-desc">How stiff or sore are you?</div>
            </div>
            <div class="slider-control">
              <input type="range" min="1" max="10" v-model.number="soreness"
                class="slider warn-slider"
                :style="{ '--fill': sliderFill(soreness) }" />
              <input type="number" min="1" max="10" v-model.number="soreness" class="num-input" />
            </div>
          </div>

          <div class="slider-card">
            <div class="slider-graphic">🤒</div>
            <div class="slider-info">
              <div class="slider-label">Sickness</div>
              <div class="slider-desc">Any illness or discomfort?</div>
            </div>
            <div class="slider-control">
              <input type="range" min="1" max="10" v-model.number="sickness"
                class="slider warn-slider"
                :style="{ '--fill': sliderFill(sickness) }" />
              <input type="number" min="1" max="10" v-model.number="sickness" class="num-input" />
            </div>
          </div>
        </div>

        <p v-if="error" class="error">{{ error }}</p>
        <button class="primary-btn" @click="submitStateNew" :disabled="loading">
          See my suggested tasks →
        </button>
      </div>

      <!-- Stage: loading -->
      <div v-if="stage === 'loading'" class="welcome-card centered">
        <div class="spinner"></div>
        <p class="processing-text">Building your personalized task list…</p>
      </div>

      <!-- Stage: suggestions -->
      <div v-if="stage === 'suggestions'" class="welcome-card suggestions-card">
        <h2>Choose your starting tasks</h2>
        <p class="suggestions-sub">These are tailored to your goal and current state. Select the ones that feel right — you can always add more later.</p>

        <div class="task-grid">
          <div
            v-for="(task, idx) in suggestions"
            :key="idx"
            class="task-card"
            :class="{ selected: selectedTasks.has(idx) }"
            @click="toggleTask(idx)"
          >
            <div class="task-check" v-if="selectedTasks.has(idx)">✓</div>
            <div class="task-emoji">{{ task.emoji }}</div>
            <div class="task-title">{{ task.title }}</div>
            <div class="task-badge" :class="task.type === 'recurring' ? 'badge-recurring' : 'badge-once'">
              {{ task.type === 'recurring' ? (task.interval_days === 1 ? 'Daily' : `Every ${task.interval_days}d`) : 'One-time' }}
            </div>
            <div class="task-desc">{{ task.description }}</div>
          </div>
        </div>

        <p v-if="error" class="error">{{ error }}</p>
        <div class="suggestions-footer">
          <button class="primary-btn" @click="confirmTasks" :disabled="loading || selectedCount === 0">
            {{ loading ? 'Saving...' : `Add ${selectedCount} task${selectedCount !== 1 ? 's' : ''} and start planning →` }}
          </button>
          <button class="ghost-btn" @click="toggleTask(-1); router.push('/chat')">Skip for now</button>
        </div>
      </div>

    </template>

    <!-- ── RETURNING USER ── -->
    <template v-else>
      <div class="welcome-card returning-card">
        <div class="returning-header">
          <div>
            <h1>{{ greeting }}, {{ displayName }} 👋</h1>
            <p v-if="lifeGoal" class="goal-pill">🎯 {{ lifeGoal }}</p>
          </div>
          <img v-if="aspirationalImage" :src="`data:image/png;base64,${aspirationalImage}`" class="thumb-img" alt="Your goal" />
        </div>

        <h2 class="section-title">How are you feeling today?</h2>

        <div class="sliders">
          <div class="slider-card">
            <div class="slider-graphic">⚡</div>
            <div class="slider-info">
              <div class="slider-label">Energy</div>
              <div class="slider-desc">How much fuel do you have?</div>
            </div>
            <div class="slider-control">
              <input type="range" min="1" max="10" v-model.number="energy"
                class="slider energy-slider"
                :style="{ '--fill': sliderFill(energy) }" />
              <input type="number" min="1" max="10" v-model.number="energy" class="num-input" />
            </div>
          </div>

          <div class="slider-card">
            <div class="slider-graphic">💪</div>
            <div class="slider-info">
              <div class="slider-label">Soreness</div>
              <div class="slider-desc">How stiff or sore are you?</div>
            </div>
            <div class="slider-control">
              <input type="range" min="1" max="10" v-model.number="soreness"
                class="slider warn-slider"
                :style="{ '--fill': sliderFill(soreness) }" />
              <input type="number" min="1" max="10" v-model.number="soreness" class="num-input" />
            </div>
          </div>

          <div class="slider-card">
            <div class="slider-graphic">🤒</div>
            <div class="slider-info">
              <div class="slider-label">Sickness</div>
              <div class="slider-desc">Any illness or discomfort?</div>
            </div>
            <div class="slider-control">
              <input type="range" min="1" max="10" v-model.number="sickness"
                class="slider warn-slider"
                :style="{ '--fill': sliderFill(sickness) }" />
              <input type="number" min="1" max="10" v-model.number="sickness" class="num-input" />
            </div>
          </div>
        </div>

        <p v-if="error" class="error">{{ error }}</p>

        <div class="action-buttons">
          <button class="action-btn primary-action" @click="goToChat('plan')" :disabled="loading">
            <span class="action-icon">📋</span>
            <span class="action-label">Build my plan</span>
            <span class="action-sub">Generate today's todo list</span>
          </button>
          <button class="action-btn" @click="goToChat('review')" :disabled="loading">
            <span class="action-icon">📊</span>
            <span class="action-label">Weekly review</span>
            <span class="action-sub">Review last 7 days</span>
          </button>
          <button class="action-btn" @click="goToChat('tasks')" :disabled="loading">
            <span class="action-icon">✏️</span>
            <span class="action-label">Update tasks</span>
            <span class="action-sub">Add, edit, or remove tasks</span>
          </button>
        </div>
      </div>
    </template>

  </div>
</template>

<style scoped>
.welcome-page {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  min-height: 100vh;
  padding: 24px 20px 80px;
  background: var(--bg-primary);
  overflow-y: auto;
}

.welcome-card {
  background: var(--bg-secondary);
  border-radius: var(--radius);
  padding: 32px;
  width: 100%;
  max-width: 680px;
  box-shadow: var(--shadow);
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.welcome-card.centered {
  align-items: center;
  justify-content: center;
  min-height: 300px;
  text-align: center;
}

.suggestions-card {
  max-width: 860px;
}

/* Hero (new user) */
.hero {
  display: flex;
  gap: 20px;
  align-items: flex-start;
}

.hero-img {
  width: 140px;
  height: 140px;
  object-fit: cover;
  border-radius: var(--radius);
  flex-shrink: 0;
}

.hero-simple { text-align: center; }
.hero-simple h1 { margin-bottom: 8px; }

.hero-text h1 { font-size: 22px; margin: 0 0 8px; }

.goal-pill {
  display: inline-block;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 4px 12px;
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 8px;
}

.hero-desc {
  font-size: 14px;
  color: var(--text-muted);
  line-height: 1.6;
  margin: 0;
}

/* Returning user header */
.returning-card { max-width: 600px; }

.returning-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.returning-header h1 {
  font-size: 22px;
  margin: 0 0 8px;
}

.thumb-img {
  width: 72px;
  height: 72px;
  object-fit: cover;
  border-radius: var(--radius);
  flex-shrink: 0;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

/* Sliders */
.sliders {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.slider-card {
  display: grid;
  grid-template-columns: 44px 1fr auto;
  align-items: center;
  gap: 14px;
  background: var(--bg-primary);
  border-radius: var(--radius);
  padding: 14px 16px;
}

.slider-graphic {
  font-size: 28px;
  text-align: center;
  line-height: 1;
}

.slider-label {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}

.slider-desc {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

.slider-control {
  display: flex;
  align-items: center;
  gap: 10px;
}

.slider {
  -webkit-appearance: none;
  appearance: none;
  width: 160px;
  height: 6px;
  border-radius: 3px;
  outline: none;
  cursor: pointer;
}

.energy-slider {
  background: linear-gradient(to right, #22c55e var(--fill), var(--border) var(--fill));
}

.warn-slider {
  background: linear-gradient(to right, var(--accent) var(--fill), var(--border) var(--fill));
}

.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--accent);
  cursor: pointer;
  box-shadow: 0 1px 4px rgba(0,0,0,0.3);
}

.slider::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--accent);
  cursor: pointer;
  border: none;
}

.num-input {
  width: 52px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 600;
  text-align: center;
  padding: 4px 6px;
  font-family: inherit;
}

.num-input:focus { outline: none; border-color: var(--accent); }

/* Action buttons (returning user) */
.action-buttons {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 16px 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  text-align: center;
}

.action-btn:hover:not(:disabled) {
  border-color: var(--accent);
  background: var(--bg-secondary);
}

.action-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.action-btn.primary-action {
  border-color: var(--accent);
}

.action-icon { font-size: 24px; }

.action-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.action-sub {
  font-size: 11px;
  color: var(--text-muted);
}

/* Task suggestion grid */
.suggestions-sub {
  color: var(--text-muted);
  font-size: 14px;
  margin: -12px 0 0;
}

.task-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.task-card {
  position: relative;
  background: var(--bg-primary);
  border: 2px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 12px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.task-card:hover { border-color: var(--accent); }

.task-card.selected {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 8%, var(--bg-primary));
}

.task-check {
  position: absolute;
  top: 8px;
  right: 10px;
  color: var(--accent);
  font-weight: 700;
  font-size: 14px;
}

.task-emoji { font-size: 26px; line-height: 1; }
.task-title { font-size: 13px; font-weight: 600; color: var(--text-primary); }

.task-badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 10px;
  width: fit-content;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.badge-recurring { background: color-mix(in srgb, var(--accent) 15%, transparent); color: var(--accent); }
.badge-once { background: var(--bg-secondary); color: var(--text-muted); border: 1px solid var(--border); }

.task-desc {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.4;
}

.suggestions-footer {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: flex-start;
}

/* Shared */
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
  align-self: stretch;
}

.primary-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.primary-btn:hover:not(:disabled) { opacity: 0.9; }

.ghost-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 13px;
  cursor: pointer;
  padding: 0;
  text-decoration: underline;
}

.ghost-btn:hover { color: var(--text-secondary); }

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin { to { transform: rotate(360deg); } }

.processing-text { color: var(--text-muted); font-size: 15px; }

.error {
  color: var(--error);
  font-size: 13px;
  margin: 0;
}

@media (max-width: 560px) {
  .hero { flex-direction: column; }
  .hero-img { width: 100%; height: 200px; }
  .slider { width: 110px; }
  .action-buttons { grid-template-columns: 1fr; }
  .returning-header { flex-direction: column-reverse; }
  .thumb-img { width: 56px; height: 56px; }
}
</style>
