from contextlib import closing
from datetime import datetime, timedelta, timezone
from io import BytesIO
from urllib.parse import quote

from fastapi import Response
from xlsxwriter import Workbook

from ..database import connect
from ..errors import fail
from .documents import document_selection
from .products import list_products


XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
BEIJING_TIME = timezone(timedelta(hours=8))
CATEGORIES = {"ALCOHOL": "酒水", "TOBACCO": "烟草"}
DOCUMENT_TYPES = {"IN": "入库单", "OUT": "出库单"}


def _workbook(buffer: BytesIO) -> Workbook:
    return Workbook(buffer, {"constant_memory": True, "default_date_format": "yyyy-mm-dd hh:mm:ss"})


def _sheet(workbook, name, columns):
    sheet = workbook.add_worksheet(name)
    heading = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#81305E",
                                   "valign": "vcenter"})
    sheet.set_row(0, 25)
    for index, (label, width) in enumerate(columns):
        sheet.set_column(index, index, width)
        sheet.write_string(0, index, label, heading)
    sheet.freeze_panes(1, 0)
    return sheet


def _write_row(sheet, index, values):
    for column, value in enumerate(values):
        write = sheet.write_string if isinstance(value, str) else sheet.write
        if write(index, column, value) != 0:
            fail(422, "EXCEL_SHEET_LIMIT", "数据超过 Excel 工作表容量，请缩小筛选范围")


def _download(buffer: BytesIO, filename: str) -> Response:
    return Response(buffer.getvalue(), media_type=XLSX_TYPE, headers={
        "Content-Disposition": f"attachment; filename=\"stockflow.xlsx\"; filename*=UTF-8''{quote(filename, safe='')}",
        "Cache-Control": "no-store",
    })


def export_documents(direction: str | None = None, product_id: int | None = None,
                     supplier_id: int | None = None, doc_id: int | None = None) -> Response:
    with closing(connect()) as db, BytesIO() as buffer:
        db.execute("BEGIN")
        if doc_id is not None:
            document = db.execute("SELECT doc_no,direction FROM documents WHERE id=? AND kind='NORMAL'",
                                  (doc_id,)).fetchone()
            if document is None:
                fail(404, "NOT_FOUND", "入库单或出库单不存在")
            direction = document["direction"]
            filename = f"{DOCUMENT_TYPES[direction]}-{document['doc_no']}.xlsx"
        else:
            filename = f"{DOCUMENT_TYPES.get(direction, '出入库单')}.xlsx"

        selection, args = document_selection(direction, "NORMAL", doc_id=doc_id,
                                             product_id=product_id, supplier_id=supplier_id)
        selected_documents = f"""
            SELECT d.id,d.doc_no,d.direction,d.created_at,d.supplier_name,d.recipient,d.recipient_company_id,d.remark,
                   COALESCE(u.name,u.username) operator_name
            {selection}
        """
        with _workbook(buffer) as workbook:
            sheets = {
                key: _sheet(workbook, label, [
                    ("单据编号", 24), ("制单时间（北京时间）", 25), ("操作人", 19),
                    ("供应商" if key == "IN" else "领用公司", 25), ("类别", 12), ("品牌", 19),
                    ("物资名称", 26), ("规格", 19), ("单位", 10), ("数量", 11), ("散瓶数量", 13), ("备注", 36),
                ] + ([("历史领用人", 25)] if key == "OUT" else []))
                for key, label in DOCUMENT_TYPES.items() if direction is None or key == direction
            }
            next_row = dict.fromkeys(sheets, 1)
            item_rows = db.execute(f"""WITH selected_documents AS ({selected_documents})
                SELECT d.*,p.category,p.brand,p.name,p.specification,p.unit,i.quantity,i.loose_quantity
                FROM selected_documents d JOIN document_items i ON i.document_id=d.id
                JOIN products p ON p.id=i.product_id ORDER BY d.id DESC,i.id""", args)
            for item in item_rows:
                key = item["direction"]
                created_at = datetime.fromisoformat(item["created_at"]).astimezone(BEIJING_TIME)
                recipient = item["recipient"] if item["recipient_company_id"] is not None else None
                values = (
                    item["doc_no"], created_at.replace(tzinfo=None, microsecond=0), item["operator_name"],
                    item["supplier_name"] if key == "IN" else recipient,
                    CATEGORIES[item["category"]], item["brand"], item["name"], item["specification"], item["unit"],
                    item["quantity"], item["loose_quantity"] if item["category"] == "ALCOHOL" else None, item["remark"],
                )
                if key == "OUT":
                    values += (item["recipient"] if item["recipient_company_id"] is None else None,)
                _write_row(sheets[key], next_row[key], values)
                next_row[key] += 1
            for key, sheet in sheets.items():
                sheet.autofilter(0, 0, next_row[key] - 1, 12 if key == "OUT" else 11)

            code_rows = db.execute(f"""WITH selected_documents AS ({selected_documents}),
                selected_items AS (
                    SELECT i.id,d.id document_id,d.doc_no,d.direction,p.brand,p.name,p.specification
                    FROM selected_documents d JOIN document_items i ON i.document_id=d.id
                    JOIN products p ON p.id=i.product_id
                )
                SELECT i.*,a.code_value,'箱码' code_type,a.quantity,a.capacity,a.remaining_after,a.id event_id
                FROM selected_items i JOIN box_actions a ON a.document_item_id=i.id
                UNION ALL
                SELECT i.*,s.code_value,'扫码',NULL,NULL,NULL,s.id
                FROM selected_items i JOIN scan_events s ON s.document_item_id=i.id
                ORDER BY document_id DESC,id,code_type,event_id""", args)
            code_sheet = _sheet(workbook, "扫码明细", [
                ("单据编号", 24), ("业务类型", 12), ("品牌", 19), ("物资名称", 26), ("规格", 19),
                ("编码类型", 12), ("编码", 38), ("本次瓶数", 13), ("箱容量（瓶）", 15), ("操作后箱内余瓶", 19),
            ])
            last_row = 0
            for last_row, code in enumerate(code_rows, 1):
                _write_row(code_sheet, last_row, (
                    code["doc_no"], DOCUMENT_TYPES[code["direction"]], code["brand"], code["name"], code["specification"],
                    code["code_type"], code["code_value"], code["quantity"], code["capacity"], code["remaining_after"],
                ))
            code_sheet.autofilter(0, 0, last_row, 9)
        return _download(buffer, filename)


def export_stock(category: str | None, q: str | None) -> Response:
    with closing(connect()) as db, BytesIO() as buffer:
        db.execute("BEGIN")
        products = list_products(db, category, include_inactive=True)
        if q and (keyword := q.strip().lower()):
            products = [p for p in products if keyword in f"{p['brand']} {p['name']} · {p['specification']}".lower()]
        alcohol = {p["id"]: p for p in products if p["category"] == "ALCOHOL"}
        with _workbook(buffer) as workbook:
            sheet = _sheet(workbook, "当前库存", [
                ("类别", 12), ("品牌", 19), ("物资名称", 26), ("规格", 19), ("单位", 10),
                ("库存总量", 13), ("散瓶数量", 13), ("完整箱数", 13), ("已开箱数", 13),
                ("箱内合计瓶数", 17), ("状态", 12),
            ])
            for index, p in enumerate(products, 1):
                breakdown = (p["loose_qty"], p["full_boxes"], p["opened_boxes"], p["boxed_qty"]) if p["id"] in alcohol else (None,) * 4
                _write_row(sheet, index, (
                    CATEGORIES[p["category"]], p["brand"], p["name"], p["specification"], p["unit"], p["stock_qty"],
                    *breakdown, "启用" if p["is_active"] else "已停用",
                ))
            sheet.autofilter(0, 0, len(products), 10)

            box_sheet = _sheet(workbook, "箱码余量", [
                ("品牌", 19), ("物资名称", 26), ("规格", 19), ("箱码", 38),
                ("供应商", 25), ("箱容量（瓶）", 15), ("箱内余瓶", 13),
            ])
            last_row = 0
            if alcohol:
                boxes = db.execute("""SELECT b.product_id,b.code_value,b.capacity,b.remaining,s.name supplier_name
                                      FROM box_units b LEFT JOIN suppliers s ON s.id=b.supplier_id
                                      WHERE b.remaining>0 ORDER BY b.product_id,b.id DESC""")
                for box in boxes:
                    if product := alcohol.get(box["product_id"]):
                        last_row += 1
                        _write_row(box_sheet, last_row, (
                            product["brand"], product["name"], product["specification"], box["code_value"],
                            box["supplier_name"], box["capacity"], box["remaining"],
                        ))
            box_sheet.autofilter(0, 0, last_row, 6)
        return _download(buffer, "当前库存.xlsx")
