from contextlib import closing
from datetime import datetime, timedelta, timezone
from io import BytesIO
from itertools import chain, groupby
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


def _workbook(buffer: BytesIO, *, constant_memory: bool = True) -> Workbook:
    return Workbook(buffer, {"constant_memory": constant_memory, "default_date_format": "yyyy-mm-dd hh:mm:ss"})


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


def _write_merged(sheet, first, last, column, value, cell_format):
    # Merge with an empty value, then write texts explicitly to keep them literal.
    if first != last and sheet.merge_range(first, column, last, column, "", cell_format) != 0:
        fail(422, "EXCEL_SHEET_LIMIT", "数据超过 Excel 工作表容量，请缩小筛选范围")
    write = sheet.write_string if isinstance(value, str) else sheet.write
    if write(first, column, value, cell_format) != 0:
        fail(422, "EXCEL_SHEET_LIMIT", "数据超过 Excel 工作表容量，请缩小筛选范围")


def _download(buffer: BytesIO, filename: str) -> Response:
    return Response(buffer.getvalue(), media_type=XLSX_TYPE, headers={
        "Content-Disposition": f"attachment; filename=\"stockflow.xlsx\"; filename*=UTF-8''{quote(filename, safe='')}",
        "Cache-Control": "no-store",
    })


def export_documents(direction: str | None = None, product_id: int | None = None,
                     supplier_id: int | None = None, doc_id: int | None = None, *,
                     recipient_company_id: int | None = None, box_code: str | None = None,
                     created_from: datetime | None = None, created_before: datetime | None = None) -> Response:
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
                                             product_id=product_id, supplier_id=supplier_id,
                                             recipient_company_id=recipient_company_id, box_code=box_code,
                                             created_from=created_from, created_before=created_before)
        selected_documents = f"""
            SELECT d.id,d.doc_no,d.direction,d.created_at,d.supplier_name,d.recipient,d.recipient_company_id,d.remark,
                   COALESCE(u.name,u.username) operator_name
            {selection}
        """
        with _workbook(buffer, constant_memory=False) as workbook:
            common_format = workbook.add_format({"valign": "top"})
            date_format = workbook.add_format({"valign": "top", "num_format": "yyyy-mm-dd hh:mm:ss"})
            scan_format = workbook.add_format({"text_wrap": True})
            sheets = {
                key: _sheet(workbook, label, [
                    ("单据编号", 24), ("制单时间（北京时间）", 25), ("操作人", 19),
                    ("供应商" if key == "IN" else "领用公司", 25), ("类别", 12), ("品牌", 19),
                    ("物资名称", 26), ("规格", 19), ("单位", 10), ("数量", 11), ("散瓶数量", 13), ("备注", 36),
                ] + ([("历史领用人", 25)] if key == "OUT" else []) + [("扫码明细", 72)])
                for key, label in DOCUMENT_TYPES.items()
            }
            next_row = dict.fromkeys(sheets, 1)
            code_rows = db.execute(f"""WITH selected_documents AS ({selected_documents}),
                selected_items AS (
                    SELECT i.id,d.id document_id FROM selected_documents d
                    JOIN document_items i ON i.document_id=d.id
                )
                SELECT i.*,a.code_value,'箱码' code_type,a.quantity,a.capacity,a.remaining_after,a.id event_id
                FROM selected_items i JOIN box_actions a ON a.document_item_id=i.id
                UNION ALL
                SELECT i.*,s.code_value,'扫码',NULL,NULL,NULL,s.id
                FROM selected_items i JOIN scan_events s ON s.document_item_id=i.id
                ORDER BY document_id DESC,id,code_type,event_id""", args)
            code = next(code_rows, None)
            item_rows = db.execute(f"""WITH selected_documents AS ({selected_documents})
                SELECT d.*,i.id item_id,p.category,p.brand,p.name,p.specification,p.unit,i.quantity,i.loose_quantity
                FROM selected_documents d JOIN document_items i ON i.document_id=d.id
                JOIN products p ON p.id=i.product_id ORDER BY d.id DESC,i.id""", args)
            for _, items in groupby(item_rows, key=lambda row: row["id"]):
                document = next(items)
                key = document["direction"]
                sheet = sheets[key]
                scan_column = 13 if key == "OUT" else 12
                document_first = next_row[key]
                for item in chain((document,), items):
                    item_first = next_row[key]
                    while code is not None and code["id"] == item["item_id"]:
                        text = code["code_value"]
                        if code["code_type"] == "箱码":
                            text += f"（本次 {code['quantity']} 瓶，容量 {code['capacity']} 瓶，余 {code['remaining_after']} 瓶）"
                        _write_merged(sheet, next_row[key], next_row[key], scan_column, text, scan_format)
                        next_row[key] += 1
                        code = next(code_rows, None)
                    if next_row[key] == item_first:
                        next_row[key] += 1
                    material = (
                        CATEGORIES[item["category"]], item["brand"], item["name"], item["specification"], item["unit"],
                        item["quantity"], item["loose_quantity"] if item["category"] == "ALCOHOL" else None,
                    )
                    for column, value in enumerate(material, 4):
                        _write_merged(sheet, item_first, next_row[key] - 1, column, value, common_format)

                document_last = next_row[key] - 1
                created_at = datetime.fromisoformat(document["created_at"]).astimezone(BEIJING_TIME)
                company = document["recipient"] if document["recipient_company_id"] is not None else None
                party = document["supplier_name"] if key == "IN" else company
                common = {
                    0: document["doc_no"], 1: created_at.replace(tzinfo=None, microsecond=0),
                    2: document["operator_name"], 3: party, 11: document["remark"],
                }
                if key == "OUT":
                    common[12] = document["recipient"] if company is None else None
                for column, value in common.items():
                    _write_merged(sheet, document_first, document_last, column, value,
                                  date_format if column == 1 else common_format)
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
