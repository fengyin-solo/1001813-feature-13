<template>
  <section class="page cctv-page" data-module="cctv">
    <header class="page-head">
      <div>
        <h2>内窥检测管理</h2>
        <p class="page-desc">按管段查看检测报告：最近一次结论、历次检测前后对比；退回重检的报告进入待复核清单。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记检测报告</button>
        <button class="btn" type="button" @click="exportRows">导出内窥检测清单</button>
      </div>
    </header>

    <!-- 单次检测报告详情：从管段分组或列表点入，可返回分组视图 -->
    <article v-if="detail" class="report-detail">
      <div class="detail-head">
        <button class="btn ghost" type="button" @click="closeDetail">← 返回管段报告</button>
        <span class="detail-code">{{ detail['检测编号'] }}</span>
        <span class="status-tag" :class="statusClass(detail.status)">{{ detail.status }}</span>
        <span v-if="detail['等级已锁定']" class="archive-tag">按 {{ detail['判定口径'] }} 留档</span>
      </div>
      <h3 class="detail-title">{{ detail['检测管段'] }} 检测报告</h3>
      <dl class="detail-grid">
        <div v-for="field in detailFields" :key="field" class="detail-cell">
          <dt>{{ field }}</dt>
          <dd>{{ detail[field] ?? '—' }}</dd>
        </div>
      </dl>
      <p v-if="detail['等级已锁定']" class="detail-note">
        该报告已出具结论，缺陷等级按出具时的「{{ detail['判定口径'] }}」判定口径锁定留档，口径调整不改变本结论。
      </p>
      <p v-else-if="detail.status !== '已退回'" class="detail-note">
        该报告尚未出具结论，缺陷等级随当前生效口径「{{ detail['判定口径'] }}」实时重算。
      </p>
      <p v-else class="detail-note warn">该报告已退回重检，原结论作废，不计入管段最近结论。</p>
      <div class="detail-actions">
        <button
          v-for="action in availableActions(detail)"
          :key="action"
          class="btn"
          type="button"
          @click="runAction(action, detail)"
        >
          {{ action }}
        </button>
      </div>
    </article>

    <template v-else>
      <div class="tab-bar" role="tablist">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="tab-item"
          :class="{ active: activeTab === tab.key }"
          type="button"
          role="tab"
          @click="switchTab(tab.key)"
        >
          {{ tab.label }}
          <span v-if="tab.key === 'review' && grouped" class="tab-badge">{{ grouped.summary['待复核条数'] }}</span>
        </button>
      </div>

      <!-- 管段分组检测报告 -->
      <div v-if="activeTab === 'grouped'">
        <div class="stat-row">
          <article v-for="item in groupStats" :key="item.label" class="stat-card">
            <span class="stat-label">{{ item.label }}</span>
            <strong class="stat-value" :class="{ warn: item.warn }">{{ item.value }}</strong>
          </article>
        </div>

        <div class="grading-bar">
          <span class="grading-label">缺陷等级判定口径：</span>
          <select v-model="gradingVersion" class="grading-select" @change="switchGrading">
            <option v-for="v in gradingVersions" :key="v" :value="v">{{ v }}</option>
          </select>
          <span class="grading-hint">当前生效 {{ grouped?.grading.current }}；未出结论的检测按当前口径重算，已出具的按当时版本留档。</span>
        </div>

        <div v-if="grouped" class="segment-list">
          <article
            v-for="group in grouped.groups"
            :key="group['管段编号']"
            class="segment-card"
            :class="{ raised: group['等级上升'], untested: group['尚未检测'] }"
          >
            <header class="segment-head">
              <h3 class="segment-name">
                {{ group['管段编号'] }}
                <span v-if="group['等级上升']" class="rise-tag">等级上升 ⬆</span>
              </h3>
              <span class="segment-meta">共 {{ group['检测次数'] }} 次检测</span>
            </header>

            <div v-if="group['尚未检测']" class="untested-tip">该管段尚未检测</div>

            <template v-else>
              <section v-if="group['最近结论']" class="latest-conclusion">
                <span class="conclusion-label">最近一次检测</span>
                <div class="conclusion-body">
                  <span class="grade-badge" :class="gradeClass(group['最近结论']['缺陷等级'])">
                    {{ group['最近结论']['缺陷等级'] }}
                  </span>
                  <span class="conclusion-meta">
                    {{ group['最近结论']['检测日期'] }} · {{ group['最近结论']['检测编号'] }}
                  </span>
                  <span class="conclusion-meta">检测长度 {{ group['最近结论']['检测长度'] }} m</span>
                  <span class="conclusion-meta">设备 {{ group['最近结论']['检测设备'] }}</span>
                  <span v-if="group['进行中数量']" class="pending-chip">另有 {{ group['进行中数量'] }} 次检测待出具</span>
                </div>
              </section>
              <section v-else class="latest-conclusion no-conclusion">
                <span class="conclusion-label">最近一次检测</span>
                <span class="no-conclusion-text">暂无有效结论（报告待出具或已退回重检）</span>
              </section>

              <section class="history-block">
                <h4 class="history-title">历次检测对比</h4>
                <ol class="history-list">
                  <li
                    v-for="(item, index) in group['历史检测']"
                    :key="String(item.id)"
                    class="history-item"
                    :class="historyTrendClass(group['历史检测'], index)"
                  >
                    <button class="history-link" type="button" @click="openReport(Number(item.id))">
                      <span class="history-date">{{ item['检测日期'] }}</span>
                      <span class="grade-badge sm" :class="gradeClass(item['缺陷等级'])">{{ item['缺陷等级'] }}</span>
                      <span class="history-device">{{ item['检测设备'] }} · {{ item['检测长度'] ?? '—' }} m</span>
                      <span v-if="historyTrend(group['历史检测'], index) === 'up'" class="trend up">⬆ 上升</span>
                      <span v-else-if="historyTrend(group['历史检测'], index) === 'down'" class="trend down">⬇ 下降</span>
                      <span class="history-status" :class="statusClass(item.status)">{{ item.status }}</span>
                    </button>
                  </li>
                </ol>
              </section>
            </template>
          </article>
        </div>
      </div>

      <!-- 平铺检测列表（原视图） -->
      <div v-else-if="activeTab === 'list'">
        <div class="stat-row">
          <article v-for="item in listStats" :key="item.label" class="stat-card">
            <span class="stat-label">{{ item.label }}</span>
            <strong class="stat-value" :class="{ warn: item.warn }">{{ item.value }}</strong>
          </article>
        </div>

        <form class="filter-bar" @submit.prevent="reloadList">
          <label class="filter-item">
            <span>检测编号</span>
            <input v-model="filters.keyword" placeholder="按检测编号检索" />
          </label>
          <label class="filter-item">
            <span>检测状态</span>
            <select v-model="filters.status">
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
              <th v-for="column in columns" :key="column">{{ column }}</th>
              <th>判定口径</th>
              <th>可执行动作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="String(row.id)">
              <td v-for="column in columns" :key="column">
                <button v-if="column === '检测编号'" class="link" type="button" @click="openReport(Number(row.id))">
                  {{ row[column] ?? '—' }}
                </button>
                <template v-else>
                  <span v-if="column === '缺陷等级'" class="grade-badge sm" :class="gradeClass(String(row[column]))">{{ row[column] ?? '—' }}</span>
                  <template v-else>{{ row[column] ?? '—' }}</template>
                </template>
              </td>
              <td>
                {{ row['判定口径'] ?? '—' }}
                <span v-if="row['等级已锁定']" class="lock-hint">留档</span>
              </td>
              <td class="row-actions">
                <button
                  v-for="action in availableActions(row)"
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
              <td :colspan="columns.length + 2" class="empty-state">暂无符合条件的内窥检测数据</td>
            </tr>
          </tbody>
        </table>

        <footer class="page-foot">
          <span>共 {{ total }} 条内窥检测记录</span>
          <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
        </footer>
      </div>

      <!-- 待复核清单（退回重检） -->
      <div v-else-if="activeTab === 'review'">
        <div class="stat-row">
          <article class="stat-card">
            <span class="stat-label">待复核条数</span>
            <strong class="stat-value warn">{{ reviewTotal }}</strong>
          </article>
          <article class="stat-card">
            <span class="stat-label">说明</span>
            <span class="stat-note">退回重检的报告不计入管段最近结论，完成重检并重新出具后自动移出本清单。</span>
          </article>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>检测编号</th><th>检测管段</th><th>检测设备</th><th>检测长度</th>
              <th>检测人员</th><th>检测日期</th><th>当前等级（按{{ grouped?.grading.current }}重算）</th><th>可执行动作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in reviewRows" :key="String(row.id)">
              <td><button class="link" type="button" @click="openReport(Number(row.id))">{{ row['检测编号'] }}</button></td>
              <td>{{ row['检测管段'] }}</td>
              <td>{{ row['检测设备'] }}</td>
              <td>{{ row['检测长度'] ?? '—' }}</td>
              <td>{{ row['检测人员'] }}</td>
              <td>{{ row['检测日期'] }}</td>
              <td><span class="grade-badge sm" :class="gradeClass(row['缺陷等级'])">{{ row['缺陷等级'] }}</span></td>
              <td class="row-actions">
                <button
                  v-for="action in availableActions(row)"
                  :key="action"
                  class="link"
                  type="button"
                  @click="runAction(action, row)"
                >
                  {{ action }}
                </button>
              </td>
            </tr>
            <tr v-if="!reviewRows.length">
              <td colspan="8" class="empty-state">暂无退回重检的报告，待复核清单为空</td>
            </tr>
          </tbody>
        </table>
        <footer class="page-foot">
          <span>共 {{ reviewTotal }} 条待复核记录</span>
          <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
        </footer>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

interface Conclusion {
  检测编号: string
  检测日期: string
  缺陷等级: string
  检测长度: number | string
  检测设备: string
  检测人员: string
  判定口径: string
}

interface SegmentGroup {
  id?: number
  管段编号: string
  检测次数: number
  尚未检测: boolean
  最近结论: Conclusion | null
  上次结论: Pick<Conclusion, '检测编号' | '检测日期' | '缺陷等级'> | null
  等级上升: boolean
  进行中数量: number
  待复核数量: number
  最新检测日期: string | null
  历史检测: Row[]
}

interface GroupedReport {
  summary: Record<string, number | string>
  groups: SegmentGroup[]
  grading: { current: string; versions: { version: string; thresholds: [number, string][] }[] }
}

const ENDPOINT = '/api/cctv'
const columns = ["检测编号", "检测管段", "检测设备", "检测长度", "缺陷等级", "检测人员", "检测日期", "检测状态"]
const detailFields = ["检测编号", "检测管段", "检测设备", "检测长度", "缺陷指数", "缺陷等级", "检测人员", "检测日期", "检测状态"]
const statuses = ["待检测", "检测中", "已出具", "已退回"]
const tabs = [
  { key: 'grouped', label: '管段报告' },
  { key: 'list', label: '检测列表' },
  { key: 'review', label: '待复核清单' },
] as const

type TabKey = (typeof tabs)[number]['key']

const activeTab = ref<TabKey>('grouped')
const grouped = ref<GroupedReport | null>(null)
const rows = ref<Row[]>([])
const total = ref(0)
const reviewRows = ref<Row[]>([])
const reviewTotal = ref(0)
const detail = ref<Row | null>(null)
const loading = ref(false)
const errorMessage = ref('')
const filters = ref<{ keyword: string; status: string }>({ keyword: '', status: '' })
const gradingVersion = ref('')
const gradingVersions = ref<string[]>([])

const groupStats = computed(() => {
  const s = grouped.value?.summary
  return [
    { label: '管段总数', value: Number(s?.['管段总数'] ?? 0) },
    { label: '已检测管段', value: Number(s?.['已检测管段'] ?? 0) },
    { label: '尚未检测管段', value: Number(s?.['尚未检测管段'] ?? 0) },
    { label: '等级上升管段', value: Number(s?.['等级上升管段'] ?? 0), warn: true },
    { label: '检测报告总数', value: Number(s?.['检测报告总数'] ?? 0) },
    { label: '待出具检测', value: Number(s?.['待出具检测'] ?? 0) },
    { label: '待复核条数', value: Number(s?.['待复核条数'] ?? 0), warn: true },
  ]
})

const listStats = computed(() => [
  { label: '检测报告总数', value: Number(grouped.value?.summary['检测报告总数'] ?? 0) },
  { label: '待出具检测', value: Number(grouped.value?.summary['待出具检测'] ?? 0) },
  { label: '退回待复核', value: reviewTotal.value, warn: reviewTotal.value > 0 },
  { label: '等级上升管段', value: Number(grouped.value?.summary['等级上升管段'] ?? 0), warn: true },
])

function gradeClass(grade: unknown): string {
  return {
    四级: 'grade-4',
    三级: 'grade-3',
    二级: 'grade-2',
    一级: 'grade-1',
  }[String(grade)] ?? 'grade-none'
}

function statusClass(status: unknown): string {
  return {
    待检测: 'status-pending',
    检测中: 'status-running',
    已出具: 'status-done',
    已退回: 'status-returned',
  }[String(status)] ?? ''
}

function availableActions(row: Row): string[] {
  switch (row.status) {
    case '待检测':
    case '已退回':
      return ['安排检测']
    case '检测中':
      return ['确认出具']
    case '已出具':
      return ['退回重检']
    default:
      return []
  }
}

function historyTrend(history: Row[], index: number): 'up' | 'down' | null {
  const current = history[index]
  if (current.status !== '已出具') return null
  for (let i = index - 1; i >= 0; i -= 1) {
    const prev = history[i]
    if (prev.status !== '已出具') continue
    const ranks: Record<string, number> = { 一级: 1, 二级: 2, 三级: 3, 四级: 4 }
    const cur = ranks[String(current['缺陷等级'])] ?? 0
    const old = ranks[String(prev['缺陷等级'])] ?? 0
    if (cur > old) return 'up'
    if (cur < old) return 'down'
    return null
  }
  return null
}

function historyTrendClass(history: Row[], index: number): string {
  const trend = historyTrend(history, index)
  return trend === 'up' ? 'is-up' : trend === 'down' ? 'is-down' : ''
}

async function loadGrouped() {
  const payload = await request(`${ENDPOINT}/grouped`).then((res) => {
    if (!res.ok) throw new Error('管段检测报告读取失败')
    return res.json() as Promise<GroupedReport>
  })
  grouped.value = payload
  gradingVersion.value = payload.grading.current
  gradingVersions.value = payload.grading.versions.map((v) => v.version)
}

async function loadList() {
  const params = new URLSearchParams()
  if (filters.value.keyword) params.set('keyword', filters.value.keyword)
  if (filters.value.status) params.set('status', filters.value.status)
  const response = await request(`${ENDPOINT}?${params.toString()}`)
  if (!response.ok) throw new Error('检测报告列表读取失败')
  const payload = await response.json()
  rows.value = payload.items ?? []
  total.value = payload.total ?? rows.value.length
}

async function loadReview() {
  const response = await request(`${ENDPOINT}/review`)
  if (!response.ok) throw new Error('待复核清单读取失败')
  const payload = await response.json()
  reviewRows.value = payload.items ?? []
  reviewTotal.value = payload.total ?? reviewRows.value.length
}

async function refreshActive() {
  loading.value = true
  errorMessage.value = ''
  try {
    await loadGrouped()
    if (activeTab.value === 'list') await loadList()
    if (activeTab.value === 'review') await loadReview()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '内窥检测数据读取失败'
  } finally {
    loading.value = false
  }
}

function switchTab(tab: TabKey) {
  activeTab.value = tab
  void refreshActive()
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void loadList().catch((error) => {
    errorMessage.value = error instanceof Error ? error.message : '检测报告列表读取失败'
  })
}

function reloadList() {
  errorMessage.value = ''
  void loadList().catch((error) => {
    errorMessage.value = error instanceof Error ? error.message : '检测报告列表读取失败'
  })
}

async function openReport(id: number) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${id}`)
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new Error(payload?.detail ?? '检测报告读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测报告读取失败'
  }
}

function closeDetail() {
  detail.value = null
  void refreshActive()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '检测报告登记入口尚未接入审批流'
}

async function switchGrading() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/grading/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { version: gradingVersion.value } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload?.message ?? '判定口径切换失败')
    }
    await refreshActive()
    if (detail.value) await openReport(Number(detail.value.id))
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '判定口径切换失败'
    await loadGrouped().catch(() => undefined)
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload?.message ?? '内窥检测动作未生效')
    }
    if (detail.value && Number(detail.value.id) === Number(row.id)) {
      detail.value = (payload.entry as Row) ?? detail.value
    }
    await refreshActive()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '内窥检测操作失败'
  }
}

onMounted(refreshActive)
</script>

<style scoped>
.cctv-page .tab-bar { display: flex; gap: 4px; margin-bottom: 12px; border-bottom: 1px solid var(--border); }
.tab-item { border: none; background: none; padding: 8px 16px; cursor: pointer; font-size: 14px; color: var(--muted); border-bottom: 2px solid transparent; }
.tab-item.active { color: var(--brand); border-bottom-color: var(--brand); font-weight: 600; }
.tab-badge { display: inline-block; margin-left: 4px; min-width: 18px; padding: 0 5px; border-radius: 9px; background: #b42318; color: #fff; font-size: 11px; line-height: 18px; text-align: center; }

.grading-bar { display: flex; align-items: center; gap: 8px; background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; margin-bottom: 12px; font-size: 13px; }
.grading-label { color: var(--muted); }
.grading-select { padding: 4px 8px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; }
.grading-hint { color: var(--muted); font-size: 12px; }

.segment-list { display: flex; flex-direction: column; gap: 12px; }
.segment-card { background: #fff; border: 1px solid var(--border); border-left: 4px solid var(--border); border-radius: 8px; padding: 12px 14px; }
.segment-card.raised { border-left-color: #d92d20; background: #fff8f7; }
.segment-card.untested { opacity: 0.85; }
.segment-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.segment-name { margin: 0; font-size: 15px; display: flex; align-items: center; gap: 8px; }
.rise-tag { font-size: 12px; color: #fff; background: #d92d20; border-radius: 4px; padding: 2px 8px; }
.segment-meta { color: var(--muted); font-size: 12px; }

.untested-tip { color: var(--muted); font-size: 13px; padding: 8px 0; }
.latest-conclusion { margin-bottom: 10px; }
.conclusion-label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.conclusion-body { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; font-size: 13px; }
.conclusion-meta { color: #334155; }
.pending-chip { font-size: 12px; color: #b54708; background: #fef3c7; border-radius: 4px; padding: 1px 8px; }
.no-conclusion-text { color: var(--muted); font-size: 13px; }

.history-title { font-size: 13px; margin: 6px 0; color: #334155; }
.history-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.history-item.is-up { background: #fee4e2; border-radius: 6px; }
.history-link { display: flex; align-items: center; gap: 10px; width: 100%; border: none; background: none; padding: 6px 8px; cursor: pointer; font-size: 13px; text-align: left; border-radius: 6px; }
.history-link:hover { background: #eef4ff; }
.history-date { min-width: 92px; color: #1f2937; }
.history-device { color: var(--muted); flex: 1; }
.trend { font-size: 12px; padding: 1px 6px; border-radius: 4px; }
.trend.up { color: #b42318; background: #fee4e2; }
.trend.down { color: #067647; background: #dcfae6; }
.history-status { font-size: 12px; color: var(--muted); }

.grade-badge { display: inline-block; min-width: 44px; text-align: center; border-radius: 4px; padding: 2px 8px; font-weight: 600; font-size: 13px; }
.grade-badge.sm { min-width: 36px; font-size: 12px; padding: 1px 6px; }
.grade-1 { background: #dcfae6; color: #067647; }
.grade-2 { background: #fef3c7; color: #b54708; }
.grade-3 { background: #ffedd5; color: #c2410c; }
.grade-4 { background: #fee4e2; color: #b42318; }
.grade-none { background: #f1f5f9; color: var(--muted); }

.status-tag, .history-status { font-size: 12px; border-radius: 4px; padding: 1px 8px; }
.status-pending { background: #f1f5f9; color: var(--muted); }
.status-running { background: #e0edff; color: #1f6feb; }
.status-done { background: #dcfae6; color: #067647; }
.status-returned { background: #fee4e2; color: #b42318; }

.report-detail { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
.detail-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.detail-code { font-weight: 600; font-size: 14px; }
.archive-tag { font-size: 12px; color: #6941c6; background: #f4ebff; border-radius: 4px; padding: 2px 8px; }
.detail-title { margin: 0 0 12px; font-size: 17px; }
.detail-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 0 0 12px; }
.detail-cell { border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; }
.detail-cell dt { font-size: 12px; color: var(--muted); }
.detail-cell dd { margin: 2px 0 0; font-size: 14px; }
.detail-note { font-size: 12px; color: var(--muted); margin: 0 0 12px; }
.detail-note.warn { color: #b42318; }
.detail-actions { display: flex; gap: 8px; }
.lock-hint { font-size: 11px; color: #6941c6; margin-left: 4px; }
.stat-note { font-size: 12px; color: var(--muted); }
</style>
