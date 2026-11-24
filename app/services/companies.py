import sqlite3

from ..errors import fail


def require_active_company(db: sqlite3.Connection, company_id: int) -> sqlite3.Row:
    company = db.execute("SELECT id,name FROM departments WHERE id=? AND is_active=1", (company_id,)).fetchone()
    if not company:
        fail(422, "COMPANY_INVALID", "子公司不存在或已停用，请重新选择")
    return company
