# 物资通 StockFlow

按 [系统设计](documents/design/SDD.md) 和 [酒水箱码规则](documents/design/alcohol-flow.md) 实现的单仓库共享库存 MVP。后端是 FastAPI + 服务器本地 SQLite，移动端是 uni-app + Vue 3 + TypeScript。管理员维护物资、供应商、用户及扫码匹配规则。登录用户可以记录出入库、关联原单退库和库存调整，并查询库存与单据历史。扫码用于识别原始文本并匹配规则。

## 项目目录

```text
backend/app/          FastAPI、认证、SQLite、单据事务
backend/tests/        临时数据库自动化测试
backend/scripts/      SQLite 一致性备份
frontend/src/pages/   登录、工作台、业务办理、出入库、库存、单据、退库、详情、管理中心及独立管理页
frontend/src/api/     uni.request、令牌与 API 类型
deployment/           Compose、HTTPS 代理、部署脚本与发布清单
documents/            公共设计文档与工程管理说明
```

项目在一个 Git 仓库的 `main` 分支维护。克隆一次即可获取前端、后端、部署资源和公共文档。工作区边界和验证结果见 [PROJECT_STRUCTURE.md](documents/PROJECT_STRUCTURE.md)。

## 前端菜单

页面采用顶部标题、中间业务内容、底部四个固定入口：

界面采用“轻甜专业”主题：奶油白背景、樱粉与淡紫点缀、深莓色主操作。库存助手形象用于工作台欢迎区；入库、出库、扫码和单据的业务状态仍通过文字及独立的成功、警告、错误色表达。

| 底部入口 | 用途 |
| --- | --- |
| 工作台 | 常用操作、最近单据；管理员从这里进入管理中心 |
| 业务 | 集中办理采购入库、领用出库、关联退库和库存调整 |
| 库存 | 查询物资结存、酒水箱码余量和散瓶数量 |
| 单据 | 按类型查询历史单据并查看详情 |

管理员从工作台进入“管理中心”。物资、供应商和扫码规则分别在独立页面维护；用户管理归入“账号与权限”，与业务基础资料分开。

关联退库从“业务”进入出库单筛选，选择原出库单后办理。库存调整从“业务”选择盘盈或盘亏，填写原因并生成调整单。

## 本地运行后端

需要 Python 3.11+。在 `backend/` 目录执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock
$env:STOCKFLOW_DB_PATH = './data/stockflow.db'
$env:STOCKFLOW_JWT_SECRET = ([guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N'))
$env:STOCKFLOW_ADMIN_USERNAME = 'admin'
$env:STOCKFLOW_ADMIN_PASSWORD = Read-Host '设置管理员初始密码（至少10位）'
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Linux/macOS 用 `python3 -m venv .venv`、`source .venv/bin/activate`、`export 变量=值`，然后运行 `python -m uvicorn ...`。环境变量参考 [backend/.env.example](backend/.env.example)。首次启动仅当用户表为空时创建管理员；以后修改环境变量不会重置密码。数据库文件所在目录必须可写且持久化。

打开 `http://127.0.0.1:8000/docs` 可调试 API。示例请求见 [backend/docs/api-examples.md](backend/docs/api-examples.md)。对外部署必须经 HTTPS 代理，详见 [deployment/README.md](deployment/README.md)。

### 本地 Docker Compose 启动（Windows）

把 [compose.yaml](deployment/compose.yaml) 和 [init-env.cmd](deployment/init-env.cmd) 放到已经导入后端镜像的电脑上。第一次执行 `.\init-env.cmd` 设置管理员初始密码，然后运行 `docker compose up -d`。也可以在项目的 `deployment/` 目录直接执行这两条命令。

数据库保存在 `stockflow-data` 命名卷。首次部署、沿用旧容器数据和版本升级的完整步骤见 [Windows 部署说明](deployment/README.md#windows-使用-docker-compose)。

Linux 服务器使用 [Linux Compose 配置](deployment/linux/compose.yaml) 和 [初始化脚本](deployment/linux/init-env.sh)。数据库使用服务器上已有的 `stockflow-data` 卷，公网 HTTPS 访问通过 Caddy 转发。详见 [Linux 部署说明](deployment/README.md#linux-云服务器使用-docker-compose)。

## 测试

在 `backend/` 安装开发依赖并运行：

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.lock
.\.venv\Scripts\python -m pytest -q
```

测试使用各自的临时 SQLite 文件，覆盖多行事务、超库存回滚、并发出库、request_id 幂等、序列码及酒水箱码流转、部分出箱、散瓶校验、关联原单退库、库存调整、供应商快照、旧库迁移、扫码规则优先级、角色权限、账号停用和备份恢复。不会使用生产数据库。

## 运行移动端

需要 Node.js 18+ 和 HBuilderX。`frontend/` 中执行：

```powershell
npm ci
npm run type-check
npm run build:app
```

`build:app` 只生成 uni-app App 源码编译产物，不生成 APK/IPA。打开 HBuilderX 导入 `frontend/`，在 `src/manifest.json` 设置实际 DCloud AppID、应用标识和签名信息，确认 Barcode 模块已启用，然后用“运行到手机或模拟器”验证相机扫码。发行 Android 包需配置 Android 签名并打包；iOS 需 Apple 开发者证书、描述文件以及 macOS/Xcode 离线打包环境或 HBuilderX 云打包。请在真实 Android/iOS 设备上分别验证登录、相机权限、扫码、两行出入库与超库存提示。本仓库不含证书，也不声称已生成安装包。

客户端默认连接 `https://fengjianren.xyz:8000`，可在构建前设置 `VITE_API_BASE_URL`，登录页输入工号或原账号及密码。令牌保存在 uni-app 本地存储，到期后重新登录。

**H5 开发联调**可在 `frontend/.env` 设置 `VITE_API_PROXY_TARGET=http://127.0.0.1:8000`，由 Vite 代理 `/api` 到本机后端。修改后重启 `npm run dev:h5`。未配置代理目标时使用 VITE_API_BASE_URL 或项目默认 HTTPS 地址。浏览器摄像头需要 HTTPS 或 localhost。

**Android/iOS 正式 App：** 使用受设备信任的 HTTPS API 地址。Android 9 及以上默认限制明文 HTTP；通过 HBuilderX 运行到设备后，再验证相机扫码和移动端网络。关于 Android 的限制可参考 [Android 网络安全配置](https://developer.android.com/privacy-and-security/security-config)。

## 业务要点

- 所有已登录用户看到同一库存。初始库存通过入库单建立，不能直接编辑余额。
- 管理员在「基础资料 → 组织机构」维护子公司，再为用户录入纯数字工号、姓名和所属公司。已有用户可在「用户管理 → 编辑资料」补录信息，保存后使用工号和原密码登录，历史单据继续关联该用户。
- 新建出库单时，从已启用的子公司中选择领用公司。单据保存制单时的公司名称，旧出库单继续显示原领用人。
- `QUANTITY` 行手动输入正整数；扫码用于选择物资，可在多张单使用同一通用码。
- 烟草 `SERIAL` 每件扫一个独立码。酒水统一使用“箱码＋散瓶”，每码代表一箱，每箱瓶数按物资维护，开箱余瓶仍绑定原箱码；普通入库散瓶数严格小于每箱瓶数，出库散瓶库存独立校验。详见 [酒水箱码规则](documents/design/alcohol-flow.md)。
- 普通入库和出库单共用“相机连扫”。摄像头和逐条扫码结果在当前物资卡片内展开。App 端成功扫码短震，重复扫码长震。确认保存单据后更新库存。
- 提交失败或网络超时后可重试。客户端保留该次 `request_id`，服务端在原子事务中保证同一请求只生成一张单据。
- 管理员可在单据详情删除误录单据，库存和编码状态会随单据一并回退。有关联退库、后续编码流转或库存依赖时，系统会提示涉及的单据。领用后退回从原出库单详情发起。盘点差异通过库存调整单处理，并填写原因。
- 客户端对管理员页面做入口控制，服务端对每个管理员接口独立检查权限。

## 已验证与待真机验证

后端自动化测试、前端 TypeScript 类型检查与 uni-app App 源码编译可在本地运行。相机、Android 安装包、iOS 安装包和实际 HTTPS 网络链路需要设备及打包证书继续验证。
