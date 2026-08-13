def _format_tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def _crc16_ccitt(payload: str) -> str:
    crc = 0xFFFF
    for byte in payload.encode("ascii"):
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return format(crc, "04X")


def generate_promptpay_payload(target: str, amount: float | None = None) -> str:
    """สร้าง payload string สำหรับ QR พร้อมเพย์ (EMV QR Code Specification)

    target: เบอร์โทร 10 หลัก (เช่น 0812345678) หรือเลขประจำตัวผู้เสียภาษี/บัตรประชาชน 13 หลัก
    """
    digits = "".join(ch for ch in target if ch.isdigit())
    if len(digits) == 10 and digits.startswith("0"):
        account_id = ("0066" + digits[1:]).rjust(13, "0")
        merchant_info = _format_tlv("00", "A000000677010111") + _format_tlv("01", account_id)
    elif len(digits) == 13:
        merchant_info = _format_tlv("00", "A000000677010111") + _format_tlv("02", digits)
    else:
        raise ValueError("PromptPay ID ต้องเป็นเบอร์โทร 10 หลัก หรือเลขประจำตัว 13 หลัก")

    payload = (
        _format_tlv("00", "01")
        + _format_tlv("01", "12" if amount is not None else "11")
        + _format_tlv("29", merchant_info)
        + _format_tlv("53", "764")
    )
    if amount is not None:
        payload += _format_tlv("54", f"{amount:.2f}")
    payload += _format_tlv("58", "TH")
    payload += "6304"
    return payload + _crc16_ccitt(payload)
