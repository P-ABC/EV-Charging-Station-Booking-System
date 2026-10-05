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

# ความกว้างสูงสุดของตารางในรายงาน (จำนวนช่อง)
# ต้องไม่เกินความกว้างหน้าจอที่ใช้เปิดไฟล์ทั่วไป มิฉะนั้นโปรแกรมจะ
# ตัดบรรทัด (wrap) แล้วเส้น "|" ที่ปลายบรรทัดจะตกไปบรรทัดถัดไป
# ทำให้เส้นแนวตั้งของตารางดูเหมือนไม่ตรงกัน
DEFAULT_MAX_TABLE_WIDTH = 96
MIN_COLUMN_WIDTH = 6          # ความกว้างขั้นต่ำของคอลัมน์ที่ยอมให้แคบ

# ---------------------------------------------------------------------------
# 0) โหมดการวัดความกว้าง (เลือกได้ 2 แบบ เพื่อให้ตารางตรงในทุกโปรแกรมเปิดไฟล์)
# ---------------------------------------------------------------------------
# ปัญหาที่พบ
# ------------
# สระ/วรรณยุกต์ไทย (ั ิ ี ื ุ ู ็ ่ ้ ์) เป็น "อักขระประสม" ที่ Unicode นับเป็น
# 1 ตัวอักษร แต่กินพื้นที่บนจอ **0 ช่อง** ดังนั้นบรรทัดเดียวกันจะมี
# "จำนวนตัวอักษร" กับ "ความกว้างจริง" ไม่เท่ากัน เช่น 149 ถึง 157 ตัวอักษร
#
# ผลที่ตามมา: ถ้าโปรแกรมที่เปิดไฟล์นับตำแหน่งเส้น "|" จาก "จำนวนตัวอักษร"
# (เช่น โปรแกรมที่ไม่รองรับการจัดวางสระไทย หรือไม่มีฟอนต์ไทย) เส้นแนวตั้ง
# ของตารางจะเบี้ยวไม่ตรงกัน
#
# การแก้ไข
# ---------
# จึงเพิ่ม 2 โหมด ให้ผู้ใช้เลือกตามโปรแกรมที่เปิดดูรายงาน:
#
#   * smart (ค่าเริ่มต้น) — วัดด้วย display_width (นับสระไทยเป็น 0 ช่อง)
#     ตารางจะตรงใน Terminal และโปรแกรมที่จัดวางสระไทยได้ถูกต้อง
#     (เช่น Windows Terminal, VS Code, Notepad รุ่นใหม่)
#
#   * simple — นับทุกตัวอักษรเป็น 1 ช่อง (len)
#     ตารางจะตรงในโปรแกรมที่ไม่จัดวางสระไทยหรือไม่มีฟอนต์ไทย
#
# ทั้งสองโหมดผลิตผลได้ถูกต้อง เพียงแต่วัดความกว้างคนละแบบ
_SMART_WIDTH = True


def set_alignment_mode(smart: bool = True) -> None:
    """เลือกวิธีวัดความกว้างของตาราง

    Args:
        smart: True = วัดด้วย display_width (นับสระ/วรรณยุกต์ไทยเป็น 0 ช่อง)
            False = นับทุกตัวอักษรเป็น 1 ช่อง (เหมาะกับโปรแกรมที่ไม่จัดวางสระไทย)
    """
    global _SMART_WIDTH
    _SMART_WIDTH = bool(smart)


def alignment_mode_name() -> str:
    """คืนชื่อโหมดปัจจุบันเป็นข้อความ ("smart" หรือ "simple")"""
    return "smart" if _SMART_WIDTH else "simple"


def measure(text: str) -> int:
    """วัดความกว้างของข้อความตามโหมดที่เลือกไว้ปัจจุบัน

    Args:
        text: ข้อความที่จะวัด

    Returns:
        ความกว้างเป็นจำนวนช่องตามโหมดปัจจุบัน
    """
    if _SMART_WIDTH:
        return display_width(text)
    return len(text or "")


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
    padding = max(0, width - measure(text))
    if align == "right":
        return " " * padding + text
    return text + " " * padding


def truncate_to_width(text: str, width: int) -> str:
    """ตัดข้อความให้พอดีความกว้างเป้าหมาย (ไม่ตัดกลางอักขระประสม)

    ใช้กับข้อความภาษาไทยยาว ๆ ในตาราง เพื่อไม่ให้เส้นขอบตารางเบี้ยว
    """
    if measure(text) <= width:
        return text
    ellipsis = "..."                      # จุดไข่ปลา ใช้พื้นที่ 3 ช่อง
    result = ""
    current = 0
    budget = width - measure(ellipsis)
    for char in text:
        char_width = 1 if not _SMART_WIDTH else _char_width(char)
        if current + char_width > budget:
            break
        result += char
        current += char_width
    return result + ellipsis

# ---------------------------------------------------------------------------
# 2) การเรนเดอร์ตาราง
# ---------------------------------------------------------------------------
def _fit_column_widths(widths: List[int], max_width: int,
                       floors: Optional[Sequence[int]] = None) -> List[int]:
    """ลดความกว้างคอลัมน์ที่กว้างที่สุดลงจนพอดีกับความกว้างที่กำหนด

    เหตุผลที่ต้องทำ
    --------------
    ตารางที่กว้างเกินกว่าความกว้างหน้าจอ (มักเกิน 100 ช่อง) จะถูกโปรแกรม
    ที่เปิดไฟล์ตัดบรรทัด (wrap) ทำให้เส้น "|" ที่อยู่ปลายบรรทัด
    ตกไปบรรทัดถัดไป เส้นแนวตั้งจึงดูเหมือนไม่ตรงกัน

    กติกาการลดความกว้าง
    ------------------
    * ลดทีละ 1 ช่องจากคอลัมน์ที่กว้างที่สุดเสมอ เพื่อให้ความกว้างสมดุลกัน
    * **ห้ามลดให้ต่ำกว่าความกว้างหัวคอลัมน์** เพราะหัวที่ถูกตัดกลายเป็น
      "Struct f..." ซึ่งอ่านไม่รู้เรื่อง ถ้าลดไม่ได้จริงจะปล่อยให้ตาราง
      กว้างเกินไปเล็กน้อยดีกว่าทำให้ข้อมูลสำคัญหาย

    Args:
        widths: ความกว้างธรรมชาติของแต่ละคอลัมน์
        max_width: ความกว้างรวมสูงสุดที่ยอมรับ (รวมเส้นขอบและช่องว่าง)
        floors: ความกว้างขั้นต่ำของแต่ละคอลัมน์ (ปกติคือความกว้างหัวคอลัมน์)

    Returns:
        รายการความกว้างใหม่ที่รวมกันไม่เกิน max_width (ถ้าเป็นไปได้)
    """
    widths = list(widths)
    if not max_width or not widths:
        return widths
    if floors is None:
        floors = [MIN_COLUMN_WIDTH] * len(widths)
    # หักส่วนที่ใช้ไปกับช่องว่างรอบเซลล์ (2 ต่อคอลัมน์) และเส้นขอบ (n+1 ตัว)
    limit = max_width - (len(widths) * 2 + len(widths) + 1)
    while sum(widths) > limit:
        # เลือกคอลัมน์ที่กว้างที่สุดและยังเหลือที่จะลดได้
        candidates = [index for index in range(len(widths))
                      if widths[index] > floors[index]]
        if not candidates:
            break                      # ลดต่ำกว่าหัวคอลัมน์ไม่ได้แล้ว
        widest = max(candidates, key=lambda index: widths[index])
        widths[widest] -= 1
    return widths


def render_table(headers: Sequence[str], rows: Sequence[Sequence[str]],
                 aligns: Optional[Sequence[str]] = None,
                 max_width: Optional[int] = DEFAULT_MAX_TABLE_WIDTH
                 ) -> List[str]:
    """สร้างบรรทัดตาราง (รวมเส้นขอบแบบ +----+ และ |) ตามความกว้างเนื้อหาจริง

    ความกว้างคอลัมน์คำนวณจาก display_width จึงรองรับภาษาไทยที่มีสระ/วรรณยุกต์
    โดยไม่ทำให้เส้นขอบตารางเบี้ยว และถูกจำกัดไม่เกิน ``max_width``
    เพื่อไม่ให้ตารางกว้างจนโปรแกรมที่เปิดไฟล์ต้องตัดบรรทัด
    (ซึ่งจะทำให้เส้นแนวตั้งดูเหมือนไม่ตรง)

    Args:
        headers: หัวคอลัมน์
        rows: แต่ละแถวเป็น sequence ของข้อความ
        aligns: การจัดตำแหน่งของแต่ละคอลัมน์ ("left"/"right") ถ้าไม่ส่งค่า
            จะจัดตำแหน่งตามประเภทของหัวคอลัมน์อัตโนมัติ (ตัวเลข -> right)
        max_width: ความกว้างรวมสูงสุดที่ยอมรับ (None = ไม่จำกัด)

    Returns:
        รายการบรรทัดของตาราง (ยังไม่รวม \n)
    """
    if aligns is None:
        aligns = ["right" if _looks_numeric(header) else "left"
                  for header in headers]

    # ความกว้างของแต่ละคอลัมน์ = ความกว้างหัวคอลัมน์ที่กว้างที่สุด
    widths = [measure(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], measure(str(cell)))
    # จำกัดความกว้างรวมไม่ให้เกินความกว้างหน้าจอ
    # โดยห้ามลดต่ำกว่าความกว้างหัวคอลัมน์ (กันหัวตารางถูกตัดจนอ่านไม่ออก)
    header_widths = [measure(header) for header in headers]
    widths = _fit_column_widths(widths, max_width, header_widths)

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
        * Total Points   = จำนวน record ทั้งหมดที่อ่านได้ (รวมที่ถูกลบแล้ว)
        * Active Points  = จำนวนที่ is_deleted=0 และ status=1
        * Deleted Points = จำนวนที่ is_deleted=1
        * Booked         = จำนวนที่ is_deleted=0 และ is_booked=1
        * Available Now  = จำนวนที่ is_deleted=0 และ status=1 และ is_booked=0
        * Free Slots     = จำนวน record ที่ is_deleted=1 (ช่องว่างที่นำกลับมาใช้ได้)
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
    """คำนวณราคาต่ำสุด/สูงสุด/เฉลี่ย (นับเฉพาะ record ที่ยังไม่ถูกลบและ Active)

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
    """นับจำนวนหัวชาร์จแยกตามประเภทหัว (นับเฉพาะ record ที่ยังไม่ถูกลบและ Active)

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
        points: record หัวชาร์จทั้งหมด (รวมที่ถูก soft delete แล้ว)
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
        points: record หัวชาร์จทั้งหมด (รวมที่ถูก soft delete แล้ว)
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
