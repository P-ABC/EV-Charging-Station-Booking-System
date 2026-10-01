"""tests/test_app.py — ทดสอบการทำงานรวมของระบบ (CRUD ครบทุกเมนู + ซ่อมแซมไฟล์)

ครอบคลุม:
* CRUD ครบทุกเมนูผ่าน :class:`main.ChargingStationApp` (ชั้นบริการ)
* การนำช่องที่ลบแล้วกลับมาใช้ซ้ำในระดับแอปพลิเคชัน
* เทสต์เชิงลบ: ข้อมูลซ้ำ, ไม่พบคีย์, ลบหัวที่กำลังถูกจอง
* การสร้างดัชนีใหม่ (rebuild_index) และการตรวจซ่อมไฟล์เสีย
* การสร้างรายงานและการออกอย่างปลอดภัย
"""

import os
import shutil
import tempfile
import unittest

import index as index_module
import logger as logger_module
import main
import models
import seed_data
import storage


class AppTestCase(unittest.TestCase):
    """คลาสฐาน: สร้างแอปพลิเคชันที่ใช้โฟลเดอร์ชั่วคราว"""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="ev_app_")
        self.app = main.ChargingStationApp(self.tmp_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def add(self, point_id=1001, **overrides):
        """ทางลัดสำหรับเพิ่มหัวชาร์จในเทสต์"""
        data = {
            "station_code": "EVS-0001",
            "location": "ทดสอบ",
            "plug_type": "Type2",
            "power_kw": 22.0,
            "price_per_kwh": 7.0,
        }
        data.update(overrides)
        return self.app.add_record(point_id, **data)


class TestAddMenu(AppTestCase):
    """ทดสอบเมนู 1) Add"""

    def test_add_creates_record_log_and_index(self):
        """เพิ่มข้อมูลแล้วต้องมีทั้งระเบียกในไฟล์, log และ index"""
        point = self.add(1001)
        self.assertEqual(point.point_id, 1001)
        self.assertEqual(self.app.store.count_records(), 1)
        self.assertEqual(self.app.audit.count(), 1)
        self.assertEqual(self.app.point_index.get(1001), 0)

    def test_add_sets_timestamps(self):
        """created_at และ updated_at ต้องถูกตั้งเป็นเวลาปัจจุบัน"""
        point = self.add(1001)
        self.assertGreater(point.created_at, 0)
        self.assertEqual(point.created_at, point.updated_at)

    def test_add_logs_op_add(self):
        """เหตุการณ์เพิ่มต้องบันทึกด้วย op_code = ADD (1)"""
        point = self.add(1001)
        entry = self.app.audit.read_at(0)
        self.assertEqual(entry.op_code, models.OP_ADD)
        self.assertEqual(entry.point_id, 1001)
        self.assertEqual(entry.status_after, point.status)
        self.assertAlmostEqual(entry.price_after_thb, point.price_per_kwh,
                               places=3)

    def test_add_truncates_long_location(self):
        """location ที่ยาวเกิน 30 ไบต์ต้องถูกตัดพอดีก่อนบันทึก"""
        point = self.add(1001,
                         location="สถานีชาร์จไฟฟ้าสยามพารากอนชั้นใต้ดิน")
        self.assertLessEqual(models.text_byte_length(point.location), 30)
        self.assertNotIn("\ufffd", point.location)

    def test_add_duplicate_raises(self):
        """point_id ซ้ำกับระเบียกที่ยังไม่ถูกลบต้องถูกปฏิเสธ"""
        self.add(1001)
        with self.assertRaises(storage.DuplicatePointError):
            self.add(1001)

    def test_add_after_delete_reuses_slot(self):
        """เพิ่ม point_id เดิมหลัง soft delete ต้องใช้ช่องเดิม ไม่ต่อท้ายไฟล์"""
        self.add(1001)
        self.app.delete_record(1001)
        self.assertEqual(self.app.store.count_records(), 1,
                         "soft delete ต้องไม่ลบไบต์ออก")

        self.add(1001)
        self.assertEqual(self.app.store.count_records(), 1,
                         "ต้องใช้ช่องว่างเดิม ไม่เพิ่มระเบียกใหม่")
class TestUpdateMenu(AppTestCase):
    """ทดสอบเมนู 2) Update"""

    def setUp(self):
        super().setUp()
        self.point = self.add(1001)

    def test_update_changes_fields(self):
        """แก้ไขฟิลด์ที่อนุญาตได้ผลจริง"""
        updated = self.app.update_record(1001, price_per_kwh=9.99,
                                         power_kw=350.0)
        self.assertAlmostEqual(updated.price_per_kwh, 9.99, places=3)
        self.assertAlmostEqual(updated.power_kw, 350.0, places=3)

    def test_update_does_not_change_file_size(self):
        """การแก้ไขต้องเขียนทับระเบียกเดิม (ขนาดไฟล์คงที่)"""
        size_before = self.app.store.file_size()
        self.app.update_record(1001, location="ที่ใหม่")
        self.assertEqual(self.app.store.file_size(), size_before)
        self.assertEqual(self.app.store.count_records(), 1)

    def test_update_preserves_point_id_and_created_at(self):
        """ห้ามแก้ point_id และ created_at"""
        updated = self.app.update_record(1001, status=0)
        self.assertEqual(updated.point_id, 1001)
        self.assertEqual(updated.created_at, self.point.created_at)

    def test_update_refreshes_updated_at(self):
        """updated_at ต้องถูกอัปเดตเป็นเวลาปัจจุบัน"""
        updated = self.app.update_record(1001, status=0)
        self.assertGreaterEqual(updated.updated_at, self.point.updated_at)

    def test_update_toggles_booked_and_status(self):
        """สลับสถานะการจอง/ช่องว่างและ Active/Inactive ได้"""
        self.assertEqual(self.app.update_record(1001, is_booked=1).is_booked, 1)
        self.assertEqual(self.app.update_record(1001, is_booked=0).is_booked, 0)
        self.assertEqual(self.app.update_record(1001, status=0).status, 0)

    def test_update_logs_op_update_and_moves_index(self):
        """แก้ไขต้องเขียน log (op=UPDATE) และเลื่อน log_seq ใน index"""
        self.app.update_record(1001, status=0)
        self.assertEqual(self.app.audit.count(), 2)
        self.assertEqual(self.app.audit.read_at(1).op_code, models.OP_UPDATE)
        self.assertEqual(self.app.point_index.get(1001), 1)

    def test_update_unknown_key_raises(self):
        """แก้ไข point_id ที่ไม่มีอยู่ต้องแจ้งอย่างสุภาพ (raise ข้อผิดพลาด)"""
        with self.assertRaises(storage.PointNotFoundError):
            self.app.update_record(9999, status=0)

    def test_update_rejects_immutable_fields(self):
        """พยายามแก้ฟิลด์ที่ห้ามแก้ต้องถูกปฏิเสธ"""
        with self.assertRaises(KeyError):
            self.app.update_record(1001, created_at=0)

    def test_update_deleted_record_not_found(self):
        """ระเบียกที่ถูก soft delete แล้วถือว่าไม่พบในการแก้ไข"""
        self.app.delete_record(1001)
        with self.assertRaises(storage.PointNotFoundError):
            self.app.update_record(1001, status=0)


class TestDeleteMenu(AppTestCase):
    """ทดสอบเมนู 3) Delete (soft delete)"""

    def test_delete_sets_flag_and_keeps_record(self):
        """ลบต้องตั้ง is_deleted=1 แต่ระเบียกยังอยู่ในไฟล์"""
        self.add(1001)
        deleted = self.app.delete_record(1001)
        self.assertEqual(deleted.is_deleted, 1)
        self.assertEqual(self.app.store.count_records(), 1)
        self.assertIsNone(self.app.store.find_slot(1001))
        self.assertIsNotNone(self.app.store.find_slot(1001, include_deleted=True))

    def test_delete_logs_op_delete(self):
        """ลบต้องเขียน log (op=DELETE)"""
        self.add(1001)
        self.app.delete_record(1001)
        self.assertEqual(self.app.audit.read_at(1).op_code, models.OP_DELETE)

    def test_delete_refreshes_updated_at(self):
        """ลบต้องอัปเดต updated_at เป็นเวลาปัจจุบัน"""
        point = self.add(1001)
        deleted = self.app.delete_record(1001)
        self.assertGreaterEqual(deleted.updated_at, point.updated_at)

    def test_delete_booked_point_is_rejected(self):
        """ห้ามลบหัวชาร์จที่กำลังถูกจองอยู่ (is_booked=1)"""
        self.add(1001, is_booked=1)
        with self.assertRaises(storage.StorageError):
            self.app.delete_record(1001)
        self.assertEqual(self.app.store.read_at(0).is_deleted, 0,
                         "ต้องยังไม่ถูกลบ")

    def test_delete_after_release_booked_is_allowed(self):
        """เมื่อปล่อยหัวชาร์จแล้ว (is_booked=0) ต้องลบได้"""
        self.add(1001, is_booked=1)
        self.app.update_record(1001, is_booked=0)
        self.app.delete_record(1001)
        self.assertEqual(self.app.store.read_at(0).is_deleted, 1)

    def test_delete_unknown_key_raises(self):
        """ลบ point_id ที่ไม่มีอยู่ต้องแจ้งอย่างสุภาพ"""
        with self.assertRaises(storage.PointNotFoundError):
            self.app.delete_record(9999)

    def test_delete_adds_slot_to_free_list(self):
        """หลังลบ ช่องต้องถูกเพิ่มเข้า free-list เพื่อนำกลับมาใช้"""
        self.add(1001)
        self.add(1002)
        self.app.delete_record(1002)
        self.assertEqual(self.app.store.free_slots, [1])

class TestViewMenu(AppTestCase):
    """ทดสอบเมนู 4) View"""

    def test_view_single_logs_view_event(self):
        """การดูรายการเดียวต้องเขียน log (op=VIEW) ตามข้อกำหนด"""
        self.add(1001)
        before = self.app.audit.count()
        point = self.app.view_record(1001)

        self.assertIsNotNone(point)
        self.assertEqual(self.app.audit.count(), before + 1)
        self.assertEqual(self.app.audit.read_at(before).op_code, models.OP_VIEW)

    def test_view_single_updates_index_to_latest_event(self):
        """หลังดู ดัชนีต้องชี้ไปที่เหตุการณ์ล่าสุด"""
        self.add(1001)
        self.app.view_record(1001)
        latest = self.app.audit.count() - 1
        self.assertEqual(self.app.point_index.get(1001), latest)

    def test_view_single_finds_deleted_record(self):
        """ค้นหารายเดียวต้องเจอแม้ระเบียกที่ถูก soft delete"""
        self.add(1001)
        self.app.delete_record(1001)
        point = self.app.view_record(1001)
        self.assertIsNotNone(point)
        self.assertEqual(point.is_deleted, 1)

    def test_view_single_unknown_key_returns_none(self):
        """ค้นหา point_id ที่ไม่มีอยู่ต้องได้ None (ไม่ error)"""
        self.assertIsNone(self.app.view_record(9999))

    def test_history_read_through_index(self):
        """ประวัติต้องอ่านได้ถูกต้องผ่าน index.dat"""
        self.add(1001)
        self.app.update_record(1001, is_booked=1)
        self.app.view_record(1001)

        history = self.app.history_of(1001)
        self.assertEqual(len(history), 3)
        # เรียงจากใหม่ไปเก่า
        self.assertEqual([entry.op_code for entry in history],
                         [models.OP_VIEW, models.OP_UPDATE, models.OP_ADD])

    def test_history_of_unknown_point_is_empty(self):
        """ประวัติของ point_id ที่ไม่มีในดัชนีต้องเป็นรายการว่าง"""
        self.assertEqual(self.app.history_of(9999), [])

    def test_view_all_includes_deleted(self):
        """เมนู 4.2 ต้องรวมระเบียกที่ถูกลบแล้ว"""
        self.add(1001)
        self.add(1002)
        self.app.delete_record(1002)
        self.assertEqual(len(self.app.store.read_all(include_deleted=True)), 2)
        self.assertEqual(len(self.app.store.read_all(include_deleted=False)), 1)


class TestStartupCheckAndRepair(AppTestCase):
    """ทดสอบการตรวจและซ่อมแซมไฟล์เสียตอนเริ่มโปรแกรม"""

    def test_startup_check_clean_data_has_no_message(self):
        """ข้อมูลที่สมบูรณ์ต้องไม่มีข้อความแจ้งเตือน"""
        self.add(1001)
        messages = main.ChargingStationApp(self.tmp_dir).startup_check()
        self.assertEqual(messages, [])

    def test_startup_repairs_truncated_data_file(self):
        """ไฟล์ข้อมูลที่ถูกตัดกลางระเบียกต้องถูกตัดส่วนเกินทิ้งให้อัตโนมัติ"""
        self.add(1001)
        self.add(1002)
        with open(self.app.data_path, "ab") as fh:
            fh.write(b"\x00" * 25)         # ระเบียกไม่ครบ

        app = main.ChargingStationApp(self.tmp_dir)
        messages = app.startup_check()

        self.assertTrue(any("ซ่อมแซม" in message for message in messages))
        self.assertTrue(app.store.integrity_check()[0])
        self.assertEqual(app.store.count_records(), 2)

    def test_startup_repairs_truncated_log_file(self):
        """ไฟล์ log ที่ถูกตัดกลางระเบียกต้องถูกซ่อมแซม"""
        self.add(1001)
        with open(self.app.log_path, "ab") as fh:
            fh.write(b"\x00" * 10)

        app = main.ChargingStationApp(self.tmp_dir)
        messages = app.startup_check()

        self.assertTrue(any("ซ่อมแซม" in message for message in messages))
        self.assertTrue(app.audit.integrity_check()[0])

    def test_startup_rebuilds_missing_index(self):
        """ดัชนีที่หายไปต้องถูกสร้างใหม่จาก log ได้"""
        self.add(1001)
        self.add(1002)
        os.remove(self.app.index_path)

        app = main.ChargingStationApp(self.tmp_dir)
        messages = app.startup_check()

        self.assertEqual(app.point_index.count(), 2)
        self.assertEqual(app.point_index.get(1001), 0)
        self.assertEqual(app.point_index.get(1002), 1)
        self.assertTrue(any("index" in message for message in messages))

    def test_startup_rebuilds_inconsistent_index(self):
        """ดัชนีที่ชี้ค่าผิดต้องถูกตรวจพบและสร้างใหม่"""
        self.add(1001)
        self.add(1002)
        # เขียนดัชนีผิด: ชี้ค่า seq ที่ไม่ถูกต้อง
        with open(self.app.index_path, "r+b") as fh:
            fh.seek(0)
            fh.write(models.pack_index_entry(models.IndexEntry(1001, 99)))

        app = main.ChargingStationApp(self.tmp_dir)
        messages = app.startup_check()

        self.assertTrue(any("ซ่อมแซม" in message for message in messages))
        self.assertEqual(app.point_index.get(1001), 0)
        self.assertEqual(app.point_index.verify_against_log(
            app.audit.read_all()), [])

    def test_rebuild_index_function(self):
        """ฟังก์ชันระดับโมดูล seed_data.rebuild_index สร้างดัชนีใหม่ได้"""
        self.add(1001)
        self.add(1002)
        os.remove(self.app.index_path)

        count = seed_data.rebuild_index(self.app.log_path, self.app.index_path)
        self.assertEqual(count, 2)
        self.assertTrue(os.path.exists(self.app.index_path))
        self.assertEqual(os.path.getsize(self.app.index_path), 2 * 8)

class TestSeedAndFullReport(AppTestCase):
    """ทดสอบข้อมูลตัวอย่างและรายงานฉบับเต็มแบบ end-to-end"""

    def seed_and_reload(self):
        """สร้างข้อมูลตัวอย่าง แล้วเปิดแอปใหม่เพื่ออ่านแคชของไฟล์ใหม่

        seed_data.seed() เขียนไฟล์ทั้งหมดใหม่ ตัวอินสแตนซ์เดิมจึงยังถือ
        ค่าแคชเก่า จึงต้องสร้าง ChargingStationApp ใหม่ทุกครั้งหลัง seed
        """
        seed_data.seed(self.tmp_dir, force=True, printer=None)
        self.app = main.ChargingStationApp(self.tmp_dir)
        return self.app

    def test_seed_creates_more_than_50_records(self):
        """ข้อมูลตัวอย่างต้องมีมากกว่า 50 ระเบียกตามข้อกำหนด"""
        app = self.seed_and_reload()
        self.assertGreater(app.store.count_records(), 50)
        self.assertEqual(app.store.count_records(), 55)

    def test_seed_creates_matching_log_and_index(self):
        """จำนวน log และ index ต้องเท่ากับจำนวนระเบียก"""
        app = self.seed_and_reload()
        records = app.store.count_records()
        self.assertEqual(self.app.audit.count(), records)
        self.assertEqual(self.app.point_index.count(), records)

    def test_seed_index_matches_log_after_rebuild(self):
        """หลัง seed ดัชนีต้องตรงกับ log สมบูรณ์"""
        app = self.seed_and_reload()
        self.assertEqual(app.point_index.verify_against_log(
            app.audit.read_all()), [])

    def test_seed_file_sizes_are_multiples_of_record_size(self):
        """ขนาดไฟล์ทุกไฟล์ต้องหารลงตัวด้วยขนาดระเบียนของมัน"""
        app = self.seed_and_reload()
        self.assertEqual(app.store.file_size() % models.RECORD_SIZE, 0)
        self.assertEqual(os.path.getsize(app.log_path)
                         % models.LOG_RECORD_SIZE, 0)
        self.assertEqual(os.path.getsize(app.index_path)
                         % models.INDEX_RECORD_SIZE, 0)

    def test_seed_includes_edge_cases(self):
        """ข้อมูลตัวอย่างต้องครอบคลุมขอบเขตที่กำหนด"""
        points = self.seed_and_reload().store.read_all(include_deleted=True)

        # มีระเบียกที่ถูก soft delete
        self.assertTrue(any(point.is_deleted for point in points))
        # มีหัวที่ถูกจองอยู่
        self.assertTrue(any(point.is_booked == 1 for point in points))
        # มีหัวที่ปิดซ่อมบำรุง (status=0)
        self.assertTrue(any(point.status == 0 for point in points))
        # มี location ที่ยาวครบ 30 ไบต์ (ขอบเขตเต็ม)
        self.assertTrue(
            any(models.text_byte_length(point.location) == 30 for point in points))
        # มี station_code ซ้ำกัน (สถานีเดียวกันมีหลายหัวชาร์จ)
        codes = [point.station_code for point in points]
        self.assertGreater(len(codes), len(set(codes)),
                           "ต้องมี station_code ที่ซ้ำกัน")
        # มีช่วงราคา/กำลังไฟกว้าง (ขอบเขตต่ำ/สูง)
        prices = [point.price_per_kwh for point in points]
        self.assertLess(min(prices), 6.0)
        self.assertGreater(max(prices), 9.0)

    def test_seed_no_location_exceeds_field_size(self):
        """หลัง seed ต้องไม่มี location เกิน 30 ไบต์ (ถูกตัดมาแล้ว)"""
        for point in self.seed_and_reload().store.read_all(
                include_deleted=True):
            self.assertLessEqual(models.text_byte_length(point.location), 30)
            self.assertNotIn("\ufffd", point.location)

    def test_full_report_from_seed_contains_summary(self):
        """รายงานฉบับเต็มจากข้อมูลตัวอย่างต้องมีสรุปและตารางครบ"""
        report_path = self.seed_and_reload().generate_report()

        self.assertTrue(os.path.exists(report_path))
        with open(report_path, "r", encoding="utf-8") as fh:
            content = fh.read()

        self.assertIn("EV Charging Station Booking System", content)
        self.assertIn("Endianness   : Little-Endian", content)
        self.assertIn("(+07:00)", content)
        self.assertIn("Price Statistics (THB/kWh, Active only)", content)
        self.assertIn("- Total Points (records) : 55", content)
        self.assertIn("Recent Activity", content)
        self.assertIn("Points by Plug Type (Active only)", content)

    def test_report_of_main_sample_matches_spec_numbers(self):
        """รายงานจากชุด 1001-1010 ต้องตรงกับตัวเลขในข้อกำหนด"""
        for spec in seed_data.MAIN_POINTS:
            fields = {key: value for key, value in spec.items()
                      if key != "is_deleted"}      # ใช้ delete_record แทนการส่งค่า
            self.add(**fields)
            if spec.get("is_deleted"):
                # จำลองสถานะ "ถูกลบแล้ว" ด้วยการ soft delete ตามตรรกะปกติ
                self.app.delete_record(spec["point_id"])

        report_path = self.app.generate_report()

        with open(report_path, "r", encoding="utf-8") as fh:
            content = fh.read()

        self.assertIn("- Total Points (records) : 10", content)
        self.assertIn("- Active Points          : 9", content)
        self.assertIn("- Deleted Points         : 1", content)
        self.assertIn("- Currently Booked       : 4", content)
        self.assertIn("- Available Now          : 5", content)
        self.assertIn("6.00 / 9.00 / 7.36", content)

    def test_shutdown_writes_report_and_fsyncs(self):
        """การออกโปรแกรมต้องสร้างรายงานและซีลข้อมูลทั้ง 3 ไฟล์"""
        self.add(1001)
        self.app._shutdown()
        self.assertTrue(os.path.exists(self.app.report_path))
        self.assertEqual(os.path.getsize(self.app.report_path) > 0, True)


class TestMenuLoopExit(AppTestCase):
    """ทดสอบลูปเมนู: เลือก 0 เพื่อออก และการจัดการ EOF"""

    def test_menu_exit_returns_zero(self):
        """เลือกเมนู 0 ต้องจบการทำงานและคืนรหัส 0"""
        import io as _io
        import sys

        original_stdin = sys.stdin
        sys.stdin = _io.StringIO("0\n")
        try:
            self.assertEqual(self.app.run(), 0)
        finally:
            sys.stdin = original_stdin

    def test_menu_handles_eof_gracefully(self):
        """EOF (ปิด stdin) ต้องออกอย่างสุภาพ ไม่ crash"""
        import io as _io
        import sys

        original_stdin = sys.stdin
        sys.stdin = _io.StringIO("")       # ไม่มีข้อมูลเลย = EOF ทันที
        try:
            self.assertEqual(self.app.run(), 0)
            self.assertTrue(os.path.exists(self.app.report_path),
                            "ต้องสร้างรายงานตอนออกโปรแกรม")
        finally:
            sys.stdin = original_stdin

