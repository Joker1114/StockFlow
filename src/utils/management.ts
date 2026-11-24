import { ref, type Ref } from 'vue'
import { onBackPress } from '@dcloudio/uni-app'
import { api, type User } from '@/api/client'

export async function requireAdmin() {
  const user=await api<User>('/auth/me')
  if (user.role==='ADMIN') return true
  uni.showToast({title:'仅管理员可进入管理中心',icon:'none'})
  uni.reLaunch({url:'/pages/index/index'})
  return false
}

export function confirmAction(title:string, content:string) {
  return new Promise<boolean>(resolve=>uni.showModal({title,content,confirmColor:'#b54c43',
    success:result=>resolve(result.confirm),fail:()=>resolve(false)}))
}

export function useDraftGuard(hasDraft:Ref<boolean>) {
  const allowLeave=ref(false)
  onBackPress(() => {
    if (allowLeave.value || !hasDraft.value) return false
    uni.showModal({title:'放弃未保存的修改？',content:'当前表单中的内容尚未保存。',
      confirmText:'放弃离开',confirmColor:'#b54c43',success:result=>{
        if (result.confirm) {
          allowLeave.value=true
          uni.navigateBack({fail:()=>uni.reLaunch({url:'/pages/settings/settings'})})
        }
      }})
    return true
  })
  return allowLeave
}
