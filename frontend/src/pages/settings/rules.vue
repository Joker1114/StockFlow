<script setup lang="ts">
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { api, message, productName, type Product, type Rule } from '@/api/client'
import { confirmAction, requireAdmin, useDraftGuard } from '@/utils/management'
import AppShell from '@/components/AppShell.vue'

const products=ref<Product[]>([])
const rules=ref<Rule[]>([])
const productId=ref(0)
const matchType=ref<'EXACT'|'PREFIX'>('EXACT')
const matchValue=ref('')
const formOpen=ref(false)
const query=ref('')
const busy=ref(false)
const loading=ref(false)
const errorText=ref('')
const activeProducts=computed(()=>products.value.filter(p=>p.is_active))
const chosenProduct=computed(()=>products.value.find(p=>p.id===productId.value))
const filtered=computed(()=>rules.value.filter(rule=>{
  const name=products.value.find(p=>p.id===rule.product_id)
  return `${rule.match_value} ${name?productName(name):''}`.toLowerCase().includes(query.value.trim().toLowerCase())
}))
const hasDraft=computed(()=>formOpen.value && Boolean(productId.value || matchValue.value.trim() || matchType.value!=='EXACT'))
const allowLeave=useDraftGuard(hasDraft)
async function load() {
  loading.value=true;errorText.value=''
  try {
    if (!await requireAdmin()) return
    const [p,r]=await Promise.all([api<Product[]>('/products?include_inactive=true'),api<Rule[]>('/qr-rules')])
    products.value=p;rules.value=r
  } catch (error) {errorText.value=message(error)}
  finally {loading.value=false}
}
onShow(load)
function startCreate() {productId.value=0;matchType.value='EXACT';matchValue.value='';formOpen.value=true;uni.pageScrollTo({scrollTop:0,duration:250})}
async function closeForm() {
  if (hasDraft.value && !await confirmAction('放弃未保存的规则？','当前填写的匹配条件将丢失。')) return
  formOpen.value=false;productId.value=0;matchValue.value='';matchType.value='EXACT'
}
async function save() {
  if (busy.value) return
  const value=matchValue.value.trim()
  if (!productId.value || !value) return uni.showToast({title:'请选择物资并填写匹配值',icon:'none'})
  busy.value=true
  try {
    await api('/qr-rules','POST',{product_id:productId.value,match_type:matchType.value,match_value:value})
    formOpen.value=false;productId.value=0;matchValue.value='';matchType.value='EXACT'
    await load();uni.showToast({title:'规则已添加',icon:'none'})
  } catch (error) {uni.showToast({title:message(error),icon:'none'})}
  finally {busy.value=false}
}
async function remove(rule:Rule) {
  if (!await confirmAction('删除扫码规则？',`删除“${rule.match_value}”后，扫码将不再按此规则匹配物资。`)) return
  try {await api('/qr-rules/'+rule.id,'DELETE');await load();uni.showToast({title:'规则已删除',icon:'none'})}
  catch (error) {uni.showToast({title:message(error),icon:'none'})}
}
</script>

<template>
  <AppShell title="扫码规则" subtitle="让条码自动匹配物资" active="home" back :confirm-leave="hasDraft" @leave-confirmed="allowLeave=true">
    <view class="page-intro">规则用于识别物资，不验证商品真伪。可按完整码精确匹配，或按固定前缀匹配。</view>
    <button v-if="!formOpen" class="btn add-button" @click="startCreate">＋ 添加扫码规则</button>
    <view v-if="formOpen" class="card form-card"><view class="row form-head"><view class="section-title">添加扫码规则</view><text class="text-action" @click="closeForm">取消</text></view>
      <view class="field"><text class="label">关联物资</text><picker :range="activeProducts" range-key="name" @change="productId=activeProducts[Number(($event as any).detail.value)]?.id||0"><view class="input picker-value">{{ chosenProduct?productName(chosenProduct):'选择物资' }}</view></picker></view>
      <view class="field"><text class="label">匹配方式</text><view class="options"><text class="pill" :class="{active:matchType==='EXACT'}" @click="matchType='EXACT'">完整码</text><text class="pill" :class="{active:matchType==='PREFIX'}" @click="matchType='PREFIX'">固定前缀</text></view></view>
      <view class="field"><text class="label">匹配值</text><input v-model="matchValue" class="input" maxlength="512" :placeholder="matchType==='EXACT'?'粘贴完整条码内容':'输入条码固定前缀'" /></view>
      <button class="btn save-button" :disabled="busy" @click="save">{{ busy?'保存中…':'保存规则' }}</button>
    </view>
    <view class="section-title list-title">现有规则 <text class="list-count">{{ filtered.length }} 条</text></view>
    <view class="card search-card"><input v-model="query" class="input" placeholder="搜索码值或物资" /><text v-if="query" class="text-action" @click="query=''">清除</text></view>
    <view v-if="errorText" class="card empty-state">{{ errorText }}<button class="btn btn-light retry" @click="load">重新加载</button></view>
    <view v-else-if="loading && !rules.length" class="card empty-state">正在加载规则…</view>
    <view v-else-if="!filtered.length" class="card empty-state">{{ query?'没有匹配的规则':'暂无扫码规则' }}</view>
    <view v-for="rule in filtered" :key="rule.id" class="card rule-card"><view class="row rule-top"><view class="rule-product">{{ products.find(p=>p.id===rule.product_id)?productName(products.find(p=>p.id===rule.product_id)!):`物资 #${rule.product_id}` }}</view><text class="pill">{{ rule.match_type==='EXACT'?'完整码':'固定前缀' }}</text></view><view class="code-value">{{ rule.match_value }}</view><view class="row actions"><button class="btn btn-danger btn-small" @click="remove(rule)">删除规则</button></view></view>
  </AppShell>
</template>

<style scoped>
.page-intro{background:var(--sf-soft);border-radius:15rpx;padding:22rpx 25rpx;color:var(--sf-subtext);font-size:23rpx;line-height:1.5;margin-bottom:18rpx}.add-button,.save-button{width:100%}.form-card{padding:25rpx}.form-head{margin-bottom:20rpx}.form-head .section-title{margin:0}.text-action{color:var(--sf-primary);font-size:23rpx;font-weight:650;white-space:nowrap}.picker-value{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.options{display:flex;gap:12rpx}.options .pill{padding:12rpx 25rpx}.options .active{background:var(--sf-primary);color:#fff}.list-title{display:flex;justify-content:space-between;align-items:center}.list-count{font-size:23rpx;color:var(--sf-subtext);font-weight:500}.search-card{display:flex;align-items:center;gap:15rpx;padding:17rpx}.search-card .input{flex:1;min-width:0}.rule-card{padding:24rpx 26rpx}.rule-top{align-items:flex-start}.rule-product{flex:1;min-width:0;font-size:26rpx;font-weight:700;line-height:1.4}.code-value{background:#f6f8fb;border-radius:10rpx;padding:13rpx 16rpx;font-size:23rpx;overflow-wrap:anywhere;margin-top:17rpx}.actions{justify-content:flex-end;margin-top:15rpx}.retry{width:200rpx;margin:20rpx auto 0}
</style>


