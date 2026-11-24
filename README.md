# StockFlow 公共文档

- [工程结构、配置边界与验证](PROJECT_STRUCTURE.md)
- [系统设计](design/SDD.md)
- [酒水箱码与散瓶规则](design/alcohol-flow.md)
- [原 MVP 开发说明](design/CODEX_PROMPT.md)

系统设计中的历史目录示意以工程结构文档为准。API 契约由 FastAPI 提供，请求示例随服务端维护。部署运行手册随部署仓库维护。

## GitHub 分支

- [main · 项目公共文档](https://github.com/Joker1114/StockFlow/tree/main)
- [frontend · uni-app 客户端](https://github.com/Joker1114/StockFlow/tree/frontend)
- [backend · FastAPI 与 SQLite](https://github.com/Joker1114/StockFlow/tree/backend)
- [deployment · Compose、运维脚本和发布清单](https://github.com/Joker1114/StockFlow/tree/deployment)

本地联调时，使用各分支分别检出到 frontend、backend、deployment 和 documents。各分支对应独立提交历史。
