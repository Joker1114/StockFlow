# StockFlow 工程结构与管理边界

## 整理前

本地项目根目录及前端、后端、部署目录均无 Git 元数据、分支、远程或索引。前端已有 npm 锁文件及部分忽略规则。后端只有范围依赖清单，运行配置、SQLite 检查库及 Python 缓存由根目录的遗留忽略规则覆盖，独立 Git 管理时缺少保护。部署有 Windows 和 Linux 两套 Compose 与 Caddy 示例，缺少发布清单及通用环境模板。系统设计和原开发说明散落在根目录，API 示例与公共业务设计同放在 `docs/`。客户端 API 地址为源码常量。

技术栈沿用 uni-app / Vue 3 / TypeScript / Vite 与 FastAPI / SQLite。后端通过 Dockerfile 构建，Compose 使用预导入镜像，Linux 通过 Caddy 提供 HTTPS，移动端及 H5 独立发布。建表和顺序迁移集中在后端 `app/database.py`，当前源码 schema 为 5。未发现可安全合并的重复部署资源，两份 Compose 有不同的监听和卷声明。

## 整理后的目录

下列树列出项目文件与本地运行目录。Git 元数据、依赖、缓存和构建产物目录按整体显示。

```text
StockFlow/
├── .git/
├── .gitignore
├── .tmp-stackflow
├── AGENTS.md
├── README.md
├── backend/
│   ├── .dockerignore
│   ├── .env
│   ├── .env.example
│   ├── .gitignore
│   ├── .pytest_cache/
│   ├── AGENTS.md
│   ├── Dockerfile
│   ├── README.md
│   ├── app/
│   │   ├── __init__.py
│   │   ├── __pycache__/
│   │   ├── auth.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── errors.py
│   │   ├── main.py
│   │   ├── schemas.py
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── __pycache__/
│   │       ├── brand_codes.py
│   │       ├── companies.py
│   │       ├── documents.py
│   │       ├── exports.py
│   │       └── products.py
│   ├── data/
│   │   └── local-check.db
│   ├── docs/
│   │   └── api-examples.md
│   ├── requirements-dev.lock
│   ├── requirements-dev.txt
│   ├── requirements.lock
│   ├── requirements.txt
│   ├── scripts/
│   │   ├── __pycache__/
│   │   └── backup.py
│   └── tests/
│       ├── __pycache__/
│       └── test_api.py
├── deployment/
│   ├── .gitattributes
│   ├── .gitignore
│   ├── AGENTS.md
│   ├── Caddyfile
│   ├── README.md
│   ├── compose.yaml
│   ├── init-env.cmd
│   ├── linux/
│   │   ├── compose.yaml
│   │   ├── init-env.sh
│   │   └── upgrade.sh
│   ├── release.yaml
│   └── stockflow.env.example
├── documents/
│   ├── .gitignore
│   ├── AGENTS.md
│   ├── PROJECT_STRUCTURE.md
│   ├── README.md
│   └── design/
│       ├── CODEX_PROMPT.md
│       ├── SDD.md
│       └── alcohol-flow.md
├── frontend/
│   ├── .env
│   ├── .env.example
│   ├── .gitignore
│   ├── .hbuilderx/
│   │   └── launch.json
│   ├── AGENTS.md
│   ├── README.md
│   ├── dist/
│   ├── index.html
│   ├── node_modules/
│   ├── package-lock.json
│   ├── package.json
│   ├── shims-uni.d.ts
│   ├── src/
│   │   ├── App.vue
│   │   ├── api/
│   │   │   ├── client.ts
│   │   │   ├── config.ts
│   │   │   └── defaults.ts
│   │   ├── components/
│   │   │   ├── AppShell.vue
│   │   │   ├── ContinuousScanner.vue
│   │   │   ├── ExcelExportButton.vue
│   │   │   ├── InlineScanner.vue
│   │   │   ├── StockAssistant.vue
│   │   │   └── WeixinScanCamera.vue
│   │   ├── env.d.ts
│   │   ├── main.ts
│   │   ├── manifest.json
│   │   ├── pages/
│   │   │   ├── detail/
│   │   │   │   └── detail.vue
│   │   │   ├── edit/
│   │   │   │   └── edit.vue
│   │   │   ├── history/
│   │   │   │   └── history.vue
│   │   │   ├── index/
│   │   │   │   └── index.vue
│   │   │   ├── login/
│   │   │   │   └── login.vue
│   │   │   ├── returns/
│   │   │   │   └── returns.vue
│   │   │   ├── settings/
│   │   │   │   ├── departments.vue
│   │   │   │   ├── products.vue
│   │   │   │   ├── rules.vue
│   │   │   │   ├── settings.vue
│   │   │   │   ├── suppliers.vue
│   │   │   │   └── users.vue
│   │   │   ├── stock/
│   │   │   │   └── stock.vue
│   │   │   └── work/
│   │   │       └── work.vue
│   │   ├── pages.json
│   │   ├── shime-uni.d.ts
│   │   ├── static/
│   │   │   ├── logo.png
│   │   │   └── nav/
│   │   │       ├── history-active.svg
│   │   │       ├── history.svg
│   │   │       ├── home-active.svg
│   │   │       ├── home.svg
│   │   │       ├── stock-active.svg
│   │   │       ├── stock.svg
│   │   │       ├── work-active.svg
│   │   │       └── work.svg
│   │   ├── uni.scss
│   │   └── utils/
│   │       ├── boxBrand.ts
│   │       └── management.ts
│   ├── tsconfig.json
│   └── vite.config.ts
└── stockflow-wechat-avatar.png
```

## Git 仓库与目录职责

| 目录 | 纳入版本管理 |
| --- | --- |
| `frontend/` | 页面、组件、API 客户端、静态资源、构建配置、公开环境模板、npm 清单及锁文件、README、AGENTS 和忽略规则 |
| `backend/` | FastAPI、数据库建表和迁移、测试、备份脚本、API 请求示例、依赖清单及锁文件、Dockerfile、Docker 构建排除规则、环境模板、README、AGENTS 和忽略规则 |
| `deployment/` | Windows/Linux Compose、Caddy 示例、初始化及升级脚本、环境模板、发布清单、部署和运维手册、README、AGENTS、忽略和换行规则 |
| `documents/` | 公共设计、原 MVP 开发说明、结构报告、文档索引、AGENTS 和忽略规则 |

项目根目录是唯一的 Git 仓库，使用 `main` 分支。前端、后端、部署和公共文档各自保留构建、运行及文档边界，原组件提交作为合并提交的父提交保留。克隆一次即可获取完整项目。 [GitHub 仓库](https://github.com/Joker1114/StockFlow)

## 独立管理资源

- 现有 `frontend/.env`、`frontend/.hbuilderx/`、`frontend/node_modules/`、`frontend/dist/`，以及后续本机签名文件和 APK/IPA。前端本机配置检查仅包含公开 API 或代理 URL。
- 现有 `backend/.env`、`backend/data/local-check.db`、Python 缓存，以及后续虚拟环境、日志、备份和上传目录。
- 两个平台的实际 `stockflow.env`、本机 Compose 覆盖、实际 Caddy 配置、私钥、镜像归档、数据库备份及 Docker 的 `stockflow-data` 持久卷。整理时本地部署目录无实际 env 或备份文件。
- 根目录原有 `.tmp-stackflow` 和 `stockflow-wechat-avatar.png` 原位保留。正式签署材料、会议纪要和管理类附件可在忽略目录 `documents/archive/` 独立归档。需要时再创建实际的数据、制品和备份目录。

## 变更清单

| 类别 | 文件 |
| --- | --- |
| 新增 | 根目录 `AGENTS.md`；`frontend/{AGENTS.md,README.md,src/api/defaults.ts}`；`backend/{.gitignore,AGENTS.md,README.md,requirements.lock,requirements-dev.lock}`；`deployment/{.gitignore,.gitattributes,AGENTS.md,release.yaml,stockflow.env.example}`；`documents/{.gitignore,AGENTS.md,README.md,PROJECT_STRUCTURE.md}` |
| 原位修改 | 根目录 `README.md`；`frontend/{.env.example,.gitignore,src/api/config.ts,vite.config.ts}`；`backend/{.dockerignore,.env.example,Dockerfile,app/config.py}` |
| 移动 | `deploy/` → `deployment/`，含 `Caddyfile`、`compose.yaml`、`init-env.cmd`、`README.md` 和 `linux/{compose.yaml,init-env.sh,upgrade.sh}`；`SDD.md`、`CODEX_PROMPT.md` 和 `docs/alcohol-flow.md` → `documents/design/`；`docs/api-examples.md` → `backend/docs/api-examples.md` |
| 移动后修改 | `documents/design/SDD.md`、`backend/docs/api-examples.md`、`deployment/README.md` 的文档引用及部署说明 |
| Git 整合 | 根目录 `.gitignore` 管理根目录本机文件，各组件的忽略规则保留。部署目录继续管理 Shell LF 规则 |
| 取消跟踪 | 无。整理前工作区没有 Git 索引或提交；排除项仍留在本机 |

## 配置管理

| 类型 | 使用方式 |
| --- | --- |
| 公共默认值与模板 | 前端公开默认地址、后端默认 SQLite 相对路径及令牌时长、Compose 两套平台默认、Caddy 示例与各仓库环境模板入库 |
| 前端实际配置 | `VITE_API_BASE_URL` 为构建时公开 API 基址，留空沿用原默认地址。H5 开发以 `VITE_API_PROXY_TARGET` 优先。有效性校验要求 HTTP(S) URL，排除 URL 凭证、查询和片段。旧 `VITE_MP_WEIXIN_API_BASE_URL` 保留在本机，当前实现没有读取它 |
| 后端实际配置 | 进程环境设置 `STOCKFLOW_DB_PATH`、JWT 密钥、令牌时长和管理员初始配置。检查密钥长度及令牌时长整数和范围。首次空库通过现有初始化逻辑检查管理员配置 |
| 部署实际配置 | 初始化脚本在所在平台目录创建或沿用 `stockflow.env`。TLS 配置与私钥由实际部署位置保存。镜像标签、端口和卷名沿用原配置 |

实际环境文件保留在原位置。Windows Compose 继续发布 8000，Linux 继续绑定 `127.0.0.1:8000`。两套 Compose 均挂载 `stockflow-data` 至 `/data`，Linux 声明外部卷，容器数据库路径为 `/data/stockflow.db`。此前使用 `deploy/` 的手工命令或外部引用，在这个工作区改用 `deployment/`；现有服务器目录可保持原位。

## 版本与发布

`deployment/release.yaml` 记录工作区整体基线 0.1.0、部署配置 1.0.0、前端 1.0.0、Compose 后端镜像版本 1.0.3、既有升级脚本目标 1.0.4 和源码 SQLite schema 5。后端版本字段对应 Compose 基线镜像，源码到镜像的映射待发布时确认。前后端可从同一分支独立测试、构建和发布。联合发布时填写源码 Git 引用，核对镜像标签、数据库迁移版本与客户端 API 地址，再按部署手册验证接口和客户端。

## 验证结果

| 检查 | 结果 |
| --- | --- |
| 前端 Node.js 22.19.0 / npm 10.9.3 | `npm run type-check`，H5、微信小程序和 App 编译通过。使用工作区现有依赖，产物输出到临时目录。另验证合法 API 覆盖进入微信产物及非法地址构建失败 |
| 后端 Python 3.11 | 以开发锁文件在隔离环境安装，`pip check` 通过，pytest **30 通过**。覆盖临时 SQLite 的迁移、API 和备份恢复。Starlette 报告测试客户端使用 httpx 的弃用警告 |
| 部署定义 | 两套 Compose 的跳过 env 解析静态检查和临时 env 完整检查均通过。Linux 两个 Shell 脚本语法通过；Windows 初始化脚本在临时目录正确沿用了已有 env |
| Git 和敏感文件 | 核对合并索引及保留的源提交。实际配置、依赖、数据库与构建产物由忽略规则排除。 |

## 待处理及风险

- Docker Desktop Linux 引擎未运行，镜像实际构建、容器联合启动及卷挂载实测待执行。当前机器缺少 Caddy 命令，反向代理仅核对配置引用和转发地址。
- 原生签名、微信发布、真机相机和公网 HTTPS 联调需使用对应发布与部署环境。App 构建验证覆盖编译产物。
- 正式发布时填写源码引用及版本标签，并确认 1.0.3 与 1.0.4 的具体镜像来源。整理过程只验证静态部署定义与隔离测试，实际生产容器、卷、数据库和配置未执行写入操作。
