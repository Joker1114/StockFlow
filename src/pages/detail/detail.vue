<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { api, go, localTime, message, type Document, type Returnable, type User } from '@/api/client'
import { confirmAction } from '@/utils/management'
import AppShell from '@/components/AppShell.vue'
import ExcelExportButton from '@/components/ExcelExportButton.vue'
const doc = ref<Document | null>(null)
const canReturn = ref(false)
const returnChecked = ref(false)
const loading = ref(true)
const loadError = ref('')
const isAdmin = ref(false)
const deleting = ref(false)
const deleteError = ref('')
let documentId = 0
const title = computed(() => doc.value?.kind==='RETURN'?'退库单详情':doc.value?.kind==='ADJUST'?'库存调整详情':doc.value?.direction==='OUT'?'出库单详情':'入库单详情')
const kindLabel = computed(() => doc.value?.kind==='RETURN'?'退库':doc.value?.kind==='ADJUST'?(doc.value.direction==='IN'?'盘盈调整':'盘亏调整'):doc.value?.direction==='OUT'?'出库':'入库')
async function refreshReturnable() {
  if (doc.value?.kind!=='NORMAL' || doc.value.direction!=='OUT') return
  canReturn.value=false
  returnChecked.value=false
  try {
    const available=await api<Returnable>(`/documents/${doc.value.id}/returnable`)
    canReturn.value=available.items.some(item=>item.quantity>0)
    returnChecked.value=true
  } catch { returnChecked.value=false }
}
async function load() {
  loading.value=true;loadError.value='';deleteError.value='';isAdmin.value=false
  try {
    doc.value = await api<Document>('/documents/'+documentId)
    await Promise.all([
      refreshReturnable(),
      api<User>('/auth/me').then(user => {isAdmin.value=user.role==='ADMIN'}).catch(() => {}),
    ])
  } catch (error) {loadError.value=message(error)}
  finally {loading.value=false}
}
async function removeDocument() {
  const target=doc.value
  if (!target || !isAdmin.value || deleting.value) return
  deleting.value=true
  deleteError.value=''
  try {
    if (!await confirmAction('删除单据？', `删除 ${target.doc_no} 后会回退这张单据的库存变动。删除后无法恢复。`)) return
    await api(`/documents/${target.id}`, 'DELETE')
    doc.value=null
    uni.showToast({title:'单据已删除',icon:'success'})
    uni.navigateBack({fail:()=>uni.reLaunch({url:'/pages/history/history'})})
  } catch (error) {deleteError.value=message(error)}
  finally {deleting.value=false}
}
onLoad((options) => {
  documentId=Number(options?.id)
  if (!Number.isInteger(documentId) || documentId<1) {loading.value=false;loadError.value='单据编号无效';return}
  void load()
})
onShow(() => {if (doc.value) void refreshReturnable()})
</script>

<template>
  <AppShell :title="title" subtitle="查看单据与物资明细" active="history" back>
    <view v-if="doc" class="detail-content">
    <view class="card summary-card"><view class="row"><text class="doc-no">{{ doc.doc_no }}</text><text class="pill" :class="doc.direction==='IN'?'pill-in':'pill-out'">{{ kindLabel }}</text></view><view class="muted created-time">{{ localTime(doc.created_at) }}</view>
      <view class="divider" /><view class="info-row"><text>操作人</text><text>{{ doc.operator_name }}</text></view><view v-if="doc.supplier_name" class="info-row"><text>供应商</text><text>{{ doc.supplier_name }}</text></view><view v-if="doc.recipient" class="info-row"><text>{{ doc.recipient_company_id ? '领用公司' : '历史领用人' }}</text><text>{{ doc.recipient }}</text></view><view v-if="doc.source_document_id" class="info-row source-link" @click="go('detail/detail?id='+doc.source_document_id)"><text>原出库单</text><text>{{ doc.source_document_no }} ›</text></view><view v-if="doc.remark" class="info-row"><text>{{ doc.kind==='NORMAL'?'备注':'原因' }}</text><text>{{ doc.remark }}</text></view>
    </view>
    <button v-if="canReturn" class="btn return-button" :disabled="deleting" @click="go('returns/returns?id='+doc.id)">按此单退库</button>
    <view v-else-if="doc.kind==='NORMAL' && doc.direction==='OUT' && returnChecked" class="muted return-complete">这张出库单已全部退回</view>
    <view class="row section-title">
      <text>物资明细</text>
      <ExcelExportButton v-if="doc.kind==='NORMAL'" :path="`/documents/${doc.id}/export.xlsx`" :filename="`${kindLabel}单-${doc.doc_no}.xlsx`" :disabled="deleting" />
    </view>
    <view v-for="i in doc.items" :key="i.id" class="card item-card">
      <view class="row"><text class="item-name">{{ i.brand }} {{ i.name }} · {{ i.specification }}</text><text class="item-qty">{{ i.quantity }} {{ i.unit }}</text></view>
      <view v-if="i.loose_quantity" class="muted">散瓶{{ doc.kind==='RETURN'?'退回':doc.kind==='ADJUST'?(doc.direction==='IN'?'增加':'扣减'):doc.direction==='IN'?'入库':'出库' }}：{{ i.loose_quantity }} 瓶</view>
      <view v-for="(box,index) in i.boxes" :key="index" class="code muted">箱码 {{ box.code_value }} · 本次{{ doc.kind==='RETURN'?'退回':doc.kind==='ADJUST'?(doc.direction==='IN'?'增加':'扣减'):doc.direction==='IN'?'入库':'出库' }} {{ box.quantity }} 瓶 · 箱内剩余 {{ box.remaining_after }} 瓶</view>
      <view v-if="i.codes.length" class="muted codes">扫码：<view v-for="(code,index) in i.codes" :key="index" class="code">{{ code }}</view></view>
    </view>
    <view v-if="isAdmin" class="delete-section">
      <view v-if="deleteError" class="delete-error" role="alert">{{ deleteError }}</view>
      <button class="btn btn-danger delete-button" :disabled="deleting" @click="removeDocument">{{ deleting?'处理中…':'删除单据' }}</button>
    </view>
    </view>
    <view v-else-if="loading" class="card empty-state">正在加载单据…</view>
    <view v-else class="card empty-state">{{ loadError || '未找到单据' }}<button class="btn btn-light retry" @click="load">重新加载</button></view>
  </AppShell>
</template>

<style scoped>
.doc-no{font-size:30rpx;font-weight:750;overflow-wrap:anywhere}.created-time{margin-top:10rpx}.pill-in{background:var(--sf-green-soft);color:var(--sf-green)}.pill-out{background:var(--sf-orange-soft);color:var(--sf-orange)}
.info-row{display:flex;justify-content:space-between;gap:20rpx;padding:8rpx 0;font-size:25rpx}.info-row text:first-child{color:#8090a2;white-space:nowrap}.info-row text:last-child{text-align:right;overflow-wrap:anywhere}
.item-card .row{margin-bottom:15rpx}.item-name{font-size:27rpx;font-weight:680;flex:1;line-height:1.4}.item-qty{font-size:27rpx;color:var(--sf-primary);font-weight:750;white-space:nowrap}.codes{margin-top:14rpx}.code{overflow-wrap:anywhere;padding:7rpx 0}
.return-complete{text-align:center;margin:10rpx 0 25rpx}.retry{margin:20rpx auto 0;width:200rpx}
.delete-section{margin-top:28rpx}.delete-button{width:100%}.delete-error{margin-bottom:14rpx;padding:18rpx;border-radius:12rpx;background:var(--sf-danger-soft);color:var(--sf-danger);font-size:25rpx;overflow-wrap:anywhere}
</style>


