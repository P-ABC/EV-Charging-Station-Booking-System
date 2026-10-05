"""index.py — ดัชนี point_id -> log_seq (index.dat)

ไฟล์ index.dat เก็บ record ละ 8 ไบต์ (struct ``<ll``) เพื่อผูก ``point_id`` กับ "ลำดับ
เริ่มที่ 0" ของเหตุการณ์ล่าสุดใน charge_points.log ทำให้ค้นประวัติล่าสุดของหัวชาร์จ
ได้ทันทีด้วย ``seek(log_seq * 24)`` โดยไม่ต้องไล่อ่าน log ทั้งไฟล์

กติกาสำคัญ
----------
* 1 point_id มีได้ **1 record เท่านั้น** ใน index (ห้ามซ้ำ)
* ถ้ามีอยู่แล้วให้ **อัปเดต log_seq แบบ seek + write ทับ** record เดิม
* ถ้า index เสีย/หาย/ไม่ตรงกับ log ต้อง **สร้างใหม่จาก log ได้** (rebuild)

การจัดการ "record ซ้ำใน index"
------------------------------
ตอนโหลดไฟล์ ถ้าพบ point_id ซ้ำ (อาจเกิดจากการเขียนผิดหรือไฟล์เสีย) จะเก็บค่าจาก
record ที่ log_seq มากสุดไว้เสมอ เพื่อให้ผลลัพธ์ตรงกับตรรกะ "อัปเดตทับค่าเดิม"
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import models


class PointIndex:
    """คลาสจัดการไฟล์ index.dat แบบ 1 point_id = 1 record

    Attributes:
        path: พาธของไฟล์ดัชนี
        _seq_by_id: แคช {point_id: log_seq} สำหรับค้นหา O(1)
        _slot_by_id: แคช {point_id: slot index} เพื่อรู้ตำแหน่งที่จะ seek ไปเขียนทับ
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._seq_by_id: Dict[int, int] = {}
        self._slot_by_id: Dict[int, int] = {}
        if not os.path.exists(self.path):
            with open(self.path, "a+b"):
                pass
        else:
            self.load()

    # ------------------------------------------------------------------
    # ความถูกต้องของไฟล์
    # ------------------------------------------------------------------
    def integrity_check(self) -> tuple[bool, int]:
        """ตรวจว่าขนาด index หารด้วย 8 ลงตัวหรือไม่

        Returns:
            (is_valid, remainder_bytes) — remainder คือไบต์เกินท้ายที่เป็น record ไม่ครบ
        """
        remainder = os.path.getsize(self.path) % models.INDEX_RECORD_SIZE
        return (remainder == 0, remainder)

    def truncate_incomplete(self) -> int:
        """ตัด record index ที่ไม่ครบ 8 ไบต์ทิ้ง (ไฟล์ถูกตัดกลาง record)

        Returns:
            จำนวนไบต์ที่ถูกตัดทิ้ง (0 เมื่อไฟล์ปกติ)
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
    # อ่าน / เขียน
    # ------------------------------------------------------------------
    def load(self) -> Dict[int, int]:
        """โหลด index ทั้งหมดเข้าแคชในหน่วยความจำ

        Returns:
            dict {point_id: log_seq}
        """
        seq_by_id: Dict[int, int] = {}
        slot_by_id: Dict[int, int] = {}
        with open(self.path, "rb") as fh:
            slot = 0
            while True:
                raw = fh.read(models.INDEX_RECORD_SIZE)
                if len(raw) < models.INDEX_RECORD_SIZE:
                    break
                item = models.unpack_index_entry(raw)
                if item.point_id not in seq_by_id or item.log_seq >= seq_by_id[item.point_id]:
                    seq_by_id[item.point_id] = item.log_seq
                    slot_by_id[item.point_id] = slot
                slot += 1
        self._seq_by_id = seq_by_id
        self._slot_by_id = slot_by_id
        return seq_by_id

    def get(self, point_id: int) -> Optional[int]:
        """คืน log_seq ล่าสุดของ point_id หรือ None เมื่อไม่พบ"""
        return self._seq_by_id.get(point_id)

    def count(self) -> int:
        """จำนวน point_id ที่มีในดัชนี"""
        return len(self._seq_by_id)

    def as_dict(self) -> Dict[int, int]:
        """คืนสำเนา dict ของดัชนีทั้งหมด (ป้องกันการแก้ไขแคชโดยตรง)"""
        return dict(self._seq_by_id)

    def update(self, point_id: int, log_seq: int) -> None:
        """ผูก point_id กับ log_seq (seek + write ทับเมื่อมีอยู่แล้ว)

        ขั้นตอน:
            1. ถ้า point_id มีอยู่แล้ว -> seek ไป offset = slot*8 แล้วเขียนทับ record เดิม
            2. ถ้ายังไม่มี -> ต่อ record ใหม่ท้ายไฟล์ (ไม่ต้อง rewrite ทั้งไฟล์)
        """
        entry = models.IndexEntry(point_id=point_id, log_seq=log_seq)
        if point_id in self._slot_by_id:
            # กรณีที่ 1: seek ไปทับ record เดิมของ point_id นี้
            offset = self._slot_by_id[point_id] * models.INDEX_RECORD_SIZE
            with open(self.path, "r+b") as fh:
                fh.seek(offset)
                fh.write(models.pack_index_entry(entry))
                fh.flush()
                os.fsync(fh.fileno())
        else:
            # กรณีที่ 2: ต่อท้ายไฟล์
            with open(self.path, "a+b") as fh:
                fh.seek(0, os.SEEK_END)
                slot = fh.tell() // models.INDEX_RECORD_SIZE
                fh.write(models.pack_index_entry(entry))
                fh.flush()
                os.fsync(fh.fileno())
            self._slot_by_id[point_id] = slot
        self._seq_by_id[point_id] = log_seq

    def remove(self, point_id: int) -> bool:
        """ลบ point_id ออกจากดัชนีโดยเขียนไฟล์ใหม่ทั้งไฟล์ (คง record ที่เหลือไว้)

        ใช้เป็นเครื่องมือซ่อมแซม ยังไม่ได้เรียกใน CRUD ปกติ เพราะต้องรักษา
        ประวัติของ point_id ไว้เพื่อให้ค้นย้อนหลังได้

        Returns:
            True เมื่อพบและลบสำเร็จ, False เมื่อไม่พบ
        """
        if point_id not in self._seq_by_id:
            return False
        kept: List[models.IndexEntry] = []
        with open(self.path, "rb") as fh:
            while True:
                raw = fh.read(models.INDEX_RECORD_SIZE)
                if len(raw) < models.INDEX_RECORD_SIZE:
                    break
                item = models.unpack_index_entry(raw)
                if item.point_id != point_id:
                    kept.append(item)
        with open(self.path, "w+b") as fh:
            for item in kept:
                fh.write(models.pack_index_entry(item))
            fh.flush()
            os.fsync(fh.fileno())
        self.load()
        return True

    # ------------------------------------------------------------------
    # การสร้างดัชนีใหม่จาก log (rebuild_index)
    # ------------------------------------------------------------------
    def rebuild(self, log_entries: List[models.LogEntry]) -> int:
        """สร้าง index.dat ใหม่ทั้งไฟล์จากเหตุการณ์ใน log

        ใช้เมื่อ index เสียหาย หาย หรือไม่ตรงกับ log

        Args:
            log_entries: รายการเหตุการณ์ทั้งหมดใน log เรียงจากเก่าไปใหม่

        Returns:
            จำนวน point_id ที่ถูกใส่ลงดัชนี
        """
        latest: Dict[int, int] = {}
        for seq, entry in enumerate(log_entries):
            latest[entry.point_id] = seq      # ทับค่าเดิม -> ได้ seq ล่าสุดเสมอ

        # เขียนใหม่ทั้งไฟล์ด้วย mode "w+b" (ตัดไฟล์เดิมทิ้งแล้วเขียนใหม่)
        with open(self.path, "w+b") as fh:
            for point_id in sorted(latest):
                fh.write(models.pack_index_entry(
                    models.IndexEntry(point_id, latest[point_id])
                ))
            fh.flush()
            os.fsync(fh.fileno())
        self.load()
        return len(latest)

    def verify_against_log(self, log_entries: List[models.LogEntry]) -> List[str]:
        """ตรวจสอบว่า index สอดคล้องกับ log หรือไม่

        Returns:
            รายการข้อความปัญหา (ว่างเปล่า = ถูกต้องต้องกันหมด)
        """
        problems: List[str] = []
        expected: Dict[int, int] = {}
        for seq, entry in enumerate(log_entries):
            expected[entry.point_id] = seq

        for point_id, seq in self._seq_by_id.items():
            if point_id not in expected:
                problems.append(
                    f"index มี point_id {point_id} แต่ไม่มีใน log (log_seq={seq})"
                )
            elif expected[point_id] != seq:
                problems.append(
                    f"index ของ point_id {point_id} ชี้ไปที่ log_seq={seq} "
                    f"แต่ค่าที่ถูกต้องคือ {expected[point_id]}"
                )
        for point_id in expected:
            if point_id not in self._seq_by_id:
                problems.append(f"log มี point_id {point_id} แต่ไม่มีใน index")
        return problems
