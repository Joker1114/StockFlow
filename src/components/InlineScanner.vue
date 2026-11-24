<script setup lang="ts">
import { getCurrentInstance, nextTick, onMounted, onUnmounted, ref } from 'vue'
// #ifdef MP-WEIXIN
import WeixinScanCamera from './WeixinScanCamera.vue'
// #endif

declare const plus:any

type ScanResult = {status:'success'|'duplicate'|'error'; message:string; code?:string}
type ScanEntry = {code:string; time:string}
type ScanNotice = {status:'duplicate'|'error'; message:string}

const props = defineProps<{
  count:number
  processCode:(code:string)=>Promise<ScanResult>
}>()
const emit = defineEmits<{close:[]}>()
const instance = getCurrentInstance()
const cameraError = ref('')
const entries = ref<ScanEntry[]>([])
const notice = ref<ScanNotice|null>(null)
let active = true
let processing = false
let lastCode = ''
let lastScanAt = 0
let nativeBarcode:any = null
let stopWeb:(()=>void)|null = null
let restartTimer:ReturnType<typeof setTimeout>|null = null
let noticeTimer:ReturnType<typeof setTimeout>|null = null

function clearNotice() {
  if (noticeTimer!==null) clearTimeout(noticeTimer)
  noticeTimer=null
  notice.value=null
}

function showNotice(status:ScanNotice['status'], message:string) {
  clearNotice()
  notice.value={status,message}
  noticeTimer=setTimeout(clearNotice,3500)
}

function restartNative() {
  // #ifdef APP-PLUS
  restartTimer = setTimeout(() => {
    if (active && nativeBarcode) nativeBarcode.start({vibrate:false,sound:'none'})
  }, 450)
  // #endif
}

function vibrate(status:ScanResult['status']) {
  // #ifdef APP-PLUS || MP-WEIXIN
  if (status==='success') uni.vibrateShort({type:'heavy',fail:()=>{}})
  else if (status==='duplicate') uni.vibrateLong({fail:()=>{}})
  // #endif
}

async function detected(raw:string) {
  const code=raw.trim()
  if (!active || processing || !code) return
  const now=Date.now()
  // 原码仍停留在取景框时忽略自动重复识别；移开后再扫会收到重复提醒。
  if (code===lastCode && now-lastScanAt<3000) { restartNative(); return }
  lastCode=code
  lastScanAt=now
  processing=true
  try {
    const result=await props.processCode(code)
    if (!active) return
    if (result.status==='success') {
      clearNotice()
      entries.value.unshift({code:result.code ?? code,time:new Date().toLocaleTimeString()})
      if (entries.value.length>30) entries.value.pop()
    } else {
      showNotice(result.status,result.message)
    }
    vibrate(result.status)
  } catch (error) {
    if (active) showNotice('error',error instanceof Error?error.message:'处理失败，请重试')
  } finally {
    processing=false
    restartNative()
  }
}

async function startCamera() {
  // #ifdef H5
  if (!navigator.mediaDevices?.getUserMedia) {
    cameraError.value='浏览器相机需要 HTTPS 或 localhost 环境'
    return
  }
  try {
    const host=document.getElementById('inline-camera-host')
    if (!host) throw new Error('扫码区域尚未就绪')
    const video=document.createElement('video')
    video.setAttribute('playsinline','')
    video.muted=true
    video.autoplay=true
    video.style.cssText='width:100%;height:100%;object-fit:cover;display:block;'
    host.appendChild(video)
    const { BrowserMultiFormatReader }=await import('@zxing/browser')
    if (!active) return
    const reader=new BrowserMultiFormatReader(undefined,{delayBetweenScanSuccess:350,delayBetweenScanAttempts:150})
    const controls=await reader.decodeFromVideoDevice(undefined,video,result=>{
      if (result) void detected(result.getText())
    })
    if (!active) controls.stop()
    else stopWeb=()=>controls.stop()
  } catch (error) {
    if (active) cameraError.value=error instanceof Error?`相机启动失败：${error.message}`:'相机启动失败'
  }
  // #endif

  // #ifdef APP-PLUS
  try {
    const pages=getCurrentPages()
    const page=pages[pages.length-1] as any
    const webview=page?.$getAppWebview?.()
    if (!webview) throw new Error('当前页面尚未准备好，请关闭后重试')
    const bounds=await new Promise<{top:number;left:number;width:number;height:number;panelTop?:number}>(resolve=>{
      const query=uni.createSelectorQuery().in(instance?.proxy as any)
      query.select('#inline-camera-host').boundingClientRect()
      query.selectViewport().scrollOffset(()=>{})
      query.select('#inline-scanner-panel').boundingClientRect()
      query.exec((data:any[])=>{
        const rect=data?.[0]
        const scrollTop=Number(data?.[1]?.scrollTop||0)
        if (!rect) {
          resolve({top:0,left:0,width:0,height:0})
          return
        }
        const panel=data?.[2]
        resolve({
          top:rect.top+scrollTop,
          left:rect.left,
          width:rect.width,
          height:rect.height,
          panelTop:panel ? panel.top+scrollTop : undefined
        })
      })
    })
    if (!active) return
    if (!bounds.width || !bounds.height) throw new Error('无法定位扫码区域，请关闭后重试')
    nativeBarcode=plus.barcode.create(`stockflow-inline-${Date.now()}`,
      [plus.barcode.QR,plus.barcode.EAN13,plus.barcode.EAN8,plus.barcode.CODE128,plus.barcode.CODE39,plus.barcode.CODE93],
      {top:`${bounds.top}px`,left:`${bounds.left}px`,width:`${bounds.width}px`,height:`${bounds.height}px`,position:'static',background:'#231b2a',frameColor:'#e999c2',scanbarColor:'#e999c2'})
    nativeBarcode.onmarked=(_type:number,code:string)=>{void detected(code)}
    nativeBarcode.onerror=(error:any)=>{if (active) cameraError.value=error?.message?`相机扫码失败：${error.message}`:'相机扫码失败，请检查相机权限'}
    webview.append(nativeBarcode)
    nativeBarcode.start({vibrate:false,sound:'none'})
    if (bounds.panelTop!==undefined) {
      uni.pageScrollTo({scrollTop:Math.max(0,bounds.panelTop-8),duration:200})
    }
  } catch (error) {
    if (active) cameraError.value=error instanceof Error?`相机启动失败：${error.message}`:'相机启动失败'
  }
  // #endif
}

onMounted(async () => {
  await nextTick()
  if (!active) return
  // #ifdef MP-WEIXIN
  const query = uni.createSelectorQuery().in(instance?.proxy)
  query.select('#inline-scanner-panel').boundingClientRect()
  query.selectViewport().scrollOffset(() => {})
  query.exec(([panel, viewport]) => {
    if (active && panel && viewport) {
      uni.pageScrollTo({ scrollTop: Math.max(0, panel.top + viewport.scrollTop - 12), duration: 200 })
    }
  })
  // #endif
  await startCamera()
})
onUnmounted(()=>{
  active=false
  clearNotice()
  if (restartTimer) clearTimeout(restartTimer)
  if (stopWeb) stopWeb()
  if (nativeBarcode) {nativeBarcode.cancel();nativeBarcode.close();nativeBarcode=null}
})
</script>

<template>
  <view id="inline-scanner-panel" class="scanner-panel">
    <view class="panel-heading"><view><view class="panel-title">连续扫码</view><view class="panel-subtitle">对准二维码或条码，识别后继续扫描</view></view><text class="close" @click="emit('close')">结束</text></view>
    <view id="inline-camera-host" class="camera-host">
      <!-- #ifdef MP-WEIXIN -->
      <WeixinScanCamera @scan="detected" />
      <!-- #endif -->
      <!-- #ifdef H5 -->
      <view v-if="!cameraError" class="camera-guide" aria-hidden="true" />
      <!-- #endif -->
      <view v-if="cameraError" class="camera-error">{{ cameraError }}</view>
    </view>
    <view v-if="cameraError" class="camera-error-note">{{ cameraError }}</view>
    <view v-else class="scan-notice" :class="notice?.status" role="status" aria-live="polite">
      <view v-if="notice" class="notice-content">
        <text class="notice-icon" aria-hidden="true">!</text>
        <view class="notice-copy">
          <text class="notice-title">{{ notice.status==='duplicate' ? '重复扫码' : '扫码失败' }}</text>
          <text class="notice-message">{{ notice.message }}</text>
        </view>
      </view>
      <!-- #ifdef APP-PLUS || MP-WEIXIN -->
      <text v-else>成功短震 · 重复长震</text>
      <!-- #endif -->
    </view>
    <view class="result-heading"><text>成功扫码记录</text><text>已录入 {{ count }} 个</text></view>
    <view v-if="!entries.length" class="empty">暂无成功扫码记录</view>
    <view v-for="(entry,index) in entries" :key="`${entry.time}-${index}`" class="scan-entry">
      <text class="entry-code">{{ entry.code }}</text>
      <text class="entry-time">{{ entry.time }}</text>
    </view>
  </view>
</template>

<style scoped>
.scanner-panel{margin:18rpx 0 24rpx;border:1rpx solid var(--sf-border);background:var(--sf-soft);border-radius:19rpx;padding:16rpx 12rpx;overflow:hidden}
.panel-heading{display:flex;align-items:center;justify-content:space-between;gap:16rpx;margin-bottom:15rpx}.panel-title{font-size:27rpx;font-weight:720;color:var(--sf-text)}.panel-subtitle{font-size:21rpx;color:var(--sf-subtext);margin-top:5rpx}.close{padding:10rpx 20rpx;background:var(--sf-card);border-radius:99rpx;color:var(--sf-primary);font-size:22rpx;white-space:nowrap}
.camera-host{width:100%;height:550rpx;max-height:48vh;background:#231b2a;border-radius:13rpx;position:relative;overflow:hidden}
/* #ifdef APP-PLUS || MP-WEIXIN */
.scanner-panel{margin-left:-24rpx;margin-right:-24rpx}
.camera-host{height:660rpx;max-height:60vh}
/* #endif */
.camera-guide{position:absolute;inset:8%;z-index:1;border:3rpx solid #e999c2;border-radius:15rpx;pointer-events:none}
.camera-error{position:absolute;left:8%;right:8%;top:35%;text-align:center;background:rgba(8,21,35,.9);color:#fff;padding:22rpx;border-radius:12rpx;font-size:23rpx;line-height:1.5}
.camera-error-note{font-size:22rpx;color:var(--sf-danger);padding:10rpx 2rpx;line-height:1.4}
.scan-notice{display:flex;align-items:center;min-height:50rpx;margin-top:10rpx;padding:8rpx 12rpx;border-radius:10rpx;color:var(--sf-subtext);font-size:22rpx;line-height:1.45;overflow-wrap:anywhere}
.scan-notice.duplicate,.scan-notice.error{padding:16rpx;color:#fff}
.scan-notice.duplicate{background:#854400}
.scan-notice.error{background:#941d3e}
.notice-content{display:flex;align-items:center;gap:14rpx;width:100%}
.notice-icon{display:flex;align-items:center;justify-content:center;flex-shrink:0;width:42rpx;height:42rpx;border:2rpx solid currentColor;border-radius:50%;font-size:28rpx;font-weight:700}
.notice-copy{flex:1;min-width:0}
.notice-title,.notice-message{display:block}
.notice-title{font-size:28rpx;font-weight:700}
.notice-message{font-size:25rpx}
.result-heading{display:flex;justify-content:space-between;align-items:center;margin-top:16rpx;font-size:25rpx;font-weight:700;color:var(--sf-text)}.result-heading text:last-child{font-size:22rpx;font-weight:550;color:var(--sf-primary)}.empty{color:var(--sf-subtext);font-size:23rpx;text-align:center;padding:34rpx 0 16rpx}
.scan-entry{display:flex;justify-content:space-between;align-items:center;gap:12rpx;margin-top:13rpx;padding:15rpx 18rpx;background:#f4fbf7;border:1rpx solid #c9e7d9;border-radius:12rpx}
.entry-code{min-width:0;overflow-wrap:anywhere;font-size:24rpx;font-weight:700;color:var(--sf-text)}
.entry-time{font-size:21rpx;color:var(--sf-subtext);white-space:nowrap}
</style>


