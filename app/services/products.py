import sqlite3


def list_products(db: sqlite3.Connection, category: str | None = None, q: str | None = None,
                  include_inactive: bool = False) -> list[dict]:
    sql = """SELECT p.*,
             (SELECT COUNT(*) FROM box_units b WHERE b.product_id=p.id AND b.remaining=b.capacity AND b.remaining>0) full_boxes,
             (SELECT COUNT(*) FROM box_units b WHERE b.product_id=p.id AND b.remaining>0 AND b.remaining<b.capacity) opened_boxes,
             (SELECT COALESCE(SUM(b.remaining),0) FROM box_units b WHERE b.product_id=p.id) boxed_qty
             FROM products p WHERE 1=1"""
    args = []
    if not include_inactive:
        sql += " AND p.is_active=1"
    if category:
        sql += " AND p.category=?"
        args.append(category)
    if q:
        sql += " AND (p.brand LIKE ? OR p.name LIKE ?)"
        args.extend([f"%{q}%", f"%{q}%"])
    return [dict(row) for row in db.execute(sql + " ORDER BY p.category,p.brand,p.name,p.id", args)]
