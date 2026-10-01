<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>运营概览</h2>
        <p class="page-desc">汇总各业务模块的关键指标，先看总量再看异常。</p>
      </div>
    </header>
    <div class="stat-row">
      <article v-for="card in cards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>
    <h3 style="margin:20px 0 8px;font-size:15px;">草坪养护看板</h3>
    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">待处理斑秃合计（复壮前未处理完，按复壮明细重算）</span>
        <strong class="stat-value">{{ lawnBoard.斑秃合计面积 ?? 0 }}<small style="font-size:12px;color:#64748b;margin-left:2px;">㎡</small></strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">斑秃草坪数</span>
        <strong class="stat-value">{{ lawnBoard.斑秃草坪数 ?? 0 }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">累计复壮面积</span>
        <strong class="stat-value">{{ lawnBoard.累计复壮面积 ?? 0 }}<small style="font-size:12px;color:#64748b;margin-left:2px;">㎡</small></strong>
      </article>
    </div>
    <p v-if="lawnError" class="error-text">{{ lawnError }}</p>

    <table class="data-table" style="margin-top:12px;">
      <thead>
        <tr><th>业务模块</th><th>今日新增</th><th>待处理</th><th>异常量</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in moduleRows" :key="row.name">
          <td>{{ row.name }}</td>
          <td>{{ row.created }}</td>
          <td>{{ row.pending }}</td>
          <td>{{ row.abnormal }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson, request } from '@/api/client'

type Overview = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}
type LawnBoard = {
  斑秃合计面积: number
  斑秃草坪数: number
  累计复壮面积: number
}

const cards = ref<Overview['cards']>([])
const moduleRows = ref<Overview['modules']>([])
const lawnBoard = ref<Partial<LawnBoard>>({})
const lawnError = ref('')

async function loadLawnBoard() {
  // 斑秃面积来自后端按复壮明细实时重算，前端不缓存旧数。
  try {
    const response = await request('/api/lawn/board')
    if (!response.ok) {
      lawnError.value = await response.json().then((p) => p?.detail ?? '草坪看板读取失败').catch(() => '草坪看板读取失败')
      return
    }
    lawnBoard.value = await response.json()
  } catch (error) {
    lawnError.value = error instanceof Error ? error.message : '草坪看板读取失败'
  }
}

onMounted(async () => {
  try {
    const payload = await fetchJson<Overview>('/api/overview')
    cards.value = payload.cards
    moduleRows.value = payload.modules
  } catch {
    cards.value = [{"label": "业务模块", "value": 0}, {"label": "今日新增", "value": 0}]
    moduleRows.value = [{"name": "绿地台账", "created": 0, "pending": 0, "abnormal": 0}, {"name": "乔木管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "灌木管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "草坪管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "花卉造景", "created": 0, "pending": 0, "abnormal": 0}, {"name": "病虫害防治", "created": 0, "pending": 0, "abnormal": 0}, {"name": "灌溉作业", "created": 0, "pending": 0, "abnormal": 0}, {"name": "施肥作业", "created": 0, "pending": 0, "abnormal": 0}, {"name": "修剪造型", "created": 0, "pending": 0, "abnormal": 0}, {"name": "绿地巡查", "created": 0, "pending": 0, "abnormal": 0}, {"name": "杂草清除", "created": 0, "pending": 0, "abnormal": 0}, {"name": "树木支撑", "created": 0, "pending": 0, "abnormal": 0}, {"name": "苗木移植", "created": 0, "pending": 0, "abnormal": 0}, {"name": "园建设施", "created": 0, "pending": 0, "abnormal": 0}, {"name": "园林机械", "created": 0, "pending": 0, "abnormal": 0}, {"name": "苗木基地", "created": 0, "pending": 0, "abnormal": 0}, {"name": "水体养护", "created": 0, "pending": 0, "abnormal": 0}, {"name": "名木古树", "created": 0, "pending": 0, "abnormal": 0}, {"name": "市民热线", "created": 0, "pending": 0, "abnormal": 0}, {"name": "季度养护方案", "created": 0, "pending": 0, "abnormal": 0}]
  }
  await loadLawnBoard()
})
</script>
