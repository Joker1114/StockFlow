<template>
  <view class="assistant" aria-label="微笑的库存助手">
    <view class="hair" />
    <view class="face" />
    <view class="fringe" />
    <view class="eye eye-left" />
    <view class="eye eye-right" />
    <view class="blush blush-left" />
    <view class="blush blush-right" />
    <view class="mouth" />
    <view class="bow">◆</view>
    <view class="shirt" />
  </view>
</template>

<style scoped>
.assistant{position:relative;width:168rpx;height:202rpx;flex-shrink:0;overflow:hidden}
.assistant view{position:absolute;box-sizing:border-box}
.hair{left:25rpx;top:11rpx;width:126rpx;height:150rpx;background:#63446d;border-radius:46% 46% 34% 34%}
.face{left:45rpx;top:47rpx;width:87rpx;height:105rpx;background:#f8d4c5;border-radius:43% 43% 48% 48%;z-index:2}
.fringe{left:38rpx;top:34rpx;width:100rpx;height:52rpx;background:#63446d;border-radius:48% 50% 30% 12%;transform:rotate(-5deg);z-index:3}
.eye{top:102rpx;width:8rpx;height:12rpx;background:#63446d;border-radius:50%;z-index:4}.eye-left{left:70rpx}.eye-right{left:104rpx}
.blush{top:121rpx;width:16rpx;height:7rpx;background:#d983a6;border-radius:50%;opacity:.65;z-index:4}.blush-left{left:56rpx}.blush-right{left:108rpx}
.mouth{left:84rpx;top:129rpx;width:14rpx;height:8rpx;border-bottom:3rpx solid #a84c76;border-radius:50%;z-index:4}
.bow{left:15rpx;top:42rpx;color:#b64d82;font-size:31rpx;z-index:5;line-height:1}
.shirt{left:18rpx;top:150rpx;width:143rpx;height:85rpx;background:#fffafd;border-radius:50% 50% 0 0;z-index:1}
</style>
