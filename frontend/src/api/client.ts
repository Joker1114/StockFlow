import { API_BASE_URL } from './config'

export type Product = { id:number; category:'TOBACCO'|'ALCOHOL'; brand:string; name:string; specification:string; unit:string; scan_mode:'QUANTITY'|'SERIAL'; stock_qty:number; loose_qty:number; bottles_per_box:number; full_boxes:number; opened_boxes:number; boxed_qty:number; is_active:number }
export type User = { id:number; username:string; name:string|null; department_id:number|null; department_name:string|null; role:'ADMIN'|'STAFF'; is_active:number }
export type Company = { id:number; name:string; is_active:number }
export type Supplier = { id:number; name:string; is_active:number }
export type BoxRecord = { code_value:string; direction:'IN'|'OUT'; quantity:number; capacity:number; remaining_after:number }
export type DocItem = { id:number; product_id:number; quantity:number; loose_quantity:number; codes:string[]; boxes:BoxRecord[]; brand:string; name:string; specification:string; unit:string; scan_mode:string }
export type DocumentKind = 'NORMAL'|'RETURN'|'ADJUST'
export type Document = { id:number; doc_no:string; direction:'IN'|'OUT'; kind:DocumentKind; source_document_id:number|null; source_document_no:string|null; supplier_id:number|null; supplier_name:string|null; recipient:string|null; recipient_company_id:number|null; remark:string|null; created_at:string; operator_name:string; items:DocItem[] }
export type DocSummary = Omit<Document,'items'>
export type ReturnableItem = {product_id:number;category:'TOBACCO'|'ALCOHOL';brand:string;name:string;specification:string;unit:string;scan_mode:'QUANTITY'|'SERIAL';quantity:number;loose_quantity:number;boxes:{code_value:string;quantity:number}[];codes:string[]}
export type Returnable = {source_document_id:number;source_document_no:string;recipient:string|null;recipient_company_id:number|null;items:ReturnableItem[]}
export type Rule = { id:number; product_id:number; match_type:'EXACT'|'PREFIX'; match_value:string; is_active:number }
export type ScanResolution = {
  candidates: { product_id:number }[]
  box: { product_id:number; code_value:string; capacity:number; remaining:number } | null
  code_value?:string
}

const tokenKey = 'stockflow_token'

export const getToken = () => String(uni.getStorageSync(tokenKey) || '')
export const setToken = (value:string) => uni.setStorageSync(tokenKey, value)
export const clearToken = () => uni.removeStorageSync(tokenKey)

export function message(error:unknown):string {
  return error instanceof Error ? error.message : '请求失败'
}

function requestFailure(reason:string):string {
  // #ifdef MP-WEIXIN
  if (/not in (?:the )?domain list|合法域名/i.test(reason)) {
    return '微信未允许访问服务器，请核对小程序的 request 合法域名和端口配置'
  }
  if (/ssl|tls|certificate|证书/i.test(reason)) return '微信校验 HTTPS 证书失败，请检查服务器证书和证书链'
  if (/timeout|timed out|超时/i.test(reason)) return '连接服务器超时，请检查手机网络和公网映射'
  // #endif
  return '无法连接服务器，请检查网络后重试'
}

function apiUrl(path:string) {
  // #ifdef H5
  if (import.meta.env.DEV) return window.location.origin + '/api' + path
  // #endif
  return API_BASE_URL + '/api' + path
}

function authorizationHeader(): Record<string,string> {
  const token = getToken()
  return token ? {Authorization:'Bearer ' + token} : {}
}

function expireSession() {
  clearToken()
  uni.reLaunch({url:'/pages/login/login'})
}

export async function api<T>(path:string, method:'GET'|'POST'|'PATCH'|'DELETE'='GET', data?:unknown):Promise<T> {
  const url = apiUrl(path)
  return new Promise<T>((resolve, reject) => {
    uni.request({
      url, method:method === 'PATCH' ? 'PUT' : method, data:data as any,
      header:{'Content-Type':'application/json', ...authorizationHeader()},
      success:res => {
        if (res.statusCode >= 200 && res.statusCode < 300) return resolve(res.data as T)
        const body = res.data as {detail?:{message?:string}} | undefined
        if (res.statusCode === 401 && path !== '/auth/login') {
          expireSession()
        }
        reject(new Error(body?.detail?.message || `请求失败 (${res.statusCode})`))
      },
      fail:error => reject(new Error(requestFailure(error.errMsg || '')))
    })
  })
}

function exportError(statusCode:number) {
  if (statusCode === 401) {
    expireSession()
    return new Error('请重新登录后再导出')
  }
  if (statusCode === 404) return new Error('找不到导出接口或单据，请确认后端已更新、单据仍存在')
  if (statusCode === 422) return new Error('无法导出当前范围，请调整筛选条件后重试')
  return new Error(`导出失败（HTTP ${statusCode}）`)
}

export async function downloadExcel(path:string, filename:string) {
  const url = apiUrl(path)
  const header = authorizationHeader()
  // #ifdef H5
  const data = await new Promise<ArrayBuffer>((resolve, reject) => {
    uni.request({
      url, header, responseType:'arraybuffer',
      success: res => {
        if (res.statusCode !== 200) return reject(exportError(res.statusCode))
        const data = res.data
        if (!(data instanceof ArrayBuffer) || data.byteLength < 4) {
          return reject(new Error('服务器返回的内容不是有效的 Excel 文件'))
        }
        const signature = new Uint8Array(data, 0, 4)
        if (signature[0] !== 0x50 || signature[1] !== 0x4b || signature[2] !== 3 || signature[3] !== 4) {
          return reject(new Error('服务器返回的内容不是有效的 Excel 文件'))
        }
        resolve(data)
      },
      fail: error => reject(new Error(requestFailure(error.errMsg || ''))),
    })
  })
  const blobUrl = URL.createObjectURL(new Blob([data], {type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}))
  const link = document.createElement('a')
  link.href = blobUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(blobUrl), 10_000)
  // #endif
  // #ifndef H5
  const filePath = await new Promise<string>((resolve, reject) => {
    uni.downloadFile({
      url, header,
      success: result => {
        if (result.statusCode !== 200) return reject(exportError(result.statusCode))
        resolve(result.tempFilePath)
      },
      fail: error => {
        const reason = error.errMsg || ''
        // #ifdef MP-WEIXIN
        if (/domain|合法域名/i.test(reason)) {
          return reject(new Error('请在微信小程序后台将服务器加入 downloadFile 合法域名'))
        }
        // #endif
        reject(new Error(requestFailure(reason)))
      },
    })
  })
  await new Promise<void>((resolve, reject) => {
    uni.openDocument({
      filePath, fileType:'xlsx',
      // #ifdef MP-WEIXIN
      showMenu:true,
      // #endif
      success: () => resolve(),
      fail: () => reject(new Error('文件已下载，打开失败。请确认设备支持打开 .xlsx 文件')),
    })
  })
  // #endif
}

export const productName = (p:Pick<Product,'brand'|'name'|'specification'>) => `${p.brand} ${p.name} · ${p.specification}`
export function localTime(value:string, utcOffsetMinutes?:number): string {
  // 后端的 ISO 时间戳可能带微秒，按 Date 支持的毫秒精度解析。
  const date = new Date(value.replace(/(\.\d{3})\d+(?=Z$|[+-]\d{2}:\d{2}$)/, '$1'))
  if (Number.isNaN(date.getTime())) return '—'
  if (utcOffsetMinutes !== undefined) {
    return new Date(date.getTime() + utcOffsetMinutes * 60_000).toISOString().slice(0, 19).replace('T', ' ')
  }

  const pad = (part:number) => String(part).padStart(2, '0')
  const day = [date.getFullYear(), pad(date.getMonth() + 1), pad(date.getDate())].join('-')
  const time = [date.getHours(), date.getMinutes(), date.getSeconds()].map(pad).join(':')
  return `${day} ${time}`
}
export const go = (path:string) => uni.navigateTo({url:'/pages/' + path})

export function resolveCode(rawText:string, productId?:number, includeInactive = false) {
  return api<ScanResolution>(
    includeInactive ? '/scan/resolve?include_inactive=true' : '/scan/resolve',
    'POST',
    {raw_text:rawText, product_id:productId}
  )
}
