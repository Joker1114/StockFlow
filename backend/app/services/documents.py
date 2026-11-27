import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from ..database import connect, now, transaction
from ..errors import fail
from ..schemas import DocumentCreate
from .brand_codes import find_box, new_box_code, parse_brand_code, validate_box_brand
from .companies import require_active_company


def detail(db: sqlite3.Connection, doc_id: int) -> dict | None:
    row = db.execute("""SELECT d.id,d.doc_no,d.request_id,d.direction,d.kind,d.source_document_id,
                             source.doc_no source_document_no,d.supplier_id,d.supplier_name,
                             d.recipient,d.recipient_company_id,d.remark,d.created_at,
                             u.id operator_id,COALESCE(u.name,u.username) operator_name
                      FROM documents d JOIN users u ON u.id=d.operator_id
                      LEFT JOIN documents source ON source.id=d.source_document_id WHERE d.id=?""", (doc_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    items = db.execute("""SELECT i.id,i.product_id,i.quantity,i.loose_quantity,p.category,p.brand,p.name,
                               p.specification,p.unit,p.scan_mode
                        FROM document_items i JOIN products p ON p.id=i.product_id
                        WHERE i.document_id=? ORDER BY i.id""", (doc_id,)).fetchall()
    result["items"] = []
    for item in items:
        data = dict(item)
        data["codes"] = [r[0] for r in db.execute(
            "SELECT code_value FROM scan_events WHERE document_item_id=? ORDER BY id", (item["id"],)
        )]
        data["boxes"] = [dict(r) for r in db.execute("""SELECT code_value,direction,quantity,capacity,remaining_after
                                                         FROM box_actions WHERE document_item_id=? ORDER BY id""",
                                                    (item["id"],))]
        result["items"].append(data)
    return result


def canonical_hash(body: DocumentCreate, operator_id: int) -> str:
    data = {
        "operator_id": operator_id,
        "direction": body.direction,
        "kind": body.kind,
        "source_document_id": body.source_document_id,
        "supplier_id": body.supplier_id,
        "recipient": body.recipient,
        "remark": body.remark,
        "items": sorted([{
            "product_id": i.product_id,
            "quantity": i.quantity,
            "loose_quantity": i.loose_quantity,
            "codes": sorted(i.codes),
            "boxes": sorted([b.model_dump() for b in i.boxes], key=lambda b: b["code_value"]),
        } for i in body.items], key=lambda i: i["product_id"]),
    }
    # Keep existing request hashes valid when retrying orders saved before company selection.
    if body.recipient_company_id is not None:
        data["recipient_company_id"] = body.recipient_company_id
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _validate_tobacco(db, body, item, product):
    if item.boxes or item.loose_quantity not in (None, 0) or item.quantity is None:
        fail(422, "ITEM_MODE", "烟草物资需填写数量，不能使用酒水箱码或散瓶字段")
    if product["scan_mode"] == "SERIAL":
        if item.quantity != len(item.codes):
            fail(422, "SERIAL_QUANTITY", "一物一码数量必须等于编码数")
        for code in item.codes:
            history = db.execute("""SELECT product_id,direction FROM scan_events
                                     WHERE code_kind='SERIAL' AND code_value=? ORDER BY id DESC LIMIT 1""", (code,)).fetchone()
            different = db.execute("""SELECT 1 FROM scan_events WHERE code_kind='SERIAL'
                                     AND code_value=? AND product_id<>? LIMIT 1""",
                                   (code, item.product_id)).fetchone()
            bound_box = db.execute("SELECT product_id FROM box_units WHERE code_value=?", (code,)).fetchone()
            if different or bound_box:
                fail(409, "SERIAL_PRODUCT_CONFLICT", "独立编码已绑定其他物资")
            in_stock = bool(history and history["direction"] == "IN")
            if body.direction == "IN" and in_stock:
                fail(409, "SERIAL_ALREADY_IN", "独立编码已在库")
            if body.direction == "OUT" and not in_stock:
                fail(409, "SERIAL_NOT_IN", "独立编码不在库")
    if body.direction == "OUT" and product["stock_qty"] < item.quantity:
        fail(409, "INSUFFICIENT_STOCK", "库存不足")
    return {"item": item, "product": product, "quantity": item.quantity, "loose": 0, "boxes": []}


def _validate_alcohol(db, body, item, product, seen_box_codes, seen_serials, returnable_item=None):
    if product["unit"] != "瓶":
        fail(409, "ALCOHOL_UNIT", "酒水物资单位需先迁移为瓶")
    if item.codes:
        fail(422, "ITEM_MODE", "酒水箱码请使用 boxes 字段")
    loose = item.loose_quantity if item.loose_quantity is not None else (item.quantity if not item.boxes else 0)
    if loose is None:
        loose = 0
    if body.kind == "NORMAL" and body.direction == "IN" and loose >= product["bottles_per_box"]:
        fail(422, "LOOSE_LIMIT", f"入库散瓶数量必须小于每箱 {product['bottles_per_box']} 瓶")
    if returnable_item and loose > returnable_item["loose_quantity"]:
        fail(409, "RETURN_EXCEEDED", "散瓶退库数量超过原单未退数量")
    boxes = []
    for action in item.boxes:
        raw = action.code_value
        validate_box_brand(product["brand"], raw)
        parsed = parse_brand_code(raw)
        unit = find_box(db, raw, parsed)
        if unit:
            code = unit["code_value"]
        elif body.direction == "IN" and body.kind != "RETURN":
            code = new_box_code(product["brand"], raw, parsed)
        else:
            code = raw
        if code in seen_box_codes or code in seen_serials:
            fail(422, "DUPLICATE_BOX", "同张单据重复扫描箱码")
        seen_box_codes.add(code)
        if unit and unit["product_id"] != item.product_id:
            fail(409, "BOX_PRODUCT_CONFLICT", "箱码已绑定其他物资")
        prior_serial = db.execute("""SELECT product_id FROM scan_events WHERE code_kind='SERIAL'
                                     AND code_value IN (?,?) ORDER BY id DESC LIMIT 1""", (raw, code)).fetchone()
        if prior_serial and prior_serial["product_id"] != item.product_id:
            fail(409, "BOX_PRODUCT_CONFLICT", "箱码已绑定其他物资")
        if body.kind == "RETURN":
            allowed = {b["code_value"]: b["quantity"] for b in returnable_item["boxes"]}
            if not unit or action.quantity is None or action.quantity > allowed.get(code, 0):
                fail(409, "RETURN_EXCEEDED", "箱码退库数量超过原单未退数量")
            if unit["remaining"] + action.quantity > unit["capacity"]:
                fail(409, "BOX_CAPACITY", "退库后箱内数量将超过原箱容量")
            boxes.append({"code": code, "unit": unit, "quantity": action.quantity,
                          "capacity": unit["capacity"], "remaining_after": unit["remaining"] + action.quantity})
        elif body.kind == "ADJUST" and body.direction == "IN":
            if unit:
                if action.quantity is None:
                    fail(422, "BOX_QUANTITY", "调整已有箱码时必须填写增加瓶数")
                if unit["remaining"] + action.quantity > unit["capacity"]:
                    fail(409, "BOX_CAPACITY", "调整后箱内数量将超过原箱容量")
                capacity = unit["capacity"]
                remaining_after = unit["remaining"] + action.quantity
            else:
                capacity = product["bottles_per_box"]
                remaining_after = action.quantity or capacity
                if remaining_after > capacity:
                    fail(422, "BOX_CAPACITY", "新增箱码数量不能超过每箱瓶数")
            boxes.append({"code": code, "unit": unit, "quantity": action.quantity or capacity,
                          "capacity": capacity, "remaining_after": remaining_after})
        elif body.direction == "IN":
            if action.quantity is not None:
                fail(422, "BOX_QUANTITY", "入库箱码数量由物资的每箱瓶数自动计算")
            if unit and unit["remaining"] > 0:
                fail(409, "BOX_ALREADY_IN", "箱码仍有库存，请勿重复入库")
            capacity = product["bottles_per_box"]
            boxes.append({"code": code, "unit": unit, "quantity": capacity,
                          "capacity": capacity, "remaining_after": capacity})
        else:
            if not unit or unit["remaining"] == 0:
                fail(409, "BOX_NOT_IN", "箱码没有可出库存")
            if action.quantity is None:
                fail(422, "BOX_QUANTITY", "请填写该箱本次出库瓶数")
            if action.quantity > unit["remaining"]:
                fail(409, "BOX_INSUFFICIENT", "箱码剩余瓶数不足")
            boxes.append({"code": code, "unit": unit, "quantity": action.quantity,
                          "capacity": unit["capacity"], "remaining_after": unit["remaining"] - action.quantity})
    quantity = loose + sum(b["quantity"] for b in boxes)
    if quantity <= 0 or quantity > 1000000:
        fail(422, "ITEM_QUANTITY", "每行物资数量必须在 1 到 1000000 之间")
    if item.quantity is not None and item.quantity != quantity:
        fail(422, "ITEM_QUANTITY", "物资总瓶数与散瓶、箱码明细不一致")
    if body.direction == "OUT":
        if loose > product["loose_qty"]:
            fail(409, "LOOSE_INSUFFICIENT", "散瓶库存不足")
        if quantity > product["stock_qty"]:
            fail(409, "INSUFFICIENT_STOCK", "库存不足")
    return {"item": item, "product": product, "quantity": quantity, "loose": loose, "boxes": boxes}


def returnable(db: sqlite3.Connection, source_id: int) -> dict:
    source = db.execute("""SELECT id,doc_no,recipient,recipient_company_id FROM documents
                           WHERE id=? AND kind='NORMAL' AND direction='OUT'""",
                        (source_id,)).fetchone()
    if not source:
        fail(422, "SOURCE_INVALID", "原单必须是普通出库单")
    result = {"source_document_id": source_id, "source_document_no": source["doc_no"],
              "recipient": source["recipient"], "recipient_company_id": source["recipient_company_id"], "items": []}
    original_items = db.execute("""SELECT i.id,i.product_id,i.quantity,i.loose_quantity,p.category,p.brand,p.name,
                                        p.specification,p.unit,p.scan_mode FROM document_items i
                                 JOIN products p ON p.id=i.product_id WHERE i.document_id=? ORDER BY i.id""",
                                (source_id,)).fetchall()
    for original in original_items:
        item = dict(original)
        returned = db.execute("""SELECT COALESCE(SUM(i.quantity),0) total,COALESCE(SUM(i.loose_quantity),0) loose
                               FROM documents d JOIN document_items i ON i.document_id=d.id
                               WHERE d.kind='RETURN' AND d.source_document_id=? AND i.product_id=?""",
                              (source_id, original["product_id"])).fetchone()
        item["quantity"] = original["quantity"] - returned["total"]
        item["loose_quantity"] = original["loose_quantity"] - returned["loose"]
        item["boxes"] = []
        for box in db.execute("SELECT code_value,quantity FROM box_actions WHERE document_item_id=? ORDER BY id",
                              (original["id"],)):
            used = db.execute("""SELECT COALESCE(SUM(a.quantity),0) FROM documents d
                                 JOIN document_items i ON i.document_id=d.id
                                 JOIN box_actions a ON a.document_item_id=i.id
                                 WHERE d.kind='RETURN' AND d.source_document_id=? AND a.code_value=?""",
                              (source_id, box["code_value"])).fetchone()[0]
            available = box["quantity"] - used
            if available > 0:
                item["boxes"].append({"code_value": box["code_value"], "quantity": available})
        original_codes = [r[0] for r in db.execute("SELECT code_value FROM scan_events WHERE document_item_id=? ORDER BY id",
                                                 (original["id"],))]
        returned_codes = {r[0] for r in db.execute("""SELECT s.code_value FROM documents d
                   JOIN document_items i ON i.document_id=d.id JOIN scan_events s ON s.document_item_id=i.id
                   WHERE d.kind='RETURN' AND d.source_document_id=? AND i.product_id=?""",
                                                  (source_id, original["product_id"]))}
        item["codes"] = [c for c in original_codes if c not in returned_codes]
        result["items"].append(item)
    return result


def create_document(body: DocumentCreate, operator_id: int) -> dict:
    request_hash = canonical_hash(body, operator_id)
    with transaction() as db:
        prior = db.execute("SELECT id,request_hash FROM documents WHERE request_id=?", (str(body.request_id),)).fetchone()
        if prior:
            if prior["request_hash"] != request_hash:
                fail(409, "REQUEST_ID_CONFLICT", "请求编号已用于另一张单据")
            return detail(db, prior["id"])
        if db.execute("SELECT 1 FROM document_deletions WHERE request_id=?", (str(body.request_id),)).fetchone():
            fail(409, "DOCUMENT_DELETED", "此请求的单据已删除，请重新填写单据")

        supplier = None
        recipient = body.recipient
        company_id = None
        if body.kind == "NORMAL" and body.direction == "IN":
            supplier = db.execute("SELECT id,name,is_active FROM suppliers WHERE id=?", (body.supplier_id,)).fetchone()
            if not supplier or not supplier["is_active"]:
                fail(422, "SUPPLIER_INVALID", "供应商不存在或已停用")
        if body.kind == "NORMAL" and body.direction == "OUT":
            if body.recipient_company_id is None:
                fail(422, "RECIPIENT_COMPANY_REQUIRED", "请选择领用公司")
            company = require_active_company(db, body.recipient_company_id)
            company_id, recipient = company["id"], company["name"]
        available_items = {}
        source = None
        if body.kind == "RETURN":
            source = returnable(db, body.source_document_id)
            available_items = {item["product_id"]: item for item in source["items"]}
            company_id, recipient = source["recipient_company_id"], source["recipient"]

        validated = []
        seen_serials = set()
        seen_box_codes = set()
        for item in body.items:
            product = db.execute("SELECT * FROM products WHERE id=?", (item.product_id,)).fetchone()
            if not product:
                fail(422, "PRODUCT_INVALID", f"物资 {item.product_id} 不存在")
            if not product["is_active"] and body.kind == "NORMAL":
                fail(409, "PRODUCT_INACTIVE", f"物资 {item.product_id} 已停用")
            available = available_items.get(item.product_id)
            if body.kind == "RETURN":
                if not available:
                    fail(422, "RETURN_PRODUCT", "退库物资不在原出库单中")
                if product["category"] == "TOBACCO":
                    if item.quantity is None or item.quantity > available["quantity"]:
                        fail(409, "RETURN_EXCEEDED", "退库数量超过原单未退数量")
                    if product["scan_mode"] == "SERIAL" and (set(item.codes) - set(available["codes"])):
                        fail(409, "RETURN_CODE", "退库编码不属于原单未退编码")
            if product["category"] == "ALCOHOL":
                validated.append(_validate_alcohol(db, body, item, product, seen_box_codes, seen_serials, available))
            else:
                if product["scan_mode"] == "SERIAL":
                    for code in item.codes:
                        if code in seen_serials or code in seen_box_codes:
                            fail(422, "DUPLICATE_SERIAL", "同张单据不能重复独立编码")
                        seen_serials.add(code)
                validated.append(_validate_tobacco(db, body, item, product))

        created = now()
        doc_id = db.execute("""INSERT INTO documents(doc_no,request_id,request_hash,direction,kind,source_document_id,
                               operator_id,supplier_id,supplier_name,recipient,recipient_company_id,remark,created_at)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            ("PENDING-" + str(body.request_id), str(body.request_id), request_hash, body.direction,
                             body.kind, body.source_document_id, operator_id, supplier["id"] if supplier else None,
                             supplier["name"] if supplier else None, recipient, company_id, body.remark, created)).lastrowid
        prefix = "TK" if body.kind == "RETURN" else ("ZR" if body.direction == "IN" else "ZC") if body.kind == "ADJUST" else ("RK" if body.direction == "IN" else "CK")
        doc_no = prefix + created[:10].replace("-", "") + f"{doc_id:06d}"
        db.execute("UPDATE documents SET doc_no=? WHERE id=?", (doc_no, doc_id))

        for entry in validated:
            item = entry["item"]
            quantity = entry["quantity"]
            loose = entry["loose"]
            item_id = db.execute("""INSERT INTO document_items(document_id,product_id,quantity,loose_quantity)
                                    VALUES(?,?,?,?)""", (doc_id, item.product_id, quantity, loose)).lastrowid
            if body.direction == "IN":
                db.execute("UPDATE products SET stock_qty=stock_qty+?,loose_qty=loose_qty+? WHERE id=?",
                           (quantity, loose, item.product_id))
            else:
                updated = db.execute("""UPDATE products SET stock_qty=stock_qty-?,loose_qty=loose_qty-?
                                       WHERE id=? AND stock_qty>=? AND loose_qty>=?""",
                                     (quantity, loose, item.product_id, quantity, loose))
                if updated.rowcount != 1:
                    fail(409, "INSUFFICIENT_STOCK", "库存不足")
            for box in entry["boxes"]:
                unit = box["unit"]
                if body.direction == "IN" and body.kind == "NORMAL":
                    if unit:
                        unit_id = unit["id"]
                        db.execute("""UPDATE box_units SET capacity=?,remaining=?,supplier_id=?,created_at=?
                                      WHERE id=?""", (box["capacity"], box["remaining_after"],
                                                      supplier["id"], created, unit_id))
                    else:
                        unit_id = db.execute("""INSERT INTO box_units(product_id,code_value,capacity,remaining,supplier_id,created_at)
                                                VALUES(?,?,?,?,?,?)""", (item.product_id, box["code"],
                                                box["capacity"], box["remaining_after"], supplier["id"], created)).lastrowid
                elif body.direction == "IN":
                    if unit:
                        unit_id = unit["id"]
                        updated = db.execute("""UPDATE box_units SET remaining=remaining+?
                                              WHERE id=? AND remaining+?<=capacity""",
                                             (box["quantity"], unit_id, box["quantity"]))
                        if updated.rowcount != 1:
                            fail(409, "BOX_CAPACITY", "箱码容量不足")
                    else:
                        unit_id = db.execute("""INSERT INTO box_units(product_id,code_value,capacity,remaining,supplier_id,created_at)
                                                VALUES(?,?,?,?,NULL,?)""", (item.product_id, box["code"],
                                                box["capacity"], box["remaining_after"], created)).lastrowid
                else:
                    unit_id = unit["id"]
                    updated = db.execute("UPDATE box_units SET remaining=remaining-? WHERE id=? AND remaining>=?",
                                         (box["quantity"], unit_id, box["quantity"]))
                    if updated.rowcount != 1:
                        fail(409, "BOX_INSUFFICIENT", "箱码剩余瓶数不足")
                db.execute("""INSERT INTO box_actions(document_item_id,box_unit_id,code_value,direction,
                              quantity,capacity,remaining_after,created_at) VALUES(?,?,?,?,?,?,?,?)""",
                           (item_id, unit_id, box["code"], body.direction, box["quantity"],
                            box["capacity"], box["remaining_after"], created))
            kind = entry["product"]["scan_mode"]
            db.executemany("""INSERT INTO scan_events(document_item_id,product_id,code_value,code_kind,direction,created_at)
                              VALUES(?,?,?,?,?,?)""", [(item_id, item.product_id, c, kind, body.direction, created)
                                                         for c in item.codes])
        return detail(db, doc_id)


def _reverse_stock(db, doc, item, loose):
    sign = 1 if doc["direction"] == "IN" else -1
    stock = item["stock_qty"] - sign * item["quantity"]
    loose_stock = item["loose_qty"] - sign * loose
    if stock < 0 or loose_stock < 0:
        fail(409, "DELETE_STOCK_CONFLICT", f"删除会使物资「{item['name']}」库存不足，请先处理后续单据")
    if sign == 1:
        # 回推每个后续单据之前的库存，避免删除后出现历史负库存。
        balance, loose_balance = stock, loose_stock
        later_items = db.execute("""SELECT d.direction,d.doc_no,i.quantity,i.loose_quantity,
                                       EXISTS(SELECT 1 FROM box_actions WHERE document_item_id=i.id) has_boxes,
                                       (SELECT COUNT(*) FROM scan_events WHERE document_item_id=i.id
                                        AND code_kind='SERIAL') serial_count
                                    FROM document_items i JOIN documents d ON d.id=i.document_id
                                    WHERE i.product_id=? AND d.id>? ORDER BY d.id DESC""",
                                 (item["product_id"], doc["id"]))
        for later in later_items:
            later_sign = 1 if later["direction"] == "IN" else -1
            later_loose = later["loose_quantity"]
            if item["category"] == "ALCOHOL" and not later["has_boxes"] and not later_loose:
                later_loose = later["quantity"] - later["serial_count"]
            balance -= later_sign * later["quantity"]
            loose_balance -= later_sign * later_loose
            if balance < 0 or loose_balance < 0:
                fail(409, "DELETE_STOCK_CONFLICT", f"删除会使单据 {later['doc_no']} 办理前出现负库存，请先处理相关出库记录")
    db.execute("UPDATE products SET stock_qty=?,loose_qty=? WHERE id=?", (stock, loose_stock, item["product_id"]))


def _reverse_box_action(db, doc, action):
    code = action["code_value"]
    later = db.execute("""SELECT d.doc_no FROM box_actions a
                           JOIN document_items i ON i.id=a.document_item_id JOIN documents d ON d.id=i.document_id
                           WHERE a.code_value=? AND a.id>? ORDER BY a.id DESC LIMIT 1""", (code, action["id"])).fetchone()
    if later:
        fail(409, "DELETE_BOX_IN_USE", f"箱码已有后续记录，请先处理单据 {later['doc_no']}")
    previous = db.execute("""SELECT capacity,remaining_after FROM box_actions
                              WHERE code_value=? AND id<? ORDER BY id DESC LIMIT 1""", (code, action["id"])).fetchone()
    legacy = db.execute("""SELECT created_at FROM scan_events WHERE code_kind='SERIAL' AND code_value=?
                            AND product_id=? ORDER BY id DESC LIMIT 1""", (code, action["product_id"])).fetchone()
    prior_remaining = action["remaining_after"] + (-action["quantity"] if doc["direction"] == "IN" else action["quantity"])
    if (action["stock_remaining"] != action["remaining_after"] or action["stock_capacity"] != action["capacity"]
            or not 0 <= prior_remaining <= action["capacity"]
            or (previous and previous["remaining_after"] != prior_remaining)):
        fail(409, "DELETE_BOX_CONFLICT", "箱码当前状态与单据记录不一致，无法回退该单据")
    if not previous and not legacy and doc["direction"] == "IN" and action["stock_created_at"] == doc["created_at"]:
        return action["box_unit_id"]
    if doc["kind"] == "NORMAL" and doc["direction"] == "IN":
        # 同一个空箱码可以再次采购，需恢复它上次的容量和供应商。
        purchase = db.execute("""SELECT d.supplier_id,a.created_at FROM box_actions a
                                 JOIN document_items i ON i.id=a.document_item_id JOIN documents d ON d.id=i.document_id
                                 WHERE a.code_value=? AND a.id<? AND d.kind='NORMAL' AND d.direction='IN'
                                 ORDER BY a.id DESC LIMIT 1""", (code, action["id"])).fetchone()
        initial = purchase or legacy or db.execute("""SELECT created_at FROM box_actions
                          WHERE code_value=? AND id<? ORDER BY id LIMIT 1""", (code, action["id"])).fetchone()
        if not initial:
            fail(409, "DELETE_BOX_CONFLICT", "缺少该箱码此前的入库信息，无法回退该单据")
        db.execute("UPDATE box_units SET capacity=?,remaining=?,supplier_id=?,created_at=? WHERE id=?",
                   (previous["capacity"] if previous else 1, prior_remaining,
                    purchase["supplier_id"] if purchase else None, initial["created_at"], action["box_unit_id"]))
    else:
        db.execute("UPDATE box_units SET remaining=? WHERE id=?", (prior_remaining, action["box_unit_id"]))
    return None


def _reverse_serial_event(db, event, item):
    code = event["code_value"]
    later = db.execute("""SELECT d.doc_no FROM scan_events s
                           JOIN document_items i ON i.id=s.document_item_id JOIN documents d ON d.id=i.document_id
                           WHERE s.code_kind='SERIAL' AND s.code_value=? AND s.id>? ORDER BY s.id DESC LIMIT 1""",
                       (code, event["id"])).fetchone()
    if later:
        fail(409, "DELETE_SERIAL_IN_USE", f"独立编码已有后续记录，请先处理单据 {later['doc_no']}")
    if item["category"] != "ALCOHOL":
        return None
    later_box = db.execute("""SELECT d.doc_no FROM box_actions a
                              JOIN document_items i ON i.id=a.document_item_id JOIN documents d ON d.id=i.document_id
                              WHERE a.code_value=? ORDER BY a.id DESC LIMIT 1""", (code,)).fetchone()
    if later_box:
        fail(409, "DELETE_BOX_IN_USE", f"箱码已有后续记录，请先处理单据 {later_box['doc_no']}")
    unit = db.execute("SELECT * FROM box_units WHERE code_value=? AND product_id=?",
                      (code, item["product_id"])).fetchone()
    # 旧酒水序列码在数据库迁移时按每码一瓶转换为箱码。
    was_inbound = event["direction"] == "IN"
    if not unit or unit["capacity"] != 1 or unit["remaining"] != int(was_inbound):
        fail(409, "DELETE_BOX_CONFLICT", "旧酒水编码与当前库存不一致，无法回退该单据")
    if was_inbound and not db.execute("""SELECT 1 FROM scan_events
                    WHERE code_kind='SERIAL' AND code_value=? AND id<? LIMIT 1""", (code, event["id"])).fetchone():
        return unit["id"]
    db.execute("UPDATE box_units SET remaining=? WHERE id=?", (int(not was_inbound), unit["id"]))
    return None


def delete_document(doc_id: int, operator_id: int):
    with transaction() as db:
        doc = db.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not doc:
            if db.execute("SELECT 1 FROM document_deletions WHERE document_id=?", (doc_id,)).fetchone():
                return
            fail(404, "NOT_FOUND", "单据不存在")
        dependent = db.execute("SELECT doc_no FROM documents WHERE source_document_id=? ORDER BY id DESC LIMIT 1",
                               (doc_id,)).fetchone()
        if dependent:
            fail(409, "DELETE_RETURN_EXISTS", f"请先处理关联退库单 {dependent['doc_no']}")
        items = db.execute("""SELECT i.*,p.category,p.name,p.stock_qty,p.loose_qty
                              FROM document_items i JOIN products p ON p.id=i.product_id WHERE i.document_id=?""",
                           (doc_id,)).fetchall()
        for item in items:
            events = db.execute("SELECT * FROM scan_events WHERE document_item_id=? AND code_kind='SERIAL'",
                                (item["id"],)).fetchall()
            actions = db.execute("""SELECT a.*,b.product_id,b.remaining stock_remaining,b.capacity stock_capacity,
                                            b.created_at stock_created_at FROM box_actions a
                                     JOIN box_units b ON b.id=a.box_unit_id WHERE a.document_item_id=?""",
                                 (item["id"],)).fetchall()
            loose = item["loose_quantity"]
            if item["category"] == "ALCOHOL":
                if not actions and not loose:
                    loose = item["quantity"] - len(events)
                if loose < 0 or loose + len(events) + sum(action["quantity"] for action in actions) != item["quantity"]:
                    fail(409, "DELETE_STOCK_CONFLICT", "单据库存明细不一致，无法回退该单据")
            remove_boxes = [_reverse_box_action(db, doc, action) for action in actions]
            remove_boxes.extend(_reverse_serial_event(db, event, item) for event in events)
            _reverse_stock(db, doc, item, loose)
            db.execute("DELETE FROM box_actions WHERE document_item_id=?", (item["id"],))
            db.execute("DELETE FROM scan_events WHERE document_item_id=?", (item["id"],))
            db.executemany("DELETE FROM box_units WHERE id=?", ((box_id,) for box_id in remove_boxes if box_id is not None))
        db.execute("DELETE FROM document_items WHERE document_id=?", (doc_id,))
        db.execute("INSERT INTO document_deletions(document_id,request_id,operator_id,deleted_at) VALUES(?,?,?,?)",
                   (doc_id, doc["request_id"], operator_id, now()))
        db.execute("DELETE FROM documents WHERE id=?", (doc_id,))


def document_filter_options(outbound_only: bool) -> dict:
    db = connect()
    try:
        db.execute("BEGIN")
        scope = "AND d.kind='NORMAL' AND d.direction='OUT'" if outbound_only else ""
        products = db.execute(f"""SELECT p.id,p.brand,p.name,p.specification FROM products p
                                  WHERE EXISTS (
                                      SELECT 1 FROM document_items i JOIN documents d ON d.id=i.document_id
                                      WHERE i.product_id=p.id {scope}
                                  )
                                  ORDER BY p.brand,p.name,p.specification,p.id""").fetchall()
        suppliers = [] if outbound_only else db.execute(
            """SELECT s.id,s.name FROM suppliers s
               WHERE s.id IN (SELECT d.supplier_id FROM documents d WHERE d.supplier_id IS NOT NULL)
               ORDER BY s.name,s.id"""
        ).fetchall()
        companies = db.execute(f"""SELECT c.id,c.name FROM departments c
                                    WHERE EXISTS (
                                        SELECT 1 FROM documents d WHERE d.recipient_company_id=c.id {scope}
                                    )
                                    ORDER BY c.name,c.id""").fetchall()
        return {"products": [dict(row) for row in products], "suppliers": [dict(row) for row in suppliers],
                "companies": [dict(row) for row in companies]}
    finally:
        db.close()


def document_selection(direction: str | None, kind: str | None, *,
                       q: str | None = None, created_from: datetime | None = None,
                       created_before: datetime | None = None, product_id: int | None = None,
                       supplier_id: int | None = None, recipient_company_id: int | None = None,
                       box_code: str | None = None, doc_id: int | None = None) -> tuple[str, list]:
    if created_from is not None and created_before is not None and created_from >= created_before:
        fail(422, "INVALID_DATE_RANGE", "开始时间必须早于结束时间")
    conditions = []
    args = []
    if direction:
        conditions.append("d.direction=?")
        args.append(direction)
    if kind:
        conditions.append("d.kind=?")
        args.append(kind)
    if box_code is not None:
        raw_code = box_code.strip()
        if not raw_code:
            fail(422, "BOX_CODE_REQUIRED", "请提供有效的箱码")
        parsed = parse_brand_code(raw_code)
        item_filter = "AND i.product_id=?" if product_id is not None else ""
        conditions.append(f"""d.id IN (
            SELECT i.document_id FROM box_actions a JOIN document_items i ON i.id=a.document_item_id
            WHERE a.code_value IN (?,?) {item_filter}
        )""")
        args.extend((raw_code, parsed[1] if parsed else raw_code))
        if product_id is not None:
            args.append(product_id)
    elif product_id is not None:
        conditions.append("""EXISTS (
            SELECT 1 FROM document_items i WHERE i.document_id=d.id AND i.product_id=?
        )""")
        args.append(product_id)
    if supplier_id is not None:
        conditions.append("d.supplier_id=?")
        args.append(supplier_id)
    if recipient_company_id is not None:
        conditions.append("d.recipient_company_id=?")
        args.append(recipient_company_id)
    if created_from is not None:
        conditions.append("d.created_at>=?")
        args.append(created_from.astimezone(timezone.utc).isoformat())
    if created_before is not None:
        conditions.append("d.created_at<?")
        args.append(created_before.astimezone(timezone.utc).isoformat())
    if q and (keyword := q.strip()):
        conditions.append("""(
            instr(lower(d.doc_no),lower(?))>0 OR instr(lower(source.doc_no),lower(?))>0
            OR instr(lower(u.username),lower(?))>0 OR instr(lower(u.name),lower(?))>0
            OR instr(lower(d.supplier_name),lower(?))>0
            OR instr(lower(d.recipient),lower(?))>0
            OR EXISTS (
                SELECT 1 FROM document_items i JOIN products p ON p.id=i.product_id
                WHERE i.document_id=d.id
                  AND instr(lower(p.brand || ' ' || p.name || ' ' || p.specification),lower(?))>0
            )
        )""")
        args.extend([keyword] * 7)
    if doc_id is not None:
        conditions.append("d.id=?")
        args.append(doc_id)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    return f"""FROM documents d JOIN users u ON u.id=d.operator_id
               LEFT JOIN documents source ON source.id=d.source_document_id {where}""", args


def list_documents(direction: str | None, kind: str | None, limit: int, offset: int, *,
                   q: str | None = None, created_from: datetime | None = None,
                   created_before: datetime | None = None, product_id: int | None = None,
                   supplier_id: int | None = None, recipient_company_id: int | None = None,
                   box_code: str | None = None) -> dict:
    selection, args = document_selection(direction, kind, q=q, created_from=created_from,
                                          created_before=created_before, product_id=product_id,
                                          supplier_id=supplier_id, recipient_company_id=recipient_company_id,
                                          box_code=box_code)
    db = connect()
    try:
        # Keep the count and page on the same SQLite snapshot during concurrent writes.
        db.execute("BEGIN")
        total, exportable_total = db.execute(
            f"SELECT COUNT(*),COUNT(CASE WHEN d.kind='NORMAL' THEN 1 END) {selection}", args
        ).fetchone()
        rows = db.execute(f"""SELECT d.id,d.doc_no,d.direction,d.kind,d.source_document_id,
                                  source.doc_no source_document_no,d.supplier_name,d.recipient,d.recipient_company_id,d.remark,d.created_at,
                                  COALESCE(u.name,u.username) operator_name
                           {selection}
                           ORDER BY d.id DESC LIMIT ? OFFSET ?""", (*args, limit, offset)).fetchall()
        return {"total": total, "exportable_total": exportable_total, "items": [dict(r) for r in rows]}
    finally:
        db.close()
