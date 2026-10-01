"""models.py — นิยามโครงสร้างระเบียนแบบไบนารี (struct) ของโปรเจกต์ EV Charging Station Booking System

โมดูลนี้เป็น "หัวใจ" ของสเปกไฟล์ ทุกไฟล์ไบนารีจะถูก pack/unpack ด้วย ``struct.Struct``
ที่คอมไพล์ไว้ล่วงหน้า (pre-compiled) และกำหนด endianness เป็น Little-Endian (``<``)
ทั้งหมด เพื่อให้ผลลัพธ์เหมือนกันทุกเครื่อง

สเปกทั้ง 3 ไฟล์ (ห้ามเปลี่ยนชื่อฟิลด์ ลำดับ หรือขนาด)
---------------------------------------------------
1) charge_points.dat — struct format ``<l10s30s10sfflllll`` ขนาด 82 ไบต์/ระเบียน
   (ในเอกสารโจทย์เขียนไว้ว่า ``<l10s30s10sffl lll l`` ซึ่งมีช่องว่างคั่นไว้
    เพื่อให้อ่านง่ายเท่านั้น เมื่อเขียนจริงต้องไม่มีช่องว่าง และนับฟิลด์ได้
    l,10s,30s,10s,f,f,l,l,l,l,l = 11 ฟิลด์ ตรงกับตารางด้านล่าง)

2) charge_points.log — struct format ``<lllllf`` ขนาด 24 ไบต์/ระเบียน
   (ดูคำอธิบายเรื่องลำดับชนิดข้อมูลในส่วน LOG_FORMAT ด้านล่าง)

3) index.dat — struct format ``<ll`` ขนาด 8 ไบต์/ระเบียน (point_id, log_seq)
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from typing import Dict, Tuple

# ---------------------------------------------------------------------------
# ค่าคงที่ระดับแอปพลิเคชัน
# ---------------------------------------------------------------------------
APP_VERSION = "1.0"
BYTE_ORDER = "<"                      # Little-Endian ทุกไฟล์ (บังคับตามสเปก)
BYTE_ORDER_LABEL = "Little-Endian"
ENCODING_LABEL = "UTF-8 (fixed-length)"

DATA_FILE_NAME = "charge_points.dat"
LOG_FILE_NAME = "charge_points.log"
INDEX_FILE_NAME = "index.dat"
REPORT_FILE_NAME = "report.txt"

# กติกาทางธุรกิจที่ใช้ตรวจสอบอินพุต
STATION_CODE_PATTERN = "EVS-NNNN"
PLUG_TYPES: Tuple[str, ...] = ("Type2", "CCS2", "CHAdeMO", "GB-T")
LOCATION_MAX_BYTES = 30               # ขนาดฟิลด์ location ในสเปก (30s)

# รหัสเหตุการณ์สำหรับ audit log
OP_ADD = 1
OP_UPDATE = 2
OP_DELETE = 3
OP_VIEW = 4
OPERATION_NAMES: Dict[int, str] = {
    OP_ADD: "ADD",
    OP_UPDATE: "UPDATE",
    OP_DELETE: "DELETE",
    OP_VIEW: "VIEW",
}


# ---------------------------------------------------------------------------
# struct format + ขนาดระเบียน (ทุกไฟล์กำหนด endianness เป็น Little-Endian)
# ---------------------------------------------------------------------------
# ไฟล์หลัก: point_id, station_code, location, plug_type, power_kw,
#            price_per_kwh, status, is_booked, is_deleted, created_at, updated_at
CHARGE_POINT_FORMAT = "<l10s30s10sfflllll"
CHARGE_POINT_STRUCT = struct.Struct(CHARGE_POINT_FORMAT)
RECORD_SIZE = CHARGE_POINT_STRUCT.size          # ต้องเท่ากับ 82 ไบต์

# audit log: ts, op_code, point_id, status_after, is_booked_after, price_after_thb
#
# *** หมายเหตุสำคัญเรื่องลำดับชนิดข้อมูล (ตามที่โจทย์กำหนดให้อธิบายไว้ในโค้ด) ***
# ในเอกสารเขียน format ไว้เป็น "<llllfl" แต่ "ลำดับฟิลด์จริง" ที่ระบุไว้คือ
#   ts, op_code, point_id, status_after, is_booked_after  -> long (l) ทั้ง 5 ตัวแรก
#   price_after_thb                                     -> float (f) ตัวสุดท้าย
# ดังนั้นรูปแบบที่ถูกต้องตามลำดับฟิลด์จริงคือ "<lllllf" (5 ตัว l แล้วตามด้วย f)
# ซึ่งให้ขนาดเท่ากับ 24 ไบต์ตามสเปก (5*4 + 4 = 24) จึงใช้ "<lllllf"
LOG_FORMAT = "<lllllf"
LOG_STRUCT = struct.Struct(LOG_FORMAT)
LOG_RECORD_SIZE = LOG_STRUCT.size              # ต้องเท่ากับ 24 ไบต์
# ดัชนี: point_id, log_seq (ใช้ค้นประวัติล่าสุดของแต่ละ point_id แบบ O(1))
INDEX_FORMAT = "<ll"
INDEX_STRUCT = struct.Struct(INDEX_FORMAT)
INDEX_RECORD_SIZE = INDEX_STRUCT.size          # ต้องเท่ากับ 8 ไบต์



# ---------------------------------------------------------------------------
# ฟังก์ชันแปลงข้อความ <-> ไบต์แบบความยาวคงที่ (UTF-8 + \x00 padding)
# ---------------------------------------------------------------------------
def encode_text(value: str, size: int) -> bytes:
    """แปลงข้อความเป็นไบต์ความยาวคงที่ (pad ด้วย \\x00)

    ถ้าข้อความยาวเกิน ``size`` ไบต์ จะตัดให้เหลือพอดี โดย "ห้ามตัดกลางอักขระ UTF-8"
    ด้วยการตัดไบต์แล้ว decode กลับแบบ ``errors="ignore"`` (วิธีที่โจทย์กำหนด)
    ทำให้ภาษาไทย (1 ตัวอักษร = 3 ไบต์) ไม่กลายเป็นอักขระเพี้ยน (U+FFFD)

    Args:
        value: ข้อความต้นฉบับ (None ถือว่าเป็นสตริงว่าง)
        size: จำนวนไบต์ที่ต้องการ (ขนาดฟิลด์ตามสเปก)

    Returns:
        bytes ความยาวเท่ากับ ``size`` เสมอ
    """
    raw = ("" if value is None else str(value)).encode("utf-8")
    if len(raw) > size:
        # ตัดไบต์ให้พอดี แล้ว decode กลับแบบ ignore เพื่อทิ้งอักขระที่ถูกตัดครึ่ง
        raw = raw[:size].decode("utf-8", errors="ignore").encode("utf-8")
    return raw.ljust(size, b"\x00")


def decode_text(raw: bytes) -> str:
    """แปลงไบต์กลับเป็นข้อความ โดยตัด \\x00 ท้ายสตริงออก"""
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="ignore").strip()


def text_byte_length(value: str) -> int:
    """คืนความยาวจริงเป็นไบต์ (UTF-8) ของข้อความ ใช้ตรวจว่าเกินขนาดฟิลด์หรือไม่"""
    return len((value or "").encode("utf-8"))


def truncate_display(value: str, size: int) -> str:
    """คืนข้อความที่ถูกตัดตามกติกาเดียวกับ :func:`encode_text` (ใช้แสดงผลก่อนบันทึก)"""
    if text_byte_length(value) <= size:
        return value
    return value.encode("utf-8")[:size].decode("utf-8", errors="ignore")


def now_timestamp() -> int:
    """Unix timestamp ปัจจุบัน (วินาที) สำหรับ created_at / updated_at / ts"""
    return int(time.time())


# ---------------------------------------------------------------------------
# Dataclass ของแต่ละไฟล์
# ---------------------------------------------------------------------------
@dataclass
class ChargePoint:
    """หัวชาร์จ 1 หัว = 1 ระเบียก 82 ไบต์ใน charge_points.dat"""

    point_id: int
    station_code: str
    location: str
    plug_type: str
    power_kw: float
    price_per_kwh: float
    status: int          # 1 = Active, 0 = Inactive (ปิดซ่อมบำรุง)
    is_booked: int       # 1 = มีการจอง/กำลังชาร์จ, 0 = ว่าง
    is_deleted: int      # 1 = ถูกลบ (soft delete), 0 = ปกติ
    created_at: int      # Unix timestamp
    updated_at: int      # Unix timestamp

    # -- สถานะแบบอ่านง่าย --------------------------------------------------
    @property
    def is_active(self) -> bool:
        """True เมื่อสถานะเป็น Active (ไม่สนใจว่าถูกลบหรือไม่)"""
        return self.status == 1

    @property
    def is_available(self) -> bool:
        """True เมื่อ Active, ยังไม่ถูกลบ และยังไม่ถูกจอง (ใช้นับ Available Now)"""
        return self.is_active and not self.is_deleted and self.is_booked == 0

    @property
    def status_text(self) -> str:
        """ข้อความสถานะสำหรับแสดงผล/รายงาน"""
        if self.is_deleted:
            return "Deleted"
        return "Active" if self.is_active else "Inactive"

    @property
    def booked_text(self) -> str:
        """ข้อความสถานะการจองสำหรับแสดงผล/รายงาน"""
        return "Yes" if self.is_booked == 1 else "No"

    # -- pack --------------------------------------------------------------
    def to_bytes(self) -> bytes:
        """แปลงเป็นไบต์ตามสเปก (ความยาวคงที่ 82 ไบต์)

        สตริงทุกฟิลด์ผ่าน :func:`encode_text` เพื่อเติม/ตัดให้พอดีก่อน pack
        """
        return CHARGE_POINT_STRUCT.pack(
            int(self.point_id),
            encode_text(self.station_code, 10),
            encode_text(self.location, 30),
            encode_text(self.plug_type, 10),
            float(self.power_kw),
            float(self.price_per_kwh),
            int(self.status),
            int(self.is_booked),
            int(self.is_deleted),
            int(self.created_at),
            int(self.updated_at),
        )


@dataclass
class LogEntry:
    """เหตุการณ์ 1 รายการใน charge_points.log (append-only, 24 ไบต์)"""

    ts: int
    op_code: int
    point_id: int
    status_after: int
    is_booked_after: int
    price_after_thb: float

    @property
    def op_name(self) -> str:
        """ชื่อเหตุการณ์ ADD/UPDATE/DELETE/VIEW จาก op_code"""
        return OPERATION_NAMES.get(self.op_code, f"OP{self.op_code}")

    @property
    def status_text(self) -> str:
        """สถานะหลังเหตุการณ์ — DELETE แสดง "Deleted" ตามสเปกรายงาน"""
        if self.op_code == OP_DELETE:
            return "Deleted"
        return "Active" if self.status_after == 1 else "Inactive"

    @property
    def booked_text(self) -> str:
        """สถานะการจองหลังเหตุการณ์"""
        return "Yes" if self.is_booked_after == 1 else "No"

    def to_bytes(self) -> bytes:
        """แปลงเป็นไบต์ตามสเปก (ความยาวคงที่ 24 ไบต์)"""
        return LOG_STRUCT.pack(
            int(self.ts),
            int(self.op_code),
            int(self.point_id),
            int(self.status_after),
            int(self.is_booked_after),
            float(self.price_after_thb),
        )


@dataclass
class IndexEntry:
    """ระเบียกดัชนี 1 รายการใน index.dat (8 ไบต์) — point_id -> log_seq"""

    point_id: int
    log_seq: int

    def to_bytes(self) -> bytes:
        """แปลงเป็นไบต์ตามสเปก (ความยาวคงที่ 8 ไบต์)"""
        return INDEX_STRUCT.pack(int(self.point_id), int(self.log_seq))
# ---------------------------------------------------------------------------
# ฟังก์ชันระดับโมดูลสำหรับ pack / unpack (storage.py / index.py / logger.py เรียกใช้)
# ---------------------------------------------------------------------------
def pack_charge_point(point: ChargePoint) -> bytes:
    """pack หัวชาร์จเป็นไบต์ 82 ไบต์"""
    return point.to_bytes()


def unpack_charge_point(data: bytes) -> ChargePoint:
    """unpack ไบต์ 82 ไบต์กลับเป็น :class:`ChargePoint`

    Raises:
        struct.error: เมื่อความยาวข้อมูลไม่พอดีกับขนาดระเบียน
    """
    values = CHARGE_POINT_STRUCT.unpack(data)
    return ChargePoint(
        point_id=values[0],
        station_code=decode_text(values[1]),
        location=decode_text(values[2]),
        plug_type=decode_text(values[3]),
        power_kw=values[4],
        price_per_kwh=values[5],
        status=values[6],
        is_booked=values[7],
        is_deleted=values[8],
        created_at=values[9],
        updated_at=values[10],
    )


def pack_log_entry(entry: LogEntry) -> bytes:
    """pack เหตุการณ์ audit เป็นไบต์ 24 ไบต์"""
    return entry.to_bytes()


def unpack_log_entry(data: bytes) -> LogEntry:
    """unpack ไบต์ 24 ไบต์กลับเป็น :class:`LogEntry`

    Raises:
        struct.error: เมื่อความยาวข้อมูลไม่พอดีกับขนาดระเบียน
    """
    values = LOG_STRUCT.unpack(data)
    return LogEntry(
        ts=values[0],
        op_code=values[1],
        point_id=values[2],
        status_after=values[3],
        is_booked_after=values[4],
        price_after_thb=values[5],
    )


def pack_index_entry(entry: IndexEntry) -> bytes:
    """pack ระเบียกดัชนีเป็นไบต์ 8 ไบต์"""
    return entry.to_bytes()


def unpack_index_entry(data: bytes) -> IndexEntry:
    """unpack ไบต์ 8 ไบต์กลับเป็น :class:`IndexEntry`

    Raises:
        struct.error: เมื่อความยาวข้อมูลไม่พอดีกับขนาดระเบียน
    """
    values = INDEX_STRUCT.unpack(data)
    return IndexEntry(point_id=values[0], log_seq=values[1])


def describe_spec() -> str:
    """คืนข้อความสรุปสเปกระเบียนทั้ง 3 ไฟล์ (ใช้ใน --help / หน้าจอตอนเริ่มโปรแกรม)"""
    return "\n".join([
        f"{DATA_FILE_NAME:<20} format={CHARGE_POINT_FORMAT:<20} size={RECORD_SIZE} bytes",
        "   -> point_id(l,4) station_code(10s,10) location(30s,30) plug_type(10s,10)",
        "      power_kw(f,4) price_per_kwh(f,4) status(l,4) is_booked(l,4)",
        "      is_deleted(l,4) created_at(l,4) updated_at(l,4)",
        f"{LOG_FILE_NAME:<20} format={LOG_FORMAT:<20} size={LOG_RECORD_SIZE} bytes",
        "   -> ts(l,4) op_code(l,4) point_id(l,4) status_after(l,4)"
        " is_booked_after(l,4) price_after_thb(f,4)",
        f"{INDEX_FILE_NAME:<20} format={INDEX_FORMAT:<20} size={INDEX_RECORD_SIZE} bytes",
        "   -> point_id(l,4) log_seq(l,4)",
    ])


def record_to_dict(point: ChargePoint) -> Dict[str, object]:
    """แปลง :class:`ChargePoint` เป็น dict (ใช้ในการแสดงผล/ทดสอบ)"""
    return {
        "point_id": point.point_id,
        "station_code": point.station_code,
        "location": point.location,
        "plug_type": point.plug_type,
        "power_kw": point.power_kw,
        "price_per_kwh": point.price_per_kwh,
        "status": point.status,
        "is_booked": point.is_booked,
        "is_deleted": point.is_deleted,
        "created_at": point.created_at,
        "updated_at": point.updated_at,
    }


__all__ = [
    "APP_VERSION", "BYTE_ORDER", "BYTE_ORDER_LABEL", "ENCODING_LABEL",
    "DATA_FILE_NAME", "LOG_FILE_NAME", "INDEX_FILE_NAME", "REPORT_FILE_NAME",
    "STATION_CODE_PATTERN", "PLUG_TYPES", "LOCATION_MAX_BYTES",
    "OP_ADD", "OP_UPDATE", "OP_DELETE", "OP_VIEW", "OPERATION_NAMES",
    "CHARGE_POINT_FORMAT", "CHARGE_POINT_STRUCT", "RECORD_SIZE",
    "LOG_FORMAT", "LOG_STRUCT", "LOG_RECORD_SIZE",
    "INDEX_FORMAT", "INDEX_STRUCT", "INDEX_RECORD_SIZE",
    "ChargePoint", "LogEntry", "IndexEntry",
    "encode_text", "decode_text", "text_byte_length", "truncate_display",
    "now_timestamp", "pack_charge_point", "unpack_charge_point",
    "pack_log_entry", "unpack_log_entry",
    "pack_index_entry", "unpack_index_entry",
    "verify_record_sizes", "describe_spec", "record_to_dict",
]



def verify_record_sizes() -> None:
    """ตรวจสอบว่าขนาดระเบียนตรงกับสเปก (เรียกครั้งเดียวตอนเริ่มโปรแกรม)

    Raises:
        RuntimeError: เมื่อขนาดระเบียนไม่ตรงกับที่กำหนดไว้ในสเปก
    """
    expected = {
        DATA_FILE_NAME: (RECORD_SIZE, 82),
        LOG_FILE_NAME: (LOG_RECORD_SIZE, 24),
        INDEX_FILE_NAME: (INDEX_RECORD_SIZE, 8),
    }
    for file_name, (actual, spec) in expected.items():
        if actual != spec:
            raise RuntimeError(
                f"ขนาดระเบียนของ {file_name} ไม่ตรงสเปก: "
                f"ได้ {actual} ไบต์, ต้องเป็น {spec} ไบต์"
            )
