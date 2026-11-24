# 后端部署

## Windows 使用 Docker Compose

在 Docker Desktop 中使用 Linux 容器，Compose 版本要求 2.30 或更新。把 `compose.yaml` 和 `init-env.cmd` 放到同一个文件夹，并在该文件夹打开 PowerShell。

### 首次启动

导入镜像。已经导入时可以直接执行下一组命令。如果导入的是其他版本，用 `docker images` 确认标签，并更新 `compose.yaml` 中的 `image`。

```powershell
docker load -i .\stockflow-1.0.3.tar
```

```powershell
.\init-env.cmd
docker compose up -d
docker compose logs --tail 30 backend
```

初始化脚本会提示输入 `admin` 的密码（10 到 256 位），并生成随机 JWT 密钥。这些设置保存在本机的 `stockflow.env`。已有 env 文件时，脚本会沿用它。打开 [接口页面](http://127.0.0.1:8000/docs) 确认服务已启动。

容器端口 8000 映射到电脑使用的 8000 端口。手机和电脑在同一局域网时，通过电脑的局域网 IP 访问。SQLite 数据保存在命名卷 `stockflow-data`。

### 沿用现有数据

如果这台电脑曾按项目早期的 `docker run` 命令启动过服务，把原 env 文件复制为 `stockflow.env`。备份后执行 `docker stop stockflow`，再执行 `docker compose up -d`。Compose 会挂载相同的 `stockflow-data` 卷。迁移到另一台电脑时，还需要将旧数据库备份恢复到新电脑的卷中，已有数据库继续使用原账号密码。

如果启动时提示 `stockflow-data` 由 Compose 之外的命令创建，这是沿用原数据卷时的提示。用 `docker compose ps` 确认后端状态。

### 日常启动和升级

日常启动用 `docker compose up -d`。升级前执行以下命令备份数据库，并把生成的备份复制到另一个存储位置。

```powershell
docker compose exec backend python scripts/backup.py --source /data/stockflow.db --output-dir /data/backups --keep 7
docker compose cp backend:/data/backups .\backups
```

用 `docker load -i` 导入新版镜像，更新 `compose.yaml` 中的 `image` 标签，再执行 `docker compose up -d`。继续使用原 env 文件和数据卷。停止服务时用 `docker compose stop`，保留数据库卷供后续启动。

## Linux 云服务器使用 Docker Compose

使用 Docker Compose 2.30 或更新版本。将 [Linux 的 compose.yaml](linux/compose.yaml) 和 [init-env.sh](linux/init-env.sh) 放到服务器的同一个目录（以下以 `/srv/stockflow` 为例）。已有的 `stockflow.env` 放在同一目录。

配置默认使用已导入的 `stockflow:1.0.3` 镜像和现有的 `stockflow-data` 命名卷。卷名或镜像标签不同可在 `compose.yaml` 里修改。如果旧容器仍在使用这个卷，先备份数据库，再停止旧容器。首次启动执行以下命令，已使用 root 登录时省略 `sudo`。

```bash
cd /srv/stockflow
sudo bash ./init-env.sh
sudo docker compose up -d
curl -fsS --retry 5 --retry-connrefused http://127.0.0.1:8000/openapi.json -o /dev/null
```

已有 env 文件时，脚本会沿用现有配置。首次生成 env 文件时，输入 10 到 256 位的 `admin` 初始密码，脚本会生成随机 JWT 密钥，并将配置写入权限为 `600` 的 `stockflow.env`。数据库位于卷里的 `stockflow.db`，复用旧数据库时继续用原账号密码登录。

Compose 将 `stockflow-data` 作为外部卷挂载。卷在另一台机器上时，先将 SQLite 备份恢复到目标服务器的数据卷。升级时保留 `stockflow.env` 和数据卷，导入新镜像，更新 `image` 标签并运行 `sudo docker compose up -d`。

后端只绑定服务器本机的 8000 端口。对外访问可以使用 [Caddyfile](Caddyfile)，将其中的 `stockflow.example.com` 替换为指向该服务器的真实域名，再加载到 Caddy。Caddy 通过 80/443 提供 HTTPS 访问，并转发到 `127.0.0.1:8000`。客户端可通过构建环境变量 `VITE_API_BASE_URL` 指向服务器 HTTPS 地址。

### 从 1.0.3 升级到 1.0.4

在项目根目录用 Windows PowerShell 构建并保存镜像。

```powershell
docker build --platform linux/amd64 -t stockflow:1.0.4 .\backend
docker save -o .\stockflow-1.0.4.tar stockflow:1.0.4
```

上传镜像包到服务器的 `/data/`，把 [upgrade.sh](linux/upgrade.sh) 放到现有 `compose.yaml` 旁。

```bash
cd /data/stockflow
bash ./upgrade.sh /data/stockflow-1.0.4.tar
```

脚本会生成 SQLite 和 Compose 备份，使用现有外部卷启动 1.0.4，并检查组织机构接口。检查失败时恢复旧 Compose 配置并重启旧容器。确认接口正常后更新前端。

## 每日备份

通过 cron 或系统定时器每天执行：

```bash
cd /srv/stockflow
sudo docker compose exec -T backend python scripts/backup.py --source /data/stockflow.db --output-dir /data/backups --keep 7
```

脚本通过 SQLite Backup API 在运行中生成一致性快照，运行 `PRAGMA quick_check`，保留最近七份。备份仍在同一磁盘时无法抵御整盘损坏；生产中应额外复制到独立的安全存储并控制访问权限。

## 恢复演练

先在测试环境完成，核对库存与单据数。正式恢复时：

1. 停止 API 容器，确保无其他进程访问 SQLite。
2. 用 `docker volume inspect -f '{{.Mountpoint}}' stockflow-data` 查看数据卷在 Linux 服务器上的目录。将其中现有的 `stockflow.db`、`stockflow.db-wal`、`stockflow.db-shm` 移到独立的故障分析目录。
3. 将选定的备份 `.db` 复制到卷目录中，命名为 `stockflow.db`，所有者设为 UID 10001。
4. 在副本上先运行 `sqlite3 stockflow.db 'PRAGMA quick_check;'` 并核对 `SELECT COUNT(*) FROM documents;`、关键物资余额。然后启动 API 容器，登录并再次核对。

自动化测试会把实际备份复制到另一个临时数据库，检查完整性、库存、单据与重新初始化后的登录。

## 配置与联合发布

发布前核对 [release.yaml](release.yaml)。其中后端版本对应当前 Compose 默认镜像，升级示例镜像单列。整体版本 0.1.0 是此次工作区整理基线，组件 Git 引用在实际发布时填写。

1. 在后端仓库独立运行测试并用其 Dockerfile 构建镜像，记录源码 Git 引用与镜像标签。导入目标主机后，通过相应平台的 Compose 启动后端。
2. 在前端仓库设置面向客户端的 HTTPS API 基址，执行 `npm ci` 及目标平台构建。H5 产物部署至静态站点，微信小程序和原生 App 分别通过各自发布工具发布。客户端通过 HTTPS 连接 Compose 后端。
3. 置备与 Compose 同目录的本机 `stockflow.env`，参考 [配置模板](stockflow.env.example)。Linux 可使用单独保存的实际 Caddy 配置。升级前核对镜像、外部卷、SQLite 备份及迁移版本，再检查接口和客户端连通性。

Windows 与 Linux 配置可用 `docker compose -f <文件> config --no-env-resolution --quiet` 静态校验。环境文件就绪后，可在对应平台目录运行 `docker compose config --quiet` 验证完整配置。
