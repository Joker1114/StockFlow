# 物资通 StockFlow — MVP 软件设计说明书（SDD）

> 版本：V3（含统一酒水流程、关联退库与库存调整）  
> 状态：Codex 开发基线  
> 适用：Android / iOS（uni-app APP）  
> 原则：**少功能、少依赖、一套代码、一个服务、一个仓库、一个数据库**

> **业务更新：** [酒水箱码规则](alcohol-flow.md) 记录供应商、整箱、部分出箱、散瓶、退库与库存调整规则。该文档覆盖下文“不做包装换算”、旧版酒水 SERIAL 每码计 1 件、酒水数量模式、固定 6 张表、入库无供应商字段以及仅通过反向单据纠错等旧约束；烟草原流程保持不变。

## 0. 不可更改的技术与业务约束

1. **前端：uni-app + Vue 3 + TypeScript**，同时构建 Android 与 iOS APP。不要改成 Flutter、React Native，也不另外开发 Web 管理后台。
2. **后端：Python + FastAPI**，提供 JSON REST API。
3. **数据库：SQLite，部署在云服务器的持久化本地磁盘**。所有用户共用这个数据库；手机不保存业务数据库，只缓存必要的登录令牌与非敏感界面设置。
4. **一个仓库、共享库存**：所有已登录用户使用同一套库存与单据；第一版只区分管理员、普通用户两种身份。
5. 功能只做：**账号登录、物资维护、扫码识别、入库、出库、库存查看、单据历史**。管理员能简单添加/停用用户并维护二维码匹配规则。
6. 一笔操作生成一张单据；单据可以有多条物资明细。保存单据和库存变更**必须是一个原子事务**。
7. 入库/出库不能产生负库存；并发出库必须安全；重复提交不能生成重复单据。
8. 二维码不同品牌格式未知：仅做**读码、规则匹配、无法识别时手选物资**；不得假造厂商品牌二维码规则，也不得宣称离线扫码鉴伪。
9. 第一版不做：多仓库、审批、采购、财务、库存预警、报表导出、消息推送、拍照/OCR、在线鉴伪、云端对象存储、微服务、Redis、Celery、Web 管理后台、离线编辑与同步。
10. 服务器必须使用 HTTPS 对外服务；只允许单台服务器访问 SQLite 数据库文件。按常规规模小团队使用设计，不承诺高并发水平扩展。

## 1. 项目范围

### 1.1 目标

日常记录烟酒物资的入库、出库、现有库存和历史单据，允许多个用户在 Android/iOS 设备上操作同一个云端库房。

### 1.2 用户

- **管理员（ADMIN）**：普通业务全部功能，另可维护物资、二维码规则、用户账号。
- **普通用户（STAFF）**：查询物资、扫码、创建入库/出库单、查库存及历史单据。
- 不开放自行注册，不做复杂部门权限。服务启动时通过环境变量初始化唯一首位管理员；管理员可新增其他用户。

### 1.3 物资

- 类别只允许 `TOBACCO`（烟）、`ALCOHOL`（酒）。
- 每个 SKU：类别、品牌、名称、规格、计量单位（瓶/条/盒等）、扫码模式、启用状态。
- 默认 **数量模式（QUANTITY）**：手动输入正整数，扫码仅辅助选商品；同一商品的通用码可重复使用。
- 可选 **一物一码模式（SERIAL）**：每件独立码对应一件库存；扫一个独立码计 1 件，禁止同件重复在库；出库必须扫描已在库编码。
- 不做包装换算（箱→瓶），不合计不同单位的总件数。
- 初始库存通过普通入库单建立。

## 2. 简化架构

```text
Android APP ─┐
             ├── HTTPS / JSON ── FastAPI (Python) ── SQLite (server/data/stockflow.db)
iOS APP ─────┘                    │
                                └── 简单服务端备份脚本

前端：uni-app + Vue3 + TypeScript
扫码：uni.scanCode（使用设备相机）
请求：uni.request（封装 API 客户端）
后端：FastAPI + 标准库 sqlite3 + Pydantic + JWT/密码哈希
```

- 不添加 ORM、Redis、消息队列或大型前端状态库。数据库用参数化 SQL，写在独立 repository/service 中；业务规则不写进 API 路由。
- SQLite 启用 `PRAGMA foreign_keys = ON`、`PRAGMA journal_mode = WAL`、`PRAGMA busy_timeout = 10000`（WAL 设为数据库持久配置；外键和 busy_timeout 在每次连接初始化）。
- 写入单据时使用 `BEGIN IMMEDIATE`，事务内完成库存校验、编码状态校验、单号生成、单据落库、库存更新、编码流水落库，最后提交；失败回滚。
- 服务运行单实例，`uvicorn --workers 1`；SQLite 存本机持久目录，不放在网络共享磁盘上。部署和备份保留 `-wal/-shm` 正常使用所需的运行条件。
- 服务内存只保存请求短期数据，不维护库存真值。前端不允许直接连接数据库。

## 3. 页面与流程（尽量少）

| 页面 | 功能 | 备注 |
|---|---|---|
| 登录 | 用户名、密码登录 | 首次登录后缓存令牌，到期重新登录 |
| 首页 | 【入库】【出库】快捷入口、最近5笔单据 | 不做复杂仪表盘 |
| 出入库编辑 | 多行物资、扫码/手动选择、数量、领用人、备注、确认保存 | IN/OUT 共享一个页面，出库填写领用人 |
| 库存 | 按烟/酒筛选、搜索品牌名称、显示每个 SKU 库存 | 不允许编辑库存数字 |
| 单据记录/详情 | 按日期倒序、按出入库类型筛选、查看单据完整明细 | 管理员可删除误录单据并回退库存 |
| 设置/基础维护 | 管理员维护物资、二维码规则、用户 | 不开发独立后台网站 |

### 3.1 新建入库单

1. 登录用户点“入库”。
2. 扫码或搜索选中商品，数量模式输入件数；序列模式扫描每件独立编码，数量自动计算。
3. 可继续添加不同商品，填写可选备注。
4. 预览后点击确认，客户端生成 `request_id`（UUID），POST 创建单据。
5. 服务端验证并在事务中写入，返回单号和详情；页面显示已保存。

### 3.2 新建出库单

流程同入库，但必须填写领用人；服务端拒绝超库存；序列模式要求扫描真实在库编码。失败不得留下半张单据或部分扣减。

### 3.3 单据纠错

- 已确认单据可由管理员删除，删除时系统回退库存并检查关联单据与编码记录。
- 用一笔反向单据纠错，并在备注注明原单号；第一版不开发自动冲销按钮。
- 操作人从认证信息取得，不能由客户端自由指定。

## 4. 扫码业务规则

### 4.1 读取

使用 `uni.scanCode({ onlyFromCamera:true, scanType:['qrCode','barCode'], ... })` 获得二维码/条码的**原始文本**，原样传给 `/api/scan/resolve`，不擅自打开二维码 URL，也不自动向二维码提供的网站发请求。

### 4.2 规则匹配

首版仅支持简单可解释规则：

- `EXACT`：原文精确相同；适用于通用商品码。
- `PREFIX`：原文以某个固定前缀开始；适用于品牌/型号已知的固定前缀。

管理员手工维护规则（品牌、关联商品、规则类型、匹配值）。先精确匹配，再按最长前缀匹配。**若同一最高优先级匹配到多个物资，返回候选供人工选取**，不猜测；无规则命中时用户手动选择商品。真实品牌二维码规则需要通过实物样本进一步配置；本版本不做任意表达式解析引擎。

注意：**一物一码的序列号不能当作通用商品码自动保存为 `EXACT` 规则**；扫码是否可以直接映射产品取决于配置的共同前缀或已知码制，未识别则手选。

### 4.3 两类扫码模式

- `QUANTITY`：扫码只用于定位商品。数量由用户输入。通用码可在多笔单据重复出现，不做全局唯一限制。可选保存当次扫码原始文本用于追溯。
- `SERIAL`：独立码对应实物单件。一次单据内编码不可重复；同一编码入库时必须不在库；出库时必须已在库且属于当前商品。提交时服务端再次检查状态，不能仅依赖扫码时提示。
- 一物一码码值必须完整保存（数据库 TEXT）；原始码文本可能是 URL，但它不等同于防伪结果。

## 5. SQLite 表结构（6 张表）

### 5.1 users

```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('ADMIN','STAFF')),
  is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
  created_at TEXT NOT NULL
);
```

### 5.2 products

```sql
CREATE TABLE products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category TEXT NOT NULL CHECK(category IN ('TOBACCO','ALCOHOL')),
  brand TEXT NOT NULL,
  name TEXT NOT NULL,
  specification TEXT NOT NULL,
  unit TEXT NOT NULL,
  scan_mode TEXT NOT NULL DEFAULT 'QUANTITY' CHECK(scan_mode IN ('QUANTITY','SERIAL')),
  stock_qty INTEGER NOT NULL DEFAULT 0 CHECK(stock_qty >= 0),
  is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
  created_at TEXT NOT NULL,
  UNIQUE(category, brand, name, specification, unit)
);
```

- 所有时间使用带 UTC 时区的 ISO 8601 字符串记录，前端按本地时区展示。
- `stock_qty` 是服务器事务维护的物化余额，任何查询不得以客户端计算结果覆盖；必须与单据净数量一致。
- 产品产生单据后不可修改 `unit`、`scan_mode`、`category`，也不得物理删除。

### 5.3 qr_rules

```sql
CREATE TABLE qr_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL REFERENCES products(id),
  match_type TEXT NOT NULL CHECK(match_type IN ('EXACT','PREFIX')),
  match_value TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
  UNIQUE(product_id, match_type, match_value)
);
```

### 5.4 documents

```sql
CREATE TABLE documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_no TEXT NOT NULL UNIQUE,
  request_id TEXT NOT NULL UNIQUE,
  request_hash TEXT NOT NULL,
  direction TEXT NOT NULL CHECK(direction IN ('IN','OUT')),
  operator_id INTEGER NOT NULL REFERENCES users(id),
  recipient TEXT,
  remark TEXT,
  created_at TEXT NOT NULL
);
```

- `request_id` 用于客户端超时重试幂等；同一个 request_id 重试必须返回第一次保存的单据，不能重复扣库存。服务端对规范化请求业务字段计算 `request_hash`（例如 SHA-256），若相同 request_id 对应不同请求内容则返回 409。
- `doc_no` 由服务端按已提交顺序生成，如 `RK202611170001` / `CK202611170001`，不可依赖客户端时间。实现允许用全局 `id` 补零生成唯一编号，格式无须严格固定为按日流水。

### 5.5 document_items

```sql
CREATE TABLE document_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id),
  product_id INTEGER NOT NULL REFERENCES products(id),
  quantity INTEGER NOT NULL CHECK(quantity > 0),
  UNIQUE(document_id, product_id)
);
```

### 5.6 scan_events

```sql
CREATE TABLE scan_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_item_id INTEGER NOT NULL REFERENCES document_items(id),
  product_id INTEGER NOT NULL REFERENCES products(id),
  code_value TEXT NOT NULL,
  code_kind TEXT NOT NULL CHECK(code_kind IN ('QUANTITY','SERIAL')),
  direction TEXT NOT NULL CHECK(direction IN ('IN','OUT')),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_scan_events_code ON scan_events(code_kind, code_value, id);
CREATE INDEX idx_doc_items_product ON document_items(product_id);
CREATE INDEX idx_docs_created ON documents(created_at);
```

- 对于 `SERIAL` 码，使用**最后一条已提交 `scan_events`** 的方向判定状态：最后为 `IN` 则在库，最后为 `OUT` 则不在库；无历史视为不在库。还必须校验历史中同一编码绑定的 `product_id` 一致，以防换商品混用。所有检查和写入在 `BEGIN IMMEDIATE` 事务内进行。
- `SERIAL` 明细数量必须等于本行独立序列码数量；`QUANTITY` 行允许无扫码记录。
- `scan_events` 只记录随单据提交的扫码，不记录扫码页面取消的内容。

## 6. HTTP API（最小集合）

统一前缀 `/api`，认证使用 `Authorization: Bearer <token>`。全部请求/响应 JSON，统一使用明确的错误码和中文可读错误信息。必要接口：

| 方法 | 路径 | 用途 | 权限 |
|---|---|---|---|
| POST | `/api/auth/login` | 登录，获取令牌 | 公开 |
| GET | `/api/auth/me` | 查询当前用户 | 登录 |
| GET | `/api/products` | 查询物资及库存 | 登录 |
| POST | `/api/products` | 新增物资 | 管理员 |
| PATCH | `/api/products/{id}` | 修改/停用物资（受历史限制） | 管理员 |
| POST | `/api/scan/resolve` | 按规则匹配扫描原始文本 | 登录 |
| POST | `/api/documents` | 创建入库/出库单 | 登录 |
| GET | `/api/documents` | 查询单据列表（分页、类型筛选） | 登录 |
| GET | `/api/documents/{id}` | 单据详情，含扫码明细 | 登录 |
| DELETE | `/api/documents/{id}` | 删除单据并回退库存 | 管理员 |
| GET | `/api/qr-rules` | 查询二维码规则 | 管理员 |
| POST | `/api/qr-rules` | 新增规则 | 管理员 |
| DELETE | `/api/qr-rules/{id}` | 删除规则 | 管理员 |
| GET | `/api/users` | 用户列表 | 管理员 |
| POST | `/api/users` | 新增用户 | 管理员 |
| PATCH | `/api/users/{id}` | 停用/启用与重置密码 | 管理员 |

库存已由 GET `/api/products` 返回 `stock_qty`，无需另设独立库存 API。首页最近单据可以复用 `GET /api/documents?limit=5`。

### 6.1 创建单据示例

```json
{
  "request_id": "1cf7f3cb-c78b-45a5-9602-f85db054e080",
  "direction": "IN",
  "recipient": null,
  "remark": "行政接待物资入库",
  "items": [
    { "product_id": 1, "quantity": 12, "codes": [] },
    { "product_id": 2, "quantity": 2, "codes": ["SERIAL-001", "SERIAL-002"] }
  ]
}
```

- `QUANTITY` 行通过 `quantity` 指定数量，`codes` 可不提供或提供已扫码原文（不作为库存件数）。
- `SERIAL` 行必须填写 `codes`，`quantity === codes.length`；不允许同一张单中重复产品行、重复序列号。
- `direction=OUT` 时 `recipient` 必填；`direction=IN` 时不需要。
- 未登录 401，权限不足 403，业务冲突（库存不足/序列状态不符）409，参数校验 422；服务端异常 500（不能泄露堆栈）。

## 7. 保存单据核心事务（必须正确）

1. 验证用户有效、请求字段、商品是否存在与可操作、数量正整数、码模式一致、同一单无重复 SKU、领用人规则。
2. `BEGIN IMMEDIATE`；按 `request_id` 查已提交结果：请求哈希一致则返回原单，不一致则 409；新请求继续执行。
3. 对所有 OUT 行校验库存足够；SERIAL 行逐码校验最新库存状态及商品归属；对 IN 行校验产品启用状态及 SERIAL 不重复在库。
4. 插入 document、document_items、scan_events；库存更新使用：`UPDATE products SET stock_qty = stock_qty - ? WHERE id = ? AND stock_qty >= ?`，检查受影响行数；入库则 `+ ?`。
5. 生成/保存服务端单号；`COMMIT`，返回单据详情。
6. 任一失败立即 `ROLLBACK`。前端确认按钮禁重复点击，但**必须以服务端幂等与事务保证正确性**。

## 8. 安全与运维最小要求

- 用户密码只保存安全哈希（Argon2 等成熟库），不保存明文；首次管理员账号来自环境变量，初始化后不能每次启动重置。
- JWT 设置明确过期时间；管理员才能管理账号、物资、规则；后端逐请求检查，不依赖隐藏前端按钮。
- 使用 HTTPS；不把密码、令牌、二维码原文写入服务端普通访问日志；SQL 必须使用参数化语句。
- 限制接口正文大小、字段长度、每张单据商品行数和码数量，防止误操作及恶意大请求。
- SQLite 文件放在服务器持久化目录（例如 `/data/stockflow.db`），**不能放容器临时层**；每天由脚本使用 SQLite Backup API 生成一致性备份文件，建议保留最近 7 份；必须附恢复说明并验证一次恢复。
- 使用单实例 FastAPI。若以后出现大量并发写入，再评估其他数据库；第一版不提前升级。
- 开发默认不需要外网第三方服务或付费 SDK。iOS 打包与证书要求在 README 中说明，不虚报已经验证。

## 9. 推荐代码目录

```text
stockflow/
├── SDD.md
├── CODEX_PROMPT.md
├── README.md
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── auth.py
│   │   ├── schemas.py
│   │   ├── routers/       # auth, products, qr, documents, users
│   │   └── services/      # 单据事务、规则识别、商品管理
│   ├── scripts/backup.py
│   ├── tests/
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
├── frontend/
│   ├── pages/             # 登录、首页、单据编辑、库存、历史、设置
│   ├── api/               # 统一 uni.request 和令牌处理
│   ├── utils/             # 扫码、日期等少量工具
│   ├── App.vue
│   ├── main.ts
│   ├── pages.json
│   ├── manifest.json
│   └── package.json
└── deploy/
    └── README.md         # HTTPS 反向代理、环境变量、数据库挂载和备份
```

避免多层空目录、过度抽象与无用设计模式。前后端不要共享可执行代码，只共享 API 契约。

## 10. 必须通过的验收场景

1. 能在 Android APP 登录、退出、重新登录；iOS 代码兼容并提供构建说明。
2. 管理员能新增/停用普通用户；停用账号无法继续访问 API。
3. 新增烟、酒各一款物资，列表能查到，默认库存为 0。
4. 入库一张两行明细单，两个库存准确增加，单据详情可查。
5. 出库一张两行明细单，库存准确减少，领用人和操作人记录正确。
6. 库存不足时拒绝整个出库单，所有库存不变，不留下半单。
7. 同时两个用户对同一库存发出超额出库请求，最多一个成功，不出现负库存。
8. 同一 request_id 并发/重试提交，只生成一张单据；相同 id 不同内容不可悄悄重用。
9. 数量模式识别通用码后手输数量，不因多次扫码自动增加库存。
10. 一物一码同码不能重复入库；已出库编码可再次入库；未在库编码不能出库。
11. 无二维码规则时可手选商品；二维码 URL 不自动请求、不宣称鉴伪。
12. 普通用户无法调用管理员接口；非法 token 拒绝。
13. 后端重启后，库存、单据、用户依旧存在。
14. 备份后在测试环境恢复，库存和单据与备份一致。
15. 后端使用 `pytest` 覆盖核心事务、角色权限、扫码规则和幂等；测试必须采用临时 SQLite 数据库，不改生产数据。

## 11. 明确不做的需求

不开发注册短信验证码、微信登录、企业微信、部门层级、多仓库调拨、审批、流水账报表、Excel/PDF 导出、支付、价格、进销存采购/销售链路、拍照、推送、扫码联网鉴伪、离线业务编辑、多环境微服务、监控大屏。

## 12. 交付清单

- 完整可运行的 FastAPI 服务（环境变量示例、数据库初始化、JWT、API）。
- 完整 uni-app Vue3 + TypeScript 项目（可构建 Android/iOS）。
- 核心业务自动化测试、必要的接口调试示例。
- Dockerfile + 最小部署指南（服务器持久磁盘、HTTPS、备份、启动命令）。
- README：本地启动、首次管理员初始化、安装、运行、测试、构建 APK/iOS 的具体步骤。
- 若当前工作环境不支持 macOS/Xcode 或云打包，不得声称已成功生成/验证 iOS 安装包；应清楚标注未验证步骤。

## 13. 开发顺序

**阶段一：后端 + SQLite**：账号登录、商品、单据事务和库存，核心测试先通过。  
**阶段二：uni-app 页面**：登录、首页、库存、出入库、单据历史，打通 API。  
**阶段三：扫码规则**：调用相机扫码、EXACT/PREFIX 匹配、手工选择、一物一码。  
**阶段四：联调交付**：双端打包准备、权限校验、并发库存与幂等测试、备份/恢复演练、README。  

> 任何阶段都不允许擅自替换指定技术栈，或以完成阶段为名跳过真实代码、测试、部署说明。
