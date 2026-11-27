import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKFLOW_DB_PATH", str(tmp_path / "stockflow.db"))
    monkeypatch.setenv("STOCKFLOW_JWT_SECRET", "test-secret-value-with-at-least-thirty-two-chars")
    monkeypatch.setenv("STOCKFLOW_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("STOCKFLOW_ADMIN_PASSWORD", "admin-password-123")
    with TestClient(app) as client:
        admin_headers = auth(client)
        supplier = client.post("/api/suppliers", headers=admin_headers, json={"name": "默认供应商"})
        assert supplier.status_code == 201
        company = client.post("/api/companies", headers=admin_headers, json={"name": "默认子公司"})
        assert company.status_code == 201
        yield client


def auth(client, username="admin", password="admin-password-123"):
    result = client.post("/api/auth/login", json={"username": username, "password": password})
    assert result.status_code == 200, result.text
    return {"Authorization": "Bearer " + result.json()["token"]}


def user_data(username, password, name="测试员工", department_id=1):
    return {"username": username, "password": password, "name": name, "department_id": department_id}


def product(client, headers, name, mode="QUANTITY", category="TOBACCO", bottles_per_box=6, brand="品牌"):
    result = client.post("/api/products", headers=headers, json={"category": category, "brand": brand,
        "name": name, "specification": "标准", "unit": "瓶" if category == "ALCOHOL" else "件",
        "scan_mode": mode, "bottles_per_box": bottles_per_box})
    assert result.status_code == 201, result.text
    return result.json()["id"]


def doc(client, headers, direction, items, request_id=None, recipient_company_id=1, supplier_id=1):
    return client.post("/api/documents", headers=headers, json={"request_id": request_id or str(uuid4()),
        "direction": direction, "supplier_id": supplier_id if direction == "IN" else None,
        "recipient_company_id": recipient_company_id if direction == "OUT" else None, "items": items})


def item(product_id, quantity, codes=None):
    return {"product_id": product_id, "quantity": quantity, "codes": codes or []}


def alcohol_item(product_id, loose=0, boxes=None):
    return {"product_id": product_id, "loose_quantity": loose, "boxes": boxes or []}


def exported_workbook(client, path, headers):
    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["cache-control"] == "no-store"
    return load_workbook(BytesIO(response.content))


def test_document_excel_includes_filtered_documents_and_scan_details(client):
    h = auth(client)
    assert client.post("/api/users", headers=h, json=user_data("001", "pass-12345")).status_code == 201
    staff = auth(client, "001", "pass-12345")
    drink = product(client, h, "箱装酒", "SERIAL", "ALCOHOL")
    tobacco = product(client, h, "普通物资")
    serial = product(client, h, "独立物资", "SERIAL")
    code = "000000123456789012345"
    inbound = doc(client, h, "IN", [
        alcohol_item(drink, 2, [{"code_value": code}]), item(tobacco, 3), item(serial, 1, ["000123"]),
    ])
    assert inbound.status_code == 201
    inbound = inbound.json()
    assert client.patch("/api/companies/1", headers=h, json={"name": "{=1+1}"}).status_code == 200
    outbound = doc(client, h, "OUT", [alcohol_item(drink, 1, [{"code_value": code, "quantity": 3}])])
    assert outbound.status_code == 201
    outbound = outbound.json()
    second_supplier = client.post("/api/suppliers", headers=h, json={"name": "另一个供应商"}).json()["id"]
    for _ in range(21):
        assert doc(client, h, "IN", [alcohol_item(drink, 1)], supplier_id=second_supplier).status_code == 201

    path = "/api/documents/export.xlsx"
    assert client.get(path).status_code == 401
    assert client.get("/api/documents/999999/export.xlsx", headers=staff).status_code == 404
    workbook = exported_workbook(client, path, staff)
    assert workbook.sheetnames == ["入库单", "出库单", "入库单扫码", "出库单扫码"]
    assert workbook["入库单"].max_row == 25
    assert workbook["出库单"]["D1"].value == "领用公司"
    assert workbook["出库单"]["D2"].value == "{=1+1}"
    assert workbook["出库单"]["D2"].data_type == "s"
    assert workbook["出库单"]["M2"].value is None
    filtered = exported_workbook(client, f"{path}?direction=IN&product_id={drink}&supplier_id=1", staff)
    assert filtered.sheetnames == ["入库单", "入库单扫码"]
    row = list(filtered["入库单"].values)[1]
    created_at = datetime.fromisoformat(inbound["created_at"]).astimezone(timezone(timedelta(hours=8)))
    assert row[:4] == (inbound["doc_no"], created_at.replace(tzinfo=None, microsecond=0), "admin", "默认供应商")
    assert row[9:11] == (8, 2)
    assert filtered["入库单"].max_row == 4
    scans = filtered["入库单扫码"]
    assert {cell[6] for cell in list(scans.values)[1:]} == {code, "000123"}
    for row in list(scans.rows)[1:]:
        linked_row = row[10].value
        assert row[0].hyperlink.location == f"'入库单'!A{linked_row}"
        assert filtered["入库单"][f"A{linked_row}"].value == row[0].value
        assert filtered["入库单"][f"G{linked_row}"].value == row[3].value

    outbound_time = datetime.fromisoformat(outbound["created_at"]).astimezone(created_at.tzinfo)
    day_start = outbound_time.replace(hour=0, minute=0, second=0, microsecond=0)
    filters = {
        "recipient_company_id": 1, "box_code": code,
        "created_from": day_start.isoformat(), "created_before": (day_start + timedelta(days=1)).isoformat(),
    }
    response = client.get("/api/documents", headers=staff, params=filters)
    assert response.status_code == 200
    assert response.json()["exportable_total"] == 1
    assert [d["id"] for d in response.json()["items"]] == [outbound["id"]]
    for endpoint in ("/api/documents", path):
        blank = client.get(endpoint, headers=staff, params={"box_code": "  "})
        assert blank.status_code == 422
        assert blank.json()["detail"]["code"] == "BOX_CODE_REQUIRED"
    for extra in ({"box_code": code[:-1]}, {"product_id": tobacco}, {"recipient_company_id": 999}):
        response = client.get("/api/documents", headers=staff, params=filters | extra)
        assert response.json()["total"] == 0
    assert client.get("/api/documents", headers=staff, params={"box_code": code}).json()["total"] == 2
    document_list = exported_workbook(client, str(client.build_request("GET", path, params=filters).url), staff)
    assert document_list["入库单"].max_row == 1
    assert document_list["出库单"]["A2"].value == outbound["doc_no"]
    assert document_list["出库单扫码"]["G2"].value == code
    assert client.get(path, headers=staff, params=filters | {"created_before": filters["created_from"]}).status_code == 422

    single = exported_workbook(client, f"/api/documents/{outbound['id']}/export.xlsx", staff)
    assert single["出库单"].max_row == 2
    assert single["出库单"]["A2"].value == outbound["doc_no"]
    assert list(single["出库单扫码"].values)[1][6:] == (code, 3, 6, 3, 2)
    assert single["出库单扫码"]["A2"].hyperlink.location == "'出库单'!A2"
    assert single["出库单扫码"]["G2"].data_type == "s"


def test_stock_excel_matches_category_search_and_remaining_boxes(client):
    h = auth(client)
    drink = product(client, h, "箱装酒", "SERIAL", "ALCOHOL")
    other_drink = product(client, h, "另一款酒", "SERIAL", "ALCOHOL")
    tobacco = product(client, h, "普通物资")
    assert doc(client, h, "IN", [alcohol_item(drink, 2, [
        {"code_value": "00001"}, {"code_value": "00002"}, {"code_value": "00003"},
    ]), item(tobacco, 3)]).status_code == 201
    assert doc(client, h, "IN", [alcohol_item(other_drink, 0, [{"code_value": "00004"}])]).status_code == 201
    assert doc(client, h, "OUT", [alcohol_item(drink, 0, [
        {"code_value": "00002", "quantity": 3}, {"code_value": "00003", "quantity": 6},
    ])]).status_code == 201
    assert client.put(f"/api/products/{drink}", headers=h, json={"is_active": False}).status_code == 200
    response_path = "/api/stock/export.xlsx"
    assert client.get(response_path).status_code == 401
    workbook = exported_workbook(client, f"{response_path}?category=ALCOHOL&q=箱装酒", h)
    assert workbook["当前库存"].max_row == 2
    assert list(workbook["当前库存"].values)[1][4:] == ("瓶", 11, 2, 1, 1, 9, "已停用")
    assert {row[3]: row[5:] for row in list(workbook["箱码余量"].values)[1:]} == {"00001": (6, 6), "00002": (6, 3)}
    workbook = exported_workbook(client, f"{response_path}?category=TOBACCO&q=标准", h)
    assert list(workbook["当前库存"].values)[1][4:10] == ("件", 3, None, None, None, None)
    assert workbook["箱码余量"].max_row == 1


def test_user_creation_and_reset_accept_ten_character_passwords(client):
    h = auth(client)
    credentials = {"username": "002", "password": "1234567890"}
    assert client.post("/api/users", headers=h, json={**user_data(**credentials), "password": "123456789"}).status_code == 422
    created = client.post("/api/users", headers=h, json=user_data(**credentials))
    assert created.status_code == 201
    auth(client, **credentials)
    path = f"/api/users/{created.json()['id']}"
    assert client.put(path, headers=h, json={"password": "😉" * 9}).status_code == 422
    new_password = "😉" * 10
    assert client.put(path, headers=h, json={"password": new_password}).status_code == 200
    auth(client, "002", new_password)
    assert client.post("/api/auth/login", json=credentials).status_code == 401


def test_employee_accounts_require_unique_numeric_work_numbers_and_departments(client):
    h = auth(client)
    data = user_data("00128", "staff-password-123", " 张三 ")
    for invalid in ("admin", "employee12", "12.3", "１２３", "12\n"):
        assert client.post("/api/users", headers=h, json={**data, "username": invalid}).status_code == 422
    assert client.post("/api/users", headers=h, json={**data, "name": "  "}).status_code == 422
    assert client.post("/api/users", headers=h, json={**data, "department_id": 999}).status_code == 422
    assert client.patch("/api/users/1", headers=h, json={"username": "999"}).status_code == 422
    created = client.post("/api/users", headers=h, json=data)
    assert created.status_code == 201
    employee = created.json()
    assert (employee["username"], employee["name"], employee["department_name"]) == ("00128", "张三", "默认子公司")
    assert client.post("/api/users", headers=h, json=data).status_code == 409

    staff = auth(client, data["username"], data["password"])
    assert client.get("/api/departments", headers=staff).status_code == 403
    assert client.post("/api/departments", headers=h, json={"name": " 默认子公司 "}).status_code == 409
    assert client.patch("/api/departments/1", headers=h, json={"name": "仓储子公司", "is_active": False}).status_code == 200
    assert client.post("/api/users", headers=h, json={**data, "username": "00129"}).status_code == 422
    profile = client.get("/api/auth/me", headers=staff).json()
    assert (profile["id"], profile["department_name"]) == (employee["id"], "仓储子公司")
    assert client.put(f"/api/users/{employee['id']}", headers=h, json={"name": "李四"}).status_code == 200


def test_legacy_employee_switches_to_work_number_with_existing_history(client):
    from app.auth import hash_password
    from app.database import initialize, now, transaction

    h = auth(client)
    old_account = "legacy-clerk"
    password = "legacy-password-123"
    with transaction() as db:
        user_id = db.execute("INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,'STAFF',?)",
                             (old_account, hash_password(password), now())).lastrowid
        db.execute("ALTER TABLE users DROP COLUMN department_id")
        db.execute("ALTER TABLE users DROP COLUMN name")
        db.execute("PRAGMA user_version=3")
    initialize()
    initialize()
    old_headers = auth(client, old_account, password)
    product_id = product(client, h, "旧账号登记物资")
    record = doc(client, old_headers, "IN", [item(product_id, 3)])
    assert record.status_code == 201
    document = record.json()
    assert (document["operator_id"], document["operator_name"]) == (user_id, old_account)

    path = f"/api/users/{user_id}"
    assert client.patch(path, headers=h, json={"username": "00073"}).status_code == 422
    migrated = client.patch(path, headers=h, json={"username": "00073", "name": "赵敏", "department_id": 1})
    assert migrated.status_code == 200
    assert migrated.json()["id"] == user_id
    assert client.post("/api/auth/login", json={"username": old_account, "password": password}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "73", "password": password}).status_code == 401
    new_headers = auth(client, "00073", password)
    assert client.get("/api/auth/me", headers=new_headers).json()["id"] == user_id
    persisted = client.get(f"/api/documents/{document['id']}", headers=new_headers).json()
    assert (persisted["doc_no"], persisted["operator_id"], persisted["operator_name"]) == (document["doc_no"], user_id, "赵敏")
    assert client.get("/api/products", headers=new_headers).json()[0]["stock_qty"] == 3
    assert client.get("/api/documents", headers=h, params={"q": "赵敏"}).json()["total"] == 1


def test_admin_deletes_dependent_documents_and_restores_box_history(client):
    h = auth(client)
    assert client.post("/api/users", headers=h, json=user_data("001", "pass-12345")).status_code == 201
    staff = auth(client, "001", "pass-12345")
    drink = product(client, h, "箱装酒", "SERIAL", "ALCOHOL")
    serial = product(client, h, "独立物资", "SERIAL")
    unit = {"code_value": "DELETE-BOX"}
    inbound_items = [alcohol_item(drink, 2, [unit]), item(serial, 1, ["DELETE-SERIAL"])]
    request_id = str(uuid4())
    inbound = doc(client, h, "IN", inbound_items, request_id=request_id).json()
    inbound_url = f"/api/documents/{inbound['id']}"
    assert client.delete(inbound_url, headers=staff).status_code == 403
    outbound = doc(client, h, "OUT", [alcohol_item(drink, 1, [{**unit, "quantity": 6}]),
                                     item(serial, 1, ["DELETE-SERIAL"])]).json()
    outbound_url = f"/api/documents/{outbound['id']}"
    assert client.delete(inbound_url, headers=h).json()["detail"]["code"] == "DELETE_BOX_IN_USE"

    supplier = client.post("/api/suppliers", headers=h, json={"name": "另一供应商"}).json()["id"]
    assert client.put(f"/api/products/{drink}", headers=h, json={"bottles_per_box": 4}).status_code == 200
    repurchase = doc(client, h, "IN", [alcohol_item(drink, boxes=[unit])], supplier_id=supplier).json()
    assert client.delete(f"/api/documents/{repurchase['id']}", headers=h).status_code == 204

    returned = client.post("/api/documents", headers=h, json={
        "request_id": str(uuid4()), "direction": "IN", "kind": "RETURN", "source_document_id": outbound["id"],
        "remark": "测试退库", "items": [alcohol_item(drink, 1, [{**unit, "quantity": 2}])],
    })
    assert returned.status_code == 201, returned.text
    assert client.delete(outbound_url, headers=h).json()["detail"]["code"] == "DELETE_RETURN_EXISTS"
    adjustment = client.post("/api/documents", headers=h, json={
        "request_id": str(uuid4()), "direction": "OUT", "kind": "ADJUST", "remark": "测试盘亏",
        "items": [alcohol_item(drink, boxes=[{**unit, "quantity": 1}])],
    })
    assert adjustment.status_code == 201, adjustment.text
    assert client.delete(f"/api/documents/{returned.json()['id']}", headers=h).json()["detail"]["code"] == "DELETE_BOX_IN_USE"
    assert client.delete(f"/api/documents/{adjustment.json()['id']}", headers=h).status_code == 204
    assert client.delete(f"/api/documents/{returned.json()['id']}", headers=h).status_code == 204
    can_return = client.get(outbound_url + "/returnable", headers=h).json()["items"][0]
    assert (can_return["loose_quantity"], can_return["boxes"][0]["quantity"]) == (1, 6)

    assert client.delete(outbound_url, headers=h).status_code == 204
    box = client.get(f"/api/boxes?product_id={drink}", headers=h).json()["items"][0]
    assert (box["capacity"], box["remaining"], box["supplier_name"]) == (6, 6, "默认供应商")
    assert client.delete(inbound_url, headers=h).status_code == 204
    assert client.delete(inbound_url, headers=h).status_code == 204
    assert client.get(inbound_url, headers=h).status_code == 404
    assert client.get("/api/documents", headers=h).json()["total"] == 0
    assert all(p["stock_qty"] == 0 for p in client.get("/api/products", headers=h).json())
    assert doc(client, h, "IN", inbound_items, request_id=request_id).json()["detail"]["code"] == "DOCUMENT_DELETED"
    assert doc(client, h, "IN", inbound_items).status_code == 201


def test_document_delete_preserves_historical_stock_and_is_atomic(client):
    h = auth(client)
    drink = product(client, h, "独立箱", "SERIAL", "ALCOHOL")
    pooled = product(client, h, "数量物资")
    inbound = doc(client, h, "IN", [alcohol_item(drink, boxes=[{"code_value": "ATOMIC-BOX"}]), item(pooled, 5)]).json()
    assert doc(client, h, "OUT", [item(pooled, 5)]).status_code == 201
    assert doc(client, h, "IN", [item(pooled, 6)]).status_code == 201
    response = client.delete(f"/api/documents/{inbound['id']}", headers=h)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "DELETE_STOCK_CONFLICT"
    assert client.get(f"/api/boxes?product_id={drink}", headers=h).json()["items"][0]["remaining"] == 6
    assert client.get("/api/documents", headers=h).json()["total"] == 3

    independent = doc(client, h, "IN", [item(pooled, 1)]).json()
    assert doc(client, h, "IN", [item(pooled, 1)]).status_code == 201
    assert client.delete(f"/api/documents/{independent['id']}", headers=h).status_code == 204


def test_document_filters_combine_type_keyword_date_and_pagination(client, monkeypatch):
    h = auth(client)
    marked = product(client, h, "测试物资_%")
    other = product(client, h, "测试物资甲乙")

    def save(at, direction, product_id):
        monkeypatch.setattr("app.services.documents.now", lambda: at)
        response = doc(client, h, direction, [item(product_id, 1)])
        assert response.status_code == 201, response.text
        return response.json()

    save("2026-11-18T15:59:59.999999+00:00", "IN", marked)
    first = save("2026-11-18T16:00:00+00:00", "IN", marked)
    save("2026-11-19T01:00:00+00:00", "IN", other)
    last = save("2026-11-19T15:59:59.999999+00:00", "OUT", marked)
    save("2026-11-19T16:00:00+00:00", "IN", marked)

    def search(**params):
        response = client.get("/api/documents", headers=h, params=params)
        assert response.status_code == 200, response.text
        return response.json()

    day = {"created_from": "2026-11-19T00:00:00+08:00", "created_before": "2026-11-20T00:00:00+08:00"}
    page = search(**day, q="_%", limit=1)
    assert page["total"] == 2
    assert [row["id"] for row in page["items"]] == [last["id"]]
    assert [row["id"] for row in search(**day, q="_%", limit=1, offset=1)["items"]] == [first["id"]]
    assert search(**day, q="默认子公司", kind="NORMAL", direction="OUT")["total"] == 1
    assert search(**day, q="默认子公司", direction="IN")["total"] == 0
    assert search(**day, q="默认供应商", direction="IN")["total"] == 2
    assert search(**day, q="ADMIN")["total"] == 3
    path = "/api/documents/export.xlsx"
    workbook = exported_workbook(client, str(client.build_request("GET", path, params=day).url), h)
    exported_ids = {row[0] for name in ("入库单", "出库单") for row in list(workbook[name].values)[1:]}
    assert exported_ids == {row["doc_no"] for row in search(**day)["items"]}
    assert search(q=first["doc_no"].lower())["items"][0]["id"] == first["id"]
    invalid = client.get("/api/documents", headers=h, params={
        "created_from": day["created_before"], "created_before": day["created_from"],
    })
    assert invalid.status_code == 422


def test_document_dropdown_filters_match_ids_and_include_inactive_choices(client):
    h = auth(client)
    first_product = product(client, h, "历史物资")
    second_product = product(client, h, "当前物资")
    product(client, h, "未开单物资")
    supplier = client.post("/api/suppliers", headers=h, json={"name": "旧供应商"})
    assert supplier.status_code == 201
    supplier_id = supplier.json()["id"]
    first = doc(client, h, "IN", [item(first_product, 2), item(second_product, 1)], supplier_id=supplier_id)
    second = doc(client, h, "IN", [item(first_product, 1)], supplier_id=supplier_id)
    other = doc(client, h, "IN", [item(first_product, 1)])
    issued = doc(client, h, "OUT", [item(first_product, 1)])
    assert all(response.status_code == 201 for response in (first, second, other, issued))
    assert client.patch(f"/api/products/{first_product}", headers=h, json={"is_active": False}).status_code == 200
    assert client.patch(f"/api/suppliers/{supplier_id}", headers=h, json={"is_active": False}).status_code == 200
    assert client.post("/api/users", headers=h, json=user_data("003", "clerk-test-password")).status_code == 201
    clerk = auth(client, "003", "clerk-test-password")

    def get(path, **params):
        response = client.get(path, headers=clerk, params=params)
        assert response.status_code == 200, response.text
        return response.json()

    options = get("/api/documents/filter-options")
    assert {p["id"] for p in options["products"]} == {first_product, second_product}
    assert {s["id"] for s in options["suppliers"]} == {1, supplier_id}
    outbound_options = get("/api/documents/filter-options", outbound_only="true")
    assert [p["id"] for p in outbound_options["products"]] == [first_product]
    assert outbound_options["suppliers"] == []
    assert options["companies"] == outbound_options["companies"] == [{"id": 1, "name": "默认子公司"}]

    filters = {"product_id": first_product, "supplier_id": supplier_id}
    page = get("/api/documents", **filters, limit=1)
    assert page["total"] == 2
    assert [row["id"] for row in page["items"]] == [second.json()["id"]]
    assert [row["id"] for row in get("/api/documents", **filters, limit=1, offset=1)["items"]] == [first.json()["id"]]
    assert get("/api/documents", product_id=second_product)["total"] == 1
    assert get("/api/documents", supplier_id=1)["total"] == 1
    assert get("/api/documents", product_id=first_product, kind="NORMAL", direction="OUT")["total"] == 1


@pytest.mark.parametrize(("brand", "link", "code"), [
    ("贵州茅台", "https://j.imt519.cn/q?c=09566735355117", "09566735355117"),
    ("国台", "https://ax.guotaiworld.com?125419384327", "125419384327"),
    ("五粮液", "HTTPS://WLYFW.COM/CD/?W=02A00108A0039G327AE90RYT", "02A00108A0039G327AE90RYT"),
])
def test_brand_box_code_is_validated_and_saved_without_url(client, brand, link, code):
    h = auth(client)
    p = product(client, h, "箱装酒", category="ALCOHOL", brand=brand)
    resolved = client.post("/api/scan/resolve", headers=h, json={"product_id": p, "raw_text": link})
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["code_value"] == code
    wrong_code = "https://j.imt519.cn.invalid/q?c=09566735355117"
    invalid = client.post("/api/scan/resolve", headers=h, json={"product_id": p, "raw_text": wrong_code})
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "BOX_CODE_FORMAT"
    assert doc(client, h, "IN", [alcohol_item(p, boxes=[{"code_value": wrong_code}])]).status_code == 422
    assert doc(client, h, "IN", [alcohol_item(p, boxes=[{"code_value": code}])]).status_code == 422

    received = doc(client, h, "IN", [alcohol_item(p, boxes=[{"code_value": link}])])
    assert received.status_code == 201, received.text
    assert received.json()["items"][0]["boxes"][0]["code_value"] == code
    assert doc(client, h, "IN", [alcohol_item(p, boxes=[{"code_value": link}])]).status_code == 409
    resolved = client.post("/api/scan/resolve", headers=h, json={"raw_text": link}).json()
    assert resolved["box"]["code_value"] == resolved["code_value"] == code

    issued = doc(client, h, "OUT", [alcohol_item(p, boxes=[{"code_value": link, "quantity": 2}])])
    assert issued.status_code == 201, issued.text
    assert issued.json()["items"][0]["boxes"][0]["code_value"] == code
    returned = client.post("/api/documents", headers=h, json={
        "request_id": str(uuid4()), "kind": "RETURN", "direction": "IN", "source_document_id": issued.json()["id"],
        "remark": "退回", "items": [alcohol_item(p, boxes=[{"code_value": link, "quantity": 1}])],
    })
    assert returned.status_code == 201, returned.text
    assert returned.json()["items"][0]["boxes"][0]["remaining_after"] == 5
    for query in (f" {link} ", code):
        history = client.get("/api/documents", headers=h, params={"box_code": query})
        assert history.status_code == 200
        assert history.json()["total"] == 3
        assert history.json()["exportable_total"] == 2
        assert [d["id"] for d in history.json()["items"]] == [
            returned.json()["id"], issued.json()["id"], received.json()["id"],
        ]

    only_returns = client.get("/api/documents", headers=h, params={"box_code": code, "kind": "RETURN"}).json()
    assert only_returns["total"] == 1
    assert only_returns["exportable_total"] == 0


def test_other_brands_and_legacy_box_codes_remain_usable(client):
    h = auth(client)
    legacy = "HTTPS://WLYFW.COM/CD/?W=OLD01"
    p = product(client, h, "旧款", category="ALCOHOL")
    received = doc(client, h, "IN", [alcohol_item(p, boxes=[{"code_value": legacy}])])
    assert received.status_code == 201
    assert received.json()["items"][0]["boxes"][0]["code_value"] == legacy
    assert client.put(f"/api/products/{p}", headers=h, json={"brand": "五粮液"}).status_code == 200
    resolved = client.post("/api/scan/resolve", headers=h, json={"product_id": p, "raw_text": legacy}).json()
    assert resolved["box"]["code_value"] == legacy
    assert resolved["code_value"] == "OLD01"
    issued = doc(client, h, "OUT", [alcohol_item(p, boxes=[{"code_value": legacy, "quantity": 1}])])
    assert issued.status_code == 201, issued.text
    history = client.get("/api/documents", headers=h, params={"box_code": legacy, "product_id": p}).json()
    assert [d["id"] for d in history["items"]] == [issued.json()["id"], received.json()["id"]]
    other_brand = "https://ax.guotaiworld.com?125419384327"
    assert client.post("/api/scan/resolve", headers=h, json={"product_id": p, "raw_text": other_brand}).status_code == 422


def test_registered_box_cannot_bypass_brand_mismatch(client):
    h = auth(client)
    product_id = product(client, h, "旧物资", category="ALCOHOL")
    guotai_link = "https://ax.guotaiworld.com?125419384327"
    assert doc(client, h, "IN", [alcohol_item(product_id, boxes=[{"code_value": guotai_link}])]).status_code == 201
    assert client.put(f"/api/products/{product_id}", headers=h, json={"brand": "五粮液"}).status_code == 200

    for selection in ({}, {"product_id": product_id}):
        response = client.post("/api/scan/resolve", headers=h, json={"raw_text": guotai_link, **selection})
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "BOX_BRAND_MISMATCH"
        assert response.json()["detail"]["message"] == "所选物资为五粮液，扫到的是国台箱码"

    response = doc(client, h, "OUT", [alcohol_item(product_id, boxes=[
        {"code_value": guotai_link, "quantity": 1},
    ])])
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "BOX_BRAND_MISMATCH"
    assert client.get("/api/products", headers=h).json()[0]["stock_qty"] == 6


def test_documents_atomic_idempotent_and_persistent(client):
    h = auth(client)
    a = product(client, h, "香烟")
    b = product(client, h, "白酒", category="ALCOHOL")
    first_id = str(uuid4())
    first = doc(client, h, "IN", [item(a, 10), item(b, 5)], first_id)
    assert first.status_code == 201
    assert len(first.json()["items"]) == 2
    assert doc(client, h, "IN", [item(b, 5), item(a, 10)], first_id).json()["id"] == first.json()["id"]
    assert doc(client, h, "IN", [item(a, 1)], first_id).status_code == 409
    failed = doc(client, h, "OUT", [item(a, 2), item(b, 100)])
    assert failed.status_code == 409
    assert client.get("/api/documents", headers=h).json()["total"] == 1
    quantities = {p["id"]: p["stock_qty"] for p in client.get("/api/products", headers=h).json()}
    assert quantities[a] == 10 and quantities[b] == 5
    out = doc(client, h, "OUT", [item(a, 2), item(b, 3)])
    assert out.status_code == 201
    assert out.json()["operator_name"] == "admin"
    assert out.json()["recipient"] == "默认子公司"
    assert client.get(f"/api/documents/{out.json()['id']}", headers=h).json()["items"][0]["quantity"] == 2
    assert {p["id"]: p["stock_qty"] for p in client.get("/api/products", headers=h).json()} == {a: 8, b: 2}


def test_concurrent_stock_and_request_id(client):
    h = auth(client)
    p = product(client, h, "并发")
    assert doc(client, h, "IN", [item(p, 5)]).status_code == 201
    def take(i):
        return doc(client, h, "OUT", [item(p, 4)]).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(take, range(2)))
    assert sorted(statuses) == [201, 409]
    assert client.get("/api/products", headers=h).json()[0]["stock_qty"] == 1
    request_id = str(uuid4())
    def submit(_):
        return doc(client, h, "IN", [item(p, 1)], request_id).json()["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(submit, range(2)))
    assert ids[0] == ids[1]


def test_serial_flow_and_rules(client):
    h = auth(client)
    p = product(client, h, "独立码", "SERIAL")
    q = product(client, h, "第二款")
    assert doc(client, h, "IN", [item(p, 2, ["URL/001", "URL/002"])]).status_code == 201
    assert doc(client, h, "IN", [item(p, 1, ["URL/001"])]).status_code == 409
    assert doc(client, h, "OUT", [item(p, 1, ["URL/999"])]).status_code == 409
    assert doc(client, h, "OUT", [item(p, 1, ["URL/001"])]).status_code == 201
    assert doc(client, h, "IN", [item(p, 1, ["URL/001"])]).status_code == 201
    assert doc(client, h, "IN", [item(p, 2, ["URL/003", "URL/003"])]).status_code == 422
    assert client.post("/api/scan/resolve", headers=h, json={"raw_text": "https://example.invalid"}).json()["candidates"] == []
    for pid, kind, value in [(p, "PREFIX", "URL/"), (q, "PREFIX", "URL/"), (q, "EXACT", "URL/002")]:
        assert client.post("/api/qr-rules", headers=h, json={"product_id": pid,
            "match_type": kind, "match_value": value}).status_code == 201
    assert len(client.post("/api/scan/resolve", headers=h, json={"raw_text": "URL/003"}).json()["candidates"]) == 2
    result = client.post("/api/scan/resolve", headers=h, json={"raw_text": "URL/002"}).json()
    assert result["match_type"] == "EXACT" and result["candidates"][0]["product_id"] == q


def test_roles_deactivation_and_history_guard(client):
    h = auth(client)
    created = client.post("/api/users", headers=h, json=user_data("001", "staff-password-123"))
    assert created.status_code == 201
    sh = auth(client, "001", "staff-password-123")
    assert client.post("/api/products", headers=sh, json={}).status_code == 403
    assert client.get("/api/users", headers=sh).status_code == 403
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer invalid"}).status_code == 401
    p = product(client, h, "有历史")
    assert doc(client, sh, "IN", [item(p, 1)]).status_code == 201
    assert client.patch(f"/api/products/{p}", headers=h, json={"scan_mode": "SERIAL"}).status_code == 409
    assert client.put(f"/api/products/{p}", headers=h, json={"is_active": False}).status_code == 200
    assert client.get("/api/products", headers=sh).json() == []
    assert client.get("/api/products?include_inactive=true", headers=sh).json()[0]["stock_qty"] == 1
    assert client.patch(f"/api/users/{created.json()['id']}", headers=h, json={"is_active": False}).status_code == 200
    assert client.get("/api/auth/me", headers=sh).status_code == 401
    assert client.patch("/api/users/1", headers=h, json={"is_active": False}).status_code == 409
    assert client.put(f"/api/users/{created.json()['id']}", headers=h, json={"is_active": True}).status_code == 200


def test_backup_restore_and_restart(client, tmp_path, monkeypatch):
    import sqlite3
    from app.database import initialize
    from scripts.backup import backup

    h = auth(client)
    p = product(client, h, "备份商品")
    assert doc(client, h, "IN", [item(p, 7)]).status_code == 201
    original = tmp_path / "stockflow.db"
    saved = backup(original, tmp_path / "backups")
    restored = tmp_path / "restored.db"
    restored.write_bytes(saved.read_bytes())
    with sqlite3.connect(restored) as db:
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert db.execute("SELECT stock_qty FROM products WHERE id=?", (p,)).fetchone()[0] == 7
        assert db.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
    monkeypatch.setenv("STOCKFLOW_DB_PATH", str(restored))
    monkeypatch.setenv("STOCKFLOW_ADMIN_PASSWORD", "a-different-password-123")
    initialize()
    assert client.get("/api/products", headers=h).json()[0]["stock_qty"] == 7
    assert auth(client)["Authorization"]


def test_supplier_required_and_snapshot(client):
    h = auth(client)
    staff = client.post("/api/users", headers=h, json=user_data("004", "buyer-password-123")).json()
    sh = auth(client, "004", "buyer-password-123")
    assert client.post("/api/suppliers", headers=sh, json={"name": "不可创建"}).status_code == 403
    p = product(client, h, "供货物资")
    missing = client.post("/api/documents", headers=sh, json={"request_id": str(uuid4()),
        "direction": "IN", "items": [item(p, 1)]})
    assert missing.status_code == 422
    saved = doc(client, sh, "IN", [item(p, 1)])
    assert saved.status_code == 201 and saved.json()["supplier_name"] == "默认供应商"
    assert client.put("/api/suppliers/1", headers=h, json={"name": "更名后供应商"}).status_code == 200
    assert client.get(f"/api/documents/{saved.json()['id']}", headers=sh).json()["supplier_name"] == "默认供应商"
    assert client.put("/api/suppliers/1", headers=h, json={"is_active": False}).status_code == 200
    assert doc(client, sh, "IN", [item(p, 1)]).status_code == 422
    assert client.get("/api/suppliers", headers=sh).json() == []


def test_alcohol_boxes_partial_out_and_loose_stock(client):
    h = auth(client)
    p = product(client, h, "箱装白酒", "SERIAL", "ALCOHOL")
    incoming = doc(client, h, "IN", [alcohol_item(p, 3, [
        {"code_value": "BOX-A"}, {"code_value": "BOX-B"}])])
    assert incoming.status_code == 201, incoming.text
    assert incoming.json()["items"][0]["quantity"] == 15
    assert len(incoming.json()["items"][0]["boxes"]) == 2
    stock = client.get("/api/products", headers=h).json()[0]
    assert (stock["stock_qty"], stock["loose_qty"], stock["full_boxes"], stock["boxed_qty"]) == (15, 3, 2, 12)
    assert doc(client, h, "IN", [alcohol_item(p, 0, [{"code_value": "BOX-A"}])]).status_code == 409
    assert doc(client, h, "IN", [alcohol_item(p, 0, [
        {"code_value": "BOX-C"}, {"code_value": "BOX-C"}])]).status_code == 422
    match = client.post("/api/scan/resolve", headers=h, json={"raw_text": "BOX-A"}).json()
    assert match["match_type"] == "BOX" and match["box"]["remaining"] == 6

    partial = doc(client, h, "OUT", [alcohol_item(p, 2, [{"code_value": "BOX-A", "quantity": 2}])])
    assert partial.status_code == 201, partial.text
    assert partial.json()["items"][0]["quantity"] == 4
    assert partial.json()["items"][0]["boxes"][0]["remaining_after"] == 4
    stock = client.get("/api/products", headers=h).json()[0]
    assert (stock["stock_qty"], stock["loose_qty"], stock["opened_boxes"], stock["boxed_qty"]) == (11, 1, 1, 10)
    box_list = client.get(f"/api/boxes?product_id={p}", headers=h).json()
    assert box_list["total"] == 2
    assert {b["code_value"]: b["remaining"] for b in box_list["items"]} == {"BOX-A": 4, "BOX-B": 6}
    assert doc(client, h, "OUT", [alcohol_item(p, 2)]).status_code == 409
    assert doc(client, h, "OUT", [alcohol_item(p, 0, [{"code_value": "BOX-A", "quantity": 5}])]).status_code == 409

    assert doc(client, h, "OUT", [alcohol_item(p, 0, [{"code_value": "BOX-B", "quantity": 6}])]).status_code == 201
    assert doc(client, h, "OUT", [alcohol_item(p, 0, [{"code_value": "BOX-A", "quantity": 4}])]).status_code == 201
    stock = client.get("/api/products", headers=h).json()[0]
    assert (stock["stock_qty"], stock["loose_qty"], stock["boxed_qty"]) == (1, 1, 0)
    assert client.patch(f"/api/products/{p}", headers=h, json={"bottles_per_box": 12}).status_code == 200
    reentry = doc(client, h, "IN", [alcohol_item(p, 0, [{"code_value": "BOX-A"}])])
    assert reentry.status_code == 201
    assert reentry.json()["items"][0]["boxes"][0]["capacity"] == 12
    assert client.get("/api/products", headers=h).json()[0]["stock_qty"] == 13


def test_inbound_loose_must_be_less_than_one_box(client):
    h = auth(client)
    serial = product(client, h, "限量箱装酒", "SERIAL", "ALCOHOL", bottles_per_box=6)
    loose_only = product(client, h, "限量散瓶酒", "QUANTITY", "ALCOHOL", bottles_per_box=12)

    for amount in (6, 7):
        result = doc(client, h, "IN", [alcohol_item(serial, amount, [{"code_value": "BOX-1"}])])
        assert result.status_code == 422
        assert result.json()["detail"]["code"] == "LOOSE_LIMIT"
    assert doc(client, h, "IN", [alcohol_item(serial, 5, [{"code_value": "BOX-1"}])]).status_code == 201
    assert doc(client, h, "IN", [alcohol_item(loose_only, 12)]).status_code == 422
    assert doc(client, h, "IN", [alcohol_item(loose_only, 11)]).status_code == 201
    stock = {p["id"]: p for p in client.get("/api/products", headers=h).json()}
    assert (stock[serial]["stock_qty"], stock[serial]["loose_qty"]) == (11, 5)
    assert (stock[loose_only]["stock_qty"], stock[loose_only]["loose_qty"]) == (11, 11)


def test_return_is_linked_to_outbound_and_cannot_exceed_it(client):
    h = auth(client)
    p = product(client, h, "可退箱装酒", "SERIAL", "ALCOHOL")
    received = doc(client, h, "IN", [alcohol_item(p, 5, [{"code_value": "RETURN-BOX"}])])
    assert received.status_code == 201
    issued = doc(client, h, "OUT", [alcohol_item(p, 3, [{"code_value": "RETURN-BOX", "quantity": 2}])])
    assert issued.status_code == 201
    source_id = issued.json()["id"]
    available = client.get(f"/api/documents/{source_id}/returnable", headers=h).json()["items"][0]
    assert (available["loose_quantity"], available["boxes"][0]["quantity"]) == (3, 2)

    body = {"request_id": str(uuid4()), "kind": "RETURN", "direction": "IN", "source_document_id": source_id,
            "remark": "领用公司退回", "items": [alcohol_item(p, 2, [{"code_value": "RETURN-BOX", "quantity": 1}])]}
    returned = client.post("/api/documents", headers=h, json=body)
    assert returned.status_code == 201, returned.text
    assert returned.json()["kind"] == "RETURN" and returned.json()["source_document_no"] == issued.json()["doc_no"]
    assert client.post("/api/documents", headers=h, json=body).json()["id"] == returned.json()["id"]
    available = client.get(f"/api/documents/{source_id}/returnable", headers=h).json()["items"][0]
    assert (available["loose_quantity"], available["boxes"][0]["quantity"]) == (1, 1)
    stock = client.get("/api/products", headers=h).json()[0]
    assert (stock["stock_qty"], stock["loose_qty"], stock["boxed_qty"]) == (9, 4, 5)

    too_many = {**body, "request_id": str(uuid4()), "items": [alcohol_item(p, 2)]}
    assert client.post("/api/documents", headers=h, json=too_many).status_code == 409
    wrong_source = {**body, "request_id": str(uuid4()), "source_document_id": received.json()["id"]}
    assert client.post("/api/documents", headers=h, json=wrong_source).status_code == 422
    assert client.get("/api/documents?kind=RETURN", headers=h).json()["total"] == 1
    def return_last_loose(_):
        return client.post("/api/documents", headers=h, json={**body, "request_id": str(uuid4()),
            "items": [alcohol_item(p, 1)]}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(return_last_loose, range(2))) == [201, 409]


def test_outbound_requires_active_company_and_keeps_original_company_on_return(client):
    admin = auth(client)
    password = "warehouse-password"
    assert client.post("/api/users", headers=admin, json=user_data("016", password)).status_code == 201
    staff = auth(client, "016", password)
    created = client.post("/api/companies", headers=admin, json={"name": "运营子公司"})
    assert created.status_code == 201
    company_id = created.json()["id"]
    assert client.get("/api/companies", headers=staff).status_code == 200
    assert client.get("/api/companies?include_inactive=true", headers=staff).status_code == 403
    assert client.post("/api/companies", headers=staff, json={"name": "无权添加"}).status_code == 403

    product_id = product(client, admin, "办公物资")
    assert doc(client, admin, "IN", [item(product_id, 4)]).status_code == 201
    body = {"request_id": str(uuid4()), "direction": "OUT", "items": [item(product_id, 2)]}
    rejected = client.post("/api/documents", headers=staff, json={**body, "recipient": "个人领用"})
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "RECIPIENT_COMPANY_REQUIRED"
    rejected = client.post("/api/documents", headers=staff, json={**body, "recipient_company_id": 999})
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "COMPANY_INVALID"
    body["recipient_company_id"] = company_id
    issued = client.post("/api/documents", headers=staff, json=body)
    assert issued.status_code == 201, issued.text
    document_id = issued.json()["id"]
    assert (issued.json()["recipient_company_id"], issued.json()["recipient"]) == (company_id, "运营子公司")
    assert client.patch(f"/api/companies/{company_id}", headers=admin,
                        json={"name": "更名子公司", "is_active": False}).status_code == 200
    assert all(company["id"] != company_id for company in client.get("/api/companies", headers=staff).json())
    assert any(company["id"] == company_id for company in client.get(
        "/api/companies?include_inactive=true", headers=admin).json())
    assert client.post("/api/documents", headers=staff, json=body).json()["id"] == document_id
    assert doc(client, staff, "OUT", [item(product_id, 1)], recipient_company_id=company_id).status_code == 422
    source = client.get(f"/api/documents/{document_id}/returnable", headers=staff).json()
    assert (source["recipient_company_id"], source["recipient"]) == (company_id, "运营子公司")
    returned = client.post("/api/documents", headers=staff, json={
        "request_id": str(uuid4()), "kind": "RETURN", "direction": "IN", "source_document_id": document_id,
        "remark": "余量退回", "items": [item(product_id, 1)],
    })
    assert returned.status_code == 201, returned.text
    assert (returned.json()["recipient_company_id"], returned.json()["recipient"]) == (company_id, "运营子公司")
    result = client.get("/api/documents?direction=OUT", headers=staff).json()["items"][0]
    assert (result["recipient_company_id"], result["recipient"]) == (company_id, "运营子公司")


def test_company_migration_preserves_old_outbound_recipient_and_retry(client):
    from app.database import initialize, transaction

    admin = auth(client)
    product_id = product(client, admin, "历史物资")
    assert doc(client, admin, "IN", [item(product_id, 3)]).status_code == 201
    request_id = str(uuid4())
    issued = doc(client, admin, "OUT", [item(product_id, 2)], request_id=request_id).json()
    old_recipient = "历史领用人员"
    old_hash_data = {
        "operator_id": issued["operator_id"], "direction": "OUT", "kind": "NORMAL", "source_document_id": None,
        "supplier_id": None, "recipient": old_recipient, "remark": None,
        "items": [{**item(product_id, 2), "loose_quantity": None, "boxes": []}],
    }
    old_hash = hashlib.sha256(json.dumps(old_hash_data, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")).encode()).hexdigest()
    with transaction() as db:
        db.execute("ALTER TABLE documents DROP COLUMN recipient_company_id")
        db.execute("UPDATE documents SET recipient=?,request_hash=? WHERE id=?", (old_recipient, old_hash, issued["id"]))
        db.execute("PRAGMA user_version=4")
    initialize()
    initialize()

    request = {"request_id": request_id, "direction": "OUT", "recipient": old_recipient, "items": [item(product_id, 2)]}
    retried = client.post("/api/documents", headers=admin, json=request)
    assert retried.status_code == 201, retried.text
    assert (retried.json()["id"], retried.json()["recipient_company_id"], retried.json()["recipient"]) == (
        issued["id"], None, old_recipient)
    assert client.get("/api/companies", headers=admin).json()[0]["name"] == "默认子公司"
    sheet = exported_workbook(client, f"/api/documents/{issued['id']}/export.xlsx", admin)["出库单"]
    assert (sheet["D2"].value, sheet["M1"].value, sheet["M2"].value) == (None, "历史领用人", old_recipient)
    returned = client.post("/api/documents", headers=admin, json={
        "request_id": str(uuid4()), "kind": "RETURN", "direction": "IN", "source_document_id": issued["id"],
        "remark": "历史单据退回", "items": [item(product_id, 1)],
    })
    assert returned.status_code == 201, returned.text
    assert (returned.json()["recipient_company_id"], returned.json()["recipient"]) == (None, old_recipient)


def test_staff_adjustment_reason_and_box_capacity(client):
    h = auth(client)
    created = client.post("/api/users", headers=h, json=user_data("005", "counter-password-123"))
    assert created.status_code == 201
    sh = auth(client, "005", "counter-password-123")
    p = product(client, h, "盘点酒", "SERIAL", "ALCOHOL")
    assert doc(client, sh, "IN", [alcohol_item(p, 2, [{"code_value": "COUNT-BOX"}])]).status_code == 201

    def adjust(direction, loose, boxes, remark="盘点差异"):
        return client.post("/api/documents", headers=sh, json={"request_id": str(uuid4()), "kind": "ADJUST",
            "direction": direction, "remark": remark, "items": [alcohol_item(p, loose, boxes)]})

    assert adjust("OUT", 1, [{"code_value": "COUNT-BOX", "quantity": 2}], "").status_code == 422
    assert adjust("OUT", 1, [{"code_value": "COUNT-BOX", "quantity": 2}]).status_code == 201
    assert adjust("IN", 4, [{"code_value": "COUNT-BOX", "quantity": 1}]).status_code == 201
    assert adjust("IN", 0, [{"code_value": "COUNT-BOX", "quantity": 2}]).status_code == 409
    assert adjust("IN", 0, [{"code_value": "FOUND-BOX", "quantity": 6}]).status_code == 201
    stock = client.get("/api/products", headers=sh).json()[0]
    assert (stock["stock_qty"], stock["loose_qty"], stock["boxed_qty"]) == (16, 5, 11)
    assert client.get("/api/documents?kind=ADJUST", headers=sh).json()["total"] == 3
    assert client.patch(f"/api/products/{p}", headers=h, json={"is_active": False}).status_code == 200
    assert client.post("/api/scan/resolve?include_inactive=true", headers=sh,
                       json={"raw_text": "COUNT-BOX"}).json()["box"]["remaining"] == 5
    assert adjust("OUT", 1, []).status_code == 201
    stock = client.get("/api/products?include_inactive=true", headers=sh).json()[0]
    assert (stock["stock_qty"], stock["loose_qty"]) == (15, 4)


def test_tobacco_return_and_stock_adjustment(client):
    h = auth(client)
    quantity_product = product(client, h, "按数量烟草")
    serial_product = product(client, h, "独立编码烟草", "SERIAL")
    assert doc(client, h, "IN", [item(quantity_product, 10), item(serial_product, 2, ["T-1", "T-2"])]).status_code == 201
    issued = doc(client, h, "OUT", [item(quantity_product, 4), item(serial_product, 2, ["T-1", "T-2"])])
    source_id = issued.json()["id"]
    body = {"request_id": str(uuid4()), "kind": "RETURN", "direction": "IN", "source_document_id": source_id,
            "remark": "未使用退回", "items": [item(quantity_product, 2), item(serial_product, 1, ["T-1"])]}
    assert client.post("/api/documents", headers=h, json=body).status_code == 201
    invalid = {**body, "request_id": str(uuid4()), "items": [item(serial_product, 1, ["T-1"])]}
    assert client.post("/api/documents", headers=h, json=invalid).status_code == 409
    available = client.get(f"/api/documents/{source_id}/returnable", headers=h).json()["items"]
    by_product = {r["product_id"]: r for r in available}
    assert by_product[quantity_product]["quantity"] == 2
    assert by_product[serial_product]["codes"] == ["T-2"]
    adjust = {"request_id": str(uuid4()), "kind": "ADJUST", "direction": "OUT", "remark": "盘亏",
              "items": [item(quantity_product, 1)]}
    assert client.post("/api/documents", headers=h, json=adjust).status_code == 201
    stock = {r["id"]: r["stock_qty"] for r in client.get("/api/products", headers=h).json()}
    assert stock == {quantity_product: 7, serial_product: 1}


def test_v3_migration_unifies_alcohol_without_changing_stock(client):
    from app.database import connect, initialize

    h = auth(client)
    p = product(client, h, "旧数量酒", category="ALCOHOL")
    with connect() as db:
        db.execute("UPDATE products SET scan_mode='QUANTITY',stock_qty=4,loose_qty=4 WHERE id=?", (p,))
        db.execute("PRAGMA user_version=2")
    initialize()
    initialize()
    row = next(r for r in client.get("/api/products", headers=h).json() if r["id"] == p)
    assert (row["scan_mode"], row["stock_qty"], row["loose_qty"]) == ("SERIAL", 4, 4)
    assert client.post("/api/products", headers=h, json={"category":"ALCOHOL","brand":"品牌","name":"新酒",
        "specification":"标准","unit":"瓶","scan_mode":"QUANTITY"}).json()["scan_mode"] == "SERIAL"


def test_box_concurrency_and_atomic_rollback(client):
    h = auth(client)
    p = product(client, h, "并发酒", "SERIAL", "ALCOHOL")
    q = product(client, h, "其它酒", "QUANTITY", "ALCOHOL")
    assert doc(client, h, "IN", [alcohol_item(p, 0, [{"code_value": "SAME-BOX"}])]).status_code == 201
    def take(_):
        return doc(client, h, "OUT", [alcohol_item(p, 0, [{"code_value": "SAME-BOX", "quantity": 4}])]).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(take, range(2))) == [201, 409]
    stock = {r["id"]: r for r in client.get("/api/products", headers=h).json()}
    assert stock[p]["stock_qty"] == 2 and stock[p]["boxed_qty"] == 2
    count = client.get("/api/documents", headers=h).json()["total"]
    failed = doc(client, h, "OUT", [alcohol_item(p, 0, [{"code_value": "SAME-BOX", "quantity": 1}]),
                                        alcohol_item(q, 1)])
    assert failed.status_code == 409
    assert client.get("/api/documents", headers=h).json()["total"] == count
    assert client.post("/api/scan/resolve", headers=h, json={"raw_text": "SAME-BOX"}).json()["box"]["remaining"] == 2


def test_existing_serial_alcohol_migrates_without_changing_balance(tmp_path, monkeypatch):
    import sqlite3
    from app.database import connect, initialize
    from app.services.documents import delete_document

    path = tmp_path / "old.db"
    monkeypatch.setenv("STOCKFLOW_DB_PATH", str(path))
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,password_hash TEXT,role TEXT,is_active INTEGER,created_at TEXT);
        CREATE TABLE products(id INTEGER PRIMARY KEY,category TEXT,brand TEXT,name TEXT,specification TEXT,unit TEXT,
          scan_mode TEXT,stock_qty INTEGER,is_active INTEGER,created_at TEXT);
        CREATE TABLE documents(id INTEGER PRIMARY KEY,doc_no TEXT,request_id TEXT,request_hash TEXT,direction TEXT,
          operator_id INTEGER,recipient TEXT,remark TEXT,created_at TEXT);
        CREATE TABLE document_items(id INTEGER PRIMARY KEY,document_id INTEGER,product_id INTEGER,quantity INTEGER);
        CREATE TABLE scan_events(id INTEGER PRIMARY KEY,document_item_id INTEGER,product_id INTEGER,code_value TEXT,
          code_kind TEXT,direction TEXT,created_at TEXT);
        INSERT INTO users VALUES(1,'admin','old-hash','ADMIN',1,'2026-01-01T00:00:00+00:00');
        INSERT INTO products VALUES(1,'ALCOHOL','品牌','旧酒','标准','瓶','SERIAL',2,1,'2026-01-01T00:00:00+00:00');
        INSERT INTO documents VALUES(1,'RKold','old-request','old-hash','IN',1,NULL,NULL,'2026-01-01T00:00:00+00:00');
        INSERT INTO document_items VALUES(1,1,1,2);
        INSERT INTO scan_events VALUES(1,1,1,'OLD-A','SERIAL','IN','2026-01-01T00:00:00+00:00');
        INSERT INTO scan_events VALUES(2,1,1,'OLD-B','SERIAL','IN','2026-01-01T00:00:00+00:00');
        """)
    initialize()
    initialize()
    db = connect()
    try:
        row = db.execute("SELECT stock_qty,loose_qty FROM products WHERE id=1").fetchone()
        assert tuple(row) == (2, 0)
        assert db.execute("SELECT SUM(remaining) FROM box_units").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM box_units").fetchone()[0] == 2
    finally:
        db.close()
    delete_document(1, 1)
    db = connect()
    try:
        assert db.execute("SELECT stock_qty FROM products WHERE id=1").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM box_units").fetchone()[0] == 0
    finally:
        db.close()
