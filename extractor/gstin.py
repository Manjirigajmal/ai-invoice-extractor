"""GSTIN helpers: format check, checksum and state lookup.

A GSTIN has 15 characters:
    2 digits   state code
    10 chars   PAN of the business (5 letters, 4 digits, 1 letter)
    1 char     entity number (1-9, A-Z)
    'Z'        default
    1 char     checksum (mod-36 Luhn)
"""
import re

CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_PATTERN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

STATES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan",
    "09": "Uttar Pradesh", "10": "Bihar", "19": "West Bengal", "20": "Jharkhand",
    "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "27": "Maharashtra", "29": "Karnataka", "30": "Goa", "32": "Kerala",
    "33": "Tamil Nadu", "36": "Telangana", "37": "Andhra Pradesh",
}


def checksum_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        product = CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return CHARS[(36 - total % 36) % 36]


def is_valid(gstin: str | None) -> bool:
    if not gstin or not GSTIN_PATTERN.match(gstin):
        return False
    return checksum_char(gstin[:14]) == gstin[14]


def state_code(gstin: str | None) -> str | None:
    if gstin and len(gstin) >= 2 and gstin[:2].isdigit():
        return gstin[:2]
    return None


def make(state: str, pan: str, entity: str = "1") -> str:
    """Build a GSTIN with a correct checksum (used to create sample data)."""
    first14 = f"{state}{pan}{entity}Z"
    return first14 + checksum_char(first14)
