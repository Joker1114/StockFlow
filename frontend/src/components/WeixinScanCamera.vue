<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

type CameraError = 'permission' | 'privacy' | 'privacy-not-configured' | 'unavailable' | 'stopped'

defineOptions({ options: { virtualHost: true } })
const emit = defineEmits<{ scan: [code: string] }>()
const platform = uni.getDeviceInfo?.()?.platform ?? uni.getSystemInfoSync().platform
const simulator = platform === 'devtools'
const error = ref<CameraError | null>(null)
const cameraAllowed = ref(false)
const cameraReady = ref(false)
const cameraSlow = ref(false)
const cameraRestarting = ref(false)
const nativeDialog = ref(false)
const scanError = ref('')
const cameraVisible = computed(() => cameraAllowed.value && !error.value && !cameraRestarting.value && !nativeDialog.value)
let mounted = true
let startupTimer: ReturnType<typeof setTimeout> | undefined
const errorMessages: Record<CameraError, string> = {
  permission: '请在小程序设置中允许使用摄像头。',
  privacy: '请同意小程序隐私保护指引后重试。',
  'privacy-not-configured': '小程序后台尚未声明扫码所需的摄像头用途。',
  unavailable: '相机启动失败。请确认手机系统允许微信使用摄像头后重试。',
  stopped: '相机已停止，点击重试继续扫码。',
}

watch(cameraVisible, visible => {
  clearTimeout(startupTimer)
  cameraReady.value = false
  cameraSlow.value = false
  if (visible) startupTimer = setTimeout(() => { cameraSlow.value = true }, 8000)
}, { immediate: true, flush: 'sync' })

onMounted(() => {
  if (!simulator) authorizeCamera()
})

onBeforeUnmount(() => {
  mounted = false
  clearTimeout(startupTimer)
})

function handleScan(event: { detail?: { result?: string } }) {
  const code = event.detail?.result
  if (cameraVisible.value && code) emit('scan', code)
}

function handleReady() {
  if (!cameraVisible.value) return
  clearTimeout(startupTimer)
  cameraReady.value = true
  cameraSlow.value = false
}

function showCameraError(detail?: { errno?: number; errMsg?: string }) {
  if (detail?.errno === 112 || /not declared|privacy api banned/i.test(detail?.errMsg ?? '')) {
    error.value = 'privacy-not-configured'
    return
  }
  if (/privacy|隐私/i.test(detail?.errMsg ?? '')) {
    error.value = 'privacy'
    return
  }
  if (/auth deny|permission denied|auth denied/i.test(detail?.errMsg ?? '')) {
    error.value = 'permission'
    return
  }
  error.value = 'unavailable'
  uni.getSetting({
    success: ({ authSetting }) => {
      if (mounted && error.value === 'unavailable' && authSetting['scope.camera'] === false) {
        error.value = 'permission'
      }
    },
  })
}

function authorizeCamera() {
  uni.authorize({
    scope: 'scope.camera',
    success: () => { if (mounted) cameraAllowed.value = true },
    fail: detail => { if (mounted) showCameraError(detail) },
  })
}

function handleError(event: { detail?: { errno?: number; errMsg?: string } }) {
  if (cameraVisible.value) showCameraError(event.detail)
}

function handleStop() {
  if (cameraVisible.value) error.value = 'stopped'
}

async function retryCamera() {
  scanError.value = ''
  if (error.value) {
    error.value = null
    if (!cameraAllowed.value) authorizeCamera()
    return
  }
  cameraRestarting.value = true
  await nextTick()
  if (mounted) cameraRestarting.value = false
}

function openCameraSettings() {
  if (nativeDialog.value) return
  scanError.value = ''
  nativeDialog.value = true
  uni.openSetting({
    success: ({ authSetting }) => {
      if (mounted && authSetting['scope.camera']) {
        cameraAllowed.value = true
        error.value = null
      }
    },
    fail: () => { if (mounted) scanError.value = '请从小程序右上角菜单进入设置，允许使用摄像头。' },
    complete: () => { if (mounted) nativeDialog.value = false },
  })
}

async function scanWithWeixin() {
  if (nativeDialog.value) return
  scanError.value = ''
  nativeDialog.value = true
  // 先卸载内嵌相机，避免两个界面同时占用摄像头。
  await nextTick()
  if (!mounted) return
  uni.scanCode({
    scanType: ['barCode', 'qrCode'],
    success: ({ result }) => { if (mounted && result) emit('scan', result) },
    fail: ({ errMsg }) => {
      if (!mounted || /cancel/i.test(errMsg)) return
      scanError.value = simulator ? '请在开发者工具点「真机调试」，用手机微信打开后扫码。' : '微信扫一扫启动失败，请检查微信的相机权限后重试。'
    },
    complete: () => { if (mounted) nativeDialog.value = false },
  })
}
</script>

<template>
  <view class="weixin-scan-window">
    <view class="camera-tools">
      <text v-if="scanError" class="camera-tool-error" role="status">{{ scanError }}</text>
      <text v-else-if="!simulator && !error && !nativeDialog && !cameraReady" class="camera-tool-hint" role="status">
        {{ cameraSlow ? '相机还未启动，可以重试或使用微信扫一扫。' : cameraAllowed ? '正在打开相机…' : '正在检查相机权限…' }}
      </text>
      <view class="camera-actions">
        <button v-if="error === 'permission'" class="btn btn-light btn-small camera-action" :disabled="nativeDialog" @click="openCameraSettings">相机设置</button>
        <button v-else-if="!simulator && (error || cameraSlow) && error !== 'privacy-not-configured'" class="btn btn-light btn-small camera-action" :disabled="nativeDialog" @click="retryCamera">重试相机</button>
        <button class="btn btn-light btn-small camera-action" :disabled="nativeDialog" @click="scanWithWeixin">微信扫一扫</button>
      </view>
    </view>
    <view class="weixin-preview">
      <camera
        v-if="cameraVisible"
        class="weixin-camera"
        mode="scanCode"
        device-position="back"
        @initdone="handleReady"
        @scancode="handleScan"
        @error="handleError"
        @rendererror="handleStop"
        @stop="handleStop"
      />
      <view v-else class="camera-status">
        <text v-if="nativeDialog">请在微信打开的窗口中操作。</text>
        <text v-else-if="simulator">连续扫码请在手机上测试。在开发者工具点击「真机调试」，再用手机微信打开。</text>
        <text v-else-if="error">{{ errorMessages[error] }}</text>
      </view>
    </view>
  </view>
</template>

<style scoped>
.weixin-scan-window{display:flex;flex-direction:column;width:100%;height:100%}
.weixin-preview{flex:1;min-height:0;width:100%;position:relative}
.weixin-camera{position:absolute;top:0;left:0;display:block;width:100%;height:100%}
.camera-status{height:100%;box-sizing:border-box;display:flex;align-items:center;justify-content:center;padding:26rpx;text-align:center;color:#fff;font-size:26rpx;line-height:1.5}
.camera-tools{flex-shrink:0;padding:12rpx 16rpx;background:#312638}
.camera-tool-hint,.camera-tool-error{display:block;margin-bottom:8rpx;color:#fff;font-size:23rpx;line-height:1.4}
.camera-tool-error{color:#ffc5d3}
.camera-actions{display:flex;flex-wrap:wrap;gap:10rpx;justify-content:flex-end}
.camera-action{margin:0}
</style>
