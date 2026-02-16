<script setup>
import { ref, onMounted } from 'vue'
import client from '../api/client'

const articles = ref([])
const loading = ref(true)

onMounted(async () => {
  try {
    const res = await client.get('/help/articles')
    articles.value = res.data.items || []
  } catch {}
  loading.value = false
})
</script>

<template>
  <div class="page">
    <h2 style="margin-bottom: 16px;">Help Center</h2>
    <div v-if="loading" class="empty-state">Loading...</div>
    <div v-else-if="articles.length === 0" class="empty-state">No articles yet.</div>
    <a
      v-for="article in articles"
      :key="article.id"
      :href="`#/help/${article.data?.slug}`"
      class="card article-link"
    >
      <h3>{{ article.data?.title }}</h3>
      <span class="badge" v-if="article.data?.category">{{ article.data.category }}</span>
    </a>
  </div>
</template>

<style scoped>
.article-link {
  display: flex;
  justify-content: space-between;
  align-items: center;
  text-decoration: none;
  color: var(--text-primary);
  cursor: pointer;
  transition: background 0.2s;
}
.article-link:hover {
  background: var(--bg-secondary);
}
.article-link h3 {
  font-size: 15px;
}
</style>
