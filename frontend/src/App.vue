<script setup lang="ts">
import { onLaunch } from '@dcloudio/uni-app'
onLaunch(() => {})
</script>
<style>
page{--sf-bg:#fff8fb;--sf-card:#fff;--sf-text:#30293a;--sf-subtext:#716577;--sf-primary:#9b3c71;--sf-primary-dark:#81305e;--sf-soft:#fceaf3;--sf-lilac:#ede3f7;--sf-border:#f0e4ed;--sf-input:#fffafd;--sf-green:#207b5c;--sf-green-soft:#e6f5ef;--sf-orange:#a95f3e;--sf-orange-soft:#fff0e8;--sf-danger:#b44761;--sf-danger-soft:#fff0f3;background:var(--sf-bg);color:var(--sf-text);font-size:28rpx;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
view,input,textarea,button{box-sizing:border-box}
.card{background:var(--sf-card);border:1rpx solid var(--sf-border);border-radius:22rpx;padding:28rpx;margin-bottom:20rpx;box-shadow:0 7rpx 24rpx rgba(87,43,75,.045)}
.section-title{font-size:31rpx;font-weight:700;margin:30rpx 0 18rpx;letter-spacing:.3rpx}
.muted{color:var(--sf-subtext);font-size:24rpx;line-height:1.55}
.row{display:flex;align-items:center;justify-content:space-between;gap:16rpx}
.gap{gap:14rpx}
.field{margin-bottom:24rpx}
.label{display:block;color:var(--sf-subtext);font-size:25rpx;font-weight:600;margin-bottom:12rpx}
.input{display:block;width:100%;background:var(--sf-input);border:1rpx solid var(--sf-border);border-radius:14rpx;padding:17rpx 20rpx;min-height:78rpx;font-size:28rpx;color:var(--sf-text)}
.btn{background:var(--sf-primary);color:#fff;border-radius:14rpx;font-size:28rpx;font-weight:650;line-height:82rpx;min-height:82rpx;margin:14rpx 0;box-shadow:none}
.btn::after{border:0}
.btn[disabled]{opacity:.55}
.btn-light{background:var(--sf-soft);color:var(--sf-primary-dark)}
.btn-danger{background:var(--sf-danger-soft);color:var(--sf-danger)}
.btn-small{font-size:24rpx;padding:0 19rpx;line-height:62rpx;min-height:62rpx;margin:0}
.pill{display:inline-block;background:var(--sf-soft);color:var(--sf-primary);padding:7rpx 18rpx;border-radius:99rpx;font-size:23rpx;font-weight:600;white-space:nowrap}
.divider{height:1rpx;background:var(--sf-border);margin:20rpx 0}
.empty-state{text-align:center;padding:72rpx 24rpx;color:var(--sf-subtext);font-size:25rpx}
</style>

