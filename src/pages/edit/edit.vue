<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onBackPress, onHide, onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import { api, message, productName, resolveCode, type Company, type Document, type Product, type ScanResolution, type Supplier } from '@/api/client'
import AppShell from '@/components/AppShell.vue'
import ContinuousScanner from '@/components/ContinuousScanner.vue'
import InlineScanner from '@/components/InlineScanner.vue'
import { boxBrandError } from '@/utils/boxBrand'

type BoxDraft = {code_value:string; scannedText:string; quantity:string; capacity:number; remaining:number}
type Line = {product_id:number; quantity:string; loose_quantity:string; codes:string[]; boxes:BoxDraft[]; inputCode:string}
const emptyLine = ():Line => ({product_id:0,quantity:'1',loose_quantity:'0',codes:[],boxes:[],inputCode:''})

const direction = ref<'IN'|'OUT'>('IN')
const kind = ref<'NORMAL'|'ADJUST'>('NORMAL')
const isPurchaseInbound = computed(() => direction.value === 'IN' && kind.value === 'NORMAL')
const isIssueOutbound = computed(() => direction.value === 'OUT' && kind.value === 'NORMAL')
const supplierId = ref(0)
const recipientCompanyId = ref<number|null>(null)
const remark = ref('')
const products = ref<Product[]>([])
const suppliers = ref<Supplier[]>([])
const companies = ref<Company[]>([])
const companyLoading = ref(false)
const companyLoadError = ref('')
const companyOptions = computed(() => [{id:null,name:'选择领用公司'}, ...companies.value])
const companyIndex = computed(() => Math.max(0, companyOptions.value.findIndex(company=>company.id===recipientCompanyId.value)))
const recipientCompany = computed(() => companies.value.find(company=>company.id===recipientCompanyId.value))
const lines = ref<Line[]>([emptyLine()])
const chooseFor = ref<number|null>(null)
const chooseQuery = ref('')
const candidates = ref<Product[]>([])
const pendingCode = ref('')
const saving = ref(false)
const allowLeave = ref(false)
const requestId = ref('')
const scanActive = ref(false)
const scanIndex = ref<number|null>(null)
const scanFeedback = ref('')
const scanTone = ref<'success'|'error'|'info'>('info')
const scanOutcome = ref<'success'|'duplicate'|'error'>('error')
let scanSession = 0
const visibleProducts = computed(() => candidates.value.filter(p => productName(p).toLowerCase().includes(chooseQuery.value.toLowerCase())))
const scannedCount = computed(() => {
  const line = scanIndex.value === null ? null : lines.value[scanIndex.value]
  return line ? line.boxes.length + line.codes.length : 0
})
const hasDraft = computed(() => Boolean(supplierId.value || recipientCompanyId.value || remark.value.trim() ||
  lines.value.some(line=>line.product_id || line.inputCode.trim() || line.codes.length || line.boxes.length ||
    Number(line.loose_quantity)!==0 || line.quantity!=='1')))

watch([supplierId,recipientCompanyId,remark,lines], () => { requestId.value='' }, {deep:true})
onLoad(options => {
  direction.value = options?.direction === 'OUT' ? 'OUT' : 'IN'
  kind.value = options?.kind === 'ADJUST' ? 'ADJUST' : 'NORMAL'
})
onShow(async () => {
  if (isIssueOutbound.value) void loadCompanies()
  try {
    const [p,s] = await Promise.all([
      api<Product[]>(kind.value==='ADJUST'?'/products?include_inactive=true':'/products'),
      isPurchaseInbound.value ? api<Supplier[]>('/suppliers') : Promise.resolve([]),
    ])
    products.value=p; suppliers.value=s
  } catch (error) { uni.showToast({title:message(error),icon:'none'}) }
})
async function loadCompanies() {
  if (companyLoading.value) return
  companyLoading.value=true
  companyLoadError.value=''
  try { companies.value=await api<Company[]>('/companies') }
  catch (error) { companyLoadError.value=message(error) }
  finally { companyLoading.value=false }
}
function chooseCompany(event:{detail:{value:unknown}}) {
  recipientCompanyId.value=companyOptions.value[Number(event.detail.value)]?.id ?? null
}
// #ifndef MP-WEIXIN
onHide(closeScanner)
// #endif
onUnload(() => closeScanner())
onBackPress(() => {
  if (chooseFor.value!==null) {closeChooser();return true}
  if (scanActive.value) {closeScanner();return true}
  if (allowLeave.value || !hasDraft.value) return false
  uni.showModal({title:'放弃未保存的内容？',content:'当前填写和扫码记录尚未保存，离开后需要重新录入。',
    confirmText:'放弃离开',confirmColor:'#b44761',success:result=>{
      if (result.confirm) {allowLeave.value=true;uni.navigateBack({fail:()=>uni.reLaunch({url:'/pages/work/work'})})}
    }})
  return true
})

function codeNotice(text:string, success=false, duplicate=false) {
  if (scanActive.value) {
    scanFeedback.value=text
    scanTone.value=success?'success':'error'
    scanOutcome.value=success?'success':duplicate?'duplicate':'error'
  } else uni.showToast({title:text,icon:'none'})
}

function selected(line:Line) { return products.value.find(p => p.id===line.product_id) }
function addLine() { lines.value.push(emptyLine()) }
function removeLine(index:number) {
  if (scanActive.value) closeScanner()
  if (lines.value.length===1) lines.value[0]=emptyLine()
  else lines.value.splice(index,1)
}
function openChooser(index:number, possible?:Product[], code='') {
  chooseFor.value=index
  candidates.value=possible || products.value
  chooseQuery.value=''
  pendingCode.value=code
}
function closeChooser() { chooseFor.value=null; pendingCode.value='' }
function setProduct(index:number, product:Product) {
  if (lines.value.some((line,i) => i!==index && line.product_id===product.id)) {
    uni.showToast({title:'该物资已在本单据中',icon:'none'})
    return false
  }
  const line = lines.value[index]
  if (line.product_id!==product.id) {
    line.codes=[]; line.boxes=[]; line.quantity=product.category==='ALCOHOL' || product.scan_mode==='SERIAL'?'0':'1'; line.loose_quantity='0'
  }
  line.product_id=product.id
  return true
}
async function chooseProduct(product:Product) {
  const index = chooseFor.value
  if (index===null) return
  const line = lines.value[index]
  const code = pendingCode.value
  const session = scanSession
  const stillChoosing = () => chooseFor.value===index && lines.value[index]===line &&
    pendingCode.value===code && scanSession===session
  if (code) {
    const mismatch = boxBrandError(product, code)
    if (mismatch) {
      uni.showToast({title:mismatch,icon:'none'})
      return
    }
    try {
      const resolution = await resolveCode(code, product.id, kind.value==='ADJUST')
      if (!stillChoosing() || !setProduct(index, product)) return
      recordCode(index, code, resolution)
    } catch (error) {
      if (stillChoosing()) uni.showToast({title:message(error),icon:'none'})
      return
    }
  } else if (!setProduct(index, product)) return
  closeChooser()
  if (scanActive.value && product.scan_mode==='QUANTITY') closeScanner()
}
function recordCode(index:number, raw:string, resolution:ScanResolution) {
  const line=lines.value[index]
  const product=selected(line)
  if (!product) return
  const code = product.category==='ALCOHOL' ? resolution.code_value ?? raw : raw
  const { box } = resolution
  if (product.category==='ALCOHOL') {
    if (lines.value.some(l => l.boxes.some(b=>b.code_value===code) || l.codes.includes(code))) {
      return codeNotice('本单据已扫描该箱码',false,true)
    }
    if (box && box.product_id!==product.id) return codeNotice('箱码属于其他物资')
    if (direction.value==='IN') {
      if (kind.value==='NORMAL') {
        if (box && box.remaining>0) return codeNotice('该箱码已有库存，请勿重复入库',false,true)
        line.boxes.push({code_value:code,scannedText:raw,quantity:'',capacity:product.bottles_per_box,remaining:0})
      } else {
        if (box && box.remaining>=box.capacity) return codeNotice('该箱已满，无法再增加库存')
        line.boxes.push({code_value:code,scannedText:raw,quantity:box?'1':String(product.bottles_per_box),
          capacity:box?.capacity||product.bottles_per_box,remaining:box?.remaining||0})
      }
    } else {
      if (!box || box.remaining<1) return codeNotice('该箱码没有可出库存')
      line.boxes.push({code_value:code,scannedText:raw,quantity:String(box.remaining),capacity:box.capacity,remaining:box.remaining})
    }
    codeNotice(`已录入箱码：${code}`,true)
    return code
  }
  if (lines.value.some(l=>l.codes.includes(code) || l.boxes.some(b=>b.code_value===code))) {
    return codeNotice('本单据已扫描该编码',false,true)
  }
  if (product.scan_mode==='QUANTITY') {
    codeNotice('已识别物资，请填写数量',true)
    return
  }
  line.codes.push(code)
  if (product.scan_mode==='SERIAL') line.quantity=String(line.codes.length)
  codeNotice(`已识别：${code}`,true)
  return code
}
async function applyCode(index:number, code:string, session?:number) {
  code=code.trim()
  if (!code) {
    uni.showToast({title:'请先输入码值',icon:'none'})
    return
  }
  const line = lines.value[index]
  if (!line) return
  const productId = line.product_id
  const isCurrent = () => lines.value[index] === line && line.product_id === productId &&
    (session === undefined || session === scanSession)
  const current = selected(line)
  const mismatch = boxBrandError(current, code)
  if (mismatch) return codeNotice(mismatch)

  try {
    const result = await resolveCode(code, productId || undefined, kind.value==='ADJUST')
    if (!isCurrent()) return
    const possible = products.value.filter(p=>result.candidates.some(c=>c.product_id===p.id))
    if (scanActive.value && current && possible.length && !possible.some(p=>p.id===current.id)) {
      codeNotice('该编码属于其他物资，请返回后切换物资')
      return
    }
    if (current && (!possible.length || possible.some(p=>p.id===current.id))) {
      line.inputCode=''
      return recordCode(index,code,result)
    } else if (possible.length===1) {
      const product = possible[0]
      const mismatch = boxBrandError(product, code)
      if (mismatch) return codeNotice(mismatch)
      const resolution = result.box ? result : await resolveCode(code, product.id, kind.value==='ADJUST')
      if (!isCurrent() || !setProduct(index, product)) return
      line.inputCode=''
      const recordedCode = recordCode(index, code, resolution)
      if (scanActive.value && product.scan_mode==='QUANTITY') closeScanner()
      return recordedCode
    } else {
      openChooser(index,possible.length?possible:products.value,code)
      if (!possible.length) codeNotice('未匹配规则，请手选物资')
    }
    line.inputCode=''
  } catch (error) {
    if (isCurrent()) codeNotice(message(error))
  }
}
function scan(index:number) {
  if (selected(lines.value[index])?.scan_mode==='QUANTITY') {
    return uni.showToast({title:'数量模式直接填写数量',icon:'none'})
  }
  scanSession++
  scanIndex.value=index
  scanFeedback.value=selected(lines.value[index])?'将条码放入取景框，识别后继续扫描下一件':'先扫码识别物资，匹配不唯一时再选择物资'
  scanTone.value='info'
  scanOutcome.value='error'
  scanActive.value=true
}
function closeScanner() {
  scanSession++
  scanActive.value=false
  scanIndex.value=null
}
async function handleScannedCode(code:string) {
  if (scanIndex.value===null) return {status:'error' as const,message:'扫码已结束'}
  scanFeedback.value='正在识别…'
  scanTone.value='info'
  scanOutcome.value='error'
  const recordedCode=await applyCode(scanIndex.value,code,scanSession)
  return {status:scanOutcome.value,message:scanFeedback.value,code:recordedCode || undefined}
}
async function handleOverlayCode(code:string) { await handleScannedCode(code) }
function removeCode(line:Line,index:number) {
  line.codes.splice(index,1)
  if (selected(line)?.scan_mode==='SERIAL') line.quantity=String(line.codes.length)
}
function totalPreview(line:Line) {
  const product=selected(line)
  if (!product) return 0
  if (product.category!=='ALCOHOL') return Number(line.quantity)||0
  const loose=Number(line.loose_quantity)||0
  return loose+(direction.value==='IN' && kind.value==='NORMAL'?line.boxes.length*product.bottles_per_box:
    line.boxes.reduce((sum,box)=>sum+(Number(box.quantity)||0),0))
}
function uuid() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{
    const n=Math.floor(Math.random()*16)
    return (c==='x'?n:(n&3|8)).toString(16)
  })
}
async function submit() {
  if (saving.value) return
  if (kind.value==='NORMAL' && direction.value==='IN' && !supplierId.value) return uni.showToast({title:'请选择供应商',icon:'none'})
  if (isIssueOutbound.value && !recipientCompany.value) return uni.showToast({title:'请选择领用公司',icon:'none'})
  if (kind.value==='ADJUST' && !remark.value.trim()) return uni.showToast({title:'请填写调整原因',icon:'none'})
  const items:Record<string,unknown>[]=[]
  for (const line of lines.value) {
    const product=selected(line)
    if (!product) return uni.showToast({title:'请选择物资',icon:'none'})
    if (product.category==='ALCOHOL') {
      const loose=Number(line.loose_quantity)
      if (!Number.isInteger(loose) || loose<0) return uni.showToast({title:'散瓶数量必须是非负整数',icon:'none'})
      if (kind.value==='NORMAL' && direction.value==='IN' && loose>=product.bottles_per_box) return uni.showToast({title:`入库散瓶须少于每箱 ${product.bottles_per_box} 瓶`,icon:'none'})
      if (direction.value==='OUT' && loose>product.loose_qty) return uni.showToast({title:'散瓶库存不足',icon:'none'})
      const boxes=[] as {code_value:string;quantity?:number}[]
      for (const box of line.boxes) {
        if (direction.value==='IN' && kind.value==='NORMAL') boxes.push({code_value:box.scannedText})
        else {
          const quantity=Number(box.quantity)
          const max=direction.value==='IN'?box.capacity-box.remaining:box.remaining
          if (!Number.isInteger(quantity) || quantity<1 || quantity>max) {
            return uni.showToast({title:`箱码数量须在 1 到 ${max} 瓶之间`,icon:'none'})
          }
          boxes.push({code_value:box.scannedText,quantity})
        }
      }
      if (totalPreview(line)<1) return uni.showToast({title:'请输入散瓶数量或扫描箱码',icon:'none'})
      items.push({product_id:product.id,loose_quantity:loose,boxes,codes:line.codes,quantity:totalPreview(line)})
    } else {
      const quantity=Number(line.quantity)
      if (!Number.isInteger(quantity) || quantity<1 ||
          (product.scan_mode==='SERIAL' && quantity!==line.codes.length)) {
        return uni.showToast({title:'请检查物资数量和独立编码',icon:'none'})
      }
      if (direction.value==='OUT' && quantity>product.stock_qty) return uni.showToast({title:`${product.name} 库存不足，当前可出 ${product.stock_qty} ${product.unit}`,icon:'none'})
      items.push({product_id:product.id,quantity,codes:product.scan_mode==='SERIAL'?line.codes:[]})
    }
  }
  if (new Set(items.map(i=>i.product_id)).size!==items.length) return uni.showToast({title:'物资行不能重复',icon:'none'})
  const actionName=kind.value==='ADJUST'?'库存调整':direction.value==='IN'?'入库':'出库'
  const confirmed=await new Promise<boolean>(resolve=>uni.showModal({title:'确认保存',
    content:`${actionName} ${items.length} 行物资，确认后不可修改`,
    success:r=>resolve(r.confirm),fail:()=>resolve(false)}))
  if (!confirmed) return
  if (!requestId.value) requestId.value=uuid()
  saving.value=true
  try {
    const saved=await api<Document>('/documents','POST',{request_id:requestId.value,direction:direction.value,kind:kind.value,
      supplier_id:kind.value==='NORMAL' && direction.value==='IN'?supplierId.value:null,
      recipient_company_id:isIssueOutbound.value?recipientCompanyId.value:null,remark:remark.value.trim()||null,items})
    allowLeave.value=true
    uni.redirectTo({url:'/pages/detail/detail?id='+saved.id})
  } catch (error) { uni.showToast({title:message(error),icon:'none'}) }
  finally { saving.value=false }
}
</script>

<template>
  <AppShell :title="kind==='ADJUST'?(direction==='IN'?'库存增加调整':'库存减少调整'):(direction==='IN'?'新建入库单':'新建出库单')" :subtitle="kind==='ADJUST'?'盘点差异须填写原因并留痕':(direction==='IN'?'扫码录入到货物资':'核对库存并登记领用')" active="work" back :confirm-leave="hasDraft && !saving" @leave-confirmed="allowLeave=true">
    <view v-if="!isPurchaseInbound" class="form-intro"><view class="intro-icon" :class="direction==='IN'?'intro-in':'intro-out'">{{ direction==='IN'?'↓':'↑' }}</view><view><view class="intro-title">{{ kind==='ADJUST'?'库存调整':'出库登记' }}</view><view class="muted">{{ kind==='ADJUST'?'按实物盘点结果调整箱码或散瓶':'填写领用信息，确认出库数量' }}</view></view></view>
    <view v-if="kind==='NORMAL'" class="section-title" :class="{ 'first-section': isPurchaseInbound }">基本信息</view>
    <view v-if="kind==='NORMAL' && direction==='IN'" class="card field"><text class="label">供应商（必选）</text>
      <picker :range="suppliers" range-key="name" @change="supplierId=suppliers[Number(($event as any).detail.value)]?.id||0">
        <view class="input">{{ suppliers.find(s=>s.id===supplierId)?.name||'选择供应商' }}</view>
      </picker><text v-if="!suppliers.length" class="muted">请先让管理员添加供应商</text>
    </view>
    <view v-if="isIssueOutbound" class="card field">
      <text class="label">领用公司（必选）</text>
      <picker v-if="companies.length" :range="companyOptions" range-key="name" :value="companyIndex" :disabled="saving" @change="chooseCompany">
        <view class="input row company-picker"><text>{{ companyOptions[companyIndex].name }}</text><text>▾</text></view>
      </picker>
      <text v-if="companyLoading" class="muted">正在加载领用公司…</text>
      <view v-else-if="companyLoadError" class="row company-feedback"><text class="muted">{{ companyLoadError }}</text><button class="btn btn-light btn-small" @click="loadCompanies">重试</button></view>
      <text v-else-if="!companies.length" class="muted">请让管理员到「组织机构」添加或启用子公司</text>
    </view>
    <view class="section-title">物资明细</view>
    <view v-for="(line,index) in lines" :key="index" class="card line-card">
      <view class="row line-heading"><text>物资 {{ index+1 }}</text><button class="btn btn-danger btn-small" @click="removeLine(index)">移除</button></view>
      <button class="btn btn-light" @click="openChooser(index)">{{ selected(line)?productName(selected(line)!):'选择物资' }}</button>
      <view v-if="selected(line)" class="muted">
        {{ selected(line)?.category==='ALCOHOL'?'箱码＋散瓶':(selected(line)?.scan_mode==='SERIAL'?'一物一码':'数量模式') }}
        <text v-if="selected(line)?.category==='ALCOHOL'"> · 每箱 {{ selected(line)?.bottles_per_box }} 瓶</text>
      </view>
      <view v-if="selected(line)?.scan_mode==='QUANTITY'" class="muted quantity-hint">数量模式无需逐件扫码，请直接填写实际{{ direction==='IN'?'入库':'出库' }}数量。</view>
      <template v-else-if="kind==='NORMAL'">
        <InlineScanner
          v-if="scanActive && chooseFor===null && scanIndex===index"
          :count="scannedCount"
          :process-code="handleScannedCode"
          @close="closeScanner"
        />
        <button v-else class="btn inline-scan-button" @click="scan(index)">相机连扫</button>
      </template>
      <view v-else class="row gap scan-row"><button class="btn btn-light btn-small" @click="scan(index)">相机连扫</button><input v-model="line.inputCode" class="input code-input" placeholder="或粘贴码值" /><button class="btn btn-light btn-small" @click="applyCode(index,line.inputCode)">识别</button></view>
      <template v-if="selected(line)?.category==='ALCOHOL'">
        <view class="field"><text class="label">{{ direction==='IN'?'增加散瓶':'扣减散瓶' }}（瓶）<text v-if="kind==='NORMAL' && direction==='IN'"> · 少于每箱 {{ selected(line)?.bottles_per_box }}</text><text v-if="direction==='OUT'"> · 当前可出 {{ selected(line)?.loose_qty }}</text></text><input v-model="line.loose_quantity" class="input" :class="{'input-error':kind==='NORMAL' && direction==='IN' && Number(line.loose_quantity)>=Number(selected(line)?.bottles_per_box)}" type="number" /><view v-if="kind==='NORMAL' && direction==='IN' && Number(line.loose_quantity)>=Number(selected(line)?.bottles_per_box)" class="validation-error">散瓶数量须小于每箱 {{ selected(line)?.bottles_per_box }} 瓶</view></view>
        <view v-for="(box,boxIndex) in line.boxes" :key="box.code_value" class="box-record">
          <view class="row"><text class="code">箱码 {{ box.code_value }}</text><text class="remove" @click="line.boxes.splice(boxIndex,1)">移除</text></view>
          <view v-if="direction==='IN' && kind==='NORMAL'" class="muted">一箱 {{ selected(line)?.bottles_per_box }} 瓶</view>
          <view v-else class="field"><text class="label">箱内现有 {{ box.remaining }} / {{ box.capacity }} 瓶 · 本次{{ direction==='IN'?'增加':'扣减' }}（瓶）</text><input v-model="box.quantity" class="input" type="number" /></view>
        </view>
        <view class="muted">本行合计 {{ totalPreview(line) }} 瓶</view>
      </template>
      <template v-else>
        <view class="field"><text class="label">数量{{ selected(line)?.scan_mode==='SERIAL'?'（按编码自动计算）':'' }}<text v-if="direction==='OUT'"> · 当前库存 {{ selected(line)?.stock_qty }} {{ selected(line)?.unit }}</text></text><input v-model="line.quantity" class="input" :class="{'input-error':direction==='OUT' && Number(line.quantity)>Number(selected(line)?.stock_qty)}" type="number" :disabled="selected(line)?.scan_mode==='SERIAL'" /><view v-if="direction==='OUT' && Number(line.quantity)>Number(selected(line)?.stock_qty)" class="validation-error">出库数量不能超过当前库存</view></view>
        <view v-for="(code,codeIndex) in line.codes" :key="codeIndex" class="row code-line"><text class="code">{{ code }}</text><text class="remove" @click="removeCode(line,codeIndex)">移除</text></view>
      </template>
    </view>
    <button class="btn btn-light add-line" @click="addLine">+ 添加物资</button>
    <view class="section-title">补充信息</view>
    <view class="card">
      <view class="field"><text class="label">{{ kind==='ADJUST'?'调整原因（必填）':'备注' }}</text><textarea v-model="remark" class="input remark" maxlength="500" :placeholder="kind==='ADJUST'?'例如：盘点发现一瓶破损':'可填写说明'" /></view>
    </view>
    <button class="btn submit-button" :disabled="saving" @click="submit">{{ saving?'保存中…':'确认保存单据' }}</button>
    <view v-if="chooseFor!==null" class="chooser"><view class="card"><view class="row"><text>选择物资</text><text class="remove" @click="closeChooser">关闭</text></view>
      <input v-model="chooseQuery" class="input" placeholder="搜索品牌或名称" />
      <scroll-view scroll-y class="choices"><view v-for="p in visibleProducts" :key="p.id" class="choice" @click="chooseProduct(p)">{{ productName(p) }} <text class="muted">{{ p.category==='ALCOHOL'?'箱码＋散瓶':p.scan_mode==='SERIAL'?'一物一码':'数量模式' }}</text></view><view v-if="!visibleProducts.length" class="muted">没有物资，请管理员先新增</view></scroll-view>
    </view></view>
    <ContinuousScanner v-if="scanActive && chooseFor===null && kind==='ADJUST'" :count="scannedCount" :feedback="scanFeedback" :tone="scanTone" :process-code="handleOverlayCode" @close="closeScanner" />
  </AppShell>
</template>

<style scoped>
.first-section{margin-top:0}
.company-picker{align-items:center}.company-picker text:first-child{overflow-wrap:anywhere;min-width:0}.company-feedback{margin-top:12rpx}
.inline-scan-button{width:100%;margin:20rpx 0}
.form-intro{display:flex;align-items:center;gap:22rpx;background:var(--sf-card);border:1rpx solid var(--sf-border);border-radius:20rpx;padding:25rpx 28rpx}.intro-icon{width:68rpx;height:68rpx;border-radius:18rpx;display:flex;align-items:center;justify-content:center;font-size:44rpx;flex-shrink:0}.intro-in{background:var(--sf-green-soft);color:var(--sf-green)}.intro-out{background:var(--sf-orange-soft);color:var(--sf-orange)}.intro-title{font-size:28rpx;font-weight:700;margin-bottom:4rpx}
.line-card{padding:26rpx}.line-heading{font-size:28rpx;font-weight:700;border-bottom:1rpx solid var(--sf-border);padding-bottom:18rpx;margin-bottom:12rpx}.scan-row{margin:20rpx 0}.quantity-hint{margin:18rpx 0 10rpx;background:var(--sf-soft);border-radius:10rpx;padding:12rpx 15rpx}.code-input{flex:1;min-width:0}.code-line,.box-record{padding:16rpx 0;border-bottom:1rpx solid var(--sf-border)}.box-record{background:var(--sf-input);border:1rpx solid var(--sf-border);border-radius:12rpx;margin:12rpx 0;padding:17rpx}.code{overflow-wrap:anywhere;flex:1;font-size:24rpx}.remove{color:var(--sf-danger);white-space:nowrap;font-size:24rpx}.remark{width:100%;height:130rpx}.add-line{border:1rpx dashed #d3a7bf;background:var(--sf-soft);width:100%}.submit-button{margin-top:10rpx;width:100%}.input-error{border-color:var(--sf-danger);background:var(--sf-danger-soft)}.validation-error{font-size:22rpx;color:var(--sf-danger);margin-top:8rpx}
.chooser{position:fixed;inset:0;background:rgba(11,30,51,.45);display:flex;align-items:flex-end;z-index:6}.chooser .card{width:100%;margin:0;border-radius:24rpx 24rpx 0 0;padding-bottom:calc(30rpx + env(safe-area-inset-bottom))}.choices{max-height:55vh}.choice{padding:22rpx 0;border-bottom:1rpx solid var(--sf-border)}
</style>


