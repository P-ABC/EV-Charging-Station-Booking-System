"""logger.py — audit log แบบ append-only (charge_points.log)

ไฟล์ log เก็บ 1 ระเบียก (24 ไบต์) ต่อ 1 เหตุการณ์ ทุกครั้งที่ Add/Update/Delete/View
เพื่อให้ตรวจสอบย้อนหลังได้ โดยอ้างอิงตำแหน่งได้จาก "ลำดับ" (log_seq) ซึ่งเริ่มที่ 0

การคำนวณ offset:  offset = log_seq * LOG_RECORD_SIZE (24 ไบต์)
จึงไล่อ่านประวัติทั้งหมดไม่ต้องเปิดอ่านทั้งไฟล์ และอ่านระเบียกเดียวได้ด้วย seek ตรง ๆ
"""

from __future__ import annotations

import os
from typing import List, Optional

import models


class AuditLog:
    """คลาสจัดการไฟล์ charge_points.log (append-only)

    Attributes:
        path: พาธของไฟล์ log
    """

    def __init__(self, path: str) -> None:
        self.path = path
        if not os.path.exists(self.path):
            with open(self.path, "a+b"):
                pass

    # ------------------------------------------------------------------
    # ความถูกต้องของไฟล์
    # ------------------------------------------------------------------
    def integrity_check(self) -> tuple[bool, int]:
        """ตรวจว่าขนาดไฟล์ log หารด้วย 24 ลงตัวหรือไม่

        Returns:
            (is_valid, remainder_bytes)
        """
        size = os.path.getsize(self.path)
        remainder = size % models.LOG_RECORD_SIZE
        return (remainder == 0, remainder)

    def truncate_incomplete(self) -> int:
        """ตัดระเบียก log ที่ไม่ครบ 24 ไบต์ทิ้ง (ไฟล์ถูกตัดกลางระเบียน)

        Returns:
            จำนวนไบต์ที่ถูกตัดทิ้ง
        """
        _valid, remainder = self.integrity_check()
        if remainder == 0:
            return 0
        keep = os.path.getsize(self.path) - remainder
        with open(self.path, "r+b") as fh:
            fh.truncate(keep)
            fh.flush()
            os.fsync(fh.fileno())
        return remainder

    # ------------------------------------------------------------------
    # นับ / อ่าน
    # ------------------------------------------------------------------
    def count(self) -> int:
        """จำนวนเหตุการณ์ทั้งหมดใน log (คือจำนวนลำดับถัดไป)"""
        return os.path.getsize(self.path) // models.LOG_RECORD_SIZE

    def read_at(self, seq: int) -> Optional[models.LogEntry]:
        """อ่านเหตุการณ์ที่ลำดับ seq (ใช้ seek ไปที่ seq * 24 ได้เลย)

        Returns:
            :class:`models.LogEntry` หรือ None เมื่อ seq อยู่นอกขอบเขต
        """
        if seq < 0 or seq >= self.count():
            return None
        with open(self.path, "rb") as fh:
            fh.seek(seq * models.LOG_RECORD_SIZE)
            raw = fh.read(models.LOG_RECORD_SIZE)
        if len(raw) < models.LOG_RECORD_SIZE:
            return None
        return models.unpack_log_entry(raw)

    def read_all(self) -> List[models.LogEntry]:
        """อ่านเหตุการณ์ทั้งหมดใน log เรียงจากเก่าไปใหม่"""
        entries: List[models.LogEntry] = []
        with open(self.path, "rb") as fh:
            while True:
                raw = fh.read(models.LOG_RECORD_SIZE)
                if len(raw) < models.LOG_RECORD_SIZE:
                    break
                entries.append(models.unpack_log_entry(raw))
        return entries

    def read_recent(self, limit: int = 5) -> List[models.LogEntry]:
        """อ่านเหตุการณ์ล่าสุด limit รายการ เรียงจากใหม่ไปเก่า (ใช้ในรายงาน)

        อ่านแบบ seek จากท้ายไฟล์ จึงไม่ต้องไล่อ่านทั้งไฟล์ (ยิ่ง log โตยิ่งเร็ว)
        """
        total = self.count()
        start = max(0, total - limit)
        with open(self.path, "rb") as fh:
            fh.seek(start * models.LOG_RECORD_SIZE)
            data = fh.read()
        entries = [
            models.unpack_log_entry(data[i:i + models.LOG_RECORD_SIZE])
            for i in range(0, len(data) - len(data) % models.LOG_RECORD_SIZE,
                           models.LOG_RECORD_SIZE)
        ]
        return list(reversed(entries))

    def read_for_point(self, point_id: int, from_seq: Optional[int] = None,
                       limit: int = 50) -> List[models.LogEntry]:
        """อ่านเหตุการณ์ของ point_id หนึ่ง ๆ เรียงจากใหม่ไปเก่า

        ใช้ร่วมกับ index.dat: ส่ง ``from_seq`` = log_seq ล่าสุดจากดัชนีเข้ามา
        แล้วจึงไล่ย้อนเท่านั้น ไม่ต้องอ่าน log ทั้งไฟล์

        Args:
            point_id: รหัสหัวชาร์จ
            from_seq: ลำดับเริ่มต้น (ปกติคือค่าจาก index.dat)
                ถ้าเป็น None จะเริ่มจากเหตุการณ์ล่าสุดของ log
            limit: จำนวนเหตุการณ์สูงสุดที่คืนค่า
        """
        total = self.count()
        start = (total - 1) if from_seq is None else min(from_seq, total - 1)
        found: List[models.LogEntry] = []
        for seq in range(start, -1, -1):
            entry = self.read_at(seq)
            if entry is not None and entry.point_id == point_id:
                found.append(entry)
                if len(found) >= limit:
                    break
        return found

    # ------------------------------------------------------------------
    # เขียน (append-only)
    # ------------------------------------------------------------------
    def append(self, point_id: int, op_code: int, point: models.ChargePoint) -> int:
        """บันทึกเหตุการณ์ 1 รายการต่อท้ายไฟล์ (mode a+b)

        ค่าที่บันทึกคือ "สถานะหลังเหตุการณ์" (status_after, is_booked_after,
        price_after_thb) ตามสเปกที่กำหนด

        Returns:
            log_seq ของเหตุการณ์ที่เพิ่งเขียน (เริ่มที่ 0)
        """
        entry = models.LogEntry(
            ts=models.now_timestamp(),
            op_code=op_code,
            point_id=point_id,
            status_after=point.status,
            is_booked_after=point.is_booked,
            price_after_thb=point.price_per_kwh,
        )
        with open(self.path, "a+b") as fh:
            fh.seek(0, os.SEEK_END)
            seq = fh.tell() // models.LOG_RECORD_SIZE
            fh.write(models.pack_log_entry(entry))
            fh.flush()
            os.fsync(fh.fileno())
        return seq
