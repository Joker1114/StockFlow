<script setup lang="ts">
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { api, message, productName, type Product } from '@/api/client'
import AppShell from '@/components/AppShell.vue'
import ExcelExportButton from '@/components/ExcelExportButton.vue'

const products = ref<Product[]>([])
const loading = ref(false)
const loadError = ref('')
const category = ref('ALL')
const query = ref('')
const expandedId = ref<number|null>(null)
const boxes = ref<{code_value:string;capacity:number;remaining:number;supplier_name:string|null}[]>([])
const boxTotal = ref(0)
const loadingBoxes = ref(false)
let boxRequestId = 0
const filtered = computed(() => products.value.filter(p =>
  (category.value === 'ALL' || p.category === category.value) &&
  productName(p).toLowerCase().includes(query.value.trim().toLowerCase())))
const activeProducts = computed(() => products.value.filter(p=>p.is_active))
const stockedCount = computed(() => activeProducts.value.filter(p=>p.stock_qty>0).length)
const exportPath = computed(() => {
  const params = []
  if (category.value !== 'ALL') params.push(`category=${category.value}`)
  if (query.value.trim()) params.push(`q=${encodeURIComponent(query.value.trim())}`)
  return '/stock/export.xlsx' + (params.length ? '?' + params.join('&') : '')
})
async function load() {
  loading.value=true;loadError.value=''
  try { products.value = await api<Product[]>('/products?include_inactive=true') }
  catch (error) { loadError.value=message(error) }
  finally {loading.value=false}
}
onShow(load)
async function showBoxes(product:Product, more=false) {
  if (!more && expandedId.value===product.id) { boxRequestId++; expandedId.value=null; return }
  if (more && loadingBoxes.value) return
  if (!more) {expandedId.value=product.id;boxes.value=[];boxTotal.value=0}
  const currentRequest=++boxRequestId
  loadingBoxes.value=true
  try {
    const offset=more?boxes.value.length:0
    const result=await api<{items:typeof boxes.value;total:number}>(`/boxes?product_id=${product.id}&limit=100&offset=${offset}`)
    if (currentRequest!==boxRequestId) return
    boxes.value=more?[...boxes.value,...result.items]:result.items
    boxTotal.value=result.total
  } catch (error) { if (currentRequest===boxRequestId) uni.showToast({title:message(error),icon:'none'}) }
  finally {if (currentRequest===boxRequestId) loadingBoxes.value=false}
}
</script>

<template>
  <AppShell title="当前库存" subtitle="按物资查看实时结存" active="stock">
    <view class="summary-grid"><view class="summary-card"><text>物资种类</text><view>{{ activeProducts.length }}<text> 种</text></view></view><view class="summary-card"><text>有库存物资</text><view>{{ stockedCount }}<text> 种</text></view></view></view>
    <view class="card search-card"><view class="search-row"><input v-model="query" class="input" placeholder="搜索品牌、名称或规格" /><text v-if="query" class="clear-search" @click="query=''">清除</text></view>
      <view class="filters"><text v-for="c in ['ALL','TOBACCO','ALCOHOL']" :key="c" class="pill" :class="{active:category===c}" @click="category=c">{{ c==='ALL'?'全部':c==='TOBACCO'?'烟':'酒' }}</text></view>
    </view>
    <view class="list-heading">
      <view>物资列表 <text>{{ filtered.length }} 项</text></view>
      <ExcelExportButton :path="exportPath" filename="当前库存.xlsx" :disabled="loading || !filtered.length" />
    </view>
    <view v-if="loading && !products.length" class="card empty-state">正在加载库存…</view>
    <view v-else-if="loadError && !products.length" class="card empty-state">加载失败：{{ loadError }}<button class="btn btn-light retry" @click="load">重新加载</button></view>
    <view v-else-if="!filtered.length" class="card empty-state">{{ products.length?'没有符合条件的物资':'暂无物资' }}<view v-if="products.length" class="reset-filter" @click="query='';category='ALL'">清除筛选条件</view></view>
    <view v-for="p in filtered" :key="p.id" class="card product-card">
      <view class="row"><view class="product-copy"><view class="product-name">{{ productName(p) }}</view><text class="muted">{{ p.category==='TOBACCO'?'烟草':'酒水' }} · {{ p.category==='ALCOHOL'?'箱码＋散瓶':p.scan_mode==='SERIAL'?'一物一码':'数量模式' }}{{ p.is_active?'':' · 已停用' }}</text></view><view class="stock">{{ p.stock_qty }}<text> {{ p.unit }}</text></view></view>
      <view v-if="p.category==='ALCOHOL'" class="breakdown"><view><text>散瓶</text><strong>{{ p.loose_qty }}</strong></view><view><text>完整箱</text><strong>{{ p.full_boxes }}</strong></view><view><text>已开箱</text><strong>{{ p.opened_boxes }}</strong></view></view>
      <view v-if="p.category==='ALCOHOL' && p.scan_mode==='SERIAL'" class="box-link" @click="showBoxes(p)">{{ expandedId===p.id?'收起箱码':'查看箱码余量' }}</view>
      <view v-if="expandedId===p.id" class="box-list"><view v-if="loadingBoxes && !boxes.length" class="muted box-status">正在加载箱码…</view><view v-else-if="!boxes.length" class="muted box-status">暂无有余量的箱码</view><view v-for="box in boxes" :key="box.code_value" class="row box-row"><text class="code">{{ box.code_value }}</text><text class="box-balance">{{ box.remaining }}/{{ box.capacity }} 瓶</text></view><view v-if="boxes.length<boxTotal" class="box-link" @click="showBoxes(p,true)">{{ loadingBoxes?'加载中…':`加载更多（${boxes.length}/${boxTotal}）` }}</view></view>
    </view>
  </AppShell>
</template>

<style scoped>
.summary-grid{display:flex;gap:16rpx;margin-bottom:20rpx}.summary-card{flex:1;background:var(--sf-soft);border:1rpx solid var(--sf-border);border-radius:18rpx;padding:23rpx 25rpx}.summary-card>text{font-size:23rpx;color:var(--sf-subtext)}.summary-card>view{font-size:41rpx;font-weight:750;color:var(--sf-primary-dark);margin-top:5rpx}.summary-card>view text{font-size:22rpx;font-weight:500}
.search-card{padding:22rpx}.filters{display:flex;gap:12rpx;margin-top:18rpx}.filters .pill{padding:8rpx 22rpx}.active{background:var(--sf-primary);color:#fff}
.search-row{display:flex;align-items:center;gap:14rpx}.search-row .input{flex:1;min-width:0}.clear-search,.reset-filter{color:var(--sf-primary);font-size:23rpx;font-weight:650;white-space:nowrap}.reset-filter{margin-top:18rpx}.box-status{padding:17rpx 0}
.retry{margin:20rpx auto 0;width:200rpx}
.list-heading{display:flex;justify-content:space-between;align-items:center;font-size:27rpx;font-weight:700;margin:28rpx 0 16rpx}.list-heading text{font-size:23rpx;color:var(--sf-subtext);font-weight:500}
.product-card{padding:25rpx 27rpx}.product-copy{flex:1;min-width:0}.product-name{font-size:27rpx;font-weight:680;line-height:1.4;margin-bottom:7rpx}.stock{color:var(--sf-primary);font-size:39rpx;font-weight:750;white-space:nowrap}.stock text{font-size:23rpx;font-weight:500}
.breakdown{display:flex;background:var(--sf-input);border-radius:13rpx;margin-top:20rpx;padding:17rpx 8rpx}.breakdown view{flex:1;text-align:center;border-right:1rpx solid var(--sf-border)}.breakdown view:last-child{border:0}.breakdown text{display:block;color:var(--sf-subtext);font-size:21rpx}.breakdown strong{display:block;font-size:27rpx;color:var(--sf-text);margin-top:4rpx}
.box-link{color:var(--sf-primary);margin-top:18rpx;font-size:24rpx;font-weight:650}.box-list{margin-top:16rpx;border-top:1rpx solid var(--sf-border)}.box-row{padding:16rpx 0;border-bottom:1rpx solid var(--sf-border);font-size:23rpx}.code{flex:1;overflow-wrap:anywhere}.box-balance{white-space:nowrap;color:var(--sf-subtext)}
</style>


