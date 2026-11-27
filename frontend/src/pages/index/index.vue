<script setup lang="ts">
import { ref } from 'vue'
import { onHide, onShow, onUnload } from '@dcloudio/uni-app'
import { api, clearToken, go, localTime, message, type DocSummary, type Product, type User } from '@/api/client'
import AppShell from '@/components/AppShell.vue'
import StockAssistant from '@/components/StockAssistant.vue'

const user = ref<User | null>(null)
const recent = ref<DocSummary[]>([])
const stockedCount = ref<number|null>(null)
const documentCount = ref<number|null>(null)
const greeting = ref(currentGreeting())
let greetingTimer: ReturnType<typeof setInterval> | undefined

function currentGreeting() {
  const hour = new Date().getHours()
  if (hour < 5 || hour >= 18) return '晚上好'
  if (hour < 11) return '早上好'
  if (hour < 14) return '中午好'
  return '下午好'
}

function stopGreetingTimer() {
  clearInterval(greetingTimer)
  greetingTimer = undefined
}

onHide(stopGreetingTimer)
onUnload(stopGreetingTimer)
onShow(async () => {
  stopGreetingTimer()
  greeting.value = currentGreeting()
  greetingTimer = setInterval(() => { greeting.value = currentGreeting() }, 60_000)
  let authenticated=false
  try {
    user.value = await api<User>('/auth/me')
    authenticated=true
    const documents=await api<{items:DocSummary[];total:number}>('/documents?limit=5')
    recent.value=documents.items
    documentCount.value=documents.total
  } catch (error) { uni.showToast({title:message(error),icon:'none'}) }
  if (!authenticated) return
  try {stockedCount.value=(await api<Product[]>('/products')).filter(p=>p.stock_qty>0).length}
  catch {stockedCount.value=null}
})
function logout() {
  clearToken()
  uni.reLaunch({url:'/pages/login/login'})
}
</script>

<template>
  <AppShell title="工作台" subtitle="库存与单据概览" active="home">
    <template #action><button class="btn btn-light btn-small logout" @click="logout">退出登录</button></template>
    <view class="welcome-card">
      <view class="welcome-copy"><view class="welcome-kicker">今日也要顺利出入库 ♡</view>
        <view class="welcome-title">{{ greeting }}，{{ user?.name || user?.username || '用户' }}</view>
        <view class="welcome-note">库存与单据，一眼就清楚</view></view>
      <view class="mascot-wrap"><StockAssistant /></view>
    </view>
    <view class="summary-grid"><view class="summary-card"><text>在库物资</text><view>{{ stockedCount ?? '—' }}<text v-if="stockedCount!==null"> 种</text></view></view><view class="summary-card"><text>累计单据</text><view>{{ documentCount ?? '—' }}<text v-if="documentCount!==null"> 笔</text></view></view></view>
    <view class="row section-heading"><view class="section-title">常用操作</view><text class="more-link" @click="go('work/work')">全部业务 ›</text></view>
    <view class="quick-grid">
      <view class="quick-card" @click="go('edit/edit?direction=IN')"><view class="quick-icon in-icon">↓</view><view class="quick-name">新建入库单</view><view class="quick-note">扫码或填写数量入库</view><text class="quick-arrow">›</text></view>
      <view class="quick-card" @click="go('edit/edit?direction=OUT')"><view class="quick-icon out-icon">↑</view><view class="quick-name">新建出库单</view><view class="quick-note">核对库存后完成出库</view><text class="quick-arrow">›</text></view>
    </view>
    <view v-if="user?.role === 'ADMIN'" class="manage-link" @click="go('settings/settings')"><view><view class="manage-title">管理中心</view><view class="muted">基础资料与账号权限</view></view><text>›</text></view>
    <view class="row section-heading"><view class="section-title">最近单据</view><text class="more-link" @click="go('history/history')">查看全部 ›</text></view>
    <view v-if="!recent.length" class="card empty-state">暂无单据，创建第一张出入库单吧</view>
    <view v-for="d in recent" :key="d.id" class="card recent-card" @click="go('detail/detail?id=' + d.id)">
      <view class="row"><text class="doc-no">{{ d.doc_no }}</text><text class="pill" :class="d.direction==='IN'?'pill-in':'pill-out'">{{ d.kind==='RETURN'?'退库':d.kind==='ADJUST'?(d.direction==='IN'?'盘盈调整':'盘亏调整'):d.direction==='IN'?'入库':'出库' }}</text></view>
      <view class="muted recent-meta">{{ localTime(d.created_at) }} · {{ d.operator_name }}</view>
    </view>
  </AppShell>
</template>

<style scoped>
.logout{white-space:nowrap}
.welcome-card{position:relative;overflow:hidden;background:linear-gradient(125deg,var(--sf-soft),var(--sf-lilac));color:var(--sf-text);border-radius:24rpx;padding:31rpx 30rpx 35rpx;min-height:208rpx;box-shadow:0 10rpx 30rpx rgba(87,43,75,.075)}
.welcome-copy{position:relative;z-index:2;max-width:70%}.welcome-kicker{font-size:21rpx;color:var(--sf-primary);font-weight:650}
.welcome-title{font-size:37rpx;font-weight:750;margin:17rpx 0 10rpx;overflow-wrap:anywhere;line-height:1.3}
.welcome-note{font-size:23rpx;color:var(--sf-subtext)}
.mascot-wrap{position:absolute;right:10rpx;bottom:-13rpx;z-index:1}
.summary-grid{display:flex;gap:17rpx;margin-top:19rpx}.summary-card{flex:1;background:var(--sf-card);border:1rpx solid var(--sf-border);border-radius:19rpx;padding:18rpx 25rpx;box-shadow:0 5rpx 20rpx rgba(87,43,75,.035)}.summary-card>text{font-size:22rpx;color:var(--sf-subtext)}.summary-card>view{font-size:35rpx;font-weight:750;margin-top:4rpx}.summary-card>view text{font-size:22rpx;font-weight:500}
.quick-grid{display:flex;gap:18rpx}
.quick-card{position:relative;flex:1;min-width:0;background:var(--sf-card);border:1rpx solid var(--sf-border);border-radius:20rpx;padding:25rpx 22rpx 30rpx;box-shadow:0 5rpx 20rpx rgba(87,43,75,.04)}
.quick-icon{width:64rpx;height:64rpx;border-radius:17rpx;display:flex;align-items:center;justify-content:center;font-size:42rpx;font-weight:400;margin-bottom:23rpx}
.in-icon{background:var(--sf-soft);color:var(--sf-primary)}.out-icon{background:var(--sf-lilac);color:#775589}
.quick-name{font-size:28rpx;font-weight:700;white-space:nowrap}.quick-note{font-size:21rpx;color:var(--sf-subtext);margin-top:10rpx;line-height:1.35}
.quick-arrow{position:absolute;right:20rpx;top:25rpx;color:#b5a1b7;font-size:38rpx}
.manage-link{margin-top:20rpx;background:var(--sf-card);border:1rpx solid var(--sf-border);border-radius:18rpx;padding:22rpx 28rpx;display:flex;align-items:center;justify-content:space-between}
.manage-title{font-size:27rpx;font-weight:680;margin-bottom:4rpx}.manage-link>text{font-size:42rpx;color:#b5a1b7}
.section-heading{margin-top:8rpx}.section-heading .section-title{margin-bottom:16rpx}.more-link{font-size:23rpx;color:var(--sf-primary);font-weight:650}
.recent-card{padding:24rpx 28rpx}.doc-no{font-size:27rpx;font-weight:650;overflow-wrap:anywhere}.recent-meta{margin-top:10rpx}
.pill-in{background:var(--sf-green-soft);color:var(--sf-green)}.pill-out{background:var(--sf-orange-soft);color:var(--sf-orange)}
</style>
