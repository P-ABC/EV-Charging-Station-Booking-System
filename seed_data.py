"""seed_data.py — สร้างชุดข้อมูลตัวอย่างสำหรับทดสอบระบบ

เป้าหมายของข้อมูลตัวอย่าง (ตามข้อกำหนดของงาน)
-----------------------------------------------
* มี record **มากกว่า 50 record** เพื่อทดสอบการอ่าน/เขียนไฟล์ขนาดใหญ่
* record ชุดแรกใช้ point_id **1001-1010** ซึ่งเป็นชุดเดียวกับที่แสดงใน
  ตัวอย่าง report.txt เพื่อให้ตรวจสอบยอดสรุปได้ตรงกัน:
      - Active Points    = 9   (มี 1 record ที่ถูก soft delete)
      - Deleted Points   = 1
      - Currently Booked = 4
      - Available Now    = 5   (= Active 9 - Booked 4)
      - ราคา Min 6.00 / Max 9.00 / Avg 7.36  (เฉลี่ยของ 9 record ที่ Active)
* มีขอบเขต (edge cases) ครบตามที่กำหนด:
      - location ยาวเกิน 30 ไบต์ (ภาษาไทย) -> ต้องถูกตัดอย่างปลอดภัย
      - ชื่อ/station_code ซ้ำกัน (สถานีเดียวกันมีหลายหัว)
      - record ที่ถูกลบแล้ว (is_deleted=1)
      - ราคา/กำลังไฟขอบเขต (ค่าต่ำสุด/สูงสุด, ค่าทศนิยมละเอียด)
      - หัวชาร์จที่ถูกจองอยู่ (is_booked=1) และหัวที่ปิดซ่อมบำรุง (status=0)

หมายเหตุเรื่องความยาว location
------------------------------
ฟิลด์ location ในสเปกกำหนดไว้ 30 ไบต์ (30s) แต่ข้อความไทย 1 ตัวอักษร = 3 ไบต์
เช่น "สยามพารากอน ชั้น B1" ยาว 49 ไบต์ จึง **เกินฟิลด์** ตามกติกาของโจทย์
ระบบจึงตัดให้พอดี 30 ไบต์ตอนบันทึก (ไม่ตัดกลางอักขระ UTF-8) ซึ่งถือเป็น
ข้อสมมติฐานที่ระบุไว้ใน README.md — ดูรายละเอียดหัวข้อ "ข้อสมมติฐาน"
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence

import index as index_module
import logger as logger_module
import models
import storage as storage_module

# ฐานเวลาสำหรับข้อมูลตัวอย่าง (ให้ผลลัพธ์ที่ทำซ้ำได้ แต่ยังเป็นเวลาที่สมจริง)
BASE_TIMESTAMP = 1_789_000_000      # 2026-09-16 ประมาณ 16:26:40 UTC (+07:00 = 23:26)

# ชุดข้อมูลหลัก 10 record ที่รายงานตัวอย่างอ้างอิง (point_id 1001-1010)
#  ราคา 9 record ที่ Active: 6.00, 6.25, 6.75, 7.00, 7.25, 7.50, 8.00, 8.50, 9.00
#  -> Min 6.00 / Max 9.00 / Avg = 66.25 / 9 = 7.3611... -> "7.36" ✔
#  ราคาทุกค่าเป็นเลขที่แทนได้แม่นยำใน float32 จึงไม่มีเศษปัดรบกวนผลรวม
MAIN_POINTS: List[dict] = [
    {"point_id": 1001, "station_code": "EVS-0001", "location": "สยามพารากอน ชั้น B1",
     "plug_type": "Type2", "power_kw": 7.4, "price_per_kwh": 6.00,
     "status": 1, "is_booked": 1},
    {"point_id": 1002, "station_code": "EVS-0002", "location": "เซ็นทรัลเวิลด์ ลาน P2",
     "plug_type": "CCS2", "power_kw": 150.0, "price_per_kwh": 6.25,
     "status": 1, "is_booked": 1},
    {"point_id": 1003, "station_code": "EVS-0003", "location": "ICONSIAM ชั้น G",
     "plug_type": "CCS2", "power_kw": 120.0, "price_per_kwh": 6.75,
     "status": 1, "is_booked": 1},
    {"point_id": 1004, "station_code": "EVS-0004", "location": "เมกาบางนา โซน A",
     "plug_type": "CHAdeMO", "power_kw": 50.0, "price_per_kwh": 7.00,
     "status": 1, "is_booked": 1},
    # 1005 เป็นหัวที่ว่าง (Booked รวม 4 หัว: 1001-1004) แต่ราคายัง Active
    {"point_id": 1005, "station_code": "EVS-0005", "location": "เซ็นทรัลพระราม 9",
     "plug_type": "Type2", "power_kw": 22.0, "price_per_kwh": 7.25,
     "status": 1, "is_booked": 0},
    {"point_id": 1006, "station_code": "EVS-0006", "location": "บิกกิ้ง สาทร ชั้น 2",
     "plug_type": "CHAdeMO", "power_kw": 60.0, "price_per_kwh": 7.50,
     "status": 1, "is_booked": 0},
    {"point_id": 1007, "station_code": "EVS-0007", "location": "ลาดพร้าว ไทยรัฐ 2",
     "plug_type": "GB-T", "power_kw": 60.0, "price_per_kwh": 8.00,
     "status": 1, "is_booked": 0},
    {"point_id": 1008, "station_code": "EVS-0008", "location": "เอเชีย เซนเทอร์ ชั้น G",
     "plug_type": "CCS2", "power_kw": 180.0, "price_per_kwh": 8.50,
     "status": 1, "is_booked": 0},
    {"point_id": 1009, "station_code": "EVS-0009", "location": "เซ็นทรัล พหมโพธิยา",
     "plug_type": "Type2", "power_kw": 11.0, "price_per_kwh": 9.00,
     "status": 1, "is_booked": 0},
    # 1010 ถูก soft delete -> Active = 9, Deleted = 1 ✔ (ราคาจึงไม่ถูกนับในสถิติ)
    {"point_id": 1010, "station_code": "EVS-0010", "location": "พารากอน โครงการเก่า",
     "plug_type": "Type2", "power_kw": 7.0, "price_per_kwh": 9.00,
     "status": 0, "is_booked": 0, "is_deleted": 1},
]
# ตำแหน่งที่ใช้สร้างข้อมูลจำนวนมาก (สลับกันเพื่อให้ station_code ซ้ำกันเกิดขึ้นจริง)
_BULK_LOCATIONS = [
    "สยามพารากอน ชั้น B1",
    "เซ็นทรัลเวิลด์ ลาน P2",
    "ICONSIAM ชั้น G",
    "เมกาบางนา โซน A",
    "เซ็นทรัลพระราม 9",
    "บิกกิ้ง สาทร ชั้น 2",
    "ลาดพร้าว ไทยรัฐ 2",
    "เอเชีย เซนเทอร์ ชั้น G",
    "เซ็นทรัล พหมโพธิยา",
    "พารากอน โครงการเก่า",
    # ขอบเขต: ยาวเกิน 30 ไบต์ (ภาษาไทย 3 ไบต์/ตัว) -> ระบบจะตัดให้พอดี
    "สถานีชาร์จไฟฟ้าสยามพารากอนชั้นใต้ดินโครงการใหม่และลานจอดรถ",
]

_BULK_PLUGS = ["Type2", "CCS2", "CHAdeMO", "GB-T"]

# กำลังไฟ (kW) และราคา (THB/kWh) ที่ใช้สุ่มแบบมีการหมุนเวียน
# รวมค่าขอบเขต: ต่ำสุด 3.7 kW / 3.50 THB และสูงสุด 350 kW / 15.50 THB
_BULK_POWERS = [3.7, 7.4, 11.0, 22.0, 50.0, 60.0, 120.0, 150.0, 180.0, 350.0]
_BULK_PRICES = [3.50, 4.25, 5.00, 6.00, 6.50, 7.00, 7.50, 8.00, 9.50, 15.50]


def build_bulk_points(count: int = 45, start_id: int = 2001) -> List[dict]:
    """สร้าง record ตัวอย่างจำนวนมากเพื่อทดสอบระบบ

    ข้อมูลที่สร้างมีความหลากหลายโดยตั้งใจ เพื่อให้ครอบคลุมขอบเขตที่กำหนด:
        * station_code และ location ซ้ำกัน (สถานีเดียวกันมีหลายหัวชาร์จ)
        * location ที่ยาวเกิน 30 ไบต์ (หมุนไปตัวที่ index 10 เป็นระยะ)
        * status=0 (ปิดซ่อมบำรุง) และ is_booked=1 (ถูกจองอยู่)
        * ราคา/กำลังไฟขอบเขต (ต่ำสุดและสูงสุดในตารางด้านบน)
        * บาง record ถูก soft delete ไว้ (เพื่อทดสอบ free-list)

    Args:
        count: จำนวน record ที่ต้องการ
        start_id: point_id แรก

    Returns:
        รายการ dict ที่นำไปแปลงเป็น :class:`models.ChargePoint` ได้
    """
    points: List[dict] = []
    for offset in range(count):
        points.append({
            "point_id": start_id + offset,
            "station_code": f"EVS-{((offset % 25) + 1):04d}",   # ทำให้เกิดรหัสซ้ำ
            "location": _BULK_LOCATIONS[offset % len(_BULK_LOCATIONS)],
            "plug_type": _BULK_PLUGS[offset % len(_BULK_PLUGS)],
            "power_kw": _BULK_POWERS[offset % len(_BULK_POWERS)],
            "price_per_kwh": _BULK_PRICES[offset % len(_BULK_PRICES)],
            "status": 0 if offset % 13 == 12 else 1,              # ปิดซ่อมบำรุงเป็นระยะ
            "is_booked": 1 if offset % 4 == 1 else 0,             # ถูกจองเป็นระยะ
            # ทุก 17 record ให้ 1 record ถูก soft delete (ไม่เป็นหัวที่ถูกจอง)
            "is_deleted": 1 if (offset % 17 == 16 and offset % 4 != 1) else 0,
        })
    return points


def build_all_specs() -> List[dict]:
    """คืนรายการสเปกข้อมูลตัวอย่างทั้งหมด (ชุดหลัก 10 + ชุดจำนวนมาก)

    รวมกันแล้วมากกว่า 50 record ตามข้อกำหนด
    """
    return list(MAIN_POINTS) + build_bulk_points()


def specs_to_charge_points(specs: Sequence[dict],
                           base_ts: int = BASE_TIMESTAMP) -> List[models.ChargePoint]:
    """แปลงรายการ dict เป็น :class:`models.ChargePoint`

    created_at/updated_at ถูกเพิ่มขึ้นละ 60 วินาทีต่อ record เพื่อให้ข้อมูล
    created_at/updated_at มีค่าไม่ซ้ำกันทั้งหมด (ตรวจสอบง่ายขึ้น)

    หมายเหตุ: location จะถูกตัดให้พอดี 30 ไบต์ที่นี่เลย (ก่อนบันทึกลงไฟล์)
    เพื่อให้สิ่งที่เห็นในไฟล์ตรงกับสิ่งที่ผ่านการ validate แล้วเสมอ
    """
    points: List[models.ChargePoint] = []
    for offset, spec in enumerate(specs):
        points.append(models.ChargePoint(
            point_id=spec["point_id"],
            station_code=spec["station_code"],
            location=models.truncate_display(spec["location"],
                                             models.LOCATION_MAX_BYTES),
            plug_type=spec["plug_type"],
            power_kw=float(spec["power_kw"]),
            price_per_kwh=float(spec["price_per_kwh"]),
            status=int(spec.get("status", 1)),
            is_booked=int(spec.get("is_booked", 0)),
            is_deleted=int(spec.get("is_deleted", 0)),
            created_at=base_ts + offset * 60,
            updated_at=base_ts + offset * 60,
        ))
    return points


def build_full_locations() -> Dict[int, str]:
    """คืน dict {point_id: ชื่อสถานที่ตั้งแบบเต็ม (ยังไม่ถูกตัด)} ของข้อมูลตัวอย่าง

    record ไบนารีเก็บ location ได้เพียง 30 ไบต์ จึงเก็บ "ชื่อเต็ม" ไว้ใน
    :mod:`locations.txt` เพื่อให้รายงานแสดงชื่อได้ครบ ไม่ถูกตัดกลางคัน

    Returns:
        dict ที่ใช้บันทึกลง locations.txt ตอนสร้างข้อมูลตัวอย่าง
    """
    return {int(spec["point_id"]): spec["location"]
            for spec in build_all_specs()}


# ชื่อสถานที่ตั้งแบบเต็ม (ก่อนถูกตัด) — ใช้บันทึกลง locations.txt
full_locations = build_full_locations()


def seed(data_dir: str, force: bool = False,
         printer=print) -> dict:
    """สร้างข้อมูลตัวอย่างลงทั้ง 3 ไฟล์ไบนารีอย่างสอดคล้องกัน

    ขั้นตอน:
        1. ถ้า ``force`` เป็น True จะลบไฟล์เดิมทิ้งทั้งหมดก่อน (ใช้ตอนอยากเริ่มใหม่)
        2. เขียน record ทั้งหมดลง charge_points.dat
        3. เขียน audit log 1 record ต่อ 1 หัว (op=ADD) พร้อมกรอก index.dat
        4. เขียนชื่อสถานที่ตั้งแบบเต็มลง locations.txt
           (record ไบนารีเก็บได้ 30 ไบต์ จึงเก็บชื่อเต็มไว้ให้รายงานแสดง)
        5. สร้างดัชนีใหม่จาก log อีกครั้งด้วย :func:`rebuild_index` เพื่อยืนยันผล

    Args:
        data_dir: โฟลเดอร์ที่เก็บไฟล์ข้อมูล
        force: True = ลบข้อมูลเดิมก่อนสร้างใหม่
        printer: ฟังก์ชันพิมพ์ข้อความ (ถ้าเป็น None จะไม่พิมพ์)

    Returns:
        dict สรุปผล {"records": int, "log_entries": int, "index_entries": int}
    """
    os.makedirs(data_dir, exist_ok=True)
    data_path = os.path.join(data_dir, models.DATA_FILE_NAME)
    log_path = os.path.join(data_dir, models.LOG_FILE_NAME)
    index_path = os.path.join(data_dir, models.INDEX_FILE_NAME)
    location_path = os.path.join(data_dir, models.LOCATION_FILE_NAME)

    if force:
        for path in (data_path, log_path, index_path, location_path):
            if os.path.exists(path):
                os.remove(path)
                if printer:
                    printer(f"ลบไฟล์เดิม: {os.path.basename(path)}")

    store = storage_module.ChargePointStore(data_path)
    audit = logger_module.AuditLog(log_path)
    point_index = index_module.PointIndex(index_path)
    locations = storage_module.LocationStore(location_path)

    points = specs_to_charge_points(build_all_specs())
    for point in points:
        store.allocate_slot(point)
        seq = audit.append(point.point_id, models.OP_ADD, point)
        point_index.update(point.point_id, seq)
        # เก็บชื่อสถานที่ตั้ง "แบบเต็ม" (ก่อนถูกตัด) สำหรับแสดงในรายงาน
        locations.set(point.point_id, full_locations.get(point.point_id)
                      or point.location)

    # ยืนยันด้วยการสร้างดัชนีใหม่จาก log (ทดสอบว่า rebuild_index ให้ผลตรงกัน)
    rebuild_index(log_path, index_path)

    if printer:
        printer(f"สร้างข้อมูลตัวอย่างเรียบร้อย: {len(points)} record")
        printer(f"  - {models.DATA_FILE_NAME:<20} {store.file_size()} ไบต์ "
                f"({store.count_records()} records)")
        printer(f"  - {models.LOG_FILE_NAME:<20} "
                f"{os.path.getsize(log_path)} ไบต์ ({audit.count()} entries)")
        printer(f"  - {models.INDEX_FILE_NAME:<20} "
                f"{os.path.getsize(index_path)} ไบต์ ({point_index.count()} entries)")
        printer(f"  - {models.LOCATION_FILE_NAME:<20} "
                f"{locations.count()} ชื่อสถานที่ (ข้อความ UTF-8)")
    return {
        "records": store.count_records(),
        "log_entries": audit.count(),
        "index_entries": point_index.count(),
        "locations": locations.count(),
    }


def rebuild_index(log_path: str, index_path: str) -> int:
    """สร้าง index.dat ใหม่จาก charge_points.log (ฟังก์ชันระดับโมดูล)

    ใช้เมื่อ index เสียหาย/หาย หรือไม่ตรงกับ log — เป็นคำสั่งซ่อมแซมหลัก

    Args:
        log_path: พาธไฟล์ log
        index_path: พาธไฟล์ index

    Returns:
        จำนวน point_id ที่ถูกใส่ลงดัชนีใหม่
    """
    audit = logger_module.AuditLog(log_path)
    point_index = index_module.PointIndex(index_path)
    return point_index.rebuild(audit.read_all())

# ---------------------------------------------------------------------------
# หมายเหตุเรื่อง "เมนูชุดเดียว" (เกณฑ์ข้อ 5 ของการตรวจงาน)
# ---------------------------------------------------------------------------
# โมดูลนี้เป็นเพียง "โมดูลช่วย" (helper module) จึง **ไม่มีจุดเริ่มโปรแกรม**
# ของตัวเอง เพื่อให้ทุกงาน (รวมถึงการสร้างข้อมูลตัวอย่าง) ต้องทำผ่าน
# เมนูชุดเดียวของ main.py เท่านั้น ไม่มีการรันโปรแกรมแยกอีกตัวหนึ่ง
#
# วิธีเรียกใช้งาน:
#   - จากเมนู:  main.py > 6) Tools > 1) โหลดข้อมูลตัวอย่าง
#   - จากบรรทัดคำสั่งของ main.py:  python main.py --seed

