import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import MIN_PASSWORD_LENGTH, database_path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 10000")
    return db


@contextmanager
def transaction():
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS departments (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL UNIQUE,
 is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 username TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('ADMIN','STAFF')),
 name TEXT,
 department_id INTEGER REFERENCES departments(id),
 is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suppliers (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL UNIQUE,
 is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 category TEXT NOT NULL CHECK(category IN ('TOBACCO','ALCOHOL')),
 brand TEXT NOT NULL, name TEXT NOT NULL, specification TEXT NOT NULL,
 unit TEXT NOT NULL,
 scan_mode TEXT NOT NULL DEFAULT 'QUANTITY' CHECK(scan_mode IN ('QUANTITY','SERIAL')),
 stock_qty INTEGER NOT NULL DEFAULT 0 CHECK(stock_qty >= 0),
 loose_qty INTEGER NOT NULL DEFAULT 0 CHECK(loose_qty >= 0),
 bottles_per_box INTEGER NOT NULL DEFAULT 6 CHECK(bottles_per_box BETWEEN 1 AND 1000),
 is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
 created_at TEXT NOT NULL,
 UNIQUE(category, brand, name, specification, unit)
);
CREATE TABLE IF NOT EXISTS qr_rules (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 product_id INTEGER NOT NULL REFERENCES products(id),
 match_type TEXT NOT NULL CHECK(match_type IN ('EXACT','PREFIX')),
 match_value TEXT NOT NULL,
 is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
 UNIQUE(product_id, match_type, match_value)
);
CREATE TABLE IF NOT EXISTS documents (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 doc_no TEXT NOT NULL UNIQUE,
 request_id TEXT NOT NULL UNIQUE,
 request_hash TEXT NOT NULL,
 direction TEXT NOT NULL CHECK(direction IN ('IN','OUT')),
 kind TEXT NOT NULL DEFAULT 'NORMAL' CHECK(kind IN ('NORMAL','RETURN','ADJUST')),
 source_document_id INTEGER REFERENCES documents(id),
 operator_id INTEGER NOT NULL REFERENCES users(id),
 supplier_id INTEGER REFERENCES suppliers(id), supplier_name TEXT,
 recipient TEXT, recipient_company_id INTEGER REFERENCES departments(id),
 remark TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS document_items (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 document_id INTEGER NOT NULL REFERENCES documents(id),
 product_id INTEGER NOT NULL REFERENCES products(id),
 quantity INTEGER NOT NULL CHECK(quantity > 0),
 loose_quantity INTEGER NOT NULL DEFAULT 0 CHECK(loose_quantity >= 0),
 UNIQUE(document_id, product_id)
);
CREATE TABLE IF NOT EXISTS document_deletions (
 document_id INTEGER PRIMARY KEY,
 request_id TEXT NOT NULL UNIQUE,
 operator_id INTEGER NOT NULL REFERENCES users(id),
 deleted_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scan_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 document_item_id INTEGER NOT NULL REFERENCES document_items(id),
 product_id INTEGER NOT NULL REFERENCES products(id),
 code_value TEXT NOT NULL,
 code_kind TEXT NOT NULL CHECK(code_kind IN ('QUANTITY','SERIAL')),
 direction TEXT NOT NULL CHECK(direction IN ('IN','OUT')),
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scan_events_code ON scan_events(code_kind, code_value, id);
CREATE INDEX IF NOT EXISTS idx_scan_events_item ON scan_events(document_item_id);
CREATE INDEX IF NOT EXISTS idx_doc_items_product ON document_items(product_id);
CREATE INDEX IF NOT EXISTS idx_docs_created ON documents(created_at);
CREATE TABLE IF NOT EXISTS box_units (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 product_id INTEGER NOT NULL REFERENCES products(id),
 code_value TEXT NOT NULL UNIQUE,
 capacity INTEGER NOT NULL CHECK(capacity > 0),
 remaining INTEGER NOT NULL CHECK(remaining >= 0 AND remaining <= capacity),
 supplier_id INTEGER REFERENCES suppliers(id),
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_box_units_product ON box_units(product_id, remaining);
CREATE TABLE IF NOT EXISTS box_actions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 document_item_id INTEGER NOT NULL REFERENCES document_items(id),
 box_unit_id INTEGER NOT NULL REFERENCES box_units(id),
 code_value TEXT NOT NULL,
 direction TEXT NOT NULL CHECK(direction IN ('IN','OUT')),
 quantity INTEGER NOT NULL CHECK(quantity > 0),
 capacity INTEGER NOT NULL CHECK(capacity > 0),
 remaining_after INTEGER NOT NULL CHECK(remaining_after >= 0),
 created_at TEXT NOT NULL,
 UNIQUE(document_item_id, box_unit_id)
);
CREATE INDEX IF NOT EXISTS idx_box_actions_code ON box_actions(code_value, id);
"""


def initialize():
    from .auth import hash_password

    db = connect()
    try:
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript(SCHEMA)
    finally:
        db.close()
    with transaction() as db:
        if db.execute("PRAGMA user_version").fetchone()[0] < 2:
            _migrate_alcohol(db)
            db.execute("PRAGMA user_version = 2")
        if db.execute("PRAGMA user_version").fetchone()[0] < 3:
            _migrate_document_workflows(db)
            db.execute("PRAGMA user_version = 3")
        if db.execute("PRAGMA user_version").fetchone()[0] < 4:
            _add_column(db, "users", "name", "TEXT")
            _add_column(db, "users", "department_id", "INTEGER REFERENCES departments(id)")
            db.execute("PRAGMA user_version = 4")
        if db.execute("PRAGMA user_version").fetchone()[0] < 5:
            _add_column(db, "documents", "recipient_company_id", "INTEGER REFERENCES departments(id)")
            db.execute("PRAGMA user_version = 5")
        count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if not count:
            username = os.getenv("STOCKFLOW_ADMIN_USERNAME", "admin").strip()
            password = os.getenv("STOCKFLOW_ADMIN_PASSWORD", "")
            if username != "admin" or not MIN_PASSWORD_LENGTH <= len(password) <= 256:
                raise RuntimeError(f"首次启动需使用管理员账号 admin，并设置 {MIN_PASSWORD_LENGTH} 至 256 位密码")
            db.execute(
                "INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,'ADMIN',?)",
                (username, hash_password(password), now()),
            )


def _add_column(db: sqlite3.Connection, table: str, column: str, definition: str):
    names = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
    if column not in names:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate_alcohol(db: sqlite3.Connection):
    """旧库存按原单位保存；旧酒水序列码按每码一件迁为容量 1 的箱记录。"""
    _add_column(db, "products", "loose_qty", "INTEGER NOT NULL DEFAULT 0 CHECK(loose_qty >= 0)")
    _add_column(db, "products", "bottles_per_box", "INTEGER NOT NULL DEFAULT 6 CHECK(bottles_per_box BETWEEN 1 AND 1000)")
    _add_column(db, "documents", "supplier_id", "INTEGER REFERENCES suppliers(id)")
    _add_column(db, "documents", "supplier_name", "TEXT")
    _add_column(db, "document_items", "loose_quantity", "INTEGER NOT NULL DEFAULT 0 CHECK(loose_quantity >= 0)")

    for product in db.execute("SELECT id,unit,scan_mode,stock_qty FROM products WHERE category='ALCOHOL'").fetchall():
        if product["stock_qty"] and product["unit"] != "瓶":
            raise RuntimeError(f"酒水物资 {product['id']} 的旧库存单位不是瓶，请先人工核对并迁移")
        if product["scan_mode"] == "QUANTITY":
            db.execute("UPDATE products SET loose_qty=stock_qty WHERE id=?", (product["id"],))
        else:
            events = db.execute("""SELECT s.code_value,s.direction FROM scan_events s
                                   WHERE s.code_kind='SERIAL' AND s.product_id=? AND s.id=(
                                     SELECT MAX(x.id) FROM scan_events x WHERE x.code_kind='SERIAL'
                                     AND x.code_value=s.code_value)""", (product["id"],)).fetchall()
            active = 0
            for event in events:
                remaining = int(event["direction"] == "IN")
                active += remaining
                db.execute("""INSERT OR IGNORE INTO box_units(product_id,code_value,capacity,remaining,created_at)
                              VALUES(?,?,1,?,?)""", (product["id"], event["code_value"], remaining, now()))
            if active > product["stock_qty"]:
                raise RuntimeError(f"酒水物资 {product['id']} 旧编码数量超过库存")
            db.execute("UPDATE products SET loose_qty=? WHERE id=?", (product["stock_qty"] - active, product["id"]))


def _migrate_document_workflows(db: sqlite3.Connection):
    columns = {row[1] for row in db.execute("PRAGMA table_info(documents)")}
    if "kind" not in columns:
        db.execute("ALTER TABLE documents ADD COLUMN kind TEXT NOT NULL DEFAULT 'NORMAL' CHECK(kind IN ('NORMAL','RETURN','ADJUST'))")
    if "source_document_id" not in columns:
        db.execute("ALTER TABLE documents ADD COLUMN source_document_id INTEGER REFERENCES documents(id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_docs_source ON documents(source_document_id,kind)")
    # 旧数量模式酒水的余额已在 v2 迁为散瓶，统一箱码流程无需改变余额。
    db.execute("UPDATE products SET scan_mode='SERIAL' WHERE category='ALCOHOL' AND scan_mode='QUANTITY'")
