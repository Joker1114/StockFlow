<script setup lang="ts">
import { computed, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { api, go, message, type Company, type User } from '@/api/client'
import { confirmAction, requireAdmin, useDraftGuard } from '@/utils/management'
import AppShell from '@/components/AppShell.vue'

const users=ref<User[]>([])
const companies=ref<Company[]>([])
const currentUserId=ref(0)
const username=ref('')
const employeeName=ref('')
const companyId=ref<number|null>(null)
const editingId=ref<number|null>(null)
const password=ref('')
const role=ref<'ADMIN'|'STAFF'>('STAFF')
const formOpen=ref(false)
const resetId=ref<number|null>(null)
const resetPassword=ref('')
const query=ref('')
const busy=ref(false)
const loading=ref(false)
const errorText=ref('')
const isEmployeeNumber=(value:string)=>/^[0-9]{1,64}$/.test(value)
const editingUser=computed(()=>users.value.find(user=>user.id===editingId.value))
const companyOptions=computed(()=>[
  {id:null,label:'请选择所属公司'},
  ...companies.value
    .filter(department=>department.is_active || department.id===editingUser.value?.department_id)
    .map(department=>({id:department.id,label:department.name+(department.is_active?'':'（已停用）')})),
])
const companyIndex=computed(()=>Math.max(0,companyOptions.value.findIndex(department=>department.id===companyId.value)))
const filtered=computed(()=>{
  const keyword=query.value.trim().toLowerCase()
  return users.value.filter(user=>[user.username,user.name,user.department_name]
    .some(value=>value?.toLowerCase().includes(keyword)))
})
const initialNumber=(user?:User)=>user && isEmployeeNumber(user.username) ? user.username : ''
const profileDraft=computed(()=>formOpen.value && (
  username.value.trim()!==initialNumber(editingUser.value) ||
  employeeName.value.trim()!==(editingUser.value?.name ?? '') ||
  companyId.value!==(editingUser.value?.department_id ?? null) ||
  Boolean(password.value) || (editingId.value===null && role.value!=='STAFF')
))
const hasDraft=computed(()=>profileDraft.value || Boolean(resetPassword.value))
const allowLeave=useDraftGuard(hasDraft)
const minimumPasswordLength=10

function validPassword(value:string) {
  const length=Array.from(value).length
  if (length>=minimumPasswordLength && length<=256) return true
  uni.showToast({title:`密码须为 ${minimumPasswordLength} 至 256 位`,icon:'none'})
  return false
}
async function load() {
  loading.value=true;errorText.value=''
  try {
    if (!await requireAdmin()) return
    const [me,list,units]=await Promise.all([api<User>('/auth/me'),api<User[]>('/users'),api<Company[]>('/companies?include_inactive=true')])
    currentUserId.value=me.id;users.value=list;companies.value=units
  } catch (error) {errorText.value=message(error)}
  finally {loading.value=false}
}
onShow(load)
async function canDiscard() {
  return !hasDraft.value || await confirmAction('放弃未保存的修改？','当前表单中的内容将丢失。')
}
async function openForm(user?:User) {
  if (busy.value || !await canDiscard()) return
  resetId.value=null;resetPassword.value=''
  editingId.value=user?.id ?? null
  username.value=initialNumber(user)
  employeeName.value=user?.name ?? ''
  companyId.value=user?.department_id ?? null
  password.value=''
  role.value='STAFF'
  formOpen.value=true
  uni.pageScrollTo({scrollTop:0,duration:250})
}
async function closeForm() {
  if (!busy.value && await canDiscard()) formOpen.value=false
}
function chooseCompany(event:{detail:{value:unknown}}) {
  companyId.value=companyOptions.value[Number(event.detail.value)]?.id ?? null
}
async function save() {
  if (busy.value) return
  const number=username.value.trim()
  const name=employeeName.value.trim()
  const department_id=companyOptions.value[companyIndex.value]?.id
  if (!isEmployeeNumber(number)) return uni.showToast({title:'请输入纯数字工号',icon:'none'})
  if (!name) return uni.showToast({title:'请输入姓名',icon:'none'})
  if (!department_id) return uni.showToast({title:'请选择所属公司',icon:'none'})
  const id=editingId.value
  if (id===null && !validPassword(password.value)) return
  busy.value=true
  try {
    const profile={username:number,name,department_id}
    if (id===null) await api('/users','POST',{...profile,password:password.value,role:role.value})
    else await api('/users/'+id,'PATCH',profile)
    formOpen.value=false
    password.value=''
    await load()
    uni.showToast({title:id===null?'用户已创建':'用户资料已保存',icon:'none'})
  } catch (error) {uni.showToast({title:message(error),icon:'none'})}
  finally {busy.value=false}
}
async function startReset(u:User) {
  if (busy.value || !await canDiscard()) return
  formOpen.value=false;password.value=''
  resetId.value=u.id;resetPassword.value=''
}
async function closeReset() {
  if (resetPassword.value && !await confirmAction('放弃密码重置？','已输入的新密码将丢失。')) return
  resetId.value=null;resetPassword.value=''
}
async function changePassword() {
  if (busy.value || resetId.value===null) return
  const newPassword=resetPassword.value
  if (!validPassword(newPassword)) return
  const targetId=resetId.value
  const target=users.value.find(u=>u.id===targetId)
  busy.value=true
  try {
    if (!await confirmAction('确认重置密码？',`即将重置 ${target?.username||'该用户'} 的登录密码。`)) return
    await api('/users/'+targetId,'PATCH',{password:newPassword})
    resetId.value=null;resetPassword.value=''
    uni.showToast({title:'密码已重置',icon:'none'})
  } catch (error) {uni.showToast({title:message(error),icon:'none'})}
  finally {busy.value=false}
}
async function toggle(u:User) {
  if (u.id===currentUserId.value && u.is_active) return uni.showToast({title:'不能停用当前登录账号',icon:'none'})
  if (!await confirmAction(u.is_active?'停用用户？':'启用用户？',
    `${u.username} ${u.is_active?'停用后将无法登录。':'启用后可以重新登录。'}`)) return
  try {await api('/users/'+u.id,'PATCH',{is_active:!u.is_active});await load()}
  catch (error) {uni.showToast({title:message(error),icon:'none'})}
}
</script>

<template>
  <AppShell title="用户管理" subtitle="账号与权限" active="home" back :confirm-leave="hasDraft" @leave-confirmed="allowLeave=true">
    <button v-if="!formOpen && !loading && !errorText" class="btn add-button" @click="openForm()">＋ 新增用户</button>
    <view v-if="formOpen" class="card form-card"><view class="row form-head"><view class="section-title">{{ editingId===null?'新增用户':'编辑用户' }}</view><text class="text-action" @click="closeForm">取消</text></view>
      <view v-if="editingUser && !isEmployeeNumber(editingUser.username)" class="page-intro">原账号 {{ editingUser.username }}，保存后使用工号和原密码登录。</view>
      <view class="field"><text class="label">工号</text><input v-model="username" type="number" class="input" maxlength="64" placeholder="请输入纯数字工号" /></view>
      <view class="field"><text class="label">姓名</text><input v-model="employeeName" class="input" maxlength="100" placeholder="请输入员工姓名" /></view>
      <view class="field"><text class="label">所属公司</text>
        <picker v-if="companyOptions.length>1" :range="companyOptions" range-key="label" :value="companyIndex" @change="chooseCompany">
          <view class="input company-picker">{{ companyOptions[companyIndex].label }}<text>▾</text></view>
        </picker>
        <view v-else class="muted">暂无可选子公司 <text class="text-action" @click="go('settings/departments')">维护子公司 ›</text></view>
      </view>
      <template v-if="editingId===null">
        <view class="field"><text class="label">初始密码（至少 {{ minimumPasswordLength }} 位）</text><input v-model="password" :password="true" :maxlength="-1" class="input" placeholder="设置初始密码" /></view>
        <view class="field"><text class="label">角色</text><view class="options"><text class="pill" :class="{active:role==='STAFF'}" @click="role='STAFF'">普通用户</text><text class="pill" :class="{active:role==='ADMIN'}" @click="role='ADMIN'">管理员</text></view></view>
      </template>
      <button class="btn save-button" :disabled="busy || loading" @click="save">{{ busy?'保存中…':editingId===null?'创建用户':'保存资料' }}</button>
    </view>
    <view class="section-title list-title">用户列表 <text class="list-count">{{ filtered.length }} 人</text></view>
    <view class="card search-card"><input v-model="query" class="input" placeholder="搜索工号、姓名或公司" /><text v-if="query" class="text-action" @click="query=''">清除</text></view>
    <view v-if="errorText" class="card empty-state">{{ errorText }}<button class="btn btn-light retry" @click="load">重新加载</button></view>
    <view v-else-if="loading && !users.length" class="card empty-state">正在加载用户…</view>
    <view v-else-if="!filtered.length" class="card empty-state">{{ query?'没有匹配的用户':'暂无用户' }}</view>
    <view v-for="u in filtered" :key="u.id" class="card user-card">
      <view class="row user-top"><view class="user-name">{{ u.name || u.username }}<text v-if="u.id===currentUserId" class="self-label">当前账号</text></view><text class="pill" :class="u.is_active?'status-on':'status-off'">{{ u.is_active?'启用':'停用' }}</text></view>
      <view class="muted role-label">
        <text v-if="u.username!=='admin'">{{ isEmployeeNumber(u.username)?'工号 ':'原账号 ' }}{{ u.username }} · {{ u.department_name || '待补录所属公司' }} · </text>
        {{ u.role==='ADMIN'?'管理员':'普通用户' }}
      </view>
      <view class="row actions"><button v-if="u.username!=='admin'" class="btn btn-light btn-small" @click="openForm(u)">编辑资料</button><button class="btn btn-light btn-small" @click="startReset(u)">重置密码</button><button class="btn btn-danger btn-small" :disabled="u.id===currentUserId && Boolean(u.is_active)" @click="toggle(u)">{{ u.is_active?'停用':'启用' }}</button></view>
      <view v-if="resetId===u.id" class="reset-panel"><view class="row reset-head"><text>重置 {{ u.username }} 的密码</text><text class="text-action" @click="closeReset">取消</text></view><input v-model="resetPassword" :password="true" :maxlength="-1" class="input" :placeholder="`新密码至少 ${minimumPasswordLength} 位`" /><button class="btn save-button" :disabled="busy" @click="changePassword">{{ busy?'提交中…':'确认重置' }}</button></view>
    </view>
  </AppShell>
</template>

<style scoped>
.company-picker{display:flex;align-items:center;justify-content:space-between}
.page-intro{background:var(--sf-soft);border-radius:15rpx;padding:22rpx 25rpx;color:var(--sf-subtext);font-size:23rpx;line-height:1.5;margin-bottom:18rpx}.add-button,.save-button{width:100%}.form-card{padding:25rpx}.form-head{margin-bottom:20rpx}.form-head .section-title{margin:0}.text-action{color:var(--sf-primary);font-size:23rpx;font-weight:650;white-space:nowrap}.options{display:flex;gap:12rpx}.options .pill{padding:12rpx 25rpx}.options .active{background:var(--sf-primary);color:#fff}.list-title{display:flex;justify-content:space-between;align-items:center}.list-count{font-size:23rpx;color:var(--sf-subtext);font-weight:500}.search-card{display:flex;align-items:center;gap:15rpx;padding:17rpx}.search-card .input{flex:1;min-width:0}.user-card{padding:24rpx 27rpx}.user-name{font-size:28rpx;font-weight:700;flex:1;min-width:0;overflow-wrap:anywhere}.self-label{font-size:21rpx;color:var(--sf-primary);font-weight:500;margin-left:12rpx}.status-on{background:var(--sf-green-soft);color:var(--sf-green)}.status-off{background:#f0f1f3;color:#8793a0}.role-label{margin-top:7rpx}.actions{justify-content:flex-end;margin-top:18rpx}.reset-panel{border-top:1rpx solid #e6edf4;padding-top:20rpx;margin-top:22rpx}.reset-head{font-size:24rpx;font-weight:650;margin-bottom:15rpx}.retry{width:200rpx;margin:20rpx auto 0}
</style>


