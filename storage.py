"""storage.py — ชั้น I/O ระดับต่ำของไฟล์หลัก charge_points.dat

หน้าที่ของโมดูลนี้
----------------
* เปิด/อ่าน/เขียนระเบียกแบบ fixed-length (82 ไบต์) ด้วย ``seek`` + ``read``/``write``
* เปิดไฟล์ด้วย mode ``r+b`` / ``a+b`` และใช้ context manager เสมอ (บังคับตามข้อกำหนด)
* ใช้ ``struct.Struct`` ที่คอมไพล์ไว้แล้วจาก :mod:`models` (ไม่ pack ซ้ำในลูป)
* ตรวจความถูกต้องของไฟล์ (ขนาดไม่หาร RECORD_SIZE ลงตัว) และตัดส่วนเกินทิ้ง
* จัดการ free-list (ระเบียก is_deleted=1) เพื่อนำช่องว่างกลับมาใช้ซ้ำ

หมายเหตุเรื่อง "ช่องว่าง" (free-list)
------------------------------------
ทุกครั้งที่ Delete จะเป็น *soft delete* (ตั้ง is_deleted=1) ไม่ลบไบต์ออกจริง เพราะ
ต้องคงลำดับระเบียนให้คงที่ (offset ของทุก head ต้องนิ่ง เพื่อให้ index.dat และ
ตำแหน่งใน log ยังอ้างอิงได้ถูกต้อง) ระเบียกที่ is_deleted=1 จึงกลายเป็น "ช่องว่าง"
ที่นำกลับมาใช้ซ้ำได้ โดยโมดูลนี้สแกนหาและเก็บเป็น list ของ slot index
(เทียบเท่ากับ offset = slot * RECORD_SIZE) ไว้ตั้งแต่ตอนเริ่มโปรแกรม
"""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

import models


class StorageError(Exception):
    """ข้อผิดพลาดกลางของชั้น storage"""


class DuplicatePointError(StorageError):
    """point_id ซ้ำกับระเบียกที่ยังไม่ถูกลบ"""


class PointNotFoundError(StorageError):
    """ไม่พบ point_id ที่ต้องการ"""


class FileCorruptedError(StorageError):
    """ไฟล์ไบนารีเสีย (ขนาดไม่หารลงตัว / อ่านไม่ได้)"""


class ChargePointStore:
    """คลาสจัดการไฟล์ charge_points.dat แบบ fixed-length record

    Attributes:
        path: พาธของไฟล์ไบนาร์
        free_slots: รายการ slot index ที่ว่าง (เคยถูก soft delete) เรียงน้อยไปมาก
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.free_slots: List[int] = []
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        """สร้างไฟล์ว่างถ้ายังไม่มี (เปิดแบบ a+b ซึ่งสร้างไฟล์ใหม่ได้)"""
        if not os.path.exists(self.path):
            with open(self.path, "a+b"):
                pass

    def file_size(self) -> int:
        """คืนขนาดไฟล์เป็นไบต์"""
        return os.path.getsize(self.path)

    def count_records(self) -> int:
        """คืนจำนวนระเบียกทั้งหมดในไฟล์ (จำนวนเต็มเท่านั้น ไม่นับส่วนค้าง)"""
        return self.file_size() // models.RECORD_SIZE

    def integrity_check(self) -> Tuple[bool, int]:
        """ตรวจว่าขนาดไฟล์หารด้วย RECORD_SIZE ลงตัวหรือไม่

        Returns:
            (is_valid, remainder_bytes) — remainder คือจำนวนไบต์เกินท้ายสุด
            ที่เป็นระเบียกไม่ครบ (เกิดเมื่อไฟล์ถูกตัด/เขียนค้างกลางระเบียน)
        """
        remainder = self.file_size() % models.RECORD_SIZE
        return (remainder == 0, remainder)

    def truncate_incomplete(self) -> int:
        """ตัดส่วนไบต์เกินท้ายสุดที่เป็นระเบียกไม่ครบทิ้ง

        ใช้ตอนตรวจไฟล์เจอเสียตอนเริ่มโปรแกรม เพื่อให้ไฟล์กลับมาเป็นจำนวนเต็มระเบียน

        Returns:
            จำนวนไบต์ที่ถูกตัดทิ้ง (0 เมื่อไฟล์ปกติ)
        """
        _valid, remainder = self.integrity_check()
        if remainder == 0:
            return 0
        keep = self.file_size() - remainder
        with open(self.path, "r+b") as fh:
            fh.truncate(keep)
            fh.flush()
            os.fsync(fh.fileno())
        return remainder

    def refresh_free_slots(self) -> List[int]:
        """สแกนทั้งไฟล์เพื่อสร้าง free-list ใหม่ (slot index ที่ is_deleted=1)

        เรียกครั้งเดียวตอนเริ่มโปรแกรม และเรียกซ้ำได้หลังมีการลบ

        Returns:
            รายการ slot index ที่ว่าง เรียงจากน้อยไปมาก
        """
        slots: List[int] = []
        with open(self.path, "rb") as fh:
            slot = 0
            while True:
                raw = fh.read(models.RECORD_SIZE)
                if len(raw) < models.RECORD_SIZE:
                    # ไฟล์หมดหรือระเบียกไม่ครบ — หยุดอย่างปลอดภัย
                    break
                if models.unpack_charge_point(raw).is_deleted == 1:
                    slots.append(slot)
                slot += 1
        self.free_slots = slots
        return slots
    def read_at(self, slot: int) -> models.ChargePoint:
        """อ่านระเบียกจาก slot ที่ระบุ (ใช้ seek คำนวณ offset = slot * RECORD_SIZE)

        Raises:
            FileCorruptedError: เมื่อ slot อยู่นอกขอบเขตไฟล์หรืออ่านไม่ครบ 82 ไบต์
        """
        with open(self.path, "rb") as fh:
            offset = slot * models.RECORD_SIZE
            fh.seek(offset)
            raw = fh.read(models.RECORD_SIZE)
        if len(raw) < models.RECORD_SIZE:
            raise FileCorruptedError(
                f"อ่านระเบียกที่ slot {slot} ไม่สำเร็จ: ได้ {len(raw)} ไบต์ "
                f"(ต้องเป็น {models.RECORD_SIZE} ไบต์)"
            )
        return models.unpack_charge_point(raw)

    def read_all(self, include_deleted: bool = True) -> List[models.ChargePoint]:
        """อ่านทุกระเบียกในไฟล์ (เรียงตาม slot)

        Args:
            include_deleted: True = รวมระเบียกที่ถูก soft delete ด้วย
        """
        points: List[models.ChargePoint] = []
        with open(self.path, "rb") as fh:
            while True:
                raw = fh.read(models.RECORD_SIZE)
                if len(raw) < models.RECORD_SIZE:
                    break        # ไฟล์หมดหรือระเบียกไม่ครบ — หยุดอย่างปลอดภัย
                point = models.unpack_charge_point(raw)
                if include_deleted or point.is_deleted == 0:
                    points.append(point)
        return points

    @staticmethod
    def decode_record(raw: bytes) -> models.ChargePoint:
        """ถอดรหัสระเบียกจาก buffer (ใช้ร่วมกับ :class:`io.BytesIO` ใน unit test)

        Raises:
            struct.error: เมื่อความยาว buffer ไม่เท่ากับ 82 ไบต์
        """
        return models.unpack_charge_point(bytes(raw))

    def write_at(self, slot: int, point: models.ChargePoint) -> None:
        """เขียนทับระเบียกที่ slot ที่ระบุ แล้ว flush + os.fsync ให้แน่นอน

        Raises:
            FileCorruptedError: เมื่อ slot อยู่นอกขอบเขตไฟล์
        """
        payload = models.pack_charge_point(point)     # ได้ 82 ไบต์เสมอ
        offset = slot * models.RECORD_SIZE
        with open(self.path, "r+b") as fh:
            fh.seek(offset)
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())

    def append(self, point: models.ChargePoint) -> int:
        """ต่อระเบียกใหม่ท้ายไฟล์ (mode a+b)

        Returns:
            slot index ของระเบียกที่เพิ่งเขียน
        """
        payload = models.pack_charge_point(point)
        with open(self.path, "a+b") as fh:
            fh.seek(0, os.SEEK_END)
            slot = fh.tell() // models.RECORD_SIZE
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        return slot

    def find_slot(self, point_id: int, include_deleted: bool = False) -> Optional[int]:
        """ค้นหา slot ของ point_id

        Args:
            point_id: รหัสหัวชาร์จ
            include_deleted: True = ยอมรับระเบียกที่ถูก soft delete ด้วย

        Returns:
            slot index หรือ None เมื่อไม่พบ
        """
        slot = 0
        with open(self.path, "rb") as fh:
            while True:
                raw = fh.read(models.RECORD_SIZE)
                if len(raw) < models.RECORD_SIZE:
                    break
                point = models.unpack_charge_point(raw)
                if point.point_id == point_id and (include_deleted or point.is_deleted == 0):
                    return slot
                slot += 1
        return None

    def exists(self, point_id: int) -> bool:
        """True เมื่อมีระเบียกที่ยังไม่ถูกลบด้วย point_id นี้"""
        return self.find_slot(point_id, include_deleted=False) is not None

    def allocate_slot(self, point: models.ChargePoint) -> Tuple[int, bool]:
        """จัดสรรช่องสำหรับระเบียกใหม่ โดยนำช่องว่าง (free-list) กลับมาใช้ก่อน

        ลำดับการตัดสินใจ:
            1. ถ้า point_id ซ้ำกับระเบียกที่ยังไม่ถูกลบ -> DuplicatePointError
            2. ถ้ามีระเบียกเดิมที่ is_deleted=1 และมี point_id ตรงกัน
               -> นำช่องนั้นกลับมาใช้ซ้ำ (overwrite ทับระเบียกเดิม)
            3. ถ้ามีช่องว่างใน free-list -> ใช้ช่องว่างช่องแรก
            4. ถ้าไม่มีช่องว่าง -> append ต่อท้ายไฟล์

        Returns:
            (slot, reused) — reused=True เมื่อใช้ช่องว่างที่เคยลบไปแล้ว

        Raises:
            DuplicatePointError: เมื่อ point_id ซ้ำกับระเบียกที่ยังไม่ถูกลบ
        """
        if self.exists(point.point_id):
            raise DuplicatePointError(
                f"point_id {point.point_id} มีอยู่ในระบบแล้ว "
                f"(รหัสหัวชาร์จต้องไม่ซ้ำกัน)"
            )

        # กรณี 2: เคยลบ point_id นี้ไปแล้ว -> กู้ช่องเดิมกลับมาใช้
        old_slot = self.find_slot(point.point_id, include_deleted=True)
        if old_slot is not None:
            self.write_at(old_slot, point)
            self._remove_free_slot(old_slot)
            return old_slot, True

        # กรณี 3: ใช้ช่องว่างจาก free-list
        if self.free_slots:
            slot = self.free_slots.pop(0)
            self.write_at(slot, point)
            return slot, True

        # กรณี 4: ไม่มีช่องว่าง -> ต่อท้ายไฟล์
        return self.append(point), False

    def _remove_free_slot(self, slot: int) -> None:
        """นำ slot ออกจาก free-list (ใช้เมื่อนำช่องว่างกลับมาใช้แล้ว)"""
        if slot in self.free_slots:
            self.free_slots.remove(slot)

    def free_slot_count(self) -> int:
        """จำนวนช่องว่างที่นำกลับมาใช้ได้ (ระเบียกที่ is_deleted=1)"""
        if not self.free_slots:
            self.refresh_free_slots()
        return len(self.free_slots)

