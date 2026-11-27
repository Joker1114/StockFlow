<script setup lang="ts">
import { ref, watch } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { api, getToken, message, setToken, type User } from '@/api/client'

const username = ref('')
const password = ref('')
const busy = ref(false)
const loginError = ref('')
watch([username,password],()=>{loginError.value=''})

onLoad(async () => {
  if (!getToken()) return
  try {
    await api<User>('/auth/me')
    uni.reLaunch({url:'/pages/index/index'})
  } catch { /* 过期令牌由 API 客户端清除 */ }
})

async function login() {
  if (busy.value) return
  loginError.value=''
  if (!username.value.trim() || !password.value) return uni.showToast({title:'请输入账号和密码',icon:'none'})
  busy.value = true
  try {
    const result = await api<{token:string}>('/auth/login','POST', {username:username.value.trim(),password:password.value})
    setToken(result.token)
    password.value = ''
    uni.reLaunch({url:'/pages/index/index'})
  } catch (error) {
    loginError.value=message(error)
  } finally { busy.value = false }
}
</script>

<template>
  <view class="login-screen">
    <view class="login-header"><view class="brand-mark">♡</view><view><view class="brand-name">物资通</view><view class="brand-en">STOCKFLOW</view></view></view>
    <view class="login-main">
      <view class="welcome-label">WELCOME</view>
      <view class="login-title">欢迎登录</view>
      <view class="muted intro">连接您的库存管理工作台</view>
      <view class="card login-card">
        <view class="field"><text class="label">登录账号</text><input v-model="username" class="input" maxlength="64" placeholder="请输入工号或原账号" /></view>
        <view class="field"><text class="label">密码</text><input v-model="password" class="input" :password="true" :maxlength="-1" placeholder="请输入密码" /></view>
        <button class="btn login-button" :disabled="busy" @click="login">{{ busy ? '登录中…' : '登录' }}</button>
        <view v-if="loginError" class="login-error">{{ loginError }}</view>
      </view>
    </view>
    <view class="login-footer">共享库存 · 扫码出入库</view>
  </view>
</template>

<style scoped>
.login-screen{min-height:100vh;padding:calc(72rpx + env(safe-area-inset-top)) 34rpx calc(45rpx + env(safe-area-inset-bottom));display:flex;flex-direction:column;background:radial-gradient(circle at 100% 0,var(--sf-lilac) 0,transparent 44%),var(--sf-bg)}
.login-header{display:flex;align-items:center;gap:17rpx;max-width:900rpx;width:100%;margin:0 auto}.brand-mark{width:70rpx;height:70rpx;border-radius:18rpx;background:var(--sf-primary);color:#fff;display:flex;align-items:center;justify-content:center;font-size:43rpx}.brand-name{font-size:30rpx;font-weight:750;line-height:1.2}.brand-en{font-size:18rpx;letter-spacing:2rpx;color:var(--sf-subtext);margin-top:5rpx}
.login-main{width:100%;max-width:900rpx;margin:auto}.welcome-label{font-size:20rpx;letter-spacing:3rpx;color:var(--sf-primary);font-weight:700}.login-title{font-size:50rpx;font-weight:760;margin:10rpx 0}.intro{margin-bottom:32rpx}.login-card{padding:34rpx 30rpx;border-radius:24rpx;box-shadow:0 16rpx 50rpx rgba(87,43,75,.07)}.login-card .field{margin-bottom:27rpx}.login-button{margin:12rpx 0 0;width:100%}
.login-footer{text-align:center;color:var(--sf-subtext);font-size:22rpx;padding-top:35rpx}
.login-error{margin-top:17rpx;padding:16rpx 18rpx;background:var(--sf-danger-soft);border:1rpx solid #f0d3ce;border-radius:11rpx;color:var(--sf-danger);font-size:23rpx;line-height:1.5}
</style>

