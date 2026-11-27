<script setup lang="ts">
import { computed, ref } from 'vue'
import { onBackPress, onHide, onLoad, onReachBottom, onShow } from '@dcloudio/uni-app'
import { api, go, localTime, message, productName, type Company, type DocSummary, type Product, type Supplier } from '@/api/client'
import AppShell from '@/components/AppShell.vue'
import ExcelExportButton from '@/components/ExcelExportButton.vue'
import ContinuousScanner from '@/components/ContinuousScanner.vue'

type FilterOption = {id:number; label:string}
type FilterOptions = {
  products: Pick<Product,'id'|'brand'|'name'|'specification'>[]
  suppliers: Pick<Supplier,'id'|'name'>[]
  companies: Pick<Company,'id'|'name'>[]
}

const returnMode = ref(false)
const outboundOnly = ref(false)
const items = ref<DocSummary[]>([])
const total = ref(0)
const exportableTotal = ref(0)
const loading = ref(false)
const loadError = ref('')
const productOptions = ref<FilterOption[]>([{id:0,label:'全部物资'}])
const supplierOptions = ref<FilterOption[]>([{id:0,label:'全部供应商'}])
const companyOptions = ref<FilterOption[]>([{id:0,label:'全部公司'}])
const companyId = ref(0)
const startDate = ref('')
const endDate = ref('')
const boxScannerOpen = ref(false)
const boxCode = ref('')
const productId = ref(0)
const supplierId = ref(0)
const loadingOptions = ref(false)
const optionsError = ref('')
const productIndex = computed(() => Math.max(0, productOptions.value.findIndex(option=>option.id===productId.value)))
const supplierIndex = computed(() => Math.max(0, supplierOptions.value.findIndex(option=>option.id===supplierId.value)))
const beijingOffsetMinutes = 8 * 60
const companyIndex = computed(() => Math.max(0, companyOptions.value.findIndex(option=>option.id===companyId.value)))
const hasFilters = computed(() => Boolean(productId.value || supplierId.value || companyId.value ||
  startDate.value || endDate.value || boxCode.value))
const filterParams = computed(() => {
  const params = []
  if (outboundOnly.value) params.push('direction=OUT')
  if (productId.value) params.push(`product_id=${productId.value}`)
  if (supplierId.value) params.push(`supplier_id=${supplierId.value}`)
  if (companyId.value) params.push(`recipient_company_id=${companyId.value}`)
  if (startDate.value) params.push(`created_from=${encodeURIComponent(startDate.value + 'T00:00:00+08:00')}`)
  if (endDate.value) {
    const nextDay = new Date(endDate.value + 'T00:00:00Z')
    nextDay.setUTCDate(nextDay.getUTCDate() + 1)
    params.push(`created_before=${encodeURIComponent(nextDay.toISOString().slice(0, 10) + 'T00:00:00+08:00')}`)
  }
  if (boxCode.value) params.push(`box_code=${encodeURIComponent(boxCode.value)}`)
  return params
})
const scopedFilters = computed(() => Boolean(companyId.value || startDate.value || endDate.value || boxCode.value))
const exportPath = computed(() => '/documents/export.xlsx' + (hasFilters.value || outboundOnly.value ? '?' + filterParams.value.join('&') : ''))
let generation = 0

async function loadOptions() {
  if (loadingOptions.value) return
  loadingOptions.value = true
  optionsError.value = ''
  try {
    const scope = outboundOnly.value ? '?outbound_only=true' : ''
    const data = await api<FilterOptions>(`/documents/filter-options${scope}`)
    productOptions.value = [{id:0,label:'全部物资'}, ...data.products.map(p=>({id:p.id,label:productName(p)}))]
    supplierOptions.value = [{id:0,label:'全部供应商'}, ...data.suppliers.map(s=>({id:s.id,label:s.name}))]
    companyOptions.value = [{id:0,label:'全部公司'}, ...(data.companies ?? []).map(c=>({id:c.id,label:c.name}))]
  } catch (error) {
    optionsError.value = message(error)
  } finally {
    loadingOptions.value = false
  }
}

async function load(reset=false) {
  if ((loading.value && !reset) || (!reset && items.value.length >= total.value)) return
  if (reset) {generation++;items.value=[];total.value=0;exportableTotal.value=0}
  const currentGeneration=generation
  loading.value = true
  loadError.value=''
  try {
    const params = ['limit=20', `offset=${reset?0:items.value.length}`, ...filterParams.value]
    if (outboundOnly.value) params.push('kind=NORMAL')

    const data = await api<{items:DocSummary[];total:number;exportable_total?:number}>(`/documents?${params.join('&')}`)
    if (currentGeneration!==generation) return
    if (data.exportable_total === undefined && scopedFilters.value) {
      throw new Error('后端版本尚未支持当前筛选，请更新后重试')
    }
    items.value = reset ? data.items : [...items.value,...data.items]
    total.value = data.total
    exportableTotal.value = data.exportable_total ?? data.total
  } catch (error) { if (currentGeneration===generation) loadError.value=message(error) }
  finally { if (currentGeneration===generation) loading.value = false }
}
function chooseFilter(field:'product'|'supplier'|'company', event:{detail:{value:unknown}}) {
  const options = {product:productOptions, supplier:supplierOptions, company:companyOptions}[field].value
  const id = {product:productId, supplier:supplierId, company:companyId}[field]
  const option = options[Number(event.detail.value)]
  if (!option || option.id===id.value) return
  id.value = option.id
  load(true)
}

function chooseDate(field:'start'|'end', event:{detail:{value:string}}) {
  const selected = field==='start' ? startDate : endDate
  const value = event.detail.value
  const from = field==='start' ? value : startDate.value
  const to = field==='end' ? value : endDate.value
  if (from && to && from > to) {
    uni.showToast({title:'开始日期不能晚于结束日期',icon:'none'})
    return
  }
  if (selected.value === value) return
  selected.value = value
  load(true)
}

async function searchBox(rawCode:string) {
  const code = rawCode.trim()
  if (!code || code.length > 2048) throw new Error('箱码无效，请重新扫描')
  boxScannerOpen.value = false
  boxCode.value = code
  await load(true)
}

function clearBoxCode() {
  boxCode.value = ''
  load(true)
}

function clearFilters() {
  productId.value = 0
  supplierId.value = 0
  companyId.value = 0
  startDate.value = ''
  endDate.value = ''
  boxCode.value = ''
  load(true)
}

onLoad(options => {
  returnMode.value = options?.mode === 'return'
  outboundOnly.value = returnMode.value || options?.filter === 'OUT'
})
onShow(() => {
  loadOptions()
  load(true)
})
// #ifndef MP-WEIXIN
onHide(() => { boxScannerOpen.value = false })
// #endif
onBackPress(() => {
  if (!boxScannerOpen.value) return false
  boxScannerOpen.value = false
  return true
})
onReachBottom(() => load())
</script>

<template>
  <AppShell title="单据记录" subtitle="追踪每一笔出入库" active="history">
    <view v-if="returnMode" class="return-guide"><view class="return-guide-title">选择原出库单</view><view>打开单据详情，点击“按此单退库”。退库数量以原单可退余量为准。</view></view>
    <view class="card filter-panel">
      <view class="row filter-controls">
        <view class="filter-field">
          <text class="label">物资</text>
          <picker :range="productOptions" range-key="label" :value="productIndex" :disabled="productOptions.length<=1" @change="chooseFilter('product', $event)">
            <view class="input filter-input">
              <text class="option-label">{{ productOptions[productIndex].label }}</text>
              <text class="filter-arrow" aria-hidden="true">▾</text>
            </view>
          </picker>
        </view>
        <view v-if="!outboundOnly" class="filter-field">
          <text class="label">供应商</text>
          <picker :range="supplierOptions" range-key="label" :value="supplierIndex" :disabled="supplierOptions.length<=1" @change="chooseFilter('supplier', $event)">
            <view class="input filter-input">
              <text class="option-label">{{ supplierOptions[supplierIndex].label }}</text>
              <text class="filter-arrow" aria-hidden="true">▾</text>
            </view>
          </picker>
        </view>
      </view>
      <view class="filter-extra">
        <text class="label">领用公司</text>
        <picker :range="companyOptions" range-key="label" :value="companyIndex" :disabled="companyOptions.length<=1" @change="chooseFilter('company', $event)">
          <view class="input filter-input">
            <text class="option-label">{{ companyOptions[companyIndex].label }}</text>
            <text class="filter-arrow" aria-hidden="true">▾</text>
          </view>
        </picker>
      </view>
      <view class="row filter-controls filter-extra">
        <view class="filter-field">
          <text class="label">开始日期</text>
          <picker mode="date" :value="startDate" :end="endDate || undefined" @change="chooseDate('start', $event)">
            <view class="input filter-input">{{ startDate || '不限' }}</view>
          </picker>
        </view>
        <view class="filter-field">
          <text class="label">结束日期</text>
          <picker mode="date" :value="endDate" :start="startDate || undefined" @change="chooseDate('end', $event)">
            <view class="input filter-input">{{ endDate || '不限' }}</view>
          </picker>
        </view>
      </view>
      <view class="filter-extra">
        <text class="label">箱码</text>
        <view class="row">
          <view class="input filter-input filter-field">
            <text class="option-label">{{ boxCode || '不限' }}</text>
            <button v-if="boxCode" class="box-clear" @click="clearBoxCode">清除</button>
          </view>
          <button class="btn btn-light btn-small" @click="boxScannerOpen = true">扫码查询</button>
        </view>
      </view>
      <view v-if="hasFilters" class="reset-filter" @click="clearFilters">清除筛选</view>
      <view v-if="optionsError" class="row filter-feedback">
        <text class="muted">筛选选项加载失败</text>
        <button class="btn btn-light btn-small" @click="loadOptions">重试</button>
      </view>
      <view v-else-if="loadingOptions" class="muted filter-feedback">正在加载筛选选项…</view>
    </view>
    <view class="list-heading">
      <view>{{ returnMode?'出库记录':'单据列表' }} <text>共 {{ total }} 条</text></view>
      <ExcelExportButton v-if="!returnMode" :path="exportPath" :filename="outboundOnly ? '出库单.xlsx' : '出入库单.xlsx'" :disabled="loading || !exportableTotal" />
    </view>
    <view v-if="!returnMode && !loading && exportableTotal < total" class="muted export-scope">
      {{ exportableTotal ? `可导出 ${exportableTotal} 张普通出入库单` : '当前结果没有可导出的普通出入库单' }}
    </view>
    <view v-if="loadError && !items.length" class="card empty-state">加载失败：{{ loadError }}<button class="btn btn-light retry" @click="load(true)">重新加载</button></view>
    <view v-else-if="loading && !items.length" class="card empty-state">正在加载单据…</view>
    <view v-else-if="!items.length" class="card empty-state">
      {{ hasFilters?'没有符合筛选条件的单据':outboundOnly?'暂无可选的出库单':'暂无单据，先创建一张单据吧' }}
    </view>
    <view v-for="d in items" :key="d.id" class="card record-card" @click="go('detail/detail?id='+d.id)">
      <view class="row"><text class="doc-no">{{ d.doc_no }}</text><text class="pill" :class="d.direction==='IN'?'pill-in':'pill-out'">{{ d.kind==='RETURN'?'退库':d.kind==='ADJUST'?(d.direction==='IN'?'盘盈调整':'盘亏调整'):d.direction==='IN'?'入库':'出库' }}</text></view>
      <view class="muted record-time">{{ localTime(d.created_at, beijingOffsetMinutes) }} · {{ d.operator_name }}</view>
      <view v-if="d.source_document_id || d.supplier_name || d.recipient || d.kind==='ADJUST'" class="record-extra">{{ d.source_document_id?'原出库单：'+d.source_document_no:d.supplier_name?'供应商：'+d.supplier_name:d.kind==='ADJUST'?'原因：'+d.remark:(d.recipient_company_id?'领用公司：':'历史领用人：')+d.recipient }}</view>
    </view>
    <view v-if="items.length" class="muted count">{{ loading?'加载中…':`已显示 ${items.length} / ${total}` }}<view v-if="loadError" class="reset-filter" @click="load()">加载更多失败，点击重试</view></view>
    <ContinuousScanner v-if="boxScannerOpen" single :process-code="searchBox" @close="boxScannerOpen = false" />
  </AppShell>
</template>

<style scoped>
.return-guide{background:var(--sf-soft);border:1rpx solid var(--sf-border);border-radius:17rpx;padding:22rpx 25rpx;margin-bottom:20rpx;color:var(--sf-subtext);font-size:23rpx;line-height:1.5}.return-guide-title{font-size:27rpx;font-weight:700;color:var(--sf-primary-dark);margin-bottom:6rpx}
.filter-panel{padding:20rpx}
.filter-controls{align-items:flex-start}
.filter-extra{margin-top:12rpx}
.filter-field{flex:1;min-width:0}
.filter-input{display:flex;justify-content:space-between;align-items:center;gap:8rpx;font-size:25rpx}
.option-label{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.box-clear{flex-shrink:0;margin:0;padding:0 4rpx;background:transparent;color:var(--sf-primary);font-size:23rpx;line-height:1.5}.box-clear::after{border:0}
.filter-arrow{flex-shrink:0;color:var(--sf-primary)}
.filter-feedback{margin-top:12rpx}
.list-heading{display:flex;align-items:center;justify-content:space-between;font-size:27rpx;font-weight:700;margin-bottom:16rpx}.list-heading text{font-size:23rpx;color:var(--sf-subtext);font-weight:500}
.export-scope{margin-bottom:16rpx}
.record-card{padding:25rpx 28rpx}.doc-no{font-size:27rpx;font-weight:700;overflow-wrap:anywhere}.record-time{margin-top:12rpx}.record-extra{font-size:23rpx;color:var(--sf-subtext);background:var(--sf-input);border-radius:10rpx;margin-top:17rpx;padding:11rpx 15rpx}
.pill-in{background:var(--sf-green-soft);color:var(--sf-green)}.pill-out{background:var(--sf-orange-soft);color:var(--sf-orange)}.count{text-align:center;padding:20rpx}
.retry{margin:20rpx auto 0;width:200rpx}.reset-filter{color:var(--sf-primary);font-size:23rpx;font-weight:650;margin-top:15rpx}
</style>


