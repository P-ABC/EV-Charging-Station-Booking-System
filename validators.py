"""validators.py — การตรวจสอบความถูกต้องของอินพุตทุกจุด

หลักการสำคัญ (ตามข้อกำหนด)
---------------------------
* ถ้าผู้ใช้กรอกผิด ต้อง **แจ้งเหตุผลแล้วให้กรอกใหม่** ไม่ใช่ปิดโปรแกรม
* ต้องรับมือกับ ``ValueError``, ``EOFError`` (stdin หมด/ถูกปิด) และ
  ``KeyboardInterrupt`` (ผู้ใช้กด Ctrl+C) ที่ต้องไม่ทำให้โปรแกรม crash
* ทุกฟังก์ชัน ``ask_*`` คืนค่าที่ผ่านการตรวจแล้วเสมอ

ฟังก์ชันตรวจสอบแบบไม่โต้ตอบ (``validate_*``) แยกออกจากฟังก์ชันถาม
(``ask_*``) เพื่อให้นำไปใช้ใน unit test ได้ง่ายโดยไม่ต้อง mock stdin
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

import models


class ValidationError(ValueError):
    """ข้อผิดพลาดจากการตรวจสอบอินพุต (สืบทอดจาก ValueError)"""


class UserAbort(Exception):
    """ผู้ใช้ยกเลิกการทำงาน (EOF หรือ Ctrl+C ระหว่างกรอกข้อมูล)"""


# ---------------------------------------------------------------------------
# ฟังก์ชันตรวจสอบล้วน (pure) — ใช้ซ้ำได้ทั้งในเมนูและใน unit test
# ---------------------------------------------------------------------------
def validate_point_id(value: int) -> int:
    """ตรวจว่า point_id เป็นจำนวนเต็มบวก

    Raises:
        ValidationError: เมื่อไม่ใช่จำนวนเต็มบวก
    """
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("point_id ต้องเป็นจำนวนเต็ม") from exc
    if number <= 0:
        raise ValidationError("point_id ต้องเป็นจำนวนเต็มบวก (มากกว่า 0)")
    return number


def validate_station_code(value: str) -> str:
    """ตรวจรูปแบบ station_code ตาม pattern EVS-NNNN (4 หลัก)

    Raises:
        ValidationError: เมื่อรูปแบบไม่ถูกต้อง
    """
    code = (value or "").strip().upper()
    parts = code.split("-")
    valid = (
        len(code) == len(models.STATION_CODE_PATTERN)
        and len(parts) == 2
        and parts[0] == "EVS"
        and parts[1].isdigit()
        and len(parts[1]) == 4
    )
    if not valid:
        raise ValidationError(
            f"รูปแบบ station_code ไม่ถูกต้อง: '{value}' "
            f"(ต้องเป็น {models.STATION_CODE_PATTERN} เช่น EVS-0001)"
        )
    return code


def validate_plug_type(value: str) -> str:
    """ตรวจว่า plug_type อยู่ในรายการที่กำหนด (Type2/CCS2/CHAdeMO/GB-T)

    Raises:
        ValidationError: เมื่อไม่อยู่ในรายการ
    """
    plug = (value or "").strip()
    for allowed in models.PLUG_TYPES:
        if plug.lower() == allowed.lower():
            return allowed
    raise ValidationError(
        f"plug_type ไม่ถูกต้อง: '{value}' (ต้องเป็น {' / '.join(models.PLUG_TYPES)})"
    )


def validate_positive_float(value: float, field_name: str = "ค่า") -> float:
    """ตรวจว่าเป็นเลขทศนิยมที่มากกว่า 0 (ใช้กับ power_kw / price_per_kwh)

    Raises:
        ValidationError: เมื่อไม่ใช่ตัวเลข หรือมีค่า <= 0
    """
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} ต้องเป็นตัวเลข") from exc
    if number <= 0:
        raise ValidationError(f"{field_name} ต้องมากกว่า 0 (ได้รับ {number})")
    return number


def validate_binary(value, field_name: str = "ค่า") -> int:
    """ตรวจว่าเป็น 0 หรือ 1 เท่านั้น (ใช้กับ status / is_booked)

    Raises:
        ValidationError: เมื่อไม่ใช่ 0 หรือ 1
    """
    text = str(value).strip()
    if text not in ("0", "1"):
        raise ValidationError(
            f"{field_name} ต้องเป็น 0 หรือ 1 เท่านั้น (ได้รับ '{text}')"
        )
    return int(text)


def validate_location(value: str, warn: Optional[Callable[[str], None]] = None) -> str:
    """ตรวจสอบ location: ห้ามว่าง และไม่เกิน 30 ไบต์ (UTF-8)

    เมื่อเกิน 30 ไบต์ จะ **เตือนก่อนตัด** แล้วจึงตัดให้พอดีโดยไม่ตัดกลาง
    อักขระ UTF-8 (ผ่าน :func:`models.truncate_display`)

    Args:
        value: ข้อความสถานที่ตั้ง
        warn: ฟังก์ชันสำหรับพิมพ์คำเตือน (ถ้าไม่ส่งมาจะไม่พิมพ์)

    Returns:
        ข้อความที่อาจถูกตัดแล้ว (ความยาวไม่เกิน 30 ไบต์)

    Raises:
        ValidationError: เมื่อข้อความว่าง
    """
    text = (value or "").strip()
    if not text:
        raise ValidationError("location ห้ามเป็นค่าว่าง")

    byte_len = models.text_byte_length(text)
    if byte_len > models.LOCATION_MAX_BYTES:
        truncated = models.truncate_display(text, models.LOCATION_MAX_BYTES)
        message = (
            f"location ยาว {byte_len} ไบต์ เกินขนาดฟิลด์ "
            f"{models.LOCATION_MAX_BYTES} ไบต์ — ระบบจะตัดให้พอดี"
        )
        if warn is not None:
            warn(message)
        return truncated
    return text

# ---------------------------------------------------------------------------
# ฟังก์ชันถามผู้ใช้ (ask_*) — วนถามใหม่จนกว่าจะถูกต้อง
# ---------------------------------------------------------------------------
def _read_line(prompt: str, reader: Callable[[str], str]) -> str:
    """อ่านบรรทัดจากผู้ใช้ โดยจัดการ EOFError / KeyboardInterrupt อย่างปลอดภัย

    Raises:
        UserAbort: เมื่อ stdin หมด (EOFError) หรือผู้ใช้กด Ctrl+C
    """
    try:
        return reader(prompt)
    except EOFError as exc:
        raise UserAbort("ได้รับ EOF จากอินพุต (ปิด stdin) — กำลังออกจากโปรแกรม") from exc
    except KeyboardInterrupt as exc:
        raise UserAbort("ผู้ใช้กด Ctrl+C — กำลังยกเลิกคำสั่งนี้") from exc


def ask_point_id(reader: Callable[[str], str] = input,
                 printer: Callable[[str], None] = print) -> int:
    """ถาม point_id จนกว่าจะเป็นจำนวนเต็มบวก

    Raises:
        UserAbort: เมื่อผู้ใช้ยกเลิก
    """
    while True:
        raw = _read_line("Point ID : ", reader).strip()
        try:
            return validate_point_id(raw)
        except ValidationError as exc:
            printer(f"   [ข้อผิดพลาด] {exc}")


def ask_station_code(reader: Callable[[str], str] = input,
                     printer: Callable[[str], None] = print) -> str:
    """ถาม station_code จนกว่ารูปแบบจะเป็น EVS-NNNN

    Raises:
        UserAbort: เมื่อผู้ใช้ยกเลิก
    """
    while True:
        printer(f"   (ตัวอย่างรูปแบบ: {models.STATION_CODE_PATTERN})")
        raw = _read_line("Station Code : ", reader).strip()
        try:
            return validate_station_code(raw)
        except ValidationError as exc:
            printer(f"   [ข้อผิดพลาด] {exc}")


def ask_location(reader: Callable[[str], str] = input,
                 printer: Callable[[str], None] = print) -> str:
    """ถาม location จนกว่าจะไม่ว่าง (และเตือน+ตัดเมื่อเกิน 30 ไบต์)

    Raises:
        UserAbort: เมื่อผู้ใช้ยกเลิก
    """
    while True:
        raw = _read_line("Location : ", reader)
        try:
            return validate_location(raw, warn=printer)
        except ValidationError as exc:
            printer(f"   [ข้อผิดพลาด] {exc}")


def ask_plug_type(reader: Callable[[str], str] = input,
                  printer: Callable[[str], None] = print) -> str:
    """แสดงเมนู plug_type แล้วถามจนกว่าจะเลือกได้ค่าที่ถูกต้อง

    Raises:
        UserAbort: เมื่อผู้ใช้ยกเลิก
    """
    while True:
        for number, plug in enumerate(models.PLUG_TYPES, start=1):
            printer(f"     {number}) {plug}")
        raw = _read_line("Plug Type [1-4] : ", reader).strip()
        if raw.isdigit() and 1 <= int(raw) <= len(models.PLUG_TYPES):
            return models.PLUG_TYPES[int(raw) - 1]
        try:
            return validate_plug_type(raw)      # ยอมรับการพิมพ์ชื่อตรง ๆ ด้วย
        except ValidationError as exc:
            printer(f"   [ข้อผิดพลาด] {exc}")


def ask_power_kw(reader: Callable[[str], str] = input,
                 printer: Callable[[str], None] = print) -> float:
    """ถามกำลังไฟสูงสุด (kW) จนกว่าจะมากกว่า 0

    Raises:
        UserAbort: เมื่อผู้ใช้ยกเลิก
    """
    while True:
        raw = _read_line("Power (kW) : ", reader).strip()
        try:
            return validate_positive_float(raw, "Power (kW)")
        except ValidationError as exc:
            printer(f"   [ข้อผิดพลาด] {exc}")


def ask_price_per_kwh(reader: Callable[[str], str] = input,
                      printer: Callable[[str], None] = print) -> float:
    """ถามราคาต่อหน่วย (THB/kWh) จนกว่าจะมากกว่า 0

    Raises:
        UserAbort: เมื่อผู้ใช้ยกเลิก
    """
    while True:
        raw = _read_line("Price (THB/kWh) : ", reader).strip()
        try:
            return validate_positive_float(raw, "Price (THB/kWh)")
        except ValidationError as exc:
            printer(f"   [ข้อผิดพลาด] {exc}")


def ask_binary(question: str, reader: Callable[[str], str] = input,
               printer: Callable[[str], None] = print) -> int:
    """ถามค่า 0/1 (สำหรับ status และ is_booked) จนกว่าจะถูกต้อง

    Raises:
        UserAbort: เมื่อผู้ใช้ยกเลิก
    """
    while True:
        raw = _read_line(f"{question} [0/1] : ", reader).strip()
        try:
            return validate_binary(raw, question)
        except ValidationError as exc:
            printer(f"   [ข้อผิดพลาด] {exc}")


def ask_yes_no(question: str, default: bool = False,
               reader: Callable[[str], str] = input,
               printer: Callable[[str], None] = print) -> bool:
    """ถามยืนยัน y/n (ใช้ตอน Delete ตามข้อกำหนด)

    Args:
        question: ข้อความคำถาม
        default: ค่าเริ่มต้นเมื่อผู้ใช้กด Enter เปล่า ๆ

    Raises:
        UserAbort: เมื่อผู้ใช้ยกเลิก
    """
    hint = "[Y/n]" if default else "[y/N]"
    while True:
        raw = _read_line(f"{question} {hint} : ", reader).strip().lower()
        if raw == "":
            return default
        if raw in ("y", "yes", "ใช่"):
            return True
        if raw in ("n", "no", "ไม่"):
            return False
        printer("   [ข้อผิดพลาด] กรุณาตอบ y หรือ n เท่านั้น")


def ask_menu_choice(prompt: str, allowed: Sequence[int],
                    reader: Callable[[str], str] = input,
                    printer: Callable[[str], None] = print) -> int:
    """ถามตัวเลือกเมนู และรับเฉพาะค่าที่อยู่ใน ``allowed``

    Raises:
        UserAbort: เมื่อผู้ใช้ยกเลิก
    """
    allowed_text = ", ".join(str(item) for item in allowed)
    while True:
        raw = _read_line(prompt, reader).strip()
        try:
            choice = int(raw)
        except ValueError:
            printer(f"   [ข้อผิดพลาด] กรุณากรอกตัวเลข ({allowed_text})")
            continue
        if choice in allowed:
            return choice
        printer(f"   [ข้อผิดพลาด] ตัวเลือกต้องเป็น ({allowed_text})")
