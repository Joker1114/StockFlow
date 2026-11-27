import re
import sqlite3
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import AwareDatetime

from .auth import USER_PROFILE, admin, current_user, hash_password, make_token, verify_password
from .config import jwt_secret, token_hours
from .database import connect, initialize, now, transaction
from .errors import fail
from .schemas import (CompanyCreate, CompanyPatch, DocumentCreate, Login, ProductCreate, ProductPatch, RuleCreate,
                      ScanResolve, SupplierCreate, SupplierPatch, UserCreate, UserPatch)
from .services.brand_codes import configured_brand, find_box, new_box_code, parse_brand_code, validate_box_brand
from .services.companies import require_active_company
from .services.documents import create_document, delete_document, detail, document_filter_options, list_documents, returnable
from .services.exports import export_documents, export_stock
from .services.products import list_products


@asynccontextmanager
async def lifespan(app: FastAPI):
    jwt_secret()
    token_hours()
    initialize()
    yield


app = FastAPI(title="物资通 StockFlow", lifespan=lifespan)


@app.middleware("http")
async def body_limit(request: Request, call_next):
    if request.method in {"POST", "PATCH", "PUT"}:
        try:
            if int(request.headers.get("content-length", "0")) > 1_200_000:
                return JSONResponse({"detail": {"code": "BODY_TOO_LARGE", "message": "请求内容过大"}}, status_code=413)
        except ValueError:
            pass
        body = await request.body()
        if len(body) > 1_200_000:
            return JSONResponse({"detail": {"code": "BODY_TOO_LARGE", "message": "请求内容过大"}}, status_code=413)
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse({"detail": {"code": "VALIDATION_ERROR", "message": "请求参数不正确", "errors": [
        {"field": ".".join(str(p) for p in e["loc"]), "message": str(e["msg"])} for e in exc.errors()
    ]}}, status_code=422)


@app.exception_handler(Exception)
async def internal_error(request: Request, exc: Exception):
    return JSONResponse({"detail": {"code": "INTERNAL_ERROR", "message": "服务器内部错误"}}, status_code=500)


@app.post("/api/auth/login")
def login(body: Login):
    db = connect()
    try:
        row = db.execute("SELECT id,username,password_hash,role,is_active FROM users WHERE username=?",
                         (body.username,)).fetchone()
    finally:
        db.close()
    if not row or not row["is_active"] or not verify_password(row["password_hash"], body.password):
        fail(401, "BAD_CREDENTIALS", "用户名或密码错误")
    return {"token": make_token(row["id"]), "token_type": "bearer",
            "user": {"id": row["id"], "username": row["username"], "role": row["role"]}}


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    return user


@app.get("/api/products")
def products(category: str | None = None, q: str | None = Query(default=None, max_length=100),
             include_inactive: bool = False, user: dict = Depends(current_user)):
    if category is not None and category not in ("TOBACCO", "ALCOHOL"):
        fail(422, "VALIDATION_ERROR", "类别不正确")
    db = connect()
    try:
        return list_products(db, category, q, include_inactive)
    finally:
        db.close()


@app.get("/api/stock/export.xlsx")
def stock_excel(category: Literal["TOBACCO", "ALCOHOL"] | None = None,
                q: str | None = Query(None, max_length=200), user: dict = Depends(current_user)):
    return export_stock(category, q)


@app.post("/api/products", status_code=201)
def add_product(body: ProductCreate, user: dict = Depends(admin)):
    with transaction() as db:
        try:
            product_id = db.execute("""INSERT INTO products(category,brand,name,specification,unit,scan_mode,bottles_per_box,created_at)
                                       VALUES(?,?,?,?,?,?,?,?)""", (body.category, body.brand, body.name,
                                       body.specification, body.unit, body.scan_mode, body.bottles_per_box, now())).lastrowid
        except sqlite3.IntegrityError:
            fail(409, "PRODUCT_EXISTS", "相同物资已存在")
        return dict(db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone())


@app.patch("/api/products/{product_id}")
@app.put("/api/products/{product_id}")
def edit_product(product_id: int, body: ProductPatch, user: dict = Depends(admin)):
    changes = body.model_dump(exclude_unset=True)
    if not changes or any(value is None for value in changes.values()):
        fail(422, "VALIDATION_ERROR", "请填写要修改的字段")
    with transaction() as db:
        row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not row:
            fail(404, "NOT_FOUND", "物资不存在")
        used = db.execute("SELECT 1 FROM document_items WHERE product_id=? LIMIT 1", (product_id,)).fetchone()
        if used and any(k in changes and changes[k] != row[k] for k in ("category", "unit", "scan_mode")):
            fail(409, "PRODUCT_HISTORY", "已有单据的物资不可修改类别、单位或扫码模式")
        category = changes.get("category", row["category"])
        unit = changes.get("unit", row["unit"])
        if category == "ALCOHOL" and unit != "瓶":
            fail(422, "ALCOHOL_UNIT", "酒水最小单位必须是瓶")
        if category == "ALCOHOL":
            if changes.get("scan_mode", "SERIAL") != "SERIAL":
                fail(422, "ALCOHOL_MODE", "酒水统一使用箱码与散瓶流程")
            changes["scan_mode"] = "SERIAL"
        try:
            db.execute("UPDATE products SET " + ",".join(f"{k}=?" for k in changes) + " WHERE id=?",
                       (*[int(v) if isinstance(v, bool) else v for v in changes.values()], product_id))
        except sqlite3.IntegrityError:
            fail(409, "PRODUCT_EXISTS", "相同物资已存在")
        return dict(db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone())


@app.get("/api/suppliers")
def suppliers(include_inactive: bool = False, user: dict = Depends(current_user)):
    if include_inactive and user["role"] != "ADMIN":
        fail(403, "FORBIDDEN", "需要管理员权限")
    db = connect()
    try:
        sql = "SELECT * FROM suppliers" + ("" if include_inactive else " WHERE is_active=1") + " ORDER BY name,id"
        return [dict(r) for r in db.execute(sql)]
    finally:
        db.close()


@app.get("/api/boxes")
def boxes(product_id: int = Query(gt=0), limit: int = Query(100, ge=1, le=200),
          offset: int = Query(0, ge=0), user: dict = Depends(current_user)):
    db = connect()
    try:
        if not db.execute("SELECT 1 FROM products WHERE id=? AND category='ALCOHOL'", (product_id,)).fetchone():
            fail(404, "NOT_FOUND", "酒水物资不存在")
        total = db.execute("SELECT COUNT(*) FROM box_units WHERE product_id=? AND remaining>0", (product_id,)).fetchone()[0]
        items = [dict(r) for r in db.execute("""SELECT b.code_value,b.capacity,b.remaining,s.name supplier_name
                                                 FROM box_units b LEFT JOIN suppliers s ON s.id=b.supplier_id
                                                 WHERE b.product_id=? AND b.remaining>0 ORDER BY b.id DESC
                                                 LIMIT ? OFFSET ?""", (product_id, limit, offset))]
        return {"total": total, "items": items}
    finally:
        db.close()


@app.post("/api/suppliers", status_code=201)
def add_supplier(body: SupplierCreate, user: dict = Depends(admin)):
    with transaction() as db:
        try:
            supplier_id = db.execute("INSERT INTO suppliers(name,created_at) VALUES(?,?)",
                                     (body.name, now())).lastrowid
        except sqlite3.IntegrityError:
            fail(409, "SUPPLIER_EXISTS", "供应商已存在")
        return dict(db.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)).fetchone())


@app.patch("/api/suppliers/{supplier_id}")
@app.put("/api/suppliers/{supplier_id}")
def edit_supplier(supplier_id: int, body: SupplierPatch, user: dict = Depends(admin)):
    changes = body.model_dump(exclude_unset=True)
    if not changes or any(v is None for v in changes.values()):
        fail(422, "VALIDATION_ERROR", "请填写要修改的字段")
    with transaction() as db:
        if not db.execute("SELECT 1 FROM suppliers WHERE id=?", (supplier_id,)).fetchone():
            fail(404, "NOT_FOUND", "供应商不存在")
        try:
            db.execute("UPDATE suppliers SET " + ",".join(f"{k}=?" for k in changes) + " WHERE id=?",
                       (*[int(v) if isinstance(v, bool) else v for v in changes.values()], supplier_id))
        except sqlite3.IntegrityError:
            fail(409, "SUPPLIER_EXISTS", "供应商已存在")
        return dict(db.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)).fetchone())


@app.post("/api/scan/resolve")
def resolve(body: ScanResolve, include_inactive: bool = False, user: dict = Depends(current_user)):
    raw = body.raw_text
    parsed = parse_brand_code(raw)
    display_code = raw
    db = connect()
    try:
        box = find_box(db, raw, parsed)
        if body.product_id is not None:
            product = db.execute("SELECT * FROM products WHERE id=?", (body.product_id,)).fetchone()
            if not product or (not product["is_active"] and not include_inactive):
                fail(422, "PRODUCT_INVALID", "物资不存在或已停用")
            if product["category"] == "ALCOHOL":
                validate_box_brand(product["brand"], raw)
                if box is None:
                    display_code = new_box_code(product["brand"], raw, parsed)
            if box and box["product_id"] != body.product_id:
                fail(409, "BOX_PRODUCT_CONFLICT", "箱码已绑定其他物资，请核对所选物资")
        elif box and (box["is_active"] or include_inactive):
            validate_box_brand(box["brand"], raw)
        rules = db.execute("""SELECT r.id,r.product_id,r.match_type,r.match_value,p.category,p.brand,
                                  p.name,p.specification,p.unit,p.scan_mode,p.stock_qty
                           FROM qr_rules r JOIN products p ON p.id=r.product_id
                           WHERE r.is_active=1 AND p.is_active=1""").fetchall()
    finally:
        db.close()
    if box and (box["is_active"] or include_inactive):
        candidates = [dict(r) for r in rules if r["product_id"] == box["product_id"]]
        if not candidates:
            db = connect()
            try:
                product = db.execute("SELECT * FROM products WHERE id=?", (box["product_id"],)).fetchone()
                candidates = [dict(product)] if product else []
            finally:
                db.close()
        if parsed and parsed[0] == configured_brand(box["brand"]):
            display_code = parsed[1]
        box_state = {key: box[key] for key in ("product_id", "code_value", "capacity", "remaining", "is_active")}
        return {"match_type": "BOX", "candidates": candidates[:1], "box": box_state, "code_value": display_code}
    exact = [r for r in rules if r["match_type"] == "EXACT" and body.raw_text == r["match_value"]]
    prefixes = [r for r in rules if r["match_type"] == "PREFIX" and body.raw_text.startswith(r["match_value"])]
    selected = exact or [r for r in prefixes if len(r["match_value"]) == max(
        (len(p["match_value"]) for p in prefixes), default=0)]
    by_product = {r["product_id"]: dict(r) for r in selected}
    return {"match_type": "EXACT" if exact else "PREFIX" if selected else None,
            "candidates": list(by_product.values()), "box": None, "code_value": display_code}


@app.get("/api/qr-rules")
def rules(user: dict = Depends(admin)):
    db = connect()
    try:
        return [dict(r) for r in db.execute("SELECT * FROM qr_rules ORDER BY id DESC")]
    finally:
        db.close()


@app.post("/api/qr-rules", status_code=201)
def add_rule(body: RuleCreate, user: dict = Depends(admin)):
    with transaction() as db:
        product = db.execute("SELECT id,is_active FROM products WHERE id=?", (body.product_id,)).fetchone()
        if not product or not product["is_active"]:
            fail(422, "PRODUCT_INVALID", "物资不存在或已停用")
        try:
            rule_id = db.execute("INSERT INTO qr_rules(product_id,match_type,match_value) VALUES(?,?,?)",
                                 (body.product_id, body.match_type, body.match_value)).lastrowid
        except sqlite3.IntegrityError:
            fail(409, "RULE_EXISTS", "规则已存在")
        return dict(db.execute("SELECT * FROM qr_rules WHERE id=?", (rule_id,)).fetchone())


@app.delete("/api/qr-rules/{rule_id}")
def delete_rule(rule_id: int, user: dict = Depends(admin)):
    with transaction() as db:
        if db.execute("DELETE FROM qr_rules WHERE id=?", (rule_id,)).rowcount != 1:
            fail(404, "NOT_FOUND", "规则不存在")
        return {"ok": True}


@app.post("/api/documents", status_code=201)
def add_document(body: DocumentCreate, user: dict = Depends(current_user)):
    return create_document(body, user["id"])


@app.get("/api/documents")
def documents(direction: str | None = None, kind: str | None = None, limit: int = Query(20, ge=1, le=100),
              offset: int = Query(0, ge=0), q: str | None = Query(None, max_length=100),
              created_from: AwareDatetime | None = None, created_before: AwareDatetime | None = None,
              product_id: int | None = Query(None, gt=0), supplier_id: int | None = Query(None, gt=0),
              recipient_company_id: int | None = Query(None, gt=0),
              box_code: str | None = Query(None, min_length=1, max_length=2048),
              user: dict = Depends(current_user)):
    if direction is not None and direction not in ("IN", "OUT"):
        fail(422, "VALIDATION_ERROR", "单据类型不正确")
    if kind is not None and kind not in ("NORMAL", "RETURN", "ADJUST"):
        fail(422, "VALIDATION_ERROR", "单据类型不正确")
    return list_documents(direction, kind, limit, offset, q=q, created_from=created_from,
                          created_before=created_before, product_id=product_id, supplier_id=supplier_id,
                          recipient_company_id=recipient_company_id, box_code=box_code)


@app.get("/api/documents/filter-options")
def filter_options(outbound_only: bool = False, user: dict = Depends(current_user)):
    return document_filter_options(outbound_only)


@app.get("/api/documents/export.xlsx")
def documents_excel(direction: Literal["IN", "OUT"] | None = None,
                    product_id: int | None = Query(None, gt=0), supplier_id: int | None = Query(None, gt=0),
                    recipient_company_id: int | None = Query(None, gt=0),
                    box_code: str | None = Query(None, min_length=1, max_length=2048),
                    created_from: AwareDatetime | None = None, created_before: AwareDatetime | None = None,
                    user: dict = Depends(current_user)):
    return export_documents(direction, product_id, supplier_id, recipient_company_id=recipient_company_id,
                            box_code=box_code, created_from=created_from, created_before=created_before)


@app.get("/api/documents/{doc_id}/export.xlsx")
def document_excel(doc_id: int, user: dict = Depends(current_user)):
    return export_documents(doc_id=doc_id)


@app.get("/api/documents/{doc_id}")
def document(doc_id: int, user: dict = Depends(current_user)):
    db = connect()
    try:
        db.execute("BEGIN")
        result = detail(db, doc_id)
    finally:
        db.close()
    if not result:
        fail(404, "NOT_FOUND", "单据不存在")
    return result


@app.delete("/api/documents/{doc_id}", status_code=204)
def remove_document(doc_id: int, user: dict = Depends(admin)):
    delete_document(doc_id, user["id"])
    return Response(status_code=204)


@app.get("/api/documents/{doc_id}/returnable")
def document_returnable(doc_id: int, user: dict = Depends(current_user)):
    db = connect()
    try:
        db.execute("BEGIN")
        return returnable(db, doc_id)
    finally:
        db.close()


@app.get("/api/companies")
def companies(include_inactive: bool = False, user: dict = Depends(current_user)):
    if include_inactive and user["role"] != "ADMIN":
        fail(403, "FORBIDDEN", "需要管理员权限")
    db = connect()
    try:
        sql = "SELECT * FROM departments" + ("" if include_inactive else " WHERE is_active=1")
        return [dict(r) for r in db.execute(sql + " ORDER BY name,id")]
    finally:
        db.close()


@app.get("/api/departments")
def departments(user: dict = Depends(admin)):
    return companies(include_inactive=True, user=user)


@app.post("/api/companies", status_code=201)
@app.post("/api/departments", status_code=201)
def add_company(body: CompanyCreate, user: dict = Depends(admin)):
    with transaction() as db:
        try:
            department_id = db.execute("INSERT INTO departments(name,created_at) VALUES(?,?)",
                                       (body.name, now())).lastrowid
        except sqlite3.IntegrityError:
            fail(409, "COMPANY_EXISTS", "子公司名称已存在")
        return dict(db.execute("SELECT * FROM departments WHERE id=?", (department_id,)).fetchone())


@app.put("/api/companies/{department_id}")
@app.patch("/api/companies/{department_id}")
@app.put("/api/departments/{department_id}")
@app.patch("/api/departments/{department_id}")
def edit_company(department_id: int, body: CompanyPatch, user: dict = Depends(admin)):
    changes = body.model_dump(exclude_unset=True)
    if not changes or any(value is None for value in changes.values()):
        fail(422, "VALIDATION_ERROR", "请填写要修改的字段")
    with transaction() as db:
        if not db.execute("SELECT 1 FROM departments WHERE id=?", (department_id,)).fetchone():
            fail(404, "NOT_FOUND", "子公司不存在")
        try:
            db.execute("UPDATE departments SET " + ",".join(f"{key}=?" for key in changes) + " WHERE id=?",
                       (*changes.values(), department_id))
        except sqlite3.IntegrityError:
            fail(409, "COMPANY_EXISTS", "子公司名称已存在")
        return dict(db.execute("SELECT * FROM departments WHERE id=?", (department_id,)).fetchone())


@app.get("/api/users")
def users(user: dict = Depends(admin)):
    db = connect()
    try:
        return [dict(r) for r in db.execute(USER_PROFILE + " ORDER BY u.id")]
    finally:
        db.close()


@app.post("/api/users", status_code=201)
def add_user(body: UserCreate, user: dict = Depends(admin)):
    with transaction() as db:
        require_active_company(db, body.department_id)
        try:
            user_id = db.execute("""INSERT INTO users(username,password_hash,role,name,department_id,created_at)
                                    VALUES(?,?,?,?,?,?)""", (body.username, hash_password(body.password),
                                    body.role, body.name, body.department_id, now())).lastrowid
        except sqlite3.IntegrityError:
            fail(409, "USER_EXISTS", "工号已存在")
        return dict(db.execute(USER_PROFILE + " WHERE u.id=?", (user_id,)).fetchone())


@app.patch("/api/users/{user_id}")
@app.put("/api/users/{user_id}")
def edit_user(user_id: int, body: UserPatch, user: dict = Depends(admin)):
    changes = body.model_dump(exclude_unset=True)
    if not changes or any(value is None for value in changes.values()):
        fail(422, "VALIDATION_ERROR", "请填写要修改的字段")
    with transaction() as db:
        target = db.execute(USER_PROFILE + " WHERE u.id=?", (user_id,)).fetchone()
        if not target:
            fail(404, "NOT_FOUND", "用户不存在")
        if target["role"] == "ADMIN" and target["is_active"] and changes.get("is_active") is False:
            count = db.execute("SELECT COUNT(*) FROM users WHERE role='ADMIN' AND is_active=1").fetchone()[0]
            if count <= 1:
                fail(409, "LAST_ADMIN", "不能停用最后一位管理员")
        if changes.keys() & {"username", "name", "department_id"}:
            if target["username"] == "admin":
                fail(422, "BUILTIN_ADMIN", "内置管理员账号资料固定")
            username = changes.get("username", target["username"])
            if not re.fullmatch(r"[0-9]+", username):
                fail(422, "EMPLOYEE_NUMBER_REQUIRED", "请填写纯数字工号")
            department_id = changes.get("department_id", target["department_id"])
            if not changes.get("name", target["name"]) or department_id is None:
                fail(422, "USER_PROFILE_INCOMPLETE", "请填写姓名并选择所属公司")
            if department_id != target["department_id"]:
                require_active_company(db, department_id)
        if "password" in changes:
            changes["password_hash"] = hash_password(changes.pop("password"))
        try:
            db.execute("UPDATE users SET " + ",".join(f"{key}=?" for key in changes) + " WHERE id=?",
                       (*changes.values(), user_id))
        except sqlite3.IntegrityError:
            fail(409, "USER_EXISTS", "工号已存在")
        return dict(db.execute(USER_PROFILE + " WHERE u.id=?", (user_id,)).fetchone())
