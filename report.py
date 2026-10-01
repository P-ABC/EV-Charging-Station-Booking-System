"""report.py — สร้างไฟล์รายงานข้อความ report.txt (UTF-8)

ประกอบด้วย 3 ส่วน
------------------
1. :func:`display_width` — คำนวณ "ความกว้างเชิงการแสดงผล" ของข้อความ
   สำหรับจัดคอลัมน์ตารางให้ตรงกัน แม้ข้อความภาษาไทยจะมีสระ/วรรณยุกต์ที่
   "กว้าง 0 ช่อง" — ใช้ ``unicodedata.combining`` ตรวจว่าเป็นอักขระประสมหรือไม่
2. :func:`render_table` — สร้างตารางด้วยเส้นขอบ ``+----+`` และ ``|``
3. :func:`generate_report` — ประกอบรายงานฉบับเต็มตามโครงที่กำหนด

หมายเหตุเรื่องเวลา
------------------
ทุกเวลาที่แสดงในรายงานใช้เขตเวลา +07:00 โดยกำหนดเป็น
``datetime.timezone(timedelta(hours=7))`` แล้วแปลงจาก Unix timestamp
"""

from __future__ import annotations

import os
import textwrap
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence

import models

# เขตเวลาไทย +07:00 (ตามข้อกำหนด ไม่ใช้เขตเวลาของเครื่อง)
THAI_TZ = timezone(timedelta(hours=7))

REPORT_TITLE = "EV Charging Station Booking System - Summary Report"
RECENT_ACTIVITY_LIMIT = 5      # จำนวนเหตุการณ์ล่าสุดที่แสดงในรายงาน


# ---------------------------------------------------------------------------
# 1) การวัดความกว้างเชิงการแสดงผล (รองรับภาษาไทย/อีมโจจิ)
# ---------------------------------------------------------------------------
def _char_width(char: str) -> int:
    """คืนความกว้างเชิงการแสดงผลของอักขระ 1 ตัว (0, 1 หรือ 2 ช่อง)

    กติกา:
        * อักขระประสม (Mark ที่ไม่กินพื้นที่ เช่น สระ/วรรณยุกต์ไทย) -> 0 ช่อง
        * อักขระ Full-width / Wide -> 2 ช่อง
        * อื่น ๆ -> 1 ช่อง

    หมายเหตุสำคัญเรื่องภาษาไทย (ข้อค้นพบระหว่างพัฒนา)
    --------------------------------------------------
    ``unicodedata.combining()`` รายงานค่าเป็น 0 สำหรับสระไทยบางตัว เช่น
    "ั" (U+0E31) และ "ิ" (U+0E35) แม้ว่าจะเป็นอักขระประสมจริง เพราะ Unicode
    จัดให้อยู่ในหมวด Mn (Mark, nonspacing) แต่มี Combining_Class = 0
    ดังนั้นการตรวจด้วย ``combining()`` อย่างเดียวจะทำให้คอลัมน์ตารางเบี้ยว
    ระบบจึงตรวจ **ทั้งสองเงื่อนไข**: ใช้ ``combining()`` ตามข้อกำหนดของโจทย์
    และเสริมด้วย ``category()`` ในหมวด Mn/Me ซึ่งครอบคลุมสระไทยครบถ้วน
    """
    if unicodedata.combining(char):
        return 0
    if unicodedata.category(char) in ("Mn", "Me"):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def display_width(text: str) -> int:
    """คำนวณความกว้างที่ "ใช้พื้นที่บนหน้าจอ" ของข้อความ

    หลักการ:
        * สระ/วรรณยุกต์ไทย (อักขระประสม) ไม่กินความกว้าง จึงไม่ทำให้คอลัมน์เบี้ยว
        * อักขระ Full-width / Wide (เช่น อักษรจีน) นับ 2 ช่อง
        * อักขระอื่นนับ 1 ช่อง

    Args:
        text: ข้อความที่จะวัด

    Returns:
        จำนวนช่องบนหน้าจอ
    """
    return sum(_char_width(char) for char in (text or ""))


def pad_to_width(text: str, width: int, align: str = "left") -> str:
    """เติมช่องว่างขวาให้ข้อความครองความกว้างที่กำหนด (คำนวณด้วย display_width)

    Args:
        text: ข้อความ
        width: ความกว้างเป้าหมายเป็นจำนวนช่อง
        align: "left" หรือ "right"
    """
    padding = max(0, width - display_width(text))
    if align == "right":
        return " " * padding + text
    return text + " " * padding


def truncate_to_width(text: str, width: int) -> str:
    """ตัดข้อความให้พอดีความกว้างเป้าหมาย (ไม่ตัดกลางอักขระประสม)

    ใช้กับข้อความภาษาไทยยาว ๆ ในตาราง เพื่อไม่ให้เส้นขอบตารางเบี้ยว
    """
    if display_width(text) <= width:
        return text
    ellipsis = "..."                      # จุดไข่ปลา ใช้พื้นที่ 3 ช่อง
    result = ""
    current = 0
    budget = width - display_width(ellipsis)
    for char in text:
        char_width = _char_width(char)
        if current + char_width > budget:
            break
        result += char
        current += char_width
    return result + ellipsis

# ---------------------------------------------------------------------------
# 2) การเรนเดอร์ตาราง
# ---------------------------------------------------------------------------
def render_table(headers: Sequence[str], rows: Sequence[Sequence[str]],
                 aligns: Optional[Sequence[str]] = None) -> List[str]:
    """สร้างบรรทัดตาราง (รวมเส้นขอบแบบ +----+ และ |) ตามความกว้างเนื้อหาจริง

    ความกว้างคอลัมน์คำนวณจาก display_width จึงรองรับภาษาไทยที่มีสระ/วรรณยุกต์
    โดยไม่ทำให้เส้นขอบตารางเบี้ยว

    Args:
        headers: หัวคอลัมน์
        rows: แต่ละแถวเป็น sequence ของข้อความ
        aligns: การจัดตำแหน่งของแต่ละคอลัมน์ ("left"/"right") ถ้าไม่ส่งค่า
            จะจัดตำแหน่งตามประเภทของหัวคอลัมน์อัตโนมัติ (ตัวเลข -> right)

    Returns:
        รายการบรรทัดของตาราง (ยังไม่รวม \n)
    """
    if aligns is None:
        aligns = ["right" if _looks_numeric(header) else "left"
                  for header in headers]

    # ความกว้างของแต่ละคอลัมน์ = ความกว้างหัวคอลัมน์ที่กว้างที่สุด
    widths = [display_width(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], display_width(str(cell)))

    def line(left: str, mid: str, right: str) -> str:
        return left + mid.join("-" * (width + 2) for width in widths) + right

    def row_line(cells: Sequence[str]) -> str:
        parts = []
        for index, cell in enumerate(cells):
            text = truncate_to_width(str(cell), widths[index])
            parts.append(" " + pad_to_width(text, widths[index],
                                            aligns[index] or "left") + " ")
        return "|" + "|".join(parts) + "|"

    result: List[str] = [line("+", "+", "+"), row_line(headers),
                         line("+", "+", "+")]
    result.extend(row_line(row) for row in rows)
    result.append(line("+", "+", "+"))
    return result


def _looks_numeric(text: str) -> bool:
    """ตรวจว่าหัวคอลัมน์ควรจัดตำแหน่งชิดขวา (ตัวเลขนำหน้า)"""
    stripped = text.strip()
    return bool(stripped) and stripped[0].isdigit()


# ---------------------------------------------------------------------------
# 3) ตัวช่วยคำนวณสถิติ
# ---------------------------------------------------------------------------
def format_timestamp(ts: int) -> str:
    """แปลง Unix timestamp เป็นข้อความเวลาเขต +07:00

    รูปแบบ: ``2026-09-16 09:30:00 (+07:00)``
    """
    return datetime.fromtimestamp(ts, THAI_TZ).strftime("%Y-%m-%d %H:%M:%S (+07:00)")


def compute_summary(points: Sequence[models.ChargePoint]) -> Dict[str, int]:
    """คำนวณตัวเลขสรุปสำหรับรายงาน

    กติกานับ (ตามสเปก):
        * Total Points   = จำนวนระเบียกทั้งหมดที่อ่านได้ (รวมที่ถูกลบแล้ว)
        * Active Points  = จำนวนที่ is_deleted=0 และ status=1
        * Deleted Points = จำนวนที่ is_deleted=1
        * Booked         = จำนวนที่ is_deleted=0 และ is_booked=1
        * Available Now  = จำนวนที่ is_deleted=0 และ status=1 และ is_booked=0
        * Free Slots     = จำนวนระเบียกที่ is_deleted=1 (ช่องว่างที่นำกลับมาใช้ได้)
    """
    alive = [point for point in points if not point.is_deleted]
    return {
        "total": len(points),
        "active": sum(1 for point in alive if point.status == 1),
        "deleted": sum(1 for point in points if point.is_deleted),
        "booked": sum(1 for point in alive if point.is_booked == 1),
        "available": sum(1 for point in alive
                         if point.status == 1 and point.is_booked == 0),
        "free_slots": sum(1 for point in points if point.is_deleted),
    }


def compute_price_stats(points: Sequence[models.ChargePoint]) -> Dict[str, float]:
    """คำนวณราคาต่ำสุด/สูงสุด/เฉลี่ย (นับเฉพาะระเบียกที่ยังไม่ถูกลบและ Active)

    Returns:
        {"min": float, "max": float, "avg": float} — ถ้าไม่มีข้อมูลจะคืน 0.0 ทั้งหมด
    """
    prices = [point.price_per_kwh for point in points
              if point.status == 1 and not point.is_deleted]
    if not prices:
        return {"min": 0.0, "max": 0.0, "avg": 0.0}
    return {
        "min": min(prices),
        "max": max(prices),
        "avg": sum(prices) / len(prices),
    }


def count_plug_types(points: Sequence[models.ChargePoint]) -> Dict[str, int]:
    """นับจำนวนหัวชาร์จแยกตามประเภทหัว (นับเฉพาะระเบียกที่ยังไม่ถูกลบและ Active)

    Returns:
        dict ที่มี key ครบทุกประเภทตามลำดับ CCS2, Type2, CHAdeMO, GB-T
        (ลำดับนี้เรียงตามรูปแบบที่กำหนดไว้ในสเปกรายงาน)
    """
    alive = [point for point in points
             if point.status == 1 and not point.is_deleted]
    counts = {plug: 0 for plug in ("CCS2", "Type2", "CHAdeMO", "GB-T")}
    for point in alive:
        if point.plug_type in counts:
            counts[point.plug_type] += 1
    return counts


# ---------------------------------------------------------------------------
# 4) การประกอบรายงานฉบับเต็ม
# ---------------------------------------------------------------------------
def build_report(points: Sequence[models.ChargePoint],
                 log_entries: Sequence[models.LogEntry],
                 generated_at: Optional[int] = None) -> str:
    """ประกอบข้อความรายงานฉบับเต็ม (ยังไม่เขียนลงไฟล์)

    Args:
        points: ระเบียกหัวชาร์จทั้งหมด (รวมที่ถูก soft delete แล้ว)
        log_entries: เหตุการณ์ใน audit log (เรียงจากเก่าไปใหม่)
        generated_at: Unix timestamp ของเวลาสร้างรายงาน (ค่าเริ่มต้น = เวลาปัจจุบัน)

    Returns:
        ข้อความรายงานที่เขียนด้วย encoding UTF-8
    """
    if generated_at is None:
        generated_at = models.now_timestamp()

    summary = compute_summary(points)
    stats = compute_price_stats(points)
    plug_counts = count_plug_types(points)

    lines: List[str] = []
    # ---- ส่วนหัวรายงาน -------------------------------------------------
    lines.append(REPORT_TITLE)
    lines.append(f"Generated At : {format_timestamp(generated_at)}")
    lines.append(f"App Version  : {models.APP_VERSION}")
    lines.append(f"Endianness   : {models.BYTE_ORDER_LABEL}")
    lines.append(f"Encoding     : {models.ENCODING_LABEL}")
    lines.append("")

    # ---- ตารางข้อมูลหัวชาร์จ (แสดงทั้ง Active และ Deleted) --------------
    lines.append("[Charge Points]")
    rows = [
        (
            str(point.point_id),
            point.station_code,
            point.location,
            point.plug_type,
            f"{point.power_kw:.1f}",
            f"{point.price_per_kwh:.2f}",
            point.status_text,
            point.booked_text,
        )
        for point in points
    ]
    headers = ["PtID", "Station", "Location", "Plug", "Power(kW)",
               "Price(THB/kWh)", "Status", "Booked"]
    lines.extend(render_table(headers, rows))
    lines.append("")

    # ---- สรุปตัวเลข -----------------------------------------------------
    lines.append("Summary (counting Active status only)")
    lines.append(f"- Total Points (records) : {summary['total']}")
    lines.append(f"- Active Points          : {summary['active']}")
    lines.append(f"- Deleted Points         : {summary['deleted']}")
    lines.append(f"- Currently Booked       : {summary['booked']}")
    lines.append(f"- Available Now          : {summary['available']}")
    lines.append(f"- Free Slots             : {summary['free_slots']}")
    lines.append("")

    # ---- สถิติราคา ------------------------------------------------------
    lines.append("Price Statistics (THB/kWh, Active only)")
    lines.append(f"- Min / Max / Avg        : {stats['min']:.2f} / "
                 f"{stats['max']:.2f} / {stats['avg']:.2f}")
    lines.append("")

    # ---- จำนวนตามประเภทหัว ---------------------------------------------
    lines.append("Points by Plug Type (Active only)")
    lines.append(f"- CCS2 : {plug_counts['CCS2']}, "
                 f"Type2 : {plug_counts['Type2']}, "
                 f"CHAdeMO : {plug_counts['CHAdeMO']}, "
                 f"GB-T : {plug_counts['GB-T']}")
    lines.append("")

    # ---- กิจกรรมล่าสุด (5 รายการล่าสุด ใหม่ -> เก่า) ----------------------
    lines.append("Recent Activity (from charge_points.log)")
    recent = list(log_entries)[-RECENT_ACTIVITY_LIMIT:]
    recent_rows = [
        (
            format_timestamp(entry.ts),
            entry.op_name,
            str(entry.point_id),
            entry.status_text,
            entry.booked_text,
            f"{entry.price_after_thb:.2f}",
        )
        for entry in reversed(recent)
    ]
    recent_headers = ["Timestamp", "Operation", "PtID", "Status", "Booked",
                      "Price(THB/kWh)"]
    lines.extend(render_table(recent_headers, recent_rows))
    lines.append("")

    # ---- ท้ายรายงาน -----------------------------------------------------
    footer = (
        f"End of report | records={summary['total']} "
        f"log_events={len(log_entries)} | {REPORT_TITLE}"
    )
    lines.extend(textwrap.wrap(footer, width=78))
    return "\n".join(lines) + "\n"


def generate_report(points: Sequence[models.ChargePoint],
                    log_entries: Sequence[models.LogEntry],
                    path: str,
                    generated_at: Optional[int] = None) -> str:
    """สร้างและ **เขียนรายงานลงไฟล์** (UTF-8) แล้ว flush + fsync ให้แน่นอน

    Args:
        points: ระเบียกหัวชาร์จทั้งหมด (รวมที่ถูก soft delete แล้ว)
        log_entries: เหตุการณ์ใน audit log
        path: พาธไฟล์รายงาน (เช่น report.txt)
        generated_at: Unix timestamp ของเวลาสร้างรายงาน

    Returns:
        ข้อความรายงานที่เขียนลงไฟล์
    """
    content = build_report(points, log_entries, generated_at)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    return content


def render_point_card(point: models.ChargePoint) -> List[str]:
    """สร้างบรรทัดแสดงรายละเอียดหัวชาร์จ 1 หัว (สำหรับเมนู View 4.1)

    ใช้ key ภาษาอังกฤษตามชื่อฟิลด์ในสเปก เพื่อให้ตรวจสอบกับไฟล์ไบนารีได้ง่าย
    """
    return [
        f"point_id       : {point.point_id}",
        f"station_code   : {point.station_code}",
        f"location       : {point.location}",
        f"plug_type      : {point.plug_type}",
        f"power_kw       : {point.power_kw:.1f}",
        f"price_per_kwh  : {point.price_per_kwh:.2f} THB/kWh",
        f"status         : {point.status_text} ({point.status})",
        f"is_booked      : {point.booked_text} ({point.is_booked})",
        f"is_deleted     : {point.is_deleted}",
        f"created_at     : {format_timestamp(point.created_at)}",
        f"updated_at     : {format_timestamp(point.updated_at)}",
    ]

    for point in alive:
        if point.plug_type in counts:
            counts[point.plug_type] += 1
    return counts
