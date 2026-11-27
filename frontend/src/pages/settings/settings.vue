<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { go, message } from '@/api/client'
import { requireAdmin } from '@/utils/management'
import AppShell from '@/components/AppShell.vue'

const ready=ref(false)
const loading=ref(true)
const errorText=ref('')
async function load() {
  loading.value=true
  errorText.value=''
  try {ready.value=await requireAdmin()}
  catch (error) {errorText.value=message(error)}
  finally {loading.value=false}
}
onShow(load)
</script>

<template>
  <AppShell title="管理中心" subtitle="资料维护与账号权限" active="home" back>
    <view v-if="errorText" class="card empty-state">{{ errorText }}<button class="btn btn-light retry" @click="load">重新加载</button></view>
    <template v-else-if="ready">
      <view class="intro"><view class="intro-label">ADMINISTRATION</view><view class="intro-title">管理中心</view><view class="intro-note">按业务资料与账号权限分别管理，修改会立即应用于后续单据。</view></view>
      <view class="section-title">基础资料</view>
      <view class="card menu-card" @click="go('settings/products')"><view class="icon products">▦</view><view class="menu-copy"><view class="menu-title">物资管理</view><view class="muted">名称、规格、单位、每箱瓶数</view></view><text class="arrow">›</text></view>
      <view class="card menu-card" @click="go('settings/suppliers')"><view class="icon suppliers">▣</view><view class="menu-copy"><view class="menu-title">供应商管理</view><view class="muted">入库单可选的供应商</view></view><text class="arrow">›</text></view>
      <view class="card menu-card" @click="go('settings/departments')"><view class="icon products">⊞</view><view class="menu-copy"><view class="menu-title">组织机构</view><view class="muted">维护子公司</view></view><text class="arrow">›</text></view>
      <view class="card menu-card" @click="go('settings/rules')"><view class="icon rules">⌗</view><view class="menu-copy"><view class="menu-title">扫码规则</view><view class="muted">配置条码与物资的匹配关系</view></view><text class="arrow">›</text></view>
      <view class="section-title account-title">账号与权限</view>
      <view class="card menu-card" @click="go('settings/users')"><view class="icon users">♙</view><view class="menu-copy"><view class="menu-title">用户管理</view><view class="muted">维护工号、姓名和所属公司</view></view><text class="arrow">›</text></view>
    </template>
    <view v-else-if="loading" class="card empty-state">正在加载管理中心…</view>
  </AppShell>
</template>

<style scoped>
.intro{background:linear-gradient(125deg,var(--sf-soft),var(--sf-lilac));color:var(--sf-text);border-radius:22rpx;padding:32rpx 34rpx;margin-bottom:30rpx;box-shadow:0 10rpx 30rpx rgba(87,43,75,.07)}.intro-label{font-size:19rpx;letter-spacing:2rpx;color:var(--sf-primary);font-weight:700}.intro-title{font-size:37rpx;font-weight:750;margin:12rpx 0}.intro-note{font-size:23rpx;line-height:1.5;color:var(--sf-subtext)}
.menu-card{display:flex;align-items:center;gap:21rpx;padding:24rpx 26rpx;margin-bottom:15rpx}.icon{width:68rpx;height:68rpx;border-radius:16rpx;display:flex;align-items:center;justify-content:center;font-size:36rpx;flex-shrink:0}.products{background:var(--sf-soft);color:var(--sf-primary)}.suppliers{background:var(--sf-green-soft);color:var(--sf-green)}.rules{background:var(--sf-orange-soft);color:var(--sf-orange)}.users{background:var(--sf-lilac);color:#775589}.menu-copy{flex:1;min-width:0}.menu-title{font-size:28rpx;font-weight:700;margin-bottom:4rpx}.arrow{font-size:40rpx;color:#b5a1b7}.account-title{margin-top:36rpx}.retry{width:200rpx;margin:20rpx auto 0}
</style>

