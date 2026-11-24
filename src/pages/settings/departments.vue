<script setup lang="ts">
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { api, message, type Company } from '@/api/client'
import { confirmAction, requireAdmin, useDraftGuard } from '@/utils/management'
import AppShell from '@/components/AppShell.vue'

const companies = ref<Company[]>([])
const name = ref('')
const editingId = ref<number | null>(null)
const formOpen = ref(false)
const busy = ref(false)
const loading = ref(true)
const errorText = ref('')
const hasDraft = computed(() => formOpen.value &&
  name.value.trim() !== (companies.value.find(company => company.id === editingId.value)?.name ?? ''))
const allowLeave = useDraftGuard(hasDraft)

async function load() {
  loading.value = true
  errorText.value = ''
  try {
    if (await requireAdmin()) companies.value = await api<Company[]>('/companies?include_inactive=true')
  } catch (error) { errorText.value = message(error) }
  finally { loading.value = false }
}
onShow(load)

async function canDiscard() {
  return !hasDraft.value || await confirmAction('放弃未保存的修改？', '当前输入的子公司名称将丢失。')
}

async function openForm(company?:Company) {
  if (busy.value || !await canDiscard()) return
  editingId.value = company?.id ?? null
  name.value = company?.name ?? ''
  formOpen.value = true
  uni.pageScrollTo({scrollTop:0, duration:250})
}

async function closeForm() {
  if (!busy.value && await canDiscard()) formOpen.value = false
}

async function save() {
  const value = name.value.trim()
  if (busy.value) return
  if (!value) return uni.showToast({title:'请输入子公司名称', icon:'none'})
  busy.value = true
  try {
    if (editingId.value === null) await api('/companies', 'POST', {name:value})
    else await api('/companies/' + editingId.value, 'PATCH', {name:value})
    formOpen.value = false
    await load()
    uni.showToast({title:'子公司已保存', icon:'none'})
  } catch (error) { uni.showToast({title:message(error), icon:'none'}) }
  finally { busy.value = false }
}

async function toggle(company:Company) {
  if (busy.value) return
  busy.value = true
  try {
    const action = company.is_active ? '停用' : '启用'
    if (!await confirmAction(action + '子公司？', company.is_active
      ? '停用后，新增用户和新出库单的下拉列表会隐藏该子公司。'
      : '启用后，可为用户或出库单选择该子公司。')) return
    await api('/companies/' + company.id, 'PATCH', {is_active:!company.is_active})
    await load()
  } catch (error) { uni.showToast({title:message(error), icon:'none'}) }
  finally { busy.value = false }
}
</script>

<template>
  <AppShell title="组织机构" subtitle="子公司" active="home" back :confirm-leave="hasDraft" @leave-confirmed="allowLeave=true">
    <view v-if="errorText" class="card empty-state">{{ errorText }}<button class="btn btn-light retry" @click="load">重新加载</button></view>
    <view v-else-if="loading && !companies.length" class="card empty-state">正在加载子公司…</view>
    <template v-else>
      <button v-if="!formOpen" class="btn" @click="openForm()">＋ 新增子公司</button>
      <view v-else class="card">
        <view class="row form-head">
          <text class="company-name">{{ editingId === null ? '新增子公司' : '编辑子公司' }}</text>
          <button class="btn btn-light btn-small" :disabled="busy" @click="closeForm">取消</button>
        </view>
        <view class="field">
          <text class="label">子公司名称</text>
          <input v-model="name" class="input" maxlength="100" placeholder="请输入子公司名称" />
        </view>
        <button class="btn" :disabled="busy" @click="save">{{ busy ? '保存中…' : '保存子公司' }}</button>
      </view>
      <view class="section-title">子公司列表</view>
      <view v-if="!companies.length" class="card empty-state">暂无子公司，请先添加</view>
      <view v-for="company in companies" :key="company.id" class="card">
        <view class="row">
          <text class="company-name">{{ company.name }}</text>
          <text class="pill" :class="company.is_active ? 'status-on' : 'status-off'">{{ company.is_active ? '启用' : '停用' }}</text>
        </view>
        <view class="row actions">
          <button class="btn btn-light btn-small" :disabled="busy" @click="openForm(company)">编辑</button>
          <button class="btn btn-danger btn-small" :disabled="busy" @click="toggle(company)">{{ company.is_active ? '停用' : '启用' }}</button>
        </view>
      </view>
    </template>
  </AppShell>
</template>

<style scoped>
.form-head{margin-bottom:20rpx}.company-name{font-size:28rpx;font-weight:700;flex:1;min-width:0;overflow-wrap:anywhere}
.actions{justify-content:flex-end;margin-top:18rpx}.status-on{background:var(--sf-green-soft);color:var(--sf-green)}.status-off{background:#f0f1f3;color:#8793a0}
.retry{width:200rpx;margin:20rpx auto 0}
</style>
