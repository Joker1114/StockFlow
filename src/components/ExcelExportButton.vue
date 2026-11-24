<script setup lang="ts">
import { ref } from 'vue'
import { downloadExcel, message } from '@/api/client'

const props = defineProps<{path:string; filename:string; disabled?:boolean}>()
const busy = ref(false)

async function exportFile() {
  if (busy.value || props.disabled) return
  busy.value = true
  try {
    await downloadExcel(props.path, props.filename)
  } catch (error) {
    uni.showModal({title:'无法完成导出', content:message(error), showCancel:false})
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <button class="export-button" :disabled="disabled || busy" @click="exportFile">
    {{ busy ? '导出中…' : '导出 Excel' }}
  </button>
</template>

<style scoped>
.export-button{margin:0;padding:0 19rpx;border-radius:14rpx;background:var(--sf-soft);color:var(--sf-primary-dark);font-size:24rpx;font-weight:650;min-height:70rpx;line-height:70rpx;white-space:nowrap;flex-shrink:0}
.export-button::after{border:0}
.export-button[disabled]{opacity:.55}
</style>
