<script setup>
import { ref, onMounted } from 'vue'
import client from '../api/client'

const props = defineProps({
  slug: String,
})

const article = ref(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const res = await client.get(`/help/articles/${props.slug}`)
    article.value = res.data?.data || res.data
  } catch {}
  loading.value = false
})

function renderMarkdown(text) {
  if (!text) return ''
  return text
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^\- (.+)$/gm, '<li>$1</li>')
    .replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>')
    .replace(/\n\n/g, '<br><br>')
}
</script>

<template>
  <div class="page">
    <a href="#/help" style="color: var(--accent); text-decoration: none; font-size: 14px;">&#8592; Back to Help</a>
    <div v-if="loading" class="empty-state" style="margin-top: 20px;">Loading...</div>
    <div v-else-if="!article" class="empty-state" style="margin-top: 20px;">Article not found.</div>
    <div v-else class="article-content" style="margin-top: 16px;">
      <div v-html="renderMarkdown(article.body || '')"></div>
    </div>
  </div>
</template>

<style scoped>
.article-content {
  line-height: 1.7;
  font-size: 15px;
}
.article-content :deep(h1) {
  font-size: 24px;
  margin-bottom: 12px;
}
.article-content :deep(h2) {
  font-size: 20px;
  margin: 16px 0 8px;
}
.article-content :deep(h3) {
  font-size: 16px;
  margin: 12px 0 6px;
}
.article-content :deep(li) {
  margin-left: 20px;
  margin-bottom: 4px;
}
</style>
