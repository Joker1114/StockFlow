<script setup lang="ts">
const props = withDefaults(defineProps<{
  title:string
  subtitle?:string
  active?:'home'|'work'|'stock'|'history'
  back?:boolean
  confirmLeave?:boolean
}>(), {subtitle:'', back:false, confirmLeave:false})
const emit=defineEmits<{leaveConfirmed:[]}>()

function getHeaderPaddingTop(): string | undefined {
  // #ifdef MP-WEIXIN || APP-PLUS
  const windowInfo = uni.getWindowInfo?.() ?? uni.getSystemInfoSync()
  const safeTop = Math.max(windowInfo.statusBarHeight ?? 0, windowInfo.safeArea?.top ?? 0, windowInfo.safeAreaInsets?.top ?? 0)
  const screenTop = 'screenTop' in windowInfo ? windowInfo.screenTop ?? 0 : 0
  let headerTop = safeTop
  // #ifdef MP-WEIXIN
  const capsule = uni.getMenuButtonBoundingClientRect?.()
  headerTop = capsule && capsule.height > 0 && capsule.bottom > safeTop ? capsule.bottom + 4 : safeTop + 44
  // #endif
  return `${Math.max(0, Math.ceil(headerTop - screenTop))}px`
  // #endif
}

const headerPaddingTop = getHeaderPaddingTop()

const tabs = [
  {key:'home', label:'工作台', icon:'home', url:'/pages/index/index'},
  {key:'work', label:'业务', icon:'work', url:'/pages/work/work'},
  {key:'stock', label:'库存', icon:'stock', url:'/pages/stock/stock'},
  {key:'history', label:'单据', icon:'history', url:'/pages/history/history'}
] as const

function leave(action:()=>void) {
  if (!props.confirmLeave) return action()
  uni.showModal({title:'放弃未保存的内容？',content:'当前填写和扫码记录尚未保存，离开后需要重新录入。',
    confirmText:'放弃离开',confirmColor:'#b44761',success:result=>{if (result.confirm) {emit('leaveConfirmed');action()}}})
}
function navigate(url:string) {
  const pages=getCurrentPages()
  const current=pages[pages.length-1] as any
  if (current?.route===url.slice(1) && !Object.keys(current?.options||{}).length) return
  leave(()=>uni.reLaunch({url}))
}
function goBack() {
  leave(()=>{
    const pages = getCurrentPages()
    if (pages.length > 1) uni.navigateBack()
    else uni.reLaunch({url:'/pages/index/index'})
  })
}
</script>

<template>
  <view class="shell">
    <view class="shell-header" :style="{ paddingTop: headerPaddingTop }">
      <view class="header-inner">
        <view v-if="back" class="back-button" @click="goBack"><text>‹</text></view>
        <view class="header-copy">
          <view class="header-kicker">物资通 · STOCKFLOW</view>
          <view class="header-title">{{ title }}</view>
          <view v-if="subtitle" class="header-subtitle">{{ subtitle }}</view>
        </view>
        <view class="header-action"><slot name="action" /></view>
      </view>
    </view>

    <view class="shell-main"><slot /></view>

    <view class="bottom-nav">
      <view class="bottom-nav-inner">
        <view v-for="item in tabs" :key="item.key" class="nav-item" :class="{'is-active':active===item.key}" @click="navigate(item.url)">
          <image class="nav-icon" :src="`/static/nav/${item.icon}${active===item.key?'-active':''}.svg`" mode="aspectFit" />
          <text>{{ item.label }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<style scoped>
.shell{min-height:100vh;background:var(--sf-bg);color:var(--sf-text)}
.shell-header{background:var(--sf-card);border-bottom:1rpx solid var(--sf-border);padding-top:env(safe-area-inset-top,0px)}
.header-inner{max-width:1080rpx;margin:0 auto;min-height:126rpx;padding:18rpx 30rpx 22rpx;display:flex;align-items:center;gap:18rpx;box-sizing:border-box}
.header-copy{flex:1;min-width:0}
.header-kicker{color:var(--sf-primary);font-size:19rpx;font-weight:700;letter-spacing:2rpx;margin-bottom:6rpx}
.header-title{font-size:38rpx;font-weight:750;line-height:1.2;letter-spacing:.5rpx}
.header-subtitle{font-size:23rpx;color:var(--sf-subtext);margin-top:7rpx}
.header-action{flex-shrink:0}
.back-button{width:60rpx;height:60rpx;border-radius:16rpx;background:var(--sf-soft);color:var(--sf-primary);display:flex;align-items:center;justify-content:center;flex-shrink:0}
.back-button text{font-size:54rpx;line-height:1;transform:translateY(-4rpx)}
.shell-main{max-width:1080rpx;margin:0 auto;box-sizing:border-box;padding:28rpx 30rpx calc(170rpx + env(safe-area-inset-bottom))}
.bottom-nav{position:fixed;left:0;right:0;bottom:0;background:var(--sf-card);border-top:1rpx solid var(--sf-border);box-shadow:0 -8rpx 30rpx rgba(87,43,75,.055);padding-bottom:env(safe-area-inset-bottom);z-index:4}
.bottom-nav-inner{max-width:1080rpx;height:108rpx;margin:0 auto;display:flex;align-items:stretch}
.nav-item{flex:1;min-width:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6rpx;color:#938397;font-size:21rpx;font-weight:550}
.nav-item.is-active{color:var(--sf-primary);font-weight:700}
.nav-icon{width:39rpx;height:39rpx}
</style>

