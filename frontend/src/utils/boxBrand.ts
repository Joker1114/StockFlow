import type { Product } from '@/api/client'

const brandsByHost = new Map([
  ['j.imt519.cn', '茅台'],
  ['ax.guotaiworld.com', '国台'],
  ['wlyfw.com', '五粮液'],
])
const checkedBrands = new Set(brandsByHost.values())

export function boxBrandError(product: Product | undefined, raw: string): string | undefined {
  if (product?.category !== 'ALCOHOL') return

  const brand = product.brand.trim()
  const expected = brand === '贵州茅台' ? '茅台' : brand
  if (!checkedBrands.has(expected)) return

  const host = /^https?:\/\/([a-z0-9.-]+)(?::[0-9]+)?(?:[/?#]|$)/i.exec(raw)?.[1].toLowerCase()
  const scanned = host && brandsByHost.get(host)
  if (scanned && scanned !== expected) return `所选物资为${expected}，扫到的是${scanned}箱码`
}
