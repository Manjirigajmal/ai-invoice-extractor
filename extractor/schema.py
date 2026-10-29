"""The fields we pull out of every invoice.

The same Pydantic model is used three ways: as the JSON schema we hand to the
LLM, to validate whatever the LLM returns, and as the row format for Excel.
"""
from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str = Field(description="Item or service description as printed")
    hsn_sac: str | None = Field(None, description="HSN or SAC code, digits only")
    quantity: float | None = Field(None, description="Quantity as a number")
    unit_price: float | None = Field(None, description="Price per unit, number only, no currency symbol or commas")
    amount: float | None = Field(None, description="Line amount as printed, number only")


class InvoiceData(BaseModel):
    vendor_name: str | None = Field(None, description="Supplier / seller business name")
    vendor_gstin: str | None = Field(None, description="Supplier GSTIN, 15 characters, uppercase")
    buyer_name: str | None = Field(None, description="Buyer / bill-to business name")
    buyer_gstin: str | None = Field(None, description="Buyer / recipient GSTIN, 15 characters, uppercase")
    invoice_number: str | None = Field(None, description="Invoice or bill number exactly as printed")
    invoice_date: str | None = Field(None, description="Invoice date in ISO format YYYY-MM-DD")
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: float | None = Field(None, description="Taxable value / amount before tax")
    cgst: float | None = Field(None, description="CGST amount, 0 if not charged")
    sgst: float | None = Field(None, description="SGST/UTGST amount, 0 if not charged")
    igst: float | None = Field(None, description="IGST amount, 0 if not charged")
    total: float | None = Field(None, description="Final invoice total / amount payable as printed")


class Issue(BaseModel):
    severity: str  # "error" | "warning"
    code: str
    message: str


class InvoiceResult(BaseModel):
    source_file: str
    engine: str
    data: InvoiceData
    issues: list[Issue] = Field(default_factory=list)
    error: str | None = None  # set when extraction itself failed

    @property
    def status(self) -> str:
        if self.error:
            return "Failed"
        if any(i.severity == "error" for i in self.issues):
            return "Needs review"
        if self.issues:
            return "Check"
        return "OK"
