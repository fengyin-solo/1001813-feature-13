<template>
  <section class="page" data-module="cctv">
    <header class="page-head">
      <div>
        <h2>内窥检测管理</h2>
        <p class="page-desc">按检测管段查看检测报告：最近一次缺陷结论、检测长度与设备，历次检测按时间对比，等级上升管段重点盯防。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记检测报告</button>
        <button class="btn" type="button" @click="exportRows">导出内窥检测清单</button>
      </div>
    </header>

    <!-- 报告详情：从任意入口点开，看完返回来源视图 -->
    <article v-if="detail" class="detail-panel">
      <div class="detail-head">
        <button class="btn" type="button" @click="closeDetail">← 返回{{ detailReturnLabel }}</button>
        <span class="detail-status" :class="statusClass(detail.status)">{{ detail.status }}</span>
      </div>
      <h3 class="detail-title">{{ detail['检测编号'] }} 检测报告</h3>
      <div class="detail-grid">
        <div class="detail-item"><span>检测管段</span><strong>{{ detail['检测管段'] }}</strong></div>
        <div class="detail-item"><span>检测设备</span><strong>{{ detail['检测设备'] }}</strong></div>
        <div class="detail-item"><span>检测长度</span><strong>{{ formatLength(detail['检测长度']) }}</strong></div>
        <div class="detail-item"><span>检测人员</span><strong>{{ detail['检测人员'] ?? '—' }}</strong></div>
        <div class="detail-item"><span>检测日期</span><strong>{{ detail['检测日期'] ?? '—' }}</strong></div>
        <div class="detail-item"><span>缺陷指数</span><strong>{{ detail['缺陷指数'] ?? '尚未录入' }}</strong></div>
        <div class="detail-item">
          <span>缺陷等级</span>
          <strong>
            <span v-if="detail['当前等级']" class="grade-badge" :class="gradeClass(detail['当前等级数值'])">{{ detail['当前等级'] }}</span>
            <template v-else>待判定</template>
            <em v-if="detail['等级待重算']" class="recalc-tag">按{{ detail['判定口径名称'] }}实时重算</em>
          </strong>
        </div>
        <div class="detail-item"><span>判定口径</span><strong>{{ detail['判定口径名称'] ?? '—' }}</strong></div>
        <div class="detail-item"><span>结论时间</span><strong>{{ detail['结论时间'] ?? '—' }}</strong></div>
        <div class="detail-item">
          <span>留档状态</span>
          <strong>
            <span v-if="detail.status === '已出具'" class="archive-tag">结论已按当时口径留档</span>
            <span v-else-if="detail.status === '已退回'" class="return-tag">已退回重检·不计入最近结论</span>
            <span v-else>尚未出具结论</span>
          </strong>
        </div>
      </div>
      <div class="detail-actions">
        <button
          v-for="action in actionsFor(detail.status)"
          :key="action"
          class="btn"
          :class="{ primary: action === '确认出具' }"
          type="button"
          @click="runAction(action, detail)"
        >
          {{ action }}
        </button>
      </div>
      <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
    </article>

    <template v-else>
      <div class="stat-row">
        <article v-for="item in statCards" :key="item.label" class="stat-card" :class="item.cls">
          <span class="stat-label">{{ item.label }}</span>
          <strong class="stat-value">{{ item.value }}</strong>
        </article>
      </div>

      <nav class="tab-bar">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="tab-item"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
          <span v-if="tab.key === 'review'" class="tab-badge">{{ summary?.pendingReview ?? 0 }}</span>
        </button>

        <div class="version-switch">
          <span class="version-label">判定口径：</span>
          <button
            v-for="version in versions"
            :key="version.id"
            type="button"
            class="version-btn"
            :class="{ active: version.id === summary?.activeVersion }"
            @click="activateVersion(version)"
          >
            {{ version.name }}
          </button>
        </div>
      </nav>

      <p v-if="activeTab === 'segments'" class="rule-note">
        已出具的报告按出具时口径留档；口径调整后，尚未出结论的检测按「{{ summary?.activeVersionName }}」实时重算。已退回重检的报告不计入最近结论。
      </p>

      <!-- 管段分组报告 -->
      <div v-if="activeTab === 'segments'" class="segment-grid">
        <article
          v-for="segment in segments"
          :key="segment['管段']"
          class="segment-card"
          :class="{ rising: segment['等级上升'], uninspected: segment['状态'] !== 'concluded' }"
        >
          <header class="segment-head">
            <h3>{{ segment['管段'] }}</h3>
            <span v-if="segment['等级上升']" class="rising-badge">等级上升 ↑</span>
          </header>

          <template v-if="segment.latest">
            <div class="segment-latest">
              <div class="latest-grade">
                <span class="grade-badge lg" :class="gradeClass(segment.latest['等级数值'])">
                  {{ segment.latest['缺陷等级'] }}
                </span>
                <span v-if="segment.prevLevel" class="grade-compare">
                  上次 {{ gradeLabel(segment.prevLevel) }}
                  <em :class="segment['等级上升'] ? 'arrow-up' : 'arrow-flat'">
                    {{ segment['等级上升'] ? '↑' : '→' }}
                  </em>
                </span>
              </div>
              <dl class="latest-meta">
                <div><dt>最近检测</dt><dd>{{ segment.latest['检测日期'] }}</dd></div>
                <div><dt>检测长度</dt><dd>{{ formatLength(segment.latest['检测长度']) }}</dd></div>
                <div><dt>检测设备</dt><dd>{{ segment.latest['检测设备'] }}</dd></div>
              </dl>
            </div>

            <ol class="history-line">
              <li v-for="item in segment.history" :key="item.id" class="history-item">
                <button type="button" class="history-link" @click="openDetail(item.id, 'segments')">
                  <span class="history-date">{{ item['检测日期'] }}</span>
                  <span class="grade-badge sm" :class="gradeClass(item['等级数值'])">{{ item['缺陷等级'] }}</span>
                  <span v-if="item['已退回']" class="return-tag">退回重检</span>
                  <span v-else-if="!item['有效结论']" class="pending-tag">{{ item['状态'] }}·待结论</span>
                  <span v-else class="archive-hint">{{ item['口径名称'] }}留档</span>
                </button>
              </li>
            </ol>
          </template>

          <div v-else-if="segment['状态'] === 'no_conclusion'" class="segment-empty">
            已有 {{ segment['检测次数'] }} 次检测记录，均未形成有效结论（退回或待出具），暂无最近缺陷等级
          </div>
          <div v-else class="segment-empty">该管段尚未检测，可先安排一次内窥检测</div>
        </article>
      </div>

      <!-- 检测列表 -->
      <template v-else-if="activeTab === 'list'">
        <form class="filter-bar" @submit.prevent="reloadList">
          <label class="filter-item">
            <span>检测编号</span>
            <input v-model="filters.keyword" placeholder="按检测编号检索" />
          </label>
          <label class="filter-item">
            <span>检测状态</span>
            <select v-model="filters.status">
              <option value="">全部状态</option>
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
              <td>
                <button class="link" type="button" @click="openDetail(Number(row.id), 'list')">{{ row['检测编号'] }}</button>
              </td>
              <td>{{ row['检测管段'] }}</td>
              <td>{{ row['检测设备'] }}</td>
              <td>{{ formatLength(row['检测长度']) }}</td>
              <td>
                <span class="grade-badge sm" :class="gradeClass(gradeValue(row['缺陷等级']))">{{ row['缺陷等级'] }}</span>
                <em v-if="row['等级留档']" class="archive-hint">留档</em>
              </td>
              <td>{{ row['检测人员'] ?? '—' }}</td>
              <td>{{ row['检测日期'] ?? '—' }}</td>
              <td><span class="status-pill" :class="statusClass(row.status)">{{ row.status }}</span></td>
              <td class="row-actions">
                <button
                  v-for="action in actionsFor(row.status)"
                  :key="action"
                  class="link"
                  type="button"
                  @click="runAction(action, row)"
                >
                  {{ action }}
                </button>
              </td>
            </tr>
            <tr v-if="!rows.length">
              <td :colspan="columns.length + 1" class="empty-state">暂无符合条件的检测记录</td>
            </tr>
          </tbody>
        </table>
      </template>

      <!-- 待复核清单 -->
      <template v-else>
        <p class="rule-note">退回重检的报告自动落到待复核清单，条数随确认出具、再次退回等操作实时重算：当前 <strong>{{ summary?.pendingReview ?? 0 }}</strong> 条。</p>
        <table class="data-table">
          <thead>
            <tr>
              <th>检测编号</th><th>检测管段</th><th>检测设备</th><th>检测长度</th>
              <th>缺陷指数</th><th>检测人员</th><th>检测日期</th><th>状态</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in reviewRows" :key="String(row.id)">
              <td><button class="link" type="button" @click="openDetail(Number(row.id), 'review')">{{ row['检测编号'] }}</button></td>
              <td>{{ row['检测管段'] }}</td>
              <td>{{ row['检测设备'] }}</td>
              <td>{{ formatLength(row['检测长度']) }}</td>
              <td>{{ row['缺陷指数'] ?? '—' }}</td>
              <td>{{ row['检测人员'] ?? '—' }}</td>
              <td>{{ row['检测日期'] ?? '—' }}</td>
              <td><span class="status-pill returned">已退回</span></td>
              <td class="row-actions">
                <button class="link" type="button" @click="runAction('安排检测', row)">安排重检</button>
              </td>
            </tr>
            <tr v-if="!reviewRows.length">
              <td colspan="9" class="empty-state">没有退回重检的报告，待复核清单为空</td>
            </tr>
          </tbody>
        </table>
      </template>

      <footer class="page-foot">
        <span v-if="activeTab === 'list'">共 {{ listTotal }} 条内窥检测记录</span>
        <span v-else-if="activeTab === 'review'">共 {{ reviewRows.length }} 条待复核记录</span>
        <span v-else>共 {{ segments.length }} 个检测管段，已检测 {{ summary?.inspectedSegments ?? 0 }} 个</span>
        <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      </footer>
    </template>

    <!-- 登记弹窗 -->
    <div v-if="createOpen" class="modal-mask" @click.self="createOpen = false">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记检测报告</h3>
        <label v-for="field in createFields" :key="field.key" class="modal-item">
          <span>{{ field.label }}<i v-if="field.required">*</i></span>
          <input v-model="createForm[field.key]" :type="field.type ?? 'text'" :placeholder="field.placeholder" />
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="createOpen = false">取消</button>
          <button class="btn primary" type="submit">保存登记</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

const ENDPOINT = '/api/cctv'

type Row = Record<string, string | number | null>

interface Summary {
  total: number
  statusCounts: Record<string, number>
  pendingReview: number
  segmentTotal: number
  inspectedSegments: number
  level4Segments: number
  risingSegments: number
  recalculating: number
  monthLength: number
  activeVersion: string
  activeVersionName: string
}

interface GradeVersion {
  id: string
  name: string
  thresholds: number[]
}

interface HistoryItem {
  id: number
  检测编号: string
  检测日期: string | null
  检测设备: string | null
  检测长度: number | string | null
  检测人员: string | null
  缺陷指数: number | null
  状态: string
  有效结论: boolean
  已退回: boolean
  等级留档: boolean
  等级数值: number | null
  缺陷等级: string
  口径名称: string | null
  结论时间: string | null
}

interface Segment {
  管段: string
  状态: 'concluded' | 'uninspected' | 'no_conclusion'
  latest: HistoryItem | null
  prevLevel: number | null
  等级上升: boolean
  检测次数: number
  history: HistoryItem[]
}

type TabKey = 'segments' | 'list' | 'review'

const columns = ['检测编号', '检测管段', '检测设备', '检测长度', '缺陷等级', '检测人员', '检测日期', '检测状态']
const statuses = ['待检测', '检测中', '已出具', '已退回']
const tabs: { key: TabKey; label: string }[] = [
  { key: 'segments', label: '管段报告' },
  { key: 'list', label: '检测列表' },
  { key: 'review', label: '待复核清单' },
]

const activeTab = ref<TabKey>('segments')
const rows = ref<Row[]>([])
const listTotal = ref(0)
const reviewRows = ref<Row[]>([])
const segments = ref<Segment[]>([])
const summary = ref<Summary | null>(null)
const versions = ref<GradeVersion[]>([])
const errorMessage = ref('')
const filters = ref<{ keyword: string; status: string }>({ keyword: '', status: '' })

const detail = ref<Row | null>(null)
const detailReturnTab = ref<TabKey>('segments')
const detailReturnLabel = computed(() => tabs.find((tab) => tab.key === detailReturnTab.value)?.label ?? '管段报告')

const createOpen = ref(false)
const createError = ref('')
const createFields = [
  { key: '检测编号', label: '检测编号', required: true },
  { key: '检测管段', label: '检测管段', required: true, placeholder: '如 PIPE-0004' },
  { key: '检测设备', label: '检测设备', required: true, placeholder: '如 爬行机器人CCTV-A02' },
  { key: '检测长度', label: '检测长度（米）', type: 'number' },
  { key: '检测人员', label: '检测人员' },
  { key: '检测日期', label: '检测日期', type: 'date' },
  { key: '缺陷指数', label: '缺陷指数', type: 'number', placeholder: '出具前可补录' },
]
const emptyCreateForm = (): Record<string, string> => ({
  检测编号: '',
  检测管段: '',
  检测设备: '',
  检测长度: '',
  检测人员: '',
  检测日期: '',
  缺陷指数: '',
})
const createForm = ref<Record<string, string>>(emptyCreateForm())

const statCards = computed(() => [
  { label: '检测报告总数', value: summary.value?.total ?? 0, cls: '' },
  { label: '已检测管段', value: `${summary.value?.inspectedSegments ?? 0}/${summary.value?.segmentTotal ?? 0}`, cls: '' },
  { label: '等级上升管段', value: summary.value?.risingSegments ?? 0, cls: (summary.value?.risingSegments ?? 0) > 0 ? 'stat-warn' : '' },
  { label: '四级缺陷段', value: summary.value?.level4Segments ?? 0, cls: (summary.value?.level4Segments ?? 0) > 0 ? 'stat-danger' : '' },
  { label: '待复核报告', value: summary.value?.pendingReview ?? 0, cls: (summary.value?.pendingReview ?? 0) > 0 ? 'stat-warn' : '' },
  { label: '本月检测长度（米）', value: formatNumber(summary.value?.monthLength), cls: '' },
])

function gradeValue(label: string | number | null | undefined): number | null {
  if (typeof label === 'number') return label
  const map: Record<string, number> = { 一级: 1, 二级: 2, 三级: 3, 四级: 4 }
  return map[String(label ?? '')] ?? null
}

function gradeLabel(level: number | null): string {
  return ['', '一级', '二级', '三级', '四级'][level ?? 0] ?? '—'
}

function gradeClass(level: number | string | null | undefined): string {
  return ['', 'grade-1', 'grade-2', 'grade-3', 'grade-4'][Number(level) ?? 0] ?? ''
}

function statusClass(status: string | number | null | undefined): string {
  return {
    待检测: 'st-pending',
    检测中: 'st-running',
    已出具: 'st-done',
    已退回: 'st-return',
  }[String(status ?? '')] ?? ''
}

function actionsFor(status: string | number | null | undefined): string[] {
  switch (String(status ?? '')) {
    case '待检测': return ['安排检测']
    case '检测中': return ['确认出具', '退回重检']
    case '已出具': return ['退回重检']
    case '已退回': return ['安排检测']
    default: return []
  }
}

function formatLength(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  return `${formatNumber(value)} 米`
}

function formatNumber(value: string | number | null | undefined): string {
  const num = Number(value)
  if (Number.isNaN(num)) return String(value ?? '—')
  return String(Math.round(num * 10) / 10)
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reloadList()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function getJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) throw new Error(`接口返回 ${response.status}`)
  return (await response.json()) as T
}

async function reloadSummary() {
  const [summaryPayload, segmentPayload, reviewPayload, versionPayload] = await Promise.all([
    getJson<Summary>(`${ENDPOINT}/summary`),
    getJson<{ segments: Segment[] }>(`${ENDPOINT}/segments`),
    getJson<{ items: Row[] }>(`${ENDPOINT}/review-queue`),
    getJson<{ versions: GradeVersion[] }>(`${ENDPOINT}/grade-versions`),
  ])
  summary.value = summaryPayload
  segments.value = segmentPayload.segments
  reviewRows.value = reviewPayload.items
  versions.value = versionPayload.versions
}

async function reloadList() {
  const params = new URLSearchParams()
  if (filters.value.keyword) params.set('keyword', filters.value.keyword)
  if (filters.value.status) params.set('status', filters.value.status)
  const payload = await getJson<{ items: Row[]; total: number }>(`${ENDPOINT}?${params.toString()}`)
  rows.value = payload.items ?? []
  listTotal.value = payload.total ?? rows.value.length
}

async function reloadAll() {
  errorMessage.value = ''
  try {
    await Promise.all([reloadSummary(), reloadList()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '内窥检测数据读取失败'
  }
}

async function openDetail(id: number, returnTab: TabKey = 'segments') {
  errorMessage.value = ''
  try {
    detailReturnTab.value = returnTab
    detail.value = await getJson<Row>(`${ENDPOINT}/${id}`)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测报告读取失败'
  }
}

function closeDetail() {
  detail.value = null
  void reloadAll()
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '内窥检测动作未生效，请稍后重试')
    }
    await reloadAll()
    if (detail.value && Number(detail.value.id) === Number(row.id)) {
      detail.value = await getJson<Row>(`${ENDPOINT}/${row.id}`)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '内窥检测操作失败'
  }
}

async function activateVersion(version: GradeVersion) {
  if (summary.value?.activeVersion === version.id) return
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/grade-versions/activate`, {
      method: 'POST',
      body: JSON.stringify({ version: version.id }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    if (!response.ok || !payload.ok) throw new Error(payload.message || '口径切换失败')
    await reloadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '判定口径切换失败'
  }
}

function openCreate() {
  createForm.value = emptyCreateForm()
  createError.value = ''
  createOpen.value = true
}

async function submitCreate() {
  createError.value = ''
  const values: Record<string, string> = {}
  for (const field of createFields) {
    const value = createForm.value[field.key]?.trim()
    if (value) values[field.key] = value
  }
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = (await response.json()) as { ok: boolean; message: string }
    if (!response.ok || !payload.ok) throw new Error(payload.message || '登记失败')
    createOpen.value = false
    await reloadAll()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '检测报告登记失败'
  }
}

onMounted(reloadAll)
</script>
