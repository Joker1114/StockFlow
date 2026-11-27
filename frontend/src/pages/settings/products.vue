<script setup lang="ts">
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { api, message, productName, type Product } from '@/api/client'
import { confirmAction, requireAdmin, useDraftGuard } from '@/utils/management'
import AppShell from '@/components/AppShell.vue'

type ProductForm={category:'TOBACCO'|'ALCOHOL';brand:string;name:string;specification:string;unit:string;scan_mode:'QUANTITY'|'SERIAL';bottles_per_box:number}
const emptyForm=():ProductForm=>({category:'TOBACCO',brand:'',name:'',specification:'',unit:'件',scan_mode:'QUANTITY',bottles_per_box:6})
const products=ref<Product[]>([])
const form=ref<ProductForm>(emptyForm())
const formOpen=ref(false)
const editingId=ref<number|null>(null)
const query=ref('')
const busy=ref(false)
const loading=ref(false)
const errorText=ref('')
const filtered=computed(()=>products.value.filter(p=>productName(p).toLowerCase().includes(query.value.trim().toLowerCase())))
const hasDraft=computed(()=>{
  if (!formOpen.value) return false
  const original=products.value.find(p=>p.id===editingId.value)
  return original
    ? (['category','brand','name','specification','unit','scan_mode','bottles_per_box'] as const).some(key=>String(form.value[key])!==String(original[key]))
    : Boolean(form.value.brand.trim() || form.value.name.trim() || form.value.specification.trim())
})
const allowLeave=useDraftGuard(hasDraft)

async function load() {
  loading.value=true;errorText.value=''
  try {
    if (!await requireAdmin()) return
    products.value=await api<Product[]>('/products?include_inactive=true')
  } catch (error) {errorText.value=message(error)}
  finally {loading.value=false}
}
onShow(load)
function startCreate() {editingId.value=null;form.value=emptyForm();formOpen.value=true;uni.pageScrollTo({scrollTop:0,duration:250})}
async function startEdit(p:Product) {
  if (hasDraft.value && !await confirmAction('放弃未保存的修改？','打开此物资后，当前表单内容将丢失。')) return
  editingId.value=p.id
  form.value={category:p.category,brand:p.brand,name:p.name,specification:p.specification,unit:p.unit,scan_mode:p.scan_mode,bottles_per_box:p.bottles_per_box}
  formOpen.value=true
  uni.pageScrollTo({scrollTop:0,duration:250})
}
async function closeForm() {
  if (hasDraft.value && !await confirmAction('放弃未保存的修改？','当前物资表单中的内容将丢失。')) return
  formOpen.value=false;editingId.value=null;form.value=emptyForm()
}
function changeCategory(category:ProductForm['category']) {
  form.value.category=category
  form.value.unit=category==='ALCOHOL'?'瓶':'件'
  form.value.scan_mode=category==='ALCOHOL'?'SERIAL':'QUANTITY'
}
async function save() {
  if (busy.value) return
  const data={...form.value,brand:form.value.brand.trim(),name:form.value.name.trim(),
    specification:form.value.specification.trim(),unit:form.value.category==='ALCOHOL'?'瓶':form.value.unit.trim(),
    scan_mode:form.value.category==='ALCOHOL'?'SERIAL' as const:form.value.scan_mode,
    bottles_per_box:Number(form.value.bottles_per_box)}
  if (!data.brand || !data.name || !data.specification || !data.unit) return uni.showToast({title:'请填写品牌、名称、规格和单位',icon:'none'})
  if (!Number.isInteger(data.bottles_per_box) || data.bottles_per_box<1 || data.bottles_per_box>1000) return uni.showToast({title:'每箱瓶数须为 1 到 1000 的整数',icon:'none'})
  busy.value=true
  try {
    if (editingId.value) await api('/products/'+editingId.value,'PATCH',data)
    else await api('/products','POST',data)
    formOpen.value=false;editingId.value=null;form.value=emptyForm()
    await load();uni.showToast({title:'物资已保存',icon:'none'})
  } catch (error) {uni.showToast({title:message(error),icon:'none'})}
  finally {busy.value=false}
}
async function toggle(p:Product) {
  if (!await confirmAction(p.is_active?'停用物资？':'启用物资？',
    `${productName(p)} ${p.is_active?'停用后不能用于新建出入库单。':'启用后可用于新建出入库单。'}`)) return
  try {await api('/products/'+p.id,'PATCH',{is_active:!p.is_active});await load()}
  catch (error) {uni.showToast({title:message(error),icon:'none'})}
}
</script>

<template>
  <AppShell title="物资管理" subtitle="维护物资资料与酒水箱规" active="home" back :confirm-leave="hasDraft" @leave-confirmed="allowLeave=true">
    <view class="page-intro">物资资料会用于库存、扫码匹配和新建单据。酒水最小单位为瓶，每箱瓶数可按物资维护。</view>
    <button v-if="!formOpen" class="btn add-button" @click="startCreate">＋ 新增物资</button>
    <view v-if="formOpen" class="card form-card"><view class="row form-head"><view class="section-title">{{ editingId?'编辑物资':'新增物资' }}</view><text class="text-action" @click="closeForm">取消</text></view>
      <view class="field"><text class="label">类别</text><view class="options"><text v-for="c in ['TOBACCO','ALCOHOL']" :key="c" class="pill" :class="{active:form.category===c}" @click="changeCategory(c as ProductForm['category'])">{{ c==='TOBACCO'?'烟草':'酒水' }}</text></view></view>
      <view class="field"><text class="label">品牌</text><input v-model="form.brand" class="input" maxlength="100" placeholder="请输入品牌" /></view>
      <view class="field"><text class="label">名称</text><input v-model="form.name" class="input" maxlength="100" placeholder="请输入物资名称" /></view>
      <view class="field"><text class="label">规格</text><input v-model="form.specification" class="input" maxlength="100" placeholder="例如：500ml、1×6" /></view>
      <view v-if="form.category==='TOBACCO'" class="field"><text class="label">单位</text><input v-model="form.unit" class="input" maxlength="20" placeholder="例如：件" /></view>
      <view v-else class="field"><text class="label">最小单位</text><view class="input fixed-value">瓶</view></view>
      <view v-if="form.category==='TOBACCO'" class="field"><text class="label">扫码模式</text><view class="options"><text v-for="m in ['QUANTITY','SERIAL']" :key="m" class="pill" :class="{active:form.scan_mode===m}" @click="form.scan_mode=m as ProductForm['scan_mode']">{{ m==='QUANTITY'?'数量模式':'一物一码' }}</text></view></view>
      <view v-else class="field"><text class="label">每箱瓶数（默认 6）</text><input v-model.number="form.bottles_per_box" class="input" type="number" /><text class="muted">每扫一个唯一箱码，按这里设置的瓶数入库。</text></view>
      <button class="btn save-button" :disabled="busy" @click="save">{{ busy?'保存中…':'保存物资' }}</button>
    </view>
    <view class="section-title list-title">物资列表 <text class="list-count">{{ filtered.length }} 项</text></view>
    <view class="card search-card"><input v-model="query" class="input" placeholder="搜索品牌、名称或规格" /><text v-if="query" class="text-action" @click="query=''">清除</text></view>
    <view v-if="errorText" class="card empty-state">{{ errorText }}<button class="btn btn-light retry" @click="load">重新加载</button></view>
    <view v-else-if="loading && !products.length" class="card empty-state">正在加载物资…</view>
    <view v-else-if="!filtered.length" class="card empty-state">{{ query?'没有匹配的物资':'暂无物资' }}</view>
    <view v-for="p in filtered" :key="p.id" class="card item-card"><view class="row item-top"><view class="item-name">{{ productName(p) }}</view><text class="pill" :class="p.is_active?'status-on':'status-off'">{{ p.is_active?'启用':'停用' }}</text></view><view class="muted item-meta">{{ p.category==='ALCOHOL'?'酒水 · 箱码＋散瓶':'烟草 · '+(p.scan_mode==='SERIAL'?'一物一码':'数量模式') }} · 库存 {{ p.stock_qty }} {{ p.unit }}<text v-if="p.category==='ALCOHOL'"> · 每箱 {{ p.bottles_per_box }} 瓶</text></view><view class="row actions"><button class="btn btn-light btn-small" @click="startEdit(p)">编辑</button><button class="btn btn-danger btn-small" @click="toggle(p)">{{ p.is_active?'停用':'启用' }}</button></view></view>
  </AppShell>
</template>

<style scoped>
.page-intro{background:var(--sf-soft);border-radius:15rpx;padding:22rpx 25rpx;color:var(--sf-subtext);font-size:23rpx;line-height:1.5;margin-bottom:18rpx}.add-button,.save-button{width:100%}.form-card{padding:25rpx}.form-head{margin-bottom:18rpx}.form-head .section-title{margin:0}.text-action{color:var(--sf-primary);font-size:23rpx;font-weight:650;white-space:nowrap}.options{display:flex;gap:12rpx;flex-wrap:wrap}.options .pill{padding:12rpx 25rpx}.options .active{background:var(--sf-primary);color:#fff}.fixed-value{color:#718399}.list-title{display:flex;justify-content:space-between;align-items:center}.list-count{font-size:23rpx;color:var(--sf-subtext);font-weight:500}.search-card{display:flex;align-items:center;gap:15rpx;padding:17rpx}.search-card .input{flex:1;min-width:0}.item-card{padding:24rpx 26rpx}.item-top{align-items:flex-start}.item-name{flex:1;min-width:0;font-size:27rpx;font-weight:700;line-height:1.4}.status-on{background:var(--sf-green-soft);color:var(--sf-green)}.status-off{background:#f0f1f3;color:#8793a0}.item-meta{margin-top:9rpx}.actions{justify-content:flex-end;margin-top:18rpx}.retry{width:200rpx;margin:20rpx auto 0}
</style>


