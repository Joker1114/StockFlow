# StockFlow 后端

FastAPI + SQLite。使用 Python 3.11+ 和虚拟环境，在 `backend/` 目录执行以下命令。

```bash
python -m pip install -r requirements-dev.lock
python -m pytest -q
```

运行环境安装 `requirements.lock`。按 [.env.example](.env.example) 在启动进程前设置环境变量。使用 `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log` 启动。相对数据库路径以启动目录为基准，首次初始化空用户表时使用管理员初始密码。

使用 `docker build -t stockflow:<版本> .` 独立构建镜像，容器的 SQLite 数据目录为 `/data`。数据库定义和顺序迁移集中在 [app/database.py](app/database.py)。运行中的 API 提供 `/openapi.json` 和 `/docs`，可参考 [请求示例](docs/api-examples.md)。

依赖更新时编辑对应的 requirements 输入文件，再依次生成锁文件并运行测试。

```bash
uv pip compile --universal --python-version 3.11 requirements.txt -o requirements.lock
uv pip compile --universal --python-version 3.11 -c requirements.lock requirements-dev.txt -o requirements-dev.lock
```
