<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
// #ifdef MP-WEIXIN
import WeixinScanCamera from './WeixinScanCamera.vue'
// #endif

declare const plus:any

const props = defineProps<{
  count:number
  feedback:string
  tone:'success'|'error'|'info'
  processCode:(code:string)=>Promise<void>
}>()
const emit = defineEmits<{close:[]}>()
const cameraError = ref('')
let active = true
let processing = false
let lastCode = ''
let lastScanAt = 0
let nativeBarcode:any = null
let stopWeb:(()=>void)|null = null

function restartNative() {
  // #ifdef APP-PLUS
  setTimeout(() => {
    if (active && nativeBarcode) nativeBarcode.start({vibrate:false,sound:'none'})
  }, 500)
  // #endif
}

async function detected(code:string) {
  if (!active || processing || !code) return
  const currentTime = Date.now()
  if (code === lastCode && currentTime - lastScanAt < 2500) { restartNative(); return }
  lastCode = code
  lastScanAt = currentTime
  processing = true
  try { await props.processCode(code); cameraError.value = '' }
  catch (error) { cameraError.value = error instanceof Error ? error.message : '识别失败，请重试' }
  finally {
    processing = false
    restartNative()
  }
}

async function startCamera() {
  // #ifdef H5
  if (!navigator.mediaDevices?.getUserMedia) {
    cameraError.value = '浏览器相机需要 HTTPS 或 localhost 环境，请改用手动输入码值'
    return
  }
  try {
    const host = document.getElementById('scan-video-host')
    if (!host) throw new Error('扫码窗口尚未就绪')
    const video = document.createElement('video')
    video.setAttribute('playsinline','')
    video.muted = true
    video.autoplay = true
    video.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block;'
    host.appendChild(video)
    const { BrowserMultiFormatReader } = await import('@zxing/browser')
    if (!active) return
    const reader = new BrowserMultiFormatReader(undefined, {delayBetweenScanSuccess:350,delayBetweenScanAttempts:150})
    const controls = await reader.decodeFromVideoDevice(undefined, video, result => {
      if (result) void detected(result.getText())
    })
    if (!active) controls.stop()
    else stopWeb = () => { controls.stop() }
  } catch (error) {
    if (active) cameraError.value = error instanceof Error ? `相机启动失败：${error.message}` : '相机启动失败，请检查浏览器权限'
  }
  // #endif

  // #ifdef APP-PLUS
  try {
    const pages = getCurrentPages()
    const currentPage = pages[pages.length - 1] as any
    const appWebview = currentPage?.$getAppWebview?.()
    if (!appWebview) throw new Error('当前页面尚未准备好，请关闭扫码窗口后重试')
    const barcode = plus.barcode.create(`stockflow-continuous-${Date.now()}`,
      [plus.barcode.QR,plus.barcode.EAN13,plus.barcode.EAN8,plus.barcode.CODE128,plus.barcode.CODE39,plus.barcode.CODE93],
      {top:'16%',left:'0px',width:'100%',height:'52%',position:'absolute',background:'#231b2a',frameColor:'#e999c2',scanbarColor:'#e999c2'})
    nativeBarcode = barcode
    barcode.onmarked = (_type:number, code:string) => { void detected(code) }
    barcode.onerror = (error:any) => { if (active) cameraError.value = error?.message ? `相机扫码失败：${error.message}` : '相机扫码失败，请检查相机权限' }
    appWebview.append(barcode)
    barcode.start({vibrate:false,sound:'none'})
  } catch (error) {
    cameraError.value = error instanceof Error ? `相机启动失败：${error.message}` : '相机启动失败，请检查相机权限'
  }
  // #endif
}

onMounted(() => { void startCamera() })
onUnmounted(() => {
  active = false
  if (stopWeb) stopWeb()
  if (nativeBarcode) {
    nativeBarcode.cancel()
    nativeBarcode.close()
    nativeBarcode = null
  }
})
</script>

<template>
  <view class="scanner-screen">
    <view class="scanner-top">
      <view><view class="scanner-title">连续扫码</view><view class="scanner-subtitle">相机保持开启，逐个扫描条码或二维码</view></view>
      <view class="close-scan" @click="emit('close')">完成</view>
    </view>
    <view class="camera-area">
      <!-- #ifdef MP-WEIXIN -->
      <WeixinScanCamera @scan="detected" />
      <!-- #endif -->
      <!-- #ifndef MP-WEIXIN -->
      <view id="scan-video-host" class="video-host" />
      <view class="scan-frame"><view class="scan-line" /></view>
      <!-- #endif -->
      <view v-if="cameraError" class="camera-error">{{ cameraError }}</view>
    </view>
    <view class="scanner-bottom">
      <view class="scan-count"><text>当前物资已录入</text><strong>{{ count }}</strong><text> 个码</text></view>
      <view class="scan-feedback" :class="tone">{{ cameraError || feedback || '将条码放入取景框，识别后继续扫描下一件' }}</view>
      <button class="btn finish-button" @click="emit('close')">结束扫码，返回单据</button>
    </view>
  </view>
</template>

<style scoped>
.scanner-screen{position:fixed;inset:0;z-index:10;background:#231b2a;color:#fff;display:flex;flex-direction:column;padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom)}
.scanner-top{height:16%;min-height:110rpx;padding:26rpx 32rpx;display:flex;align-items:center;justify-content:space-between;gap:20rpx}.scanner-title{font-size:36rpx;font-weight:750}.scanner-subtitle{font-size:22rpx;color:#d9c8d8;margin-top:9rpx}.close-scan{border:1rpx solid #9b849d;border-radius:99rpx;padding:10rpx 24rpx;white-space:nowrap;font-size:24rpx}
.camera-area{position:relative;height:52%;background:#1b1620;overflow:hidden}.video-host{width:100%;height:100%}.scan-frame{position:absolute;left:12%;right:12%;top:19%;bottom:19%;border:4rpx solid rgba(233,153,194,.85);border-radius:20rpx;pointer-events:none}.scan-line{position:absolute;left:8%;right:8%;top:50%;height:2rpx;background:rgba(233,153,194,.65)}.camera-error{position:absolute;left:8%;right:8%;top:40%;text-align:center;background:rgba(29,20,34,.88);padding:24rpx;border-radius:12rpx;font-size:25rpx;line-height:1.5}
.scanner-bottom{flex:1;background:var(--sf-card);color:var(--sf-text);border-radius:28rpx 28rpx 0 0;margin-top:-12rpx;z-index:1;padding:30rpx 32rpx;display:flex;flex-direction:column;justify-content:center}.scan-count{font-size:25rpx;color:var(--sf-subtext)}.scan-count strong{font-size:42rpx;color:var(--sf-primary);margin-left:8rpx}.scan-feedback{font-size:26rpx;margin:18rpx 0;line-height:1.45;color:var(--sf-subtext);min-height:72rpx;overflow-wrap:anywhere}.scan-feedback.success{color:var(--sf-green)}.scan-feedback.error{color:var(--sf-danger)}.finish-button{width:100%;margin:0}
</style>


