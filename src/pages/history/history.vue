<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onReachBottom, onShow } from '@dcloudio/uni-app'
import { api, go, localTime, message, productName, type DocSummary, type Product, type Supplier } from '@/api/client'
import AppShell from '@/components/AppShell.vue'
import ExcelExportButton from '@/components/ExcelExportButton.vue'

type FilterOption = {id:number; label:string}
type FilterOptions = {
  products: Pick<Product,'id'|'brand'|'name'|'specification'>[]
  suppliers: Pick<Supplier,'id'|'name'>[]
}

const returnMode = ref(false)
const outboundOnly = ref(false)
const items = ref<DocSummary[]>([])
const total = ref(0)
const loading = ref(false)
const loadError = ref('')
const productOptions = ref<FilterOption[]>([{id:0,label:'全部物资'}])
const supplierOptions = ref<FilterOption[]>([{id:0,label:'全部供应商'}])
const productId = ref(0)
const supplierId = ref(0)
const loadingOptions = ref(false)
const optionsError = ref('')
const productIndex = computed(() => Math.max(0, productOptions.value.findIndex(option=>option.id===productId.value)))
const supplierIndex = computed(() => Math.max(0, supplierOptions.value.findIndex(option=>option.id===supplierId.value)))
const hasFilters = computed(() => Boolean(productId.value || supplierId.value))
const filterParams = computed(() => {
  const params = []
  if (outboundOnly.value) params.push('direction=OUT')
  if (productId.value) params.push(`product_id=${productId.value}`)
  if (supplierId.value) params.push(`supplier_id=${supplierId.value}`)
  return params
})
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
  } catch (error) {
    optionsError.value = message(error)
  } finally {
    loadingOptions.value = false
  }
}

async function load(reset=false) {
  if ((loading.value && !reset) || (!reset && items.value.length >= total.value)) return
  if (reset) {generation++;items.value=[];total.value=0}
  const currentGeneration=generation
  loading.value = true
  loadError.value=''
  try {
    const params = ['limit=20', `offset=${reset?0:items.value.length}`, ...filterParams.value]
    if (outboundOnly.value) params.push('kind=NORMAL')

    const data = await api<{items:DocSummary[];total:number}>(`/documents?${params.join('&')}`)
    if (currentGeneration!==generation) return
    items.value = reset ? data.items : [...items.value,...data.items]
    total.value = data.total
  } catch (error) { if (currentGeneration===generation) loadError.value=message(error) }
  finally { if (currentGeneration===generation) loading.value = false }
}
function chooseFilter(field:'product'|'supplier', event:{detail:{value:unknown}}) {
  const options = field==='product' ? productOptions.value : supplierOptions.value
  const id = field==='product' ? productId : supplierId
  const option = options[Number(event.detail.value)]
  if (!option || option.id===id.value) return
  id.value = option.id
  load(true)
}

function clearFilters() {
  productId.value = 0
  supplierId.value = 0
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
      <view v-if="optionsError" class="row filter-feedback">
        <text class="muted">筛选选项加载失败</text>
        <button class="btn btn-light btn-small" @click="loadOptions">重试</button>
      </view>
      <view v-else-if="loadingOptions" class="muted filter-feedback">正在加载筛选选项…</view>
    </view>
    <view class="list-heading">
      <view>{{ returnMode?'出库记录':'单据列表' }} <text>共 {{ total }} 条</text></view>
      <ExcelExportButton v-if="!returnMode" :path="exportPath" :filename="outboundOnly ? '出库单.xlsx' : '出入库单.xlsx'" :disabled="loading || !total" />
    </view>
    <view v-if="loadError && !items.length" class="card empty-state">加载失败：{{ loadError }}<button class="btn btn-light retry" @click="load(true)">重新加载</button></view>
    <view v-else-if="loading && !items.length" class="card empty-state">正在加载单据…</view>
    <view v-else-if="!items.length" class="card empty-state">
      {{ hasFilters?'没有符合筛选条件的单据':outboundOnly?'暂无可选的出库单':'暂无单据，先创建一张单据吧' }}
      <view v-if="hasFilters" class="reset-filter" @click="clearFilters">清除筛选</view>
    </view>
    <view v-for="d in items" :key="d.id" class="card record-card" @click="go('detail/detail?id='+d.id)">
      <view class="row"><text class="doc-no">{{ d.doc_no }}</text><text class="pill" :class="d.direction==='IN'?'pill-in':'pill-out'">{{ d.kind==='RETURN'?'退库':d.kind==='ADJUST'?(d.direction==='IN'?'盘盈调整':'盘亏调整'):d.direction==='IN'?'入库':'出库' }}</text></view>
      <view class="muted record-time">{{ localTime(d.created_at) }} · {{ d.operator_name }}</view>
      <view v-if="d.source_document_id || d.supplier_name || d.recipient || d.kind==='ADJUST'" class="record-extra">{{ d.source_document_id?'原出库单：'+d.source_document_no:d.supplier_name?'供应商：'+d.supplier_name:d.kind==='ADJUST'?'原因：'+d.remark:(d.recipient_company_id?'领用公司：':'历史领用人：')+d.recipient }}</view>
    </view>
    <view v-if="items.length" class="muted count">{{ loading?'加载中…':`已显示 ${items.length} / ${total}` }}<view v-if="loadError" class="reset-filter" @click="load()">加载更多失败，点击重试</view></view>
  </AppShell>
</template>

<style scoped>
.return-guide{background:var(--sf-soft);border:1rpx solid var(--sf-border);border-radius:17rpx;padding:22rpx 25rpx;margin-bottom:20rpx;color:var(--sf-subtext);font-size:23rpx;line-height:1.5}.return-guide-title{font-size:27rpx;font-weight:700;color:var(--sf-primary-dark);margin-bottom:6rpx}
.filter-panel{padding:20rpx}
.filter-controls{align-items:flex-start}
.filter-field{flex:1;min-width:0}
.filter-input{display:flex;justify-content:space-between;align-items:center;gap:8rpx;font-size:25rpx}
.option-label{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.filter-arrow{flex-shrink:0;color:var(--sf-primary)}
.filter-feedback{margin-top:12rpx}
.list-heading{display:flex;align-items:center;justify-content:space-between;font-size:27rpx;font-weight:700;margin-bottom:16rpx}.list-heading text{font-size:23rpx;color:var(--sf-subtext);font-weight:500}
.record-card{padding:25rpx 28rpx}.doc-no{font-size:27rpx;font-weight:700;overflow-wrap:anywhere}.record-time{margin-top:12rpx}.record-extra{font-size:23rpx;color:var(--sf-subtext);background:var(--sf-input);border-radius:10rpx;margin-top:17rpx;padding:11rpx 15rpx}
.pill-in{background:var(--sf-green-soft);color:var(--sf-green)}.pill-out{background:var(--sf-orange-soft);color:var(--sf-orange)}.count{text-align:center;padding:20rpx}
.retry{margin:20rpx auto 0;width:200rpx}.reset-filter{color:var(--sf-primary);font-size:23rpx;font-weight:650;margin-top:15rpx}
</style>


