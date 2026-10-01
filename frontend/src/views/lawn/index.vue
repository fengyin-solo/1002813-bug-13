<template>
  <section class="page" data-module="lawn">
    <header class="page-head">
      <div>
        <h2>草坪管理管理</h2>
        <p class="page-desc">斑秃登记、复壮登记与验收、班次汇总与养护看板；斑秃面积一律按复壮明细实时重算。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="exportRows">导出草坪管理清单</button>
      </div>
    </header>

    <!-- 养护看板：斑秃面积随复壮明细重算，刷新结果稳定 -->
    <div class="stat-row">
      <article v-for="card in dashboardCards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
        <span v-if="card.unit" class="stat-unit">{{ card.unit }}</span>
      </article>
    </div>

    <div class="lawn-tabs" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="link"
        type="button"
        :class="{ active: activeTab === tab.key }"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- 草坪台账 -->
    <template v-if="activeTab === 'lawns'">
      <form class="filter-bar" @submit.prevent="reloadLawns">
        <label class="filter-item">
          <span>草坪编号</span>
          <input v-model="keyword" placeholder="按草坪编号检索" />
        </label>
        <label class="filter-item">
          <span>状态</span>
          <select v-model="statusFilter">
            <option value="">全部</option>
            <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in lawnColumns" :key="column">{{ column }}</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="String(row.id)">
            <td v-for="column in lawnColumns" :key="column">{{ row[column] ?? '—' }}</td>
            <td class="row-actions">
              <button class="link" type="button" @click="openEdit(row)">编辑</button>
              <button class="link" type="button" @click="openDetail(row)">详情</button>
              <button class="link" type="button" @click="openBald(row)">登记斑秃</button>
              <button class="link" type="button" @click="openRejuvenation(row)">登记复壮</button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="lawnColumns.length + 1" class="empty-state">暂无草坪数据</td>
          </tr>
        </tbody>
      </table>
      <footer class="page-foot">
        <span>共 {{ total }} 条草坪记录</span>
        <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      </footer>
    </template>

    <!-- 复壮明细 -->
    <template v-else-if="activeTab === 'rejuvenations'">
      <form class="filter-bar" @submit.prevent="reloadRejuvenations">
        <label class="filter-item">
          <span>班次</span>
          <select v-model="shiftFilter">
            <option value="">全部班次</option>
            <option v-for="s in shifts" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
        <button class="btn" type="submit">查询</button>
      </form>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in rejuvenationColumns" :key="column">{{ column }}</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rejuvenations" :key="String(row.id)">
            <td v-for="column in rejuvenationColumns" :key="column">{{ formatCell(row, column) }}</td>            <td class="row-actions">
              <button
                v-if="!row.accepted"
                class="link"
                type="button"
                @click="acceptRejuvenation(row)"
              >
                验收复壮
              </button>
              <span v-else class="muted">已验收</span>
            </td>
          </tr>
          <tr v-if="!rejuvenations.length">
            <td :colspan="rejuvenationColumns.length + 1" class="empty-state">暂无复壮明细</td>
          </tr>
        </tbody>
      </table>
      <p class="hint">说明：斑秃面积为登记复壮时的挂账面积；剩余斑秃面积与草坪列表、详情、看板同源。</p>
    </template>

    <!-- 班次汇总 -->
    <template v-else>
      <table class="data-table">
        <thead>
          <tr><th>班次</th><th>复壮笔数</th><th>斑秃合计（㎡，明细同口径）</th><th>待验收笔数</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in shiftRows" :key="String(row['班次'])">
            <td>{{ row['班次'] }}</td>
            <td>{{ row['复壮笔数'] }}</td>
            <td>{{ row['斑秃合计'] }}</td>
            <td>{{ row['待验收笔数'] }}</td>
          </tr>
        </tbody>
      </table>
      <p class="hint">斑秃合计由复壮明细逐行累加，与明细之和必然一致。</p>
    </template>

    <!-- 编辑草坪 -->
    <div v-if="editing" class="modal-mask" @click.self="editing = null">
      <form class="modal" @submit.prevent="saveEdit">
        <h3>编辑草坪 {{ editing['草坪编号'] }}</h3>
        <label v-for="field in editableFields" :key="field" class="form-item">
          <span>{{ field }}</span>
          <input v-model="editForm[field]" :type="field === '草坪面积' ? 'number' : 'text'" />
        </label>
        <p v-if="formError" class="error-text">{{ formError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="editing = null">取消</button>
          <button class="btn primary" type="submit" :disabled="saving">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </form>
    </div>

    <!-- 草坪详情 -->
    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal">
        <h3>草坪详情 {{ detail['草坪编号'] }}</h3>
        <dl class="detail-list">
          <div v-for="column in lawnColumns" :key="column">
            <dt>{{ column }}</dt>
            <dd>{{ detail[column] ?? '—' }}</dd>
          </div>
        </dl>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="detail = null">关闭</button>
        </div>
      </div>
    </div>

    <!-- 登记斑秃 -->
    <div v-if="baldTarget" class="modal-mask" @click.self="baldTarget = null">
      <form class="modal" @submit.prevent="submitBald">
        <h3>登记斑秃 · {{ baldTarget['草坪编号'] }}</h3>
        <p class="hint">草坪面积 {{ baldTarget['草坪面积'] }} ㎡，当前待处理斑秃 {{ baldTarget['斑秃面积'] }} ㎡</p>
        <label class="form-item">
          <span>斑秃面积（㎡）</span>
          <input v-model.number="baldForm['斑秃面积']" type="number" min="0" step="0.01" required />
        </label>
        <label class="form-item">
          <span>返青情况</span>
          <input v-model="baldForm['返青情况']" type="text" :placeholder="`留空则沿用：${baldTarget['返青情况'] || '未填写'}`" />
        </label>
        <label class="form-item">
          <span>班次</span>
          <select v-model="baldForm['班次']" required>
            <option value="" disabled>请选择班次</option>
            <option v-for="s in shifts" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
        <p v-if="formError" class="error-text">{{ formError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="baldTarget = null">取消</button>
          <button class="btn primary" type="submit" :disabled="saving">{{ saving ? '提交中…' : '提交' }}</button>
        </div>
      </form>
    </div>

    <!-- 登记复壮 -->
    <div v-if="rejuvTarget" class="modal-mask" @click.self="rejuvTarget = null">
      <form class="modal" @submit.prevent="submitRejuvenation">
        <h3>登记复壮 · {{ rejuvTarget['草坪编号'] }}</h3>
        <p class="hint">
          当前待处理斑秃 {{ rejuvTarget['斑秃面积'] }} ㎡，登记复壮后该面积将从斑秃合计中扣减；
          同一片草坪重复提交只认第一次。
        </p>
        <label class="form-item">
          <span>班次</span>
          <select v-model="rejuvShift" required>
            <option v-for="s in shifts" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
        <p v-if="formError" class="error-text">{{ formError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="rejuvTarget = null">取消</button>
          <button class="btn primary" type="submit" :disabled="saving">{{ saving ? '提交中…' : '提交' }}</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { readError, request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/lawn'
const shifts = ['早班', '中班', '晚班']
const statuses = ['良好', '斑秃', '退化', '已复壮']
const lawnColumns = ['草坪编号', '草种类型', '草坪面积', '修剪频率', '灌溉方式', '返青情况', '斑秃面积', '草坪状态']
const rejuvenationColumns = ['草坪编号', '草种类型', '斑秃面积', '剩余斑秃面积', '班次', '登记时间', '验收时间']
const editableFields = ['草种类型', '草坪面积', '修剪频率', '灌溉方式', '返青情况']
const tabs = [
  { key: 'lawns', label: '草坪台账' },
  { key: 'rejuvenations', label: '复壮明细' },
  { key: 'shifts', label: '班次汇总' },
] as const

type TabKey = (typeof tabs)[number]['key']

const activeTab = ref<TabKey>('lawns')
const rows = ref<Row[]>([])
const total = ref(0)
const keyword = ref('')
const statusFilter = ref('')
const shiftFilter = ref('')
const errorMessage = ref('')

const rejuvenations = ref<Row[]>([])
const shiftRows = ref<Row[]>([])
const dashboard = ref<{ 斑秃面积合计: number; 斑秃草坪数: number; 状态分布: Record<string, number> }>({
  斑秃面积合计: 0,
  斑秃草坪数: 0,
  状态分布: {},
})

const dashboardCards = computed(() => [
  { label: '待处理斑秃面积', value: dashboard.value.斑秃面积合计, unit: '㎡' },
  { label: '斑秃草坪数', value: dashboard.value.斑秃草坪数, unit: '片' },
  { label: '斑秃状态', value: dashboard.value.状态分布['斑秃'] ?? 0, unit: '片' },
  { label: '已复壮草坪', value: dashboard.value.状态分布['已复壮'] ?? 0, unit: '片' },
])

// 弹窗状态
const editing = ref<Row | null>(null)
const detail = ref<Row | null>(null)
const baldTarget = ref<Row | null>(null)
const rejuvTarget = ref<Row | null>(null)
const rejuvShift = ref('早班')
const rejuvRequestId = ref('')
const editForm = reactive<Record<string, string | number>>({})
const baldForm = reactive<Record<string, string | number>>({ 斑秃面积: '', 返青情况: '', 班次: '早班' })
const formError = ref('')
const saving = ref(false)

function formatCell(row: Row, column: string): string | number {
  const value = row[column]
  if (column === '验收时间' && (value === null || value === '')) return '待验收'
  return (value ?? '—') as string | number
}

async function loadDashboard() {
  try {
    const response = await request(`${ENDPOINT}/dashboard`)
    if (!response.ok) throw new Error(await readError(response))
    dashboard.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '养护看板读取失败'
  }
}

async function reloadLawns() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (keyword.value) params.set('keyword', keyword.value)
  if (statusFilter.value) params.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) throw new Error(await readError(response))
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '草坪列表读取失败'
  }
}

async function reloadRejuvenations() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (shiftFilter.value) params.set('shift', shiftFilter.value)
  try {
    const response = await request(`${ENDPOINT}/rejuvenations?${params.toString()}`)
    if (!response.ok) throw new Error(await readError(response))
    const payload = await response.json()
    rejuvenations.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '复壮明细读取失败'
  }
}

async function reloadShifts() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/shifts/summary`)
    if (!response.ok) throw new Error(await readError(response))
    const payload = await response.json()
    shiftRows.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '班次汇总读取失败'
  }
}

function switchTab(key: TabKey) {
  activeTab.value = key
  if (key === 'rejuvenations') void reloadRejuvenations()
  if (key === 'shifts') void reloadShifts()
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reloadLawns()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function openDetail(row: Row) {
  formError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) throw new Error(await readError(response))
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '草坪详情读取失败'
  }
}

function openEdit(row: Row) {
  formError.value = ''
  editing.value = row
  for (const field of editableFields) {
    editForm[field] = (row[field] as string | number) ?? ''
  }
}

async function saveEdit() {
  if (!editing.value) return
  saving.value = true
  formError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${editing.value.id}`, {
      method: 'PUT',
      body: JSON.stringify({ values: { ...editForm } }),
    })
    if (!response.ok) throw new Error(await readError(response))
    editing.value = null
    await Promise.all([reloadLawns(), loadDashboard()])
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '保存失败'
  } finally {
    saving.value = false
  }
}

function openBald(row: Row) {
  formError.value = ''
  baldTarget.value = row
  baldForm['斑秃面积'] = ''
  baldForm['返青情况'] = ''
  baldForm['班次'] = '早班'
}

async function submitBald() {
  if (!baldTarget.value) return
  saving.value = true
  formError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${baldTarget.value.id}/bald`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...baldForm } }),
    })
    if (!response.ok) throw new Error(await readError(response))
    baldTarget.value = null
    await Promise.all([reloadLawns(), loadDashboard()])
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '斑秃登记失败'
  } finally {
    saving.value = false
  }
}

async function postAction(path: string, body: Record<string, unknown>): Promise<{ ok: boolean; message: string }> {
  const response = await request(path, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  const payload = (await response.json().catch(() => null)) as { message?: string } | null
  if (!response.ok) throw new Error(await readError(response))
  return { ok: true, message: payload?.message ?? '操作已生效' }
}

function openRejuvenation(row: Row) {
  formError.value = ''
  rejuvTarget.value = row
  rejuvShift.value = '早班'
  // 打开弹窗即固定本次提交的幂等键：弹窗内重复点提交/网络重试，后端都只认第一次。
  rejuvRequestId.value = `lawn-${row.id}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

async function submitRejuvenation() {
  if (!rejuvTarget.value) return
  saving.value = true
  formError.value = ''
  const target = rejuvTarget.value
  try {
    const result = await postAction(`${ENDPOINT}/${target.id}/rejuvenations`, {
      values: { 班次: rejuvShift.value, request_id: rejuvRequestId.value },
    })
    rejuvTarget.value = null
    errorMessage.value = result.message
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '复壮登记失败'
  } finally {
    saving.value = false
  }
  await Promise.all([reloadLawns(), loadDashboard(), reloadShifts(), reloadRejuvenations()])
}

async function acceptRejuvenation(row: Row) {
  errorMessage.value = ''
  try {
    await postAction(`${ENDPOINT}/rejuvenations/${row.id}/accept`, {})
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '复壮验收失败'
  }
  await Promise.all([reloadLawns(), loadDashboard(), reloadShifts(), reloadRejuvenations()])
}

onMounted(() => {
  void reloadLawns()
  void loadDashboard()
})
</script>

<style scoped>
.lawn-tabs {
  display: flex;
  gap: 16px;
  margin: 12px 0;
}

.lawn-tabs .active {
  font-weight: 700;
  text-decoration: underline;
}

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}

.modal {
  background: #fff;
  border-radius: 8px;
  padding: 20px 24px;
  width: 420px;
  max-width: calc(100vw - 32px);
  max-height: 85vh;
  overflow: auto;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}

.form-item input,
.form-item select {
  padding: 6px 8px;
  border: 1px solid #cfd6e0;
  border-radius: 4px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

.detail-list div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 0;
  border-bottom: 1px dashed #e5e8ee;
}

.detail-list dt {
  color: #667085;
}

.detail-list dd {
  margin: 0;
  text-align: right;
}

.hint {
  color: #667085;
  font-size: 12px;
  margin-top: 8px;
}

.muted {
  color: #98a2b3;
}

.stat-unit {
  margin-left: 4px;
  color: #98a2b3;
  font-size: 12px;
}
</style>
