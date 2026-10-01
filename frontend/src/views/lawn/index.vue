<template>
  <section class="page" data-module="lawn">
    <header class="page-head">
      <div>
        <h2>草坪管理管理</h2>
        <p class="page-desc">斑秃面积按复壮明细实时重算；列表、详情、汇总同一份数据，重复提交复壮只认第一次。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记草坪</button>
        <button class="btn" type="button" @click="exportRows">导出草坪管理清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}<small v-if="item.unit">{{ item.unit }}</small></strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>草坪状态</span>
        <select v-model="filters.status">
          <option value="">全部</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ formatCell(column, row[column]) }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button class="link" type="button" @click="openEdit(row)">修改</button>
            <button
              v-if="row.草坪状态 === '良好'"
              class="link"
              type="button"
              @click="openRegisterBare(row)"
            >
              登记斑秃
            </button>
            <button
              v-if="row.草坪状态 === '斑秃'"
              class="link"
              type="button"
              @click="openRejuvenate(row)"
            >
              复壮登记
            </button>
            <button
              v-if="row.草坪状态 === '退化'"
              class="link"
              type="button"
              @click="runSimpleAction('验收复壮', row)"
            >
              验收复壮
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无草坪管理数据，可先登记草坪</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条草坪管理记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <section class="board-section">
      <h3>养护看板 · 班次汇总</h3>
      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">待处理斑秃合计（复壮前未处理完）</span>
          <strong class="stat-value">{{ board['斑秃合计面积'] ?? 0 }}<small>㎡</small></strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">斑秃草坪数</span>
          <strong class="stat-value">{{ board['斑秃草坪数'] ?? 0 }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">累计复壮面积</span>
          <strong class="stat-value">{{ board['累计复壮面积'] ?? 0 }}<small>㎡</small></strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">明细复壮面积之和（对账）</span>
          <strong class="stat-value">{{ summary['明细复壮面积之和'] ?? 0 }}<small>㎡</small></strong>
        </article>
      </div>
      <div class="board-columns">
        <div>
          <h4>斑秃明细（构成合计）</h4>
          <table class="data-table">
            <thead><tr><th>草坪编号</th><th>草种类型</th><th>斑秃面积(㎡)</th></tr></thead>
            <tbody>
              <tr v-for="item in board['斑秃明细'] ?? []" :key="item.草坪编号">
                <td>{{ item.草坪编号 }}</td>
                <td>{{ item.草种类型 }}</td>
                <td>{{ item.斑秃面积 }}</td>
              </tr>
              <tr v-if="!(board['斑秃明细'] ?? []).length">
                <td colspan="3" class="empty-state">暂无待处理斑秃</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div>
          <h4>班次汇总</h4>
          <table class="data-table">
            <thead><tr><th>班次</th><th>复壮条数</th><th>复壮面积合计(㎡)</th></tr></thead>
            <tbody>
              <tr v-for="item in summary['班次汇总'] ?? []" :key="item.班次">
                <td>{{ item.班次 }}</td>
                <td>{{ item.复壮条数 }}</td>
                <td>{{ item.复壮面积合计 }}</td>
              </tr>
              <tr v-if="!(summary['班次汇总'] ?? []).length">
                <td colspan="3" class="empty-state">暂无复壮登记</td>
              </tr>
            </tbody>
          </table>
          <p class="reconcile-note">
            斑秃合计 {{ summary['斑秃合计'] ?? 0 }}㎡，复壮合计 {{ summary['复壮面积合计'] ?? 0 }}㎡，
            明细之和 {{ summary['明细复壮面积之和'] ?? 0 }}㎡
            <span v-if="summaryMismatch" class="error-text">（合计与明细不一致，请刷新重算）</span>
          </p>
        </div>
      </div>
    </section>

    <!-- 登记 / 修改 -->
    <div v-if="formVisible" class="modal-mask" @click.self="closeForm">
      <form class="modal" @submit.prevent="submitForm">
        <h3>{{ formMode === 'create' ? '登记草坪' : '修改草坪' }}</h3>
        <label v-for="field in formFields" :key="field" class="form-item">
          <span>{{ field }}</span>
          <input v-model="formValues[field]" :placeholder="`请输入${field}`" />
        </label>
        <p v-if="formError" class="error-text">{{ formError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeForm">取消</button>
          <button class="btn primary" type="submit">保存</button>
        </div>
      </form>
    </div>

    <!-- 详情 -->
    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal">
        <h3>草坪详情 · {{ detail.草坪编号 }}</h3>
        <table class="data-table">
          <tbody>
            <tr v-for="field in columns" :key="field">
              <th>{{ field }}</th>
              <td>{{ formatCell(field, detail[field]) }}</td>
            </tr>
            <tr><th>累计复壮面积</th><td>{{ detail.累计复壮面积 }}㎡</td></tr>
          </tbody>
        </table>
        <h4>复壮明细</h4>
        <table class="data-table">
          <thead><tr><th>班次</th><th>复壮面积(㎡)</th><th>登记人</th><th>登记时间</th></tr></thead>
          <tbody>
            <tr v-for="record in detail.复壮明细 ?? []" :key="record.id">
              <td>{{ record.班次 }}</td>
              <td>{{ record.复壮面积 }}</td>
              <td>{{ record.登记人 || '—' }}</td>
              <td>{{ record.登记时间 || '—' }}</td>
            </tr>
            <tr v-if="!(detail.复壮明细 ?? []).length">
              <td colspan="4" class="empty-state">暂无复壮登记</td>
            </tr>
          </tbody>
        </table>
        <div class="modal-actions">
          <button class="btn" type="button" @click="detail = null">关闭</button>
        </div>
      </div>
    </div>

    <!-- 登记斑秃 -->
    <div v-if="bareTarget" class="modal-mask" @click.self="bareTarget = null">
      <form class="modal" @submit.prevent="submitRegisterBare">
        <h3>登记斑秃 · {{ bareTarget.草坪编号 }}</h3>
        <p class="page-desc">登记后草坪进入斑秃状态，斑秃面积纳入看板与班次汇总口径。</p>
        <label class="form-item">
          <span>斑秃面积(㎡)</span>
          <input v-model="bareForm.斑秃面积" placeholder="请输入斑秃面积" />
        </label>
        <label class="form-item">
          <span>返青情况</span>
          <input v-model="bareForm.返青情况" placeholder="可选，如：部分返青" />
        </label>
        <p v-if="bareError" class="error-text">{{ bareError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="bareTarget = null">取消</button>
          <button class="btn primary" type="submit">确认登记斑秃</button>
        </div>
      </form>
    </div>

    <!-- 复壮登记 -->
    <div v-if="actionTarget" class="modal-mask" @click.self="actionTarget = null">
      <form class="modal" @submit.prevent="submitRejuvenate">
        <h3>复壮登记 · {{ actionTarget.草坪编号 }}</h3>
        <p class="page-desc">
          当前剩余待复壮斑秃面积 {{ actionTarget.斑秃面积 }}㎡。同一片草坪重复提交只认第一次，
          登记后斑秃合计与看板立即重算。
        </p>
        <label class="form-item">
          <span>班次</span>
          <select v-model="actionForm.班次">
            <option v-for="shift in shifts" :key="shift" :value="shift">{{ shift }}</option>
          </select>
        </label>
        <label class="form-item">
          <span>登记人</span>
          <input v-model="actionForm.登记人" placeholder="可选，默认当前值班" />
        </label>
        <p v-if="actionError" class="error-text">{{ actionError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="actionTarget = null">取消</button>
          <button class="btn primary" type="submit">确认复壮登记</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>
interface BoardPayload {
  斑秃合计面积: number
  斑秃草坪数: number
  累计复壮面积: number
  各状态数量: Record<string, number>
  斑秃明细: { 草坪编号: string; 草种类型: string; 斑秃面积: number }[]
}
interface SummaryPayload {
  斑秃合计: number
  斑秃草坪数: number
  复壮面积合计: number
  明细复壮面积之和: number
  班次汇总: { 班次: string; 复壮条数: number; 复壮面积合计: number }[]
  复壮明细: Record<string, string | number>[]
}

const ENDPOINT = '/api/lawn'
const columns = ["草坪编号", "草种类型", "草坪面积", "修剪频率", "灌溉方式", "返青情况", "斑秃面积", "草坪状态"]
const statuses = ["良好", "斑秃", "退化", "已复壮"]
const shifts = ["白班", "夜班"]
const session = useSessionStore()

const areaColumns = new Set(["草坪面积", "斑秃面积"])
function formatCell(column: string, value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  return areaColumns.has(column) ? `${value}㎡` : value
}

/** 把接口返回的原因原样取出：ActionResult.ok=False 或 HTTP 错误都带业务消息。 */
async function readError(response: Response): Promise<string> {
  try {
    const payload = await response.json()
    if (payload && typeof payload === 'object') {
      if (typeof payload.message === 'string' && payload.message) return payload.message
      if (typeof payload.detail === 'string' && payload.detail) return payload.detail
    }
  } catch {
    // 非 JSON 响应时退回状态码
  }
  return `接口返回 ${response.status}，数据未更新`
}

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = reactive<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const board = ref<Partial<BoardPayload>>({})
const summary = ref<Partial<SummaryPayload>>({})
const summaryMismatch = computed(
  () => (summary.value.复壮面积合计 ?? 0) !== (summary.value.明细复壮面积之和 ?? 0),
)

const stats = computed(() => [
  { label: '良好草坪', value: board.value.各状态数量?.['良好'] ?? countByStatus('良好'), unit: '块' },
  { label: '斑秃草坪', value: board.value.斑秃草坪数 ?? countByStatus('斑秃'), unit: '块' },
  { label: '退化草坪', value: board.value.各状态数量?.['退化'] ?? countByStatus('退化'), unit: '块' },
  { label: '待处理斑秃合计', value: board.value.斑秃合计面积 ?? 0, unit: '㎡' },
])

function countByStatus(status: string) {
  return rows.value.filter((row) => row.草坪状态 === status).length
}

function resetFilters() {
  for (const key of Object.keys(filters)) delete filters[key]
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

// ---------- 登记 / 修改 ----------
const formVisible = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const formId = ref<number | null>(null)
const formFields = ["草坪编号", "草种类型", "草坪面积", "斑秃面积", "修剪频率", "灌溉方式", "返青情况"]
const formValues = reactive<Record<string, string>>({})
const formError = ref('')

function resetForm(source?: Row) {
  for (const field of formFields) {
    formValues[field] = source && source[field] !== null && source[field] !== undefined
      ? String(source[field])
      : ''
  }
  formError.value = ''
}

function openCreate() {
  formMode.value = 'create'
  formId.value = null
  resetForm()
  formVisible.value = true
}

function openEdit(row: Row) {
  formMode.value = 'edit'
  formId.value = Number(row.id)
  resetForm(row)
  formVisible.value = true
}

function closeForm() {
  formVisible.value = false
}

async function submitForm() {
  formError.value = ''
  const url = formMode.value === 'create' ? ENDPOINT : `${ENDPOINT}/${formId.value}`
  try {
    const response = await request(url, {
      method: formMode.value === 'create' ? 'POST' : 'PUT',
      body: JSON.stringify({ values: { ...formValues } }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      formError.value = payload.message || (await readError(response))
      return
    }
    formVisible.value = false
    await refreshAll()
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '保存失败'
  }
}

// ---------- 详情 ----------
interface RejuvenationRecord {
  id: number
  班次: string
  复壮面积: number
  登记人?: string
  登记时间?: string
}
const detail = ref<(Row & { 累计复壮面积?: number; 复壮明细?: RejuvenationRecord[] }) | null>(null)

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      errorMessage.value = await readError(response)
      return
    }
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '详情读取失败'
  }
}

// ---------- 登记斑秃 ----------
const bareTarget = ref<Row | null>(null)
const bareForm = reactive({ 斑秃面积: '', 返青情况: '' })
const bareError = ref('')

function openRegisterBare(row: Row) {
  bareTarget.value = row
  bareForm.斑秃面积 = row.斑秃面积 !== null && row.斑秃面积 !== undefined && Number(row.斑秃面积) > 0
    ? String(row.斑秃面积)
    : ''
  bareForm.返青情况 = typeof row.返青情况 === 'string' ? row.返青情况 : ''
  bareError.value = ''
}

async function submitRegisterBare() {
  if (!bareTarget.value) return
  bareError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${bareTarget.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: { action: '登记斑秃', 斑秃面积: bareForm.斑秃面积, 返青情况: bareForm.返青情况 },
      }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      bareError.value = payload.message || (await readError(response))
      return
    }
    bareTarget.value = null
    await refreshAll()
  } catch (error) {
    bareError.value = error instanceof Error ? error.message : '斑秃登记失败'
  }
}

// ---------- 验收复壮（无需额外入参） ----------
async function runSimpleAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      errorMessage.value = payload.message || (await readError(response))
      return
    }
    await refreshAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败'
  }
}

// ---------- 复壮登记 ----------
const actionTarget = ref<Row | null>(null)
const actionForm = reactive({ 班次: '白班', 登记人: '' })
const actionError = ref('')

function openRejuvenate(row: Row) {
  actionTarget.value = row
  actionForm.班次 = '白班'
  actionForm.登记人 = session.operator || ''
  actionError.value = ''
}

async function submitRejuvenate() {
  if (!actionTarget.value) return
  actionError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${actionTarget.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: { action: '复壮作业', 班次: actionForm.班次, 登记人: actionForm.登记人 },
      }),
    })
    const payload = await response.json()
    if (!response.ok || payload.ok === false) {
      // 接口报错原样带出（含「已登记复壮，请勿重复提交」等原因）
      actionError.value = payload.message || (await readError(response))
      return
    }
    actionTarget.value = null
    await refreshAll()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '复壮登记失败'
  }
}

// ---------- 列表 / 看板 ----------
async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(Object.entries(filters).filter(([, value]) => value)).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      errorMessage.value = await readError(response)
      return
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '草坪列表读取失败'
  }
}

async function reloadBoard() {
  const [boardResponse, summaryResponse] = await Promise.all([
    request(`${ENDPOINT}/board`),
    request(`${ENDPOINT}/shift-summary`),
  ])
  if (boardResponse.ok) board.value = await boardResponse.json()
  if (summaryResponse.ok) summary.value = await summaryResponse.json()
}

async function refreshAll() {
  await Promise.all([reload(), reloadBoard()])
}

onMounted(refreshAll)
</script>

<style scoped>
.board-section { margin-top: 24px; }
.board-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.board-columns h4 { margin: 8px 0; font-size: 14px; }
.reconcile-note { font-size: 12px; color: var(--muted); margin: 8px 0 0; }
.stat-value small { font-size: 12px; color: var(--muted); margin-left: 2px; }
</style>
