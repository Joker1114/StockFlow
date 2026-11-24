<script setup lang="ts">
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { api, message, type Supplier } from '@/api/client'
import { confirmAction, requireAdmin, useDraftGuard } from '@/utils/management'
import AppShell from '@/components/AppShell.vue'

const suppliers=ref<Supplier[]>([])
const name=ref('')
const editingId=ref<number|null>(null)
const formOpen=ref(false)
const query=ref('')
const busy=ref(false)
const loading=ref(false)
const errorText=ref('')
const filtered=computed(()=>suppliers.value.filter(s=>s.name.toLowerCase().includes(query.value.trim().toLowerCase())))
const hasDraft=computed(()=>{
  if (!formOpen.value) return false
  const original=suppliers.value.find(s=>s.id===editingId.value)
  return original?name.value!==original.name:Boolean(name.value.trim())
})
const allowLeave=useDraftGuard(hasDraft)
async function load() {
  loading.value=true;errorText.value=''
  try {
    if (!await requireAdmin()) return
    suppliers.value=await api<Supplier[]>('/suppliers?include_inactive=true')
  } catch (error) {errorText.value=message(error)}
  finally {loading.value=false}
}
onShow(load)
function startCreate() {editingId.value=null;name.value='';formOpen.value=true;uni.pageScrollTo({scrollTop:0,duration:250})}
async function startEdit(s:Supplier) {
  if (hasDraft.value && !await confirmAction('放弃未保存的修改？','打开此供应商后，当前表单内容将丢失。')) return
  editingId.value=s.id;name.value=s.name;formOpen.value=true
  uni.pageScrollTo({scrollTop:0,duration:250})
}
async function closeForm() {
  if (hasDraft.value && !await confirmAction('放弃未保存的修改？','当前供应商表单中的内容将丢失。')) return
  formOpen.value=false;editingId.value=null;name.value=''
}
async function save() {
  if (busy.value) return
  const value=name.value.trim()
  if (!value) return uni.showToast({title:'请输入供应商名称',icon:'none'})
  busy.value=true
  try {
    if (editingId.value) await api('/suppliers/'+editingId.value,'PATCH',{name:value})
    else await api('/suppliers','POST',{name:value})
    formOpen.value=false;editingId.value=null;name.value=''
    await load();uni.showToast({title:'供应商已保存',icon:'none'})
  } catch (error) {uni.showToast({title:message(error),icon:'none'})}
  finally {busy.value=false}
}
async function toggle(s:Supplier) {
  if (!await confirmAction(s.is_active?'停用供应商？':'启用供应商？',
    `${s.name} ${s.is_active?'停用后不能用于新入库单。':'启用后可用于新入库单。'}`)) return
  try {await api('/suppliers/'+s.id,'PATCH',{is_active:!s.is_active});await load()}
  catch (error) {uni.showToast({title:message(error),icon:'none'})}
}
</script>

<template>
  <AppShell title="供应商管理" subtitle="维护入库单供应商" active="home" back :confirm-leave="hasDraft" @leave-confirmed="allowLeave=true">
    <view class="page-intro">所有采购入库单都需要选择供应商。停用后不会影响已有单据。</view>
    <button v-if="!formOpen" class="btn add-button" @click="startCreate">＋ 新增供应商</button>
    <view v-if="formOpen" class="card form-card"><view class="row form-head"><view class="section-title">{{ editingId?'编辑供应商':'新增供应商' }}</view><text class="text-action" @click="closeForm">取消</text></view><view class="field"><text class="label">供应商名称</text><input v-model="name" class="input" maxlength="100" placeholder="请输入供应商名称" /></view><button class="btn save-button" :disabled="busy" @click="save">{{ busy?'保存中…':'保存供应商' }}</button></view>
    <view class="section-title list-title">供应商列表 <text class="list-count">{{ filtered.length }} 家</text></view>
    <view class="card search-card"><input v-model="query" class="input" placeholder="搜索供应商" /><text v-if="query" class="text-action" @click="query=''">清除</text></view>
    <view v-if="errorText" class="card empty-state">{{ errorText }}<button class="btn btn-light retry" @click="load">重新加载</button></view>
    <view v-else-if="loading && !suppliers.length" class="card empty-state">正在加载供应商…</view>
    <view v-else-if="!filtered.length" class="card empty-state">{{ query?'没有匹配的供应商':'暂无供应商，请先添加' }}</view>
    <view v-for="s in filtered" :key="s.id" class="card item-card"><view class="row"><view class="item-name">{{ s.name }}</view><text class="pill" :class="s.is_active?'status-on':'status-off'">{{ s.is_active?'启用':'停用' }}</text></view><view class="row actions"><button class="btn btn-light btn-small" @click="startEdit(s)">编辑</button><button class="btn btn-danger btn-small" @click="toggle(s)">{{ s.is_active?'停用':'启用' }}</button></view></view>
  </AppShell>
</template>

<style scoped>
.page-intro{background:var(--sf-soft);border-radius:15rpx;padding:22rpx 25rpx;color:var(--sf-subtext);font-size:23rpx;line-height:1.5;margin-bottom:18rpx}.add-button,.save-button{width:100%}.form-card{padding:25rpx}.form-head{margin-bottom:20rpx}.form-head .section-title{margin:0}.text-action{color:var(--sf-primary);font-size:23rpx;font-weight:650;white-space:nowrap}.list-title{display:flex;justify-content:space-between;align-items:center}.list-count{font-size:23rpx;color:var(--sf-subtext);font-weight:500}.search-card{display:flex;align-items:center;gap:15rpx;padding:17rpx}.search-card .input{flex:1;min-width:0}.item-card{padding:25rpx 27rpx}.item-name{font-size:27rpx;font-weight:700;flex:1;min-width:0}.status-on{background:var(--sf-green-soft);color:var(--sf-green)}.status-off{background:#f0f1f3;color:#8793a0}.actions{justify-content:flex-end;margin-top:18rpx}.retry{width:200rpx;margin:20rpx auto 0}
</style>


