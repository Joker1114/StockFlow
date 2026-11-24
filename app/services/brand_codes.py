import re
import sqlite3
from urllib.parse import urlsplit

from ..errors import fail


BRAND_PATTERNS = {
    "茅台": re.compile(r"(?i:https://j\.imt519\.cn)/q\?c=([0-9]+)"),
    "国台": re.compile(r"(?i:https://ax\.guotaiworld\.com)/?\?([0-9]+)"),
    "五粮液": re.compile(r"(?i:https://wlyfw\.com)/CD/\?W=([A-Za-z0-9]+)"),
}
BRAND_HOSTS = {
    "j.imt519.cn": "茅台",
    "ax.guotaiworld.com": "国台",
    "wlyfw.com": "五粮液",
}


def configured_brand(brand: str) -> str:
    brand = brand.strip()
    return "茅台" if brand == "贵州茅台" else brand


def parse_brand_code(raw: str) -> tuple[str, str] | None:
    for brand, pattern in BRAND_PATTERNS.items():
        if match := pattern.fullmatch(raw):
            return brand, match[1]
    return None


def validate_box_brand(brand: str, raw: str) -> None:
    expected = configured_brand(brand)
    if expected not in BRAND_PATTERNS:
        return
    try:
        link = urlsplit(raw)
        scanned = BRAND_HOSTS.get(link.hostname) if link.scheme in ("http", "https") else None
    except ValueError:
        return
    if scanned and scanned != expected:
        fail(422, "BOX_BRAND_MISMATCH", f"所选物资为{expected}，扫到的是{scanned}箱码")


def new_box_code(brand: str, raw: str, parsed: tuple[str, str] | None) -> str:
    brand = configured_brand(brand)
    if brand not in BRAND_PATTERNS:
        return raw
    if parsed is None or parsed[0] != brand:
        fail(422, "BOX_CODE_FORMAT", f"该码不符合{brand}箱码格式，请扫描{brand}外箱二维码")
    return parsed[1]


def find_box(db: sqlite3.Connection, raw: str, parsed: tuple[str, str] | None) -> sqlite3.Row | None:
    code = parsed[1] if parsed else raw
    # Exact matches keep older full-link box records usable.
    return db.execute(
        """SELECT b.*,p.brand,p.is_active FROM box_units b JOIN products p ON p.id=b.product_id
           WHERE b.code_value IN (?,?) ORDER BY b.code_value=? DESC LIMIT 1""",
        (raw, code, raw),
    ).fetchone()
