"""tests/test_storage.py — ทดสอบ CRUD ระดับไฟล์, free-list และการตรวจไฟล์เสีย

ครอบคลุม:
* เพิ่ม/อ่าน/แก้ไข/ลบผ่าน :class:`storage.ChargePointStore`
* การนำช่องที่ลบแล้วกลับมาใช้ซ้ำ (free-list)
* เทสต์เชิงลบ: point_id ซ้ำ, อ่าน slot ที่ไม่มีอยู่จริง
* การตรวจและซ่อมแซมไฟล์ที่ถูกตัดกลางระเบียน
"""

import os
import shutil
import tempfile
import unittest

import models
import storage


class StorageTestCase(unittest.TestCase):
    """คลาสฐานสำหรับเทสต์ที่ใช้ไฟล์ชั่วคราว (แต่ละเทสต์ได้ไฟล์ของตัวเอง)"""

    def setUp(self):
        """สร้างโฟลเดอร์ชั่วคราวและเปิด store"""
        self.tmp_dir = tempfile.mkdtemp(prefix="ev_test_")
        self.data_path = os.path.join(self.tmp_dir, models.DATA_FILE_NAME)
        self.store = storage.ChargePointStore(self.data_path)

    def tearDown(self):
        """ลบโฟลเดอร์ชั่วคราวทิ้ง (ไม่ทิ้งข้อมูลทดสอบไว้ในเครื่อง)"""
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def make_point(self, point_id=1001, **overrides) -> models.ChargePoint:
        """สร้าง record หัวชาร์จสำหรับทดสอบ"""
        data = {
            "point_id": point_id,
            "station_code": "EVS-0001",
            "location": "สถานีทดสอบ",
            "plug_type": "Type2",
            "power_kw": 22.0,
            "price_per_kwh": 7.5,
            "status": 1,
            "is_booked": 0,
            "is_deleted": 0,
            "created_at": 1_700_000_000,
            "updated_at": 1_700_000_000,
        }
        data.update(overrides)
        return models.ChargePoint(**data)


class TestCreateRead(StorageTestCase):
    """ทดสอบการสร้างและอ่าน record"""

    def test_new_file_is_empty_and_created(self):
        """เปิด store ต้องสร้างไฟล์ว่างขึ้นมาให้"""
        self.assertTrue(os.path.exists(self.data_path))
        self.assertEqual(self.store.count_records(), 0)
        self.assertEqual(self.store.file_size(), 0)

    def test_append_creates_82_byte_records(self):
        """ทุก record ที่เพิ่มต้องทำให้ไฟล์โตขึ้น 82 ไบต์พอดี"""
        for expected_count in range(1, 6):
            self.store.append(self.make_point(point_id=1000 + expected_count))
            self.assertEqual(self.store.file_size(),
                             expected_count * models.RECORD_SIZE)
            self.assertEqual(self.store.count_records(), expected_count)

    def test_read_at_returns_written_values(self):
        """อ่านกลับต้องได้ค่าที่เขียนไว้"""
        point = self.make_point(point_id=1234, location="ลานทดสอบ",
                                power_kw=150.0, price_per_kwh=8.25)
        self.store.append(point)
        restored = self.store.read_at(0)
        self.assertEqual(restored.point_id, 1234)
        self.assertEqual(restored.location, "ลานทดสอบ")
        self.assertEqual(restored.plug_type, "Type2")
        self.assertAlmostEqual(restored.power_kw, 150.0, places=3)
        self.assertAlmostEqual(restored.price_per_kwh, 8.25, places=3)

    def test_read_all_returns_every_record_in_order(self):
        """read_all ต้องคืนทุก record เรียงตาม slot"""
        for pid in (1001, 1002, 1003):
            self.store.append(self.make_point(point_id=pid))
        points = self.store.read_all()
        self.assertEqual([p.point_id for p in points], [1001, 1002, 1003])

    def test_read_all_can_exclude_deleted(self):
        """include_deleted=False ต้องตัด record ที่ถูก soft delete ออก"""
        self.store.append(self.make_point(point_id=1001))
        self.store.append(self.make_point(point_id=1002, is_deleted=1))
        self.assertEqual(len(self.store.read_all(include_deleted=True)), 2)
        self.assertEqual(len(self.store.read_all(include_deleted=False)), 1)

    def test_read_out_of_range_raises_corrupted_error(self):
        """อ่าน slot ที่เกินขอบเขตต้องแจ้ง FileCorruptedError"""
        self.store.append(self.make_point())
        with self.assertRaises(storage.FileCorruptedError):
            self.store.read_at(99)

    def test_decode_record_from_buffer(self):
        """decode_record ใช้ถอดรหัสจาก buffer ได้"""
        point = self.make_point(point_id=555)
        restored = storage.ChargePointStore.decode_record(point.to_bytes())
        self.assertEqual(restored.point_id, 555)
class TestUpdateAndDelete(StorageTestCase):
    """ทดสอบการเขียนทับ record (seek + write) และ soft delete"""

    def test_write_at_overwrites_in_place(self):
        """การแก้ไขต้องเขียนทับขนาดไฟล์เท่าเดิม (ไม่เพิ่ม record ใหม่)"""
        self.store.append(self.make_point(point_id=1001))
        self.store.append(self.make_point(point_id=1002))
        size_before = self.store.file_size()

        updated = self.make_point(point_id=1001, price_per_kwh=9.99,
                                  is_booked=1)
        self.store.write_at(0, updated)

        self.assertEqual(self.store.file_size(), size_before)
        self.assertEqual(self.store.count_records(), 2)
        self.assertAlmostEqual(self.store.read_at(0).price_per_kwh, 9.99, places=4)
        self.assertEqual(self.store.read_at(0).is_booked, 1)
        # record อื่นต้องไม่ถูกกระทบ
        self.assertEqual(self.store.read_at(1).point_id, 1002)

    def test_find_slot_and_exists(self):
        """find_slot คืนตำแหน่งที่ถูกต้อง และ exists ตอบได้ถูกต้อง"""
        self.store.append(self.make_point(point_id=1001))
        self.store.append(self.make_point(point_id=1002))
        self.assertEqual(self.store.find_slot(1002), 1)
        self.assertTrue(self.store.exists(1001))
        self.assertFalse(self.store.exists(9999))

    def test_find_slot_skips_deleted_by_default(self):
        """ค้นหาปกติต้องไม่เจอ record ที่ถูกลบ แต่ระบุ include_deleted ได้"""
        self.store.append(self.make_point(point_id=1001, is_deleted=1))
        self.assertIsNone(self.store.find_slot(1001))
        self.assertEqual(self.store.find_slot(1001, include_deleted=True), 0)
        self.assertFalse(self.store.exists(1001))

    def test_soft_delete_keeps_bytes_and_sets_flag(self):
        """soft delete ต้องตั้ง is_deleted=1 แต่ไม่ลบไบต์ออกจริง"""
        self.store.append(self.make_point(point_id=1001))
        size_before = self.store.file_size()

        deleted = self.make_point(point_id=1001, is_deleted=1)
        self.store.write_at(0, deleted)

        self.assertEqual(self.store.file_size(), size_before)
        self.assertEqual(self.store.count_records(), 1)
        self.assertEqual(self.store.read_at(0).is_deleted, 1)
        self.assertEqual(self.store.read_at(0).status_text, "Deleted")

class TestFreeList(StorageTestCase):
    """ทดสอบ free-list: นำช่องว่างที่ลบแล้วกลับมาใช้ซ้ำ"""

    def test_refresh_free_slots_finds_deleted(self):
        """สแกนไฟล์ต้องพบ slot ที่ is_deleted=1"""
        self.store.append(self.make_point(point_id=1001))
        self.store.append(self.make_point(point_id=1002, is_deleted=1))
        self.store.append(self.make_point(point_id=1003))
        self.store.append(self.make_point(point_id=1004, is_deleted=1))
        self.assertEqual(self.store.refresh_free_slots(), [1, 3])

    def test_allocate_appends_when_no_free_slot(self):
        """ไม่มีช่องว่าง -> ต้องต่อท้ายไฟล์ (reused=False)"""
        slot, reused = self.store.allocate_slot(self.make_point(point_id=1001))
        self.assertEqual(slot, 0)
        self.assertFalse(reused)

    def test_allocate_reuses_deleted_slot_instead_of_growing(self):
        """มีช่องว่าง -> ต้องใช้ช่องเดิมแทนการต่อท้ายไฟล์"""
        self.store.append(self.make_point(point_id=1001))
        self.store.append(self.make_point(point_id=1002, is_deleted=1))
        self.store.append(self.make_point(point_id=1003))
        self.store.refresh_free_slots()
        size_before = self.store.file_size()

        slot, reused = self.store.allocate_slot(
            self.make_point(point_id=2002, location="ใช้ช่องว่าง"))

        self.assertTrue(reused, "ควรถูกจัดเป็นการใช้ช่องว่างซ้ำ")
        self.assertEqual(slot, 1, "ต้องใช้ slot ที่ 1 ซึ่งเคยถูกลบ")
        self.assertEqual(self.store.file_size(), size_before,
                         "ขนาดไฟล์ต้องไม่เพิ่ม (ไม่เกิด record ใหม่)")
        self.assertEqual(self.store.read_at(1).point_id, 2002)

    def test_free_slot_removed_from_list_after_reuse(self):
        """เมื่อใช้ช่องว่างแล้ว ต้องถูกเอาออกจาก free-list"""
        self.store.append(self.make_point(point_id=1001, is_deleted=1))
        self.store.append(self.make_point(point_id=1002, is_deleted=1))
        self.store.refresh_free_slots()
        self.assertEqual(self.store.free_slots, [0, 1])

        self.store.allocate_slot(self.make_point(point_id=3001))
        self.assertEqual(self.store.free_slots, [1])

    def test_reuse_same_point_id_after_delete(self):
        """ถ้า point_id เดิมถูกลบไปแล้ว ให้เพิ่มใหม่โดยใช้ช่องเดิม (กู้ช่องคืน)"""
        self.store.append(self.make_point(point_id=1001))
        self.store.write_at(0, self.make_point(point_id=1001, is_deleted=1))
        self.store.refresh_free_slots()

        # ใช้ข้อความที่ยาวไม่เกิน 30 ไบต์ เพื่อไม่ให้ถูกตัดระหว่างทดสอบ
        # ("กู้ช่อง" = 18 ไบต์)
        slot, reused = self.store.allocate_slot(
            self.make_point(point_id=1001, location="กู้ช่อง"))

        self.assertTrue(reused)
        self.assertEqual(slot, 0)
        self.assertEqual(self.store.read_at(0).is_deleted, 0)
        self.assertEqual(self.store.read_at(0).location, "กู้ช่อง")
    def test_free_slot_count_reports_reusable_slots(self):
        """free_slot_count ต้องนับเฉพาะ record ที่ถูกลบ"""
        for pid, deleted in ((1001, 0), (1002, 1), (1003, 0), (1004, 1)):
            self.store.append(self.make_point(point_id=pid, is_deleted=deleted))
        self.assertEqual(self.store.free_slot_count(), 2)

class TestNegativeCases(StorageTestCase):
    """ทดสอบเชิงลบ: ข้อมูลผิดเงื่อนไขต้องถูกปฏิเสธอย่างปลอดภัย"""

    def test_duplicate_point_id_is_rejected(self):
        """point_id ที่ยังไม่ถูกลบซ้ำกันต้องถูกปฏิเสธ"""
        self.store.append(self.make_point(point_id=1001))
        with self.assertRaises(storage.DuplicatePointError):
            self.store.allocate_slot(self.make_point(point_id=1001))

    def test_same_point_id_allowed_after_delete(self):
        """หลัง soft delete แล้ว point_id เดิมต้องเพิ่มซ้ำได้ (ใช้ช่องเดิม)"""
        self.store.append(self.make_point(point_id=1001))
        self.store.write_at(0, self.make_point(point_id=1001, is_deleted=1))
        slot, reused = self.store.allocate_slot(self.make_point(point_id=1001))
        self.assertEqual(slot, 0)
        self.assertTrue(reused)

    def test_find_missing_key_returns_none(self):
        """ค้นหา point_id ที่ไม่มีอยู่ ต้องได้ None (ไม่ใช่ error)"""
        self.store.append(self.make_point(point_id=1001))
        self.assertIsNone(self.store.find_slot(4242))

    def test_empty_file_operations_are_safe(self):
        """ทำงานกับไฟล์ว่างต้องไม่พัง (คืนค่าว่าง/ผ่านการตรวจ)"""
        self.assertEqual(self.store.read_all(), [])
        self.assertIsNone(self.store.find_slot(1001))
        self.assertEqual(self.store.refresh_free_slots(), [])
        self.assertTrue(self.store.integrity_check()[0])


class TestCorruptedFile(StorageTestCase):
    """ทดสอบการตรวจจับและซ่อมแซมไฟล์ที่ถูกตัดกลางระเบียน"""

    def test_integrity_ok_for_whole_records(self):
        """ไฟล์ที่มีแต่ record ครบถือว่าปกติ"""
        self.store.append(self.make_point(point_id=1001))
        valid, remainder = self.store.integrity_check()
        self.assertTrue(valid)
        self.assertEqual(remainder, 0)

    def test_detects_truncated_record(self):
        """ไฟล์ที่ถูกตัดกลาง record ต้องถูกตรวจจับได้"""
        self.store.append(self.make_point(point_id=1001))
        self.store.append(self.make_point(point_id=1002))

        # จำลองการตัดไฟล์ทิ้ง 30 ไบต์ (เหลือ record ครึ่งตัว)
        with open(self.data_path, "r+b") as fh:
            fh.truncate(models.RECORD_SIZE + 30)

        valid, remainder = self.store.integrity_check()
        self.assertFalse(valid, "ไฟล์ที่ถูกตัดต้องถูกรายงานว่าไม่ถูกต้อง")
        self.assertEqual(remainder, 30)

    def test_truncate_incomplete_repairs_file(self):
        """ซ่อมแซมแล้วขนาดไฟล์ต้องหารลงตัวและอ่าน record ที่ครบได้"""
        self.store.append(self.make_point(point_id=1001))
        self.store.append(self.make_point(point_id=1002))
        with open(self.data_path, "r+b") as fh:
            fh.truncate(models.RECORD_SIZE + 30)

        removed = self.store.truncate_incomplete()

        self.assertEqual(removed, 30)
        self.assertTrue(self.store.integrity_check()[0])
        self.assertEqual(self.store.count_records(), 1)
        self.assertEqual(self.store.read_at(0).point_id, 1001)

    def test_truncate_incomplete_noop_on_valid_file(self):
        """ไฟล์ปกติต้องไม่ถูกตัดอะไรออก"""
        self.store.append(self.make_point(point_id=1001))
        self.assertEqual(self.store.truncate_incomplete(), 0)
        self.assertEqual(self.store.count_records(), 1)

    def test_read_all_ignores_incomplete_tail(self):
        """การอ่านต้องหยุดอย่างปลอดภัยเมื่อเจอ record ไม่ครบท้ายไฟล์"""
        self.store.append(self.make_point(point_id=1001))
        self.store.append(self.make_point(point_id=1002))
        with open(self.data_path, "ab") as fh:      # เขียนข้อมูลทิ้งกลาง record
            fh.write(b"\x00" * 17)

        points = self.store.read_all()
        self.assertEqual([p.point_id for p in points], [1001, 1002])

    def test_free_slots_scan_survives_truncated_tail(self):
        """การสแกน free-list ต้องไม่พังเมื่อไฟล์ท้ายไม่ครบ record"""
        self.store.append(self.make_point(point_id=1001, is_deleted=1))
        with open(self.data_path, "ab") as fh:
            fh.write(b"\x00" * 40)

        self.assertEqual(self.store.refresh_free_slots(), [0])

