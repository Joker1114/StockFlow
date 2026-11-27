<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onBackPress, onHide, onLoad, onUnload } from '@dcloudio/uni-app'
import { api, message, resolveCode, type Document, type Returnable, type ReturnableItem } from '@/api/client'
import AppShell from '@/components/AppShell.vue'
import ContinuousScanner from '@/components/ContinuousScanner.vue'

type Draft = {loose:string;quantity:string;boxes:Record<string,string>;codes:string[];inputCode:string}
const source = ref<Returnable|null>(null)
const drafts = ref<Record<number,Draft>>({})
const reason = ref('')
const saving = ref(false)
const allowLeave = ref(false)
const requestId = ref('')
const scanIndex = ref<number|null>(null)
const scanFeedback = ref('')
const scanTone = ref<'success'|'error'|'info'>('info')
const available = computed(() => source.value?.items.filter(item=>item.quantity>0) || [])
const scannedCount = computed(() => {
  if (scanIndex.value===null) return 0
  const item=available.value[scanIndex.value]
  const draft=item && drafts.value[item.product_id]
  return draft ? draft.codes.length+Object.values(draft.boxes).filter(value=>Number(value)>0).length : 0
})
const hasDraft = computed(() => Boolean(reason.value.trim() || Object.values(drafts.value).some(draft=>
  draft.loose!=='0' || draft.quantity!=='0' || draft.inputCode.trim() || draft.codes.length ||
  Object.values(draft.boxes).some(value=>value!=='' && value!=='0'))))

watch([drafts,reason],()=>{requestId.value=''},{deep:true})
onLoad(async options => {
  const id=Number(options?.id)
  if (!Number.isInteger(id) || id<1) return uni.showToast({title:'原出库单号无效',icon:'none'})
  try {
    const data=await api<Returnable>(`/documents/${id}/returnable`)
    for (const item of data.items) drafts.value[item.product_id]={loose:'0',quantity:'0',boxes:{},codes:[],inputCode:''}
    source.value=data
  } catch (error) { uni.showToast({title:message(error),icon:'none'}) }
})
// #ifndef MP-WEIXIN
onHide(closeScanner)
// #endif
onUnload(closeScanner)
onBackPress(() => {
  if (scanIndex.value!==null) {closeScanner();return true}
  if (allowLeave.value || !hasDraft.value) return false
  uni.showModal({title:'放弃未保存的退库单？',content:'已填写的退库数量和原因会丢失。',
    confirmText:'放弃离开',confirmColor:'#b44761',success:result=>{
      if (result.confirm) {allowLeave.value=true;uni.navigateBack({fail:()=>uni.reLaunch({url:'/pages/work/work'})})}
    }})
  return true
})

function codeNotice(text:string,success=false) {
  if (scanIndex.value!==null) {scanFeedback.value=text;scanTone.value=success?'success':'error'}
  else uni.showToast({title:text,icon:'none'})
}
async function applyCode(item:ReturnableItem, raw:string) {
  let code=raw.trim()
  if (!code) return codeNotice('请扫描或输入码值')
  const draft=drafts.value[item.product_id]
  if (item.category==='ALCOHOL') {
    let box=item.boxes.find(box=>box.code_value===code)
    if (!box) {
      const scanner=scanIndex.value
      try {
        const result=await resolveCode(code, item.product_id, true)
        if (scanIndex.value!==scanner) return
        if (result.box?.product_id===item.product_id) {
          box=item.boxes.find(box=>box.code_value===result.box?.code_value)
        }
      } catch (error) {
        if (scanIndex.value===scanner) codeNotice(message(error))
        return
      }
    }
    if (!box) return codeNotice('此箱码不在原单可退范围内')
    code=box.code_value
    if (Number(draft.boxes[code])>0) return codeNotice('本单已选择该箱码')
    draft.boxes[code]=String(box.quantity)
  } else if (item.scan_mode==='SERIAL') {
    if (!item.codes.includes(code)) return codeNotice('此编码不在原单可退范围内')
    if (draft.codes.includes(code)) return codeNotice('本单已选择该编码')
    draft.codes.push(code)
  } else return codeNotice('数量管理物资请直接填写退库数量')
  draft.inputCode=''
  codeNotice(`已选退库编码：${code}`,true)
}
function startScan(index:number) {
  scanIndex.value=index
  scanFeedback.value='扫描原出库单中的箱码或独立编码'
  scanTone.value='info'
}
function closeScanner() {
  scanIndex.value=null
}
async function processScannedCode(code:string) {
  if (scanIndex.value===null) return
  const item=available.value[scanIndex.value]
  if (item) await applyCode(item,code)
}
function toggleCode(item:ReturnableItem,code:string) {
  const codes=drafts.value[item.product_id].codes
  const index=codes.indexOf(code)
  if (index>=0) codes.splice(index,1)
  else codes.push(code)
}
function uuid() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{
    const n=Math.floor(Math.random()*16)
    return (c==='x'?n:(n&3|8)).toString(16)
  })
}
async function submit() {
  if (saving.value || !source.value) return
  if (!reason.value.trim()) return uni.showToast({title:'请填写退库原因',icon:'none'})
  const items:Record<string,unknown>[]=[]
  for (const item of available.value) {
    const draft=drafts.value[item.product_id]
    if (item.category==='ALCOHOL') {
      const loose=Number(draft.loose)
      if (!Number.isInteger(loose) || loose<0 || loose>item.loose_quantity) return uni.showToast({title:'散瓶退库数量超过可退数量',icon:'none'})
      const boxes:{code_value:string;quantity:number}[]=[]
      for (const box of item.boxes) {
        const quantity=Number(draft.boxes[box.code_value]||0)
        if (!Number.isInteger(quantity) || quantity<0 || quantity>box.quantity) return uni.showToast({title:'箱码退库数量超过可退数量',icon:'none'})
        if (quantity>0) boxes.push({code_value:box.code_value,quantity})
      }
      if (loose+boxes.reduce((total,box)=>total+box.quantity,0)>0) items.push({product_id:item.product_id,loose_quantity:loose,boxes})
    } else if (item.scan_mode==='SERIAL') {
      if (draft.codes.length) items.push({product_id:item.product_id,quantity:draft.codes.length,codes:draft.codes})
    } else {
      const quantity=Number(draft.quantity)
      if (!Number.isInteger(quantity) || quantity<0 || quantity>item.quantity) return uni.showToast({title:'退库数量超过可退数量',icon:'none'})
      if (quantity>0) items.push({product_id:item.product_id,quantity})
    }
  }
  if (!items.length) return uni.showToast({title:'请选择要退回的物资',icon:'none'})
  const confirmed=await new Promise<boolean>(resolve=>uni.showModal({title:'确认退库',
    content:`关联 ${source.value?.source_document_no}，退回 ${items.length} 款物资，确认后不可修改`,
    success:r=>resolve(r.confirm),fail:()=>resolve(false)}))
  if (!confirmed) return
  if (!requestId.value) requestId.value=uuid()
  saving.value=true
  try {
    const saved=await api<Document>('/documents','POST',{request_id:requestId.value,kind:'RETURN',direction:'IN',
      source_document_id:source.value.source_document_id,remark:reason.value.trim(),items})
    allowLeave.value=true
    uni.redirectTo({url:'/pages/detail/detail?id='+saved.id})
  } catch (error) {uni.showToast({title:message(error),icon:'none'})}
  finally {saving.value=false}
}
</script>

<template>
  <AppShell title="关联原单退库" subtitle="只退回原单尚未退回的数量" active="work" back :confirm-leave="hasDraft && !saving" @leave-confirmed="allowLeave=true">
    <view v-if="source" class="card source-card"><view class="muted">原出库单</view><view class="source-no">{{ source.source_document_no }}</view><view v-if="source.recipient" class="muted">{{ source.recipient_company_id ? '领用公司' : '历史领用人' }}：{{ source.recipient }}</view></view>
    <view v-if="source && !available.length" class="card empty-state">这张出库单已全部退回</view>
    <view v-for="(item,index) in available" :key="item.product_id" class="card return-card">
      <view class="row item-head"><view>{{ item.brand }} {{ item.name }} · {{ item.specification }}</view><text class="pill">最多 {{ item.quantity }} {{ item.unit }}</text></view>
      <template v-if="item.category==='ALCOHOL'">
        <view class="field"><text class="label">散瓶可退 {{ item.loose_quantity }} 瓶 · 本次退回</text><input v-model="drafts[item.product_id].loose" class="input" type="number" /></view>
        <view v-if="item.boxes.length" class="field"><text class="label">原单箱码</text><view class="row scan-row"><button class="btn btn-light btn-small" @click="startScan(index)">相机连扫</button><input v-model="drafts[item.product_id].inputCode" class="input code-input" placeholder="或输入箱码" /><button class="btn btn-light btn-small" @click="applyCode(item,drafts[item.product_id].inputCode)">识别</button></view></view>
        <view v-for="box in item.boxes" :key="box.code_value" class="box-row"><text class="code">{{ box.code_value }}</text><text class="muted">可退 {{ box.quantity }} 瓶</text><input v-model="drafts[item.product_id].boxes[box.code_value]" class="input box-input" type="number" placeholder="0" /></view>
      </template>
      <template v-else-if="item.scan_mode==='SERIAL'"><view class="row scan-row"><button class="btn btn-light btn-small" @click="startScan(index)">相机连扫</button><input v-model="drafts[item.product_id].inputCode" class="input code-input" placeholder="或输入独立码" /><button class="btn btn-light btn-small" @click="applyCode(item,drafts[item.product_id].inputCode)">识别</button></view><view v-for="code in item.codes" :key="code" class="code-option" :class="{'selected':drafts[item.product_id].codes.includes(code)}" @click="toggleCode(item,code)">{{ code }} <text>{{ drafts[item.product_id].codes.includes(code)?'已选':'选择' }}</text></view></template>
      <view v-else class="field"><text class="label">可退 {{ item.quantity }} {{ item.unit }} · 本次退回</text><input v-model="drafts[item.product_id].quantity" class="input" type="number" /></view>
    </view>
    <view v-if="source && available.length" class="card"><text class="label">退库原因（必填）</text><textarea v-model="reason" class="input reason" maxlength="500" placeholder="例如：领用后未使用，原物退回" /></view>
    <button v-if="source && available.length" class="btn submit-button" :disabled="saving" @click="submit">{{ saving?'保存中…':'确认退库' }}</button>
    <ContinuousScanner v-if="scanIndex!==null" :count="scannedCount" :feedback="scanFeedback" :tone="scanTone" :process-code="processScannedCode" @close="closeScanner" />
  </AppShell>
</template>

<style scoped>
.source-no{font-size:32rpx;font-weight:750;margin:8rpx 0}.return-card{padding:26rpx}.item-head{font-size:27rpx;font-weight:700;margin-bottom:25rpx;align-items:flex-start}.item-head view{flex:1;line-height:1.4}.scan-row{margin:14rpx 0}.code-input{flex:1;min-width:0}.box-row{display:flex;align-items:center;gap:12rpx;border-top:1rpx solid var(--sf-border);padding:15rpx 0;font-size:23rpx}.code{flex:1;min-width:0;overflow-wrap:anywhere}.box-input{width:110rpx;flex-shrink:0;padding:12rpx;text-align:center}.code-option{border:1rpx solid #e2eaf3;border-radius:10rpx;padding:15rpx;margin:10rpx 0;font-size:24rpx;display:flex;justify-content:space-between;overflow-wrap:anywhere}.code-option.selected{border-color:var(--sf-primary);background:var(--sf-soft);color:var(--sf-primary)}.reason{height:130rpx}.submit-button{width:100%}
</style>


