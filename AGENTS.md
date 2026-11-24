# StockFlow backend 工程约定

依赖按锁文件安装。运行 python -m pytest -q 验证变更。迁移集中在 app/database.py，测试使用临时 SQLite 数据库。运行配置和数据库独立保存。
