from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from .config import MIN_PASSWORD_LENGTH


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ProductCreate(BaseModel):
    category: Literal["TOBACCO", "ALCOHOL"]
    brand: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    specification: str = Field(min_length=1, max_length=100)
    unit: str = Field(min_length=1, max_length=20)
    scan_mode: Literal["QUANTITY", "SERIAL"] = "QUANTITY"
    bottles_per_box: int = Field(default=6, ge=1, le=1000)

    @field_validator("brand", "name", "specification", "unit")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能只输入空白字符")
        return value

    @model_validator(mode="after")
    def alcohol_uses_bottles(self):
        if self.category == "ALCOHOL" and self.unit != "瓶":
            raise ValueError("酒水最小单位必须是瓶")
        if self.category == "ALCOHOL":
            self.scan_mode = "SERIAL"
        return self


class ProductPatch(BaseModel):
    category: Literal["TOBACCO", "ALCOHOL"] | None = None
    brand: str | None = Field(default=None, min_length=1, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    specification: str | None = Field(default=None, min_length=1, max_length=100)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    scan_mode: Literal["QUANTITY", "SERIAL"] | None = None
    bottles_per_box: int | None = Field(default=None, ge=1, le=1000)
    is_active: bool | None = None

    @field_validator("brand", "name", "specification", "unit")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("不能只输入空白字符")
        return value


class RuleCreate(BaseModel):
    product_id: int = Field(gt=0)
    match_type: Literal["EXACT", "PREFIX"]
    match_value: str = Field(min_length=1, max_length=512)


class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("供应商名称不能为空")
        return value


class SupplierPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("供应商名称不能为空")
        return value


class ScanResolve(BaseModel):
    raw_text: str = Field(min_length=1, max_length=2048)
    product_id: int | None = Field(default=None, gt=0)


ProfileName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
EmployeeNumber = Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r"^[0-9]+$")]


class CompanyCreate(BaseModel):
    name: ProfileName


class CompanyPatch(BaseModel):
    name: ProfileName | None = None
    is_active: bool | None = None


class UserCreate(BaseModel):
    username: EmployeeNumber
    name: ProfileName
    department_id: int = Field(gt=0)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)
    role: Literal["ADMIN", "STAFF"] = "STAFF"


class UserPatch(BaseModel):
    username: EmployeeNumber | None = None
    name: ProfileName | None = None
    department_id: int | None = Field(default=None, gt=0)
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=MIN_PASSWORD_LENGTH, max_length=256)


class BoxAction(BaseModel):
    code_value: str = Field(min_length=1, max_length=2048)
    quantity: int | None = Field(default=None, gt=0, le=1000)


class DocumentItem(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int | None = Field(default=None, gt=0, le=1000000)
    loose_quantity: int | None = Field(default=None, ge=0, le=1000000)
    boxes: list[BoxAction] = Field(default_factory=list, max_length=200)
    codes: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("codes")
    @classmethod
    def check_codes(cls, codes: list[str]) -> list[str]:
        if any(not c or len(c) > 2048 for c in codes):
            raise ValueError("码不能为空，长度最多 2048")
        return codes


class DocumentCreate(BaseModel):
    request_id: UUID
    direction: Literal["IN", "OUT"]
    kind: Literal["NORMAL", "RETURN", "ADJUST"] = "NORMAL"
    source_document_id: int | None = Field(default=None, gt=0)
    supplier_id: int | None = Field(default=None, gt=0)
    recipient_company_id: int | None = Field(default=None, gt=0)
    recipient: str | None = Field(default=None, max_length=100)
    remark: str | None = Field(default=None, max_length=500)
    items: list[DocumentItem] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def check_document(self):
        self.recipient = self.recipient.strip() if self.recipient else None
        self.remark = self.remark.strip() if self.remark else None
        if self.kind == "NORMAL":
            if self.source_document_id is not None:
                raise ValueError("普通单据不能关联原单")
            if self.direction == "OUT" and self.recipient_company_id is not None and self.recipient:
                raise ValueError("请选择领用公司")
            if self.direction == "IN" and self.supplier_id is None:
                raise ValueError("入库必须选择供应商")
            if self.direction == "IN" and self.recipient_company_id is not None:
                raise ValueError("入库单只需选择供应商")
            if self.direction == "OUT" and self.supplier_id is not None:
                raise ValueError("出库不填写供应商")
        elif self.kind == "RETURN":
            if self.direction != "IN" or self.source_document_id is None:
                raise ValueError("退库必须关联原出库单")
            if self.supplier_id is not None or self.recipient is not None or self.recipient_company_id is not None:
                raise ValueError("退库的领用信息随原出库单保存")
            if not self.remark:
                raise ValueError("退库必须填写原因")
        else:
            if (self.source_document_id is not None or self.supplier_id is not None
                    or self.recipient is not None or self.recipient_company_id is not None):
                raise ValueError("库存调整不填写原单、供应商或领用公司")
            if not self.remark:
                raise ValueError("库存调整必须填写原因")
        if len({item.product_id for item in self.items}) != len(self.items):
            raise ValueError("同一单据不能重复物资行")
        if sum(len(item.codes) + len(item.boxes) for item in self.items) > 500:
            raise ValueError("单据扫码数最多 500")
        return self
