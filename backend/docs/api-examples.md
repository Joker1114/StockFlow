# API 调试示例

以下示例在后端启动后执行。将用户名和密码替换为环境变量中设置的首次管理员账号。真实部署使用 HTTPS 域名。

```bash
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"your-admin-password"}'
```

从响应取 `token`，后续请求添加 `Authorization: Bearer <token>`。

```bash
curl -X POST http://127.0.0.1:8000/api/products \
  -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' \
  -d '{"category":"TOBACCO","brand":"示例品牌","name":"示例商品","specification":"标准装","unit":"条","scan_mode":"QUANTITY"}'

curl -X POST http://127.0.0.1:8000/api/suppliers \
  -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' \
  -d '{"name":"示例供应商"}'

curl -X POST http://127.0.0.1:8000/api/documents \
  -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' \
  -d '{"request_id":"1cf7f3cb-c78b-45a5-9602-f85db054e080","direction":"IN","supplier_id":1,"items":[{"product_id":1,"quantity":10,"codes":[]}],"remark":"初始入库"}'

curl -H 'Authorization: Bearer <token>' http://127.0.0.1:8000/api/products
curl -H 'Authorization: Bearer <token>' http://127.0.0.1:8000/api/documents?limit=5
```

对同一 `request_id` 重试相同业务内容会返回原单；换内容返回 409。移动端通过 PUT 更新用户与物资，服务端也接受 SDD 规定的 PATCH。

酒水箱码与散瓶的业务说明见公共设计文档 `design/alcohol-flow.md`。

## 单据筛选与导出

历史单据与普通出入库 Excel 导出支持 `recipient_company_id`、`box_code`、`created_from` 和 `created_before`。箱码精确匹配，也可传已有品牌规则支持的外箱二维码链接。日期参数使用带时区的 ISO 8601 时间，起点包含、终点排除。查询北京时间 2026-11-27 整天时，传入 `2026-11-27T00:00:00+08:00` 和 `2026-11-28T00:00:00+08:00`。

历史接口同时返回 `total` 和 `exportable_total`。前者包含符合条件的所有单据类型，后者统计可导出的普通入库和出库单。Excel 保留符合条件的完整普通单据。工作簿固定包含「入库单」和「出库单」两个工作表。「扫码明细」列中每个编码占一行。单据共用字段按单据纵向合并，物资名称和数量等字段按该物资的扫码行纵向合并。没有扫码的物资仍占一行。
