# StockFlow 前端

uni-app、Vue 3、TypeScript 客户端。使用 Node.js 18+，在 `frontend/` 目录运行 `npm ci`、`npm run type-check`。用 `npm run dev:h5` 启动 H5 开发服务。

根据 [.env.example](.env.example) 设置可选 API 基址和 H5 代理。所有 `VITE_*` 设置均作为公开客户端配置管理。FastAPI 提供接口契约，见运行后端的 `/openapi.json` 和 `/docs`。

| 目标 | 构建命令 | 交付 |
| --- | --- | --- |
| H5 | `npm run build:h5` | 静态站点 |
| 微信小程序 | `npm run build:mp-weixin` | 微信开发者工具上传 |
| Android/iOS | `npm run build:app` | HBuilderX 后续签名和打包 |

版本发布时核对 `package.json`、`package-lock.json` 和 `src/manifest.json`。签名、IDE 本地设置、依赖和制品独立保存。
