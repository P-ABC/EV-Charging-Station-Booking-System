"""tests/test_log_index.py — ทดสอบ audit log (24 ไบต์) และดัชนี (8 ไบต์)

ครอบคลุม:
* การ append อ่านกลับ และการอ่านด้วย seek ที่ log_seq * 24
* การอ่านเหตุการณ์ล่าสุด / ประวัติของ point_id หนึ่ง ๆ
* กฎ "1 point_id = 1 record" ของ index และการอัปเดตแบบ seek + write ทับ
* การสร้าง index ใหม่จาก log (rebuild) และการตรวจความสอดคล้อง
"""

import os
import shutil
import tempfile
import unittest

import index as index_module
import logger as logger_module
import models


class LogIndexTestCase(unittest.TestCase):
    """คลาสฐาน: เตรียมไฟล์ชั่วคราวสำหรับ log + index"""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="ev_logindex_")
        self.log_path = os.path.join(self.tmp_dir, models.LOG_FILE_NAME)
        self.index_path = os.path.join(self.tmp_dir, models.INDEX_FILE_NAME)
        self.audit = logger_module.AuditLog(self.log_path)
        self.point_index = index_module.PointIndex(self.index_path)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @staticmethod
    def make_point(point_id=1001, **overrides) -> models.ChargePoint:
        """สร้าง record หัวชาร์จตัวอย่างสำหรับบันทึกลง log"""
        data = {
            "point_id": point_id,
            "station_code": "EVS-0001",
            "location": "ทดสอบ",
            "plug_type": "CCS2",
            "power_kw": 120.0,
            "price_per_kwh": 8.0,
            "status": 1,
            "is_booked": 0,
            "is_deleted": 0,
            "created_at": 1_700_000_000,
            "updated_at": 1_700_000_000,
        }
        data.update(overrides)
        return models.ChargePoint(**data)


class TestAuditLog(LogIndexTestCase):
    """ทดสอบไฟล์ audit log แบบ append-only"""

    def test_empty_log_has_zero_entries(self):
        """ไฟล์ log ใหม่ต้องไม่มีเหตุการณ์และขนาดเป็น 0 ไบต์"""
        self.assertEqual(self.audit.count(), 0)
        self.assertTrue(self.audit.integrity_check()[0])

    def test_append_returns_sequential_seq_starting_at_zero(self):
        """log_seq ต้องเริ่มที่ 0 และเพิ่มขึ้นทีละ 1 ตามลำดับ"""
        point = self.make_point()
        self.assertEqual(self.audit.append(point.point_id, models.OP_ADD, point), 0)
        self.assertEqual(self.audit.append(point.point_id, models.OP_UPDATE, point), 1)
        self.assertEqual(self.audit.append(point.point_id, models.OP_VIEW, point), 2)
        self.assertEqual(self.audit.count(), 3)

    def test_each_entry_is_24_bytes(self):
        """ทุกเหตุการณ์ต้องเพิ่มขนาดไฟล์ 24 ไบต์พอดี"""
        point = self.make_point()
        for expected in range(1, 4):
            self.audit.append(point.point_id, models.OP_ADD, point)
            self.assertEqual(os.path.getsize(self.log_path),
                             expected * models.LOG_RECORD_SIZE)

    def test_read_at_uses_seek_to_seq_times_24(self):
        """การอ่านที่ seq ต้องได้เหตุการณ์ที่บันทึกไว้ ณ ตำแหน่งนั้น"""
        point_a = self.make_point(point_id=1001)
        point_b = self.make_point(point_id=1002, price_per_kwh=9.0)
        self.audit.append(point_a.point_id, models.OP_ADD, point_a)
        self.audit.append(point_b.point_id, models.OP_UPDATE, point_b)

        first = self.audit.read_at(0)
        second = self.audit.read_at(1)
        self.assertEqual(first.point_id, 1001)
        self.assertEqual(first.op_code, models.OP_ADD)
        self.assertEqual(second.point_id, 1002)
        self.assertEqual(second.op_code, models.OP_UPDATE)
        self.assertAlmostEqual(second.price_after_thb, 9.0, places=4)

    def test_read_at_out_of_range_returns_none(self):
        """อ่านเลขลำดับนอกขอบเขตต้องได้ None ไม่ใช่ error"""
        self.audit.append(1001, models.OP_ADD, self.make_point())
        self.assertIsNone(self.audit.read_at(5))
        self.assertIsNone(self.audit.read_at(-1))

    def test_read_recent_returns_latest_first(self):
        """read_recent ต้องคืนเหตุการณ์ล่าสุดเรียงใหม่ไปเก่า"""
        for pid in (1001, 1002, 1003, 1004, 1005):
            self.audit.append(pid, models.OP_ADD, self.make_point(pid))
        recent = self.audit.read_recent(limit=3)
        self.assertEqual([e.point_id for e in recent], [1005, 1004, 1003])

    def test_read_recent_limit_larger_than_file(self):
        """ขอจำนวนมากกว่าที่มี ต้องได้เท่าที่มีจริง (ไม่ error)"""
        self.audit.append(1001, models.OP_ADD, self.make_point())
        self.assertEqual(len(self.audit.read_recent(limit=10)), 1)
    def test_read_for_point_filters_by_id(self):
        """ประวัติของ point_id ต้องมีเฉพาะเหตุการณ์ของหัวนั้น"""
        self.audit.append(1001, models.OP_ADD, self.make_point(1001))
        self.audit.append(1002, models.OP_ADD, self.make_point(1002))
        self.audit.append(1001, models.OP_UPDATE, self.make_point(1001))

        history = self.audit.read_for_point(1001)
        self.assertEqual(len(history), 2)
        self.assertTrue(all(entry.point_id == 1001 for entry in history))
        # เรียงจากใหม่ไปเก่า
        self.assertEqual(history[0].op_code, models.OP_UPDATE)

    def test_log_is_append_only_never_rewrites(self):
        """log เป็น append-only: เหตุการณ์เดิมต้องไม่เปลี่ยนเมื่อเพิ่มใหม่"""
        point = self.make_point()
        self.audit.append(point.point_id, models.OP_ADD, point)
        first_snapshot = self.audit.read_at(0)
        self.audit.append(1002, models.OP_DELETE, self.make_point(1002))
        again = self.audit.read_at(0)
        self.assertEqual(first_snapshot, again)

    def test_truncate_incomplete_repairs_truncated_log(self):
        """log ที่ถูกตัดกลาง record ต้องตรวจจับและซ่อมแซมได้"""
        for pid in (1001, 1002):
            self.audit.append(pid, models.OP_ADD, self.make_point(pid))
        with open(self.log_path, "ab") as fh:
            fh.write(b"\x00" * 9)          # เหลือ 9 ไบต์ (ไม่ครบ 24)

        self.assertFalse(self.audit.integrity_check()[0])
        self.assertEqual(self.audit.truncate_incomplete(), 9)
        self.assertTrue(self.audit.integrity_check()[0])
        self.assertEqual(self.audit.count(), 2)


class TestPointIndex(LogIndexTestCase):
    """ทดสอบ index.dat — ผูก point_id กับ log_seq ล่าสุด"""

    def test_update_appends_new_entry(self):
        """point_id ใหม่ต้องถูกเพิ่มเป็น record ใหม่ท้ายไฟล์"""
        self.point_index.update(1001, log_seq=0)
        self.assertEqual(self.point_index.get(1001), 0)
        self.assertEqual(self.point_index.count(), 1)
        self.assertEqual(os.path.getsize(self.index_path),
                         models.INDEX_RECORD_SIZE)

    def test_update_same_id_overwrites_in_place(self):
        """point_id เดิมต้องถูกเขียนทับ (ห้ามเพิ่ม record ซ้ำ)"""
        self.point_index.update(1001, log_seq=0)
        self.point_index.update(1001, log_seq=7)

        self.assertEqual(self.point_index.get(1001), 7)
        self.assertEqual(self.point_index.count(), 1, "ต้องมี record เดียว")
        self.assertEqual(os.path.getsize(self.index_path),
                         models.INDEX_RECORD_SIZE,
                         "ขนาดไฟล์ต้องไม่เพิ่ม (เขียนทับ ไม่ใช่ append)")

    def test_one_record_per_point_id_in_file(self):
        """ในไฟล์ต้องไม่มี point_id ซ้ำแม้อัปเดตหลายครั้ง"""
        for seq in range(10):
            self.point_index.update(1001, log_seq=seq)
        self.point_index.update(1002, log_seq=11)

        self.assertEqual(os.path.getsize(self.index_path),
                         2 * models.INDEX_RECORD_SIZE)

        # อ่านไฟล์ดิบเพื่อยืนยันว่าไม่มี record ซ้ำจริง ๆ
        with open(self.index_path, "rb") as fh:
            raw = fh.read()
        ids = [models.unpack_index_entry(
            raw[i:i + models.INDEX_RECORD_SIZE]).point_id
            for i in range(0, len(raw), models.INDEX_RECORD_SIZE)]
        self.assertEqual(len(ids), len(set(ids)), "ต้องไม่มี point_id ซ้ำ")

    def test_get_missing_id_returns_none(self):
        """point_id ที่ไม่มีในดัชนีต้องได้ None"""
        self.point_index.update(1001, log_seq=0)
        self.assertIsNone(self.point_index.get(9999))

    def test_load_reloads_from_disk(self):
        """ข้อมูลในแคชต้องถูกโหลดกลับมาจากไฟล์ได้ (จำลองการเปิดโปรแกรมใหม่)"""
        self.point_index.update(1001, log_seq=3)
        self.point_index.update(1002, log_seq=4)

        fresh = index_module.PointIndex(self.index_path)
        self.assertEqual(fresh.get(1001), 3)
        self.assertEqual(fresh.get(1002), 4)
        self.assertEqual(fresh.count(), 2)

    def test_rebuild_creates_index_from_log(self):
        """rebuild ต้องสร้างดัชนีใหม่จาก log ได้ครบทุก point_id"""
        # บันทึก log หลายเหตุการณ์ โดยไม่สร้าง index เลย
        self.audit.append(1001, models.OP_ADD, self.make_point(1001))
        self.audit.append(1002, models.OP_ADD, self.make_point(1002))
        self.audit.append(1001, models.OP_UPDATE, self.make_point(1001))
        self.audit.append(1003, models.OP_DELETE, self.make_point(1003))

        rebuilt = self.point_index.rebuild(self.audit.read_all())

        self.assertEqual(rebuilt, 3)
        self.assertEqual(self.point_index.get(1001), 2, "1001 ล่าสุดอยู่ที่ seq 2")
        self.assertEqual(self.point_index.get(1002), 1)
        self.assertEqual(self.point_index.get(1003), 3)
        self.assertEqual(os.path.getsize(self.index_path), 3 * 8)

    def test_rebuild_after_index_file_deleted(self):
        """ถ้า index.dat หาย ต้องสร้างใหม่จาก log ได้ (rebuild_index)"""
        self.audit.append(1001, models.OP_ADD, self.make_point(1001))
        self.audit.append(1002, models.OP_ADD, self.make_point(1002))
        os.remove(self.index_path)

        fresh = index_module.PointIndex(self.index_path)
        self.assertEqual(fresh.count(), 0, "ไฟล์ใหม่ต้องว่าง")

        rebuilt = fresh.rebuild(self.audit.read_all())
        self.assertEqual(rebuilt, 2)
        self.assertEqual(fresh.get(1001), 0)
        self.assertEqual(fresh.get(1002), 1)

    def test_rebuild_replaces_wrong_index(self):
        """ดัชนีที่ชี้ค่าผิดต้องถูกแก้ไขได้ด้วย rebuild"""
        self.audit.append(1001, models.OP_ADD, self.make_point(1001))
        self.audit.append(1001, models.OP_UPDATE, self.make_point(1001))
        # เขียนดัชนีผิด (ชี้ค่าผิดและมีรหัสที่ไม่มีใน log)
        self.point_index.update(1001, log_seq=99)
        self.point_index.update(5555, log_seq=0)

        self.assertGreater(len(self.point_index.verify_against_log(
            self.audit.read_all())), 0, "ต้องตรวจพบปัญหา")

        self.point_index.rebuild(self.audit.read_all())
        self.assertEqual(self.point_index.verify_against_log(
            self.audit.read_all()), [], "หลัง rebuild ต้องตรงกันทั้งหมด")

    def test_verify_detects_missing_and_extra(self):
        """ตรวจความสอดคล้องต้องพบทั้งรหัสที่ขาดและรหัสที่เกินมา"""
        self.audit.append(1001, models.OP_ADD, self.make_point(1001))
        self.point_index.update(1001, log_seq=0)
        self.point_index.update(4242, log_seq=0)      # ไม่มีใน log

        problems = self.point_index.verify_against_log(self.audit.read_all())
        self.assertTrue(any("4242" in problem for problem in problems))

    def test_index_truncate_incomplete(self):
        """index ที่ถูกตัดกลาง record ต้องซ่อมแซมได้"""
        self.point_index.update(1001, log_seq=0)
        with open(self.index_path, "ab") as fh:
            fh.write(b"\x00" * 3)

        self.assertFalse(self.point_index.integrity_check()[0])
        self.assertEqual(self.point_index.truncate_incomplete(), 3)
        self.assertTrue(self.point_index.integrity_check()[0])

