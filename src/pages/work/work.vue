<script setup lang="ts">
import { go } from '@/api/client'
import AppShell from '@/components/AppShell.vue'

function startReturn() {
  go('history/history?filter=OUT&mode=return')
}
</script>

<template>
  <AppShell title="业务办理" subtitle="选择业务类型，按步骤完成登记" active="work">
    <view class="guide"><view class="guide-mark">01—04</view><view class="guide-title">今天要办理什么业务？</view><view class="guide-copy">每笔操作保存后都会更新库存，并生成可追溯的单据。</view></view>

    <view class="section-head"><view class="section-title">日常出入库</view><text>01 / 02</text></view>
    <view class="action-card" @click="go('edit/edit?direction=IN')">
      <view class="action-icon in">↓</view><view class="action-copy"><view class="action-title">采购入库</view><view class="action-note">选择供应商，录入箱码与散瓶</view></view><text class="chevron">›</text>
    </view>
    <view class="action-card" @click="go('edit/edit?direction=OUT')">
      <view class="action-icon out">↑</view><view class="action-copy"><view class="action-title">领用出库</view><view class="action-note">选择领用公司，登记出库物资</view></view><text class="chevron">›</text>
    </view>

    <view class="section-head secondary"><view class="section-title">退回与盘点</view><text>03 / 04</text></view>
    <view class="action-card" @click="startReturn">
      <view class="action-icon returned">↩</view><view class="action-copy"><view class="action-title">关联退库</view><view class="action-note">先选择原出库单，再登记退回数量</view></view><text class="chevron">›</text>
    </view>
    <view class="adjust-card">
      <view class="adjust-head"><view class="action-icon adjust">±</view><view class="action-copy"><view class="action-title">库存调整</view><view class="action-note">盘点差异、破损等情况须填写原因</view></view></view>
      <view class="adjust-actions"><view @click="go('edit/edit?kind=ADJUST&direction=IN')">盘盈 / 增加 <text>›</text></view><view @click="go('edit/edit?kind=ADJUST&direction=OUT')">盘亏 / 减少 <text>›</text></view></view>
    </view>
  </AppShell>
</template>

<style scoped>
.guide{background:linear-gradient(125deg,var(--sf-soft),var(--sf-lilac));color:var(--sf-text);border-radius:24rpx;padding:32rpx 34rpx 35rpx;margin-bottom:34rpx;box-shadow:0 12rpx 30rpx rgba(87,43,75,.075)}
.guide-mark{font-size:20rpx;letter-spacing:3rpx;font-weight:700;color:var(--sf-primary)}.guide-title{font-size:34rpx;font-weight:750;margin-top:13rpx}.guide-copy{font-size:23rpx;line-height:1.5;color:var(--sf-subtext);margin-top:10rpx}
.section-head{display:flex;align-items:center;justify-content:space-between;margin:0 0 17rpx}.section-head .section-title{margin:0}.section-head text{font-size:21rpx;color:var(--sf-subtext);font-weight:650;letter-spacing:1rpx}.section-head.secondary{margin-top:34rpx}
.action-card,.adjust-card{background:var(--sf-card);border:1rpx solid var(--sf-border);border-radius:20rpx;padding:25rpx 27rpx;box-shadow:0 5rpx 20rpx rgba(87,43,75,.04);margin-bottom:16rpx}
.action-card,.adjust-head{display:flex;align-items:center;gap:20rpx}.action-icon{width:72rpx;height:72rpx;border-radius:18rpx;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:41rpx;font-weight:500}
.action-icon.in{background:var(--sf-soft);color:var(--sf-primary)}.action-icon.out{background:var(--sf-lilac);color:#775589}.action-icon.returned{background:var(--sf-green-soft);color:var(--sf-green)}.action-icon.adjust{background:#f1ecfb;color:#775589}
.action-copy{flex:1;min-width:0}.action-title{font-size:28rpx;font-weight:720;color:var(--sf-text)}.action-note{font-size:22rpx;color:var(--sf-subtext);line-height:1.4;margin-top:7rpx}.chevron{font-size:41rpx;color:#b5a1b7;margin-left:4rpx}
.adjust-actions{display:flex;gap:14rpx;margin-top:23rpx}.adjust-actions>view{flex:1;display:flex;align-items:center;justify-content:space-between;background:var(--sf-input);border:1rpx solid var(--sf-border);border-radius:13rpx;padding:17rpx 19rpx;color:var(--sf-primary-dark);font-size:23rpx;font-weight:650}.adjust-actions text{font-size:33rpx;line-height:.7;color:#b5a1b7}
</style>

