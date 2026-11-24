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
