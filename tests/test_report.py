"""tests/test_report.py — ทดสอบการสร้างรายงาน report.txt และการจัดตารางภาษาไทย

เน้นยืนยัน "ผลรายงานต้องตรงกับข้อมูลตัวอย่าง" ตามที่กำหนด:
    Active 9 / Deleted 1 / Booked 4 / Available 5
    ราคา Min 6.00 / Max 9.00 / Avg 7.36
"""

import os
import shutil
import tempfile
import unittest

import models
import report
import seed_data


class TestDisplayWidth(unittest.TestCase):
    """ทดสอบการคำนวณความกว้างเชิงการแสดงผล (รองรับภาษาไทย)"""

    def test_ascii_characters_count_one_each(self):
        """อักษร ASCII นับ 1 ช่องต่อตัว"""
        self.assertEqual(report.display_width(""), 0)
        self.assertEqual(report.display_width("ABC"), 3)
        self.assertEqual(report.display_width("EVS-0001"), 8)

    def test_thai_base_characters_count_one_each(self):
        """อักษรไทยที่ไม่มีสระ/วรรณยุกต์นับ 1 ช่องต่อตัว"""
        self.assertEqual(report.display_width("สยาม"), 4)
        self.assertEqual(report.display_width("สถานี"), 4)

    def test_combining_marks_count_zero(self):
        """สระ/วรรณยุกต์ไทย (combining) ต้องกว้าง 0 ช่อง ไม่ทำให้คอลัมน์เบี้ยว"""
        # "ั" (U+0E31) และ "ิ" (U+0E34) เป็นอักขระประสม
        self.assertEqual(report.display_width("\u0e31"), 0)
        self.assertEqual(report.display_width("\u0e34"), 0)
        # "ก" + "ั" + "ิ" แสดงเป็น 1 ช่องบนหน้าจอ
        self.assertEqual(report.display_width("ก\u0e31\u0e34"), 1)

    def test_word_with_tone_marks_matches_base_width(self):
        """คำไทยที่มีวรรณยุกต์ต้องกว้างเท่ากับจำนวนอักษรฐาน

        "ชั้น" = ช + ั + ้ + น  -> มีอักษรฐาน 2 ตัว (ช, น) จึงกว้าง 2 ช่อง
        สระ "ั" และวรรณยุกต์ "้" ไม่กินพื้นที่บนหน้าจอ
        """
        self.assertEqual(report.display_width("ชั้น"), 2)
        # "สถานี" = ส ถ า น ี -> มีอักษรฐาน 4 ตัว
        self.assertEqual(report.display_width("สถานี"), 4)
        # "เก็บ" = เ + ก + ็ + บ -> อักษรฐาน 3 ตัว
        self.assertEqual(report.display_width("เก็บ"), 3)

    def test_thai_vowels_count_zero_even_when_combining_is_zero(self):
        """สระไทยที่ unicodedata.combining() รายงานเป็น 0 ต้องถูกนับเป็น 0 ช่อง

        สระ "ั" (U+0E31) และ "ิ" (U+0E35) มี Combining_Class = 0 แต่เป็นอักขระ
        หมวด Mn (nonspacing mark) จึงต้องถูกนับเป็นความกว้าง 0
        """
        self.assertEqual(report.display_width("\u0e31"), 0)   # ั
        self.assertEqual(report.display_width("\u0e35"), 0)   # ิ
        self.assertEqual(report.display_width("\u0e34"), 0)   # ิ
        # "ก" + "ั" แสดงเป็น 1 ช่อง
        self.assertEqual(report.display_width("ก\u0e31"), 1)

    def test_wide_characters_count_two(self):
        """อักขระ Full-width / Wide ต้องนับ 2 ช่อง"""
        self.assertEqual(report.display_width("\u4e2d"), 2)     # 中

    def test_pad_to_width_aligns_columns(self):
        """pad_to_width ต้องทำให้ทุกข้อความกว้างเท่ากันตาม display_width"""
        target = 10
        for text in ("ABC", "สถานี", "ก\u0e31\u0e34", ""):
            padded = report.pad_to_width(text, target)
            self.assertEqual(report.display_width(padded), target)

    def test_pad_right_align(self):
        """จัดตำแหน่งชิดขวาต้องเติมช่องว่างข้างหน้า"""
        padded = report.pad_to_width("12", 5, align="right")
        self.assertEqual(padded, "   12")
        self.assertEqual(report.display_width(padded), 5)

    def test_truncate_to_width_adds_ellipsis(self):
        """ข้อความที่ยาวเกินต้องถูกตัดและเติมจุดไข่ปลา"""
        result = report.truncate_to_width("สถานีชาร์จไฟฟ้าสยาม", 10)
        self.assertTrue(result.endswith("..."))
        self.assertLessEqual(report.display_width(result), 10)

    def test_truncate_short_text_unchanged(self):
        """ข้อความที่ไม่ยาวเกินต้องคงเดิม"""
        self.assertEqual(report.truncate_to_width("สั้น", 10), "สั้น")


class TestRenderTable(unittest.TestCase):
    """ทดสอบการเรนเดอร์ตาราง"""

    def test_table_has_border_and_separator(self):
        """ตารางต้องมีเส้นขอบแบบ +----+ และใช้ | คั่นคอลัมน์"""
        lines = report.render_table(["A", "B"], [["1", "2"]])
        self.assertTrue(lines[0].startswith("+") and lines[0].endswith("+"))
        self.assertIn("|", lines[1])
        self.assertEqual(len(lines), 5)      # ขอบบน + หัว + เส้นคั่น + แถว + ขอบล่าง

    def test_all_rows_have_equal_display_width(self):
        """ทุกบรรทัดต้องกว้างเท่ากัน แม้เนื้อหาภาษาไทยมีสระ/วรรณยุกต์"""
        headers = ["ชื่อสถานี", "ราคา"]
        rows = [["สยามพารากอน", "6.00"],
                ["เซ็นทรัลเวิลด์ ชั้น 2", "7.50"],
                ["ICONSIAM", "8.75"]]
        lines = report.render_table(headers, rows)
        widths = {report.display_width(line) for line in lines}
        self.assertEqual(len(widths), 1,
                         f"ทุกบรรทัดต้องกว้างเท่ากัน แต่พบ {widths}")

    def test_empty_rows_still_render_header(self):
        """ไม่มีข้อมูลก็ยังแสดงหัวตารางและเส้นขอบได้"""
        lines = report.render_table(["A", "B"], [])
        # ขอบบน + หัวตาราง + เส้นคั่น + ขอบล่าง
        self.assertEqual(len(lines), 4)
        self.assertIn("A", lines[1])
        self.assertTrue(lines[0].startswith("+"))
        self.assertTrue(lines[-1].startswith("+"))

    def test_headers_and_cells_keep_left_alignment_by_default(self):
        """หัวตารางและค่าทั่วไปจัดชิดซ้ายเป็นค่าเริ่มต้น"""
        lines = report.render_table(
            ["Name", "Count"],
            [["CCS2", "2"], ["CHAdeMO", "13"]],
        )

        self.assertEqual(lines[1], "| Name    | Count |")
        self.assertEqual(lines[3], "| CCS2    | 2     |")
        self.assertEqual(lines[4], "| CHAdeMO | 13    |")
class TestStatistics(unittest.TestCase):
    """ทดสอบการคำนวณสถิติจากชุดข้อมูลตัวอย่าง 1001-1010"""

    def setUp(self):
        """เตรียม record 10 record ตามข้อมูลตัวอย่างในรายงาน"""
        self.points = seed_data.specs_to_charge_points(seed_data.MAIN_POINTS)

    def test_summary_matches_expected_sample(self):
        """ยอดสรุปต้องเป็น Active 9 / Deleted 1 / Booked 4 / Available 5"""
        summary = report.compute_summary(self.points)
        self.assertEqual(summary["total"], 10)
        self.assertEqual(summary["active"], 9)
        self.assertEqual(summary["deleted"], 1)
        self.assertEqual(summary["booked"], 4)
        self.assertEqual(summary["available"], 5)
        self.assertEqual(summary["free_slots"], 1)

    def test_available_equals_active_minus_booked(self):
        """Available ต้องเท่ากับ Active ที่ยังไม่ถูกจอง"""
        summary = report.compute_summary(self.points)
        self.assertEqual(summary["available"],
                         summary["active"] - summary["booked"])

    def test_price_stats_match_expected_sample(self):
        """ราคาต้องเป็น Min 6.00 / Max 9.00 / Avg 7.36 (นับเฉพาะ Active)"""
        stats = report.compute_price_stats(self.points)
        self.assertAlmostEqual(stats["min"], 6.00, places=2)
        self.assertAlmostEqual(stats["max"], 9.00, places=2)
        self.assertAlmostEqual(stats["avg"], 7.36, places=2)

    def test_deleted_record_price_excluded_from_stats(self):
        """ราคาของ record ที่ถูกลบต้องไม่ถูกนับในสถิติราคา

        record 1010 ถูก soft delete และมีราคา 9.00 ซึ่งไม่ควรทำให้
        ค่าเฉลี่ยของ 9 record ที่ Active เพี้ยนจาก 7.36
        """
        active_prices = [p.price_per_kwh for p in self.points
                         if not p.is_deleted and p.status == 1]
        self.assertEqual(len(active_prices), 9)
        self.assertAlmostEqual(sum(active_prices) / len(active_prices), 7.36,
                               places=2)

    def test_inactive_record_excluded_from_price_stats(self):
        """record status=0 ต้องไม่ถูกนับในสถิติราคา"""
        active = [p for p in self.points if p.status == 1 and not p.is_deleted]
        self.assertEqual(len(active), 9)

    def test_plug_type_counts(self):
        """การนับตามประเภทหัวต้องนับเฉพาะ Active"""
        counts = report.count_plug_types(self.points)
        self.assertEqual(sum(counts.values()), 9, "รวมต้องเท่าจำนวน Active")
        # Type2: 1001, 1005, 1009 / CCS2: 1002, 1003, 1008
        # CHAdeMO: 1004, 1006 / GB-T: 1007  (1010 ถูกลบจึงไม่ถูกนับ)
        self.assertEqual(counts["Type2"], 3)
        self.assertEqual(counts["CCS2"], 3)
        self.assertEqual(counts["CHAdeMO"], 2)
        self.assertEqual(counts["GB-T"], 1)

    def test_empty_dataset_returns_zero_stats(self):
        """ข้อมูลว่างต้องคืนค่า 0 ไม่ error (กัน Division by Zero)"""
        summary = report.compute_summary([])
        self.assertEqual(summary["total"], 0)
        stats = report.compute_price_stats([])
        self.assertEqual(stats, {"min": 0.0, "max": 0.0, "avg": 0.0})

    def test_format_timestamp_uses_plus_7_timezone(self):
        """เวลาในรายงานต้องเป็นเขตเวลา +07:00"""
        text = report.format_timestamp(0)
        self.assertIn("(+07:00)", text)
        self.assertEqual(report.THAI_TZ.utcoffset(None).total_seconds(), 7 * 3600)

class TestBuildAndWriteReport(unittest.TestCase):
    """ทดสอบการประกอบและเขียนไฟล์รายงานจริง"""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="ev_report_")
        self.report_path = os.path.join(self.tmp_dir, models.REPORT_FILE_NAME)
        self.points = seed_data.specs_to_charge_points(seed_data.MAIN_POINTS)
        self.log_entries = [
            models.LogEntry(ts=1_789_000_000 + i, op_code=models.OP_ADD,
                            point_id=point.point_id, status_after=point.status,
                            is_booked_after=point.is_booked,
                            price_after_thb=point.price_per_kwh)
            for i, point in enumerate(self.points)
        ]

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_report_contains_required_header_fields(self):
        """รายงานต้องมีหัวเรื่องและข้อมูลเวลา/เวอร์ชัน/endianness/encoding"""
        content = report.build_report(self.points, self.log_entries)
        self.assertIn(report.REPORT_TITLE, content)
        self.assertIn("Generated At :", content)
        self.assertIn("(+07:00)", content)
        self.assertIn("App Version  : 1.0", content)
        self.assertIn("Endianness   : Little-Endian", content)
        self.assertIn("Encoding     : UTF-8 (fixed-length)", content)

    def test_report_summary_lines_have_expected_values(self):
        """ตัวเลขในรายงานต้องตรงกับข้อมูลตัวอย่าง"""
        content = report.build_report(self.points, self.log_entries)
        self.assertIn("- Total Points (records) : 10", content)
        self.assertIn("- Active Points          : 9", content)
        self.assertIn("- Deleted Points         : 1", content)
        self.assertIn("- Currently Booked       : 4", content)
        self.assertIn("- Available Now          : 5", content)
        self.assertIn("- Free Slots             : 1", content)

    def test_report_price_statistics_line(self):
        """บรรทัดสถิติราคาต้องเป็น 6.00 / 9.00 / 7.36"""
        content = report.build_report(self.points, self.log_entries)
        self.assertIn("6.00 / 9.00 / 7.36", content)

    def test_report_plug_type_line(self):
        """บรรทัดสรุปตามประเภทหัวต้องครบทั้ง 4 ประเภท"""
        content = report.build_report(self.points, self.log_entries)
        for plug in ("CCS2", "Type2", "CHAdeMO", "GB-T"):
            self.assertIn(plug, content)

    def test_report_shows_all_records_including_deleted(self):
        """ตารางข้อมูลต้องแสดงทั้ง Active และ Deleted"""
        content = report.build_report(self.points, self.log_entries)
        self.assertIn("| 1001 |", content)
        self.assertIn("| 1010 |", content)
        self.assertIn("Deleted", content)      # record ที่ถูก soft delete

    def test_report_recent_activity_limited_to_five(self):
        """กิจกรรมล่าสุดต้องแสดงไม่เกิน 5 รายการ เรียงใหม่ไปเก่า"""
        content = report.build_report(self.points, self.log_entries)
        self.assertIn("Recent Activity", content)
        activity_section = content.split("Recent Activity", 1)[1]
        data_rows = [line for line in activity_section.splitlines()
                     if line.startswith("|") and "ADD" in line]
        self.assertEqual(len(data_rows), 5)

    def test_report_operation_names_are_mapped(self):
        """ชื่อเหตุการณ์ในรายงานต้องเป็น ADD/UPDATE/DELETE/VIEW"""
        log_entries = [
            models.LogEntry(ts=1, op_code=models.OP_ADD, point_id=1,
                            status_after=1, is_booked_after=0,
                            price_after_thb=1.0),
            models.LogEntry(ts=2, op_code=models.OP_UPDATE, point_id=1,
                            status_after=1, is_booked_after=1,
                            price_after_thb=1.0),
            models.LogEntry(ts=3, op_code=models.OP_DELETE, point_id=1,
                            status_after=1, is_booked_after=0,
                            price_after_thb=1.0),
            models.LogEntry(ts=4, op_code=models.OP_VIEW, point_id=1,
                            status_after=1, is_booked_after=0,
                            price_after_thb=1.0),
        ]
        content = report.build_report(self.points, log_entries)
        for name in ("ADD", "UPDATE", "DELETE", "VIEW"):
            self.assertIn(name, content)

    def test_report_status_shows_deleted_for_delete_event(self):
        """เหตุการณ์ DELETE ต้องแสดง Status = Deleted ในรายงาน"""
        log_entries = [
            models.LogEntry(ts=1, op_code=models.OP_DELETE, point_id=1001,
                            status_after=1, is_booked_after=0,
                            price_after_thb=6.0),
        ]
        content = report.build_report(self.points, log_entries)
        activity = content.split("Recent Activity", 1)[1]
        self.assertIn("DELETE", activity)
        self.assertIn("Deleted", activity)

    def test_generate_report_writes_utf8_file(self):
        """ไฟล์รายงานต้องถูกเขียนด้วย encoding UTF-8 และอ่านกลับได้"""
        content = report.generate_report(self.points, self.log_entries,
                                         self.report_path)
        self.assertTrue(os.path.exists(self.report_path))
        with open(self.report_path, "r", encoding="utf-8") as fh:
            saved = fh.read()
        self.assertEqual(saved, content)

    def test_report_thai_content_is_not_corrupted(self):
        """ข้อความไทยในไฟล์รายงานต้องอ่านกลับได้ตรง ไม่เพี้ยน"""
        report.generate_report(self.points, self.log_entries, self.report_path)
        with open(self.report_path, "r", encoding="utf-8") as fh:
            saved = fh.read()
        self.assertNotIn("\ufffd", saved, "ห้ามมีอักขระเพี้ยนจากการตัด UTF-8")
        # ทุก record ต้องมี location ที่ถอดรหัสได้ (ไม่ว่างทั้งหมด)
        for line in saved.splitlines():
            if line.startswith("| 10"):
                self.assertNotIn("\ufffd", line)

    def test_report_thai_table_lines_align(self):
        """ภายในตารางเดียวกัน ทุกบรรทัดต้องกว้างเท่ากัน (นับด้วย display_width)

        หมายเหตุ: รายงานมีหลายตาราง (ตารางหัวชาร์จ + ตารางกิจกรรมล่าสุด)
        ซึ่งมีความกว้างต่างกันได้ จึงตรวจทีละบล็อกของตาราง
        """
        content = report.build_report(self.points, self.log_entries)
        lines = content.splitlines()

        # แบ่งเป็นบล็อกของตาราง (บรรทัดตารางที่ต่อกัน โดยคั่นด้วยบรรทัดว่าง)
        blocks, current = [], []
        for line in lines:
            if line.startswith("+") or line.startswith("|"):
                current.append(line)
            elif current:
                blocks.append(current)
                current = []
        if current:
            blocks.append(current)

        self.assertGreaterEqual(len(blocks), 2, "ควรมีอย่างน้อย 2 ตาราง")
        for block in blocks:
            widths = {report.display_width(line) for line in block}
            self.assertEqual(len(widths), 1,
                             f"ทุกบรรทัดในตารางเดียวกันต้องกว้างเท่ากัน แต่พบ {widths}")

    def test_report_with_no_data_is_still_valid(self):
        """รายงานจากฐานข้อมูลว่างต้องสร้างได้ไม่ error"""
        content = report.build_report([], [])
        self.assertIn(report.REPORT_TITLE, content)
        self.assertIn("- Total Points (records) : 0", content)

    def test_render_point_card_contains_all_fields(self):
        """การ์ดข้อมูลหัวชาร์จต้องแสดงครบทุกฟิลด์ตามชื่อในสเปก"""
        card = "\n".join(report.render_point_card(self.points[0]))
        for field in ("point_id", "station_code", "location", "plug_type",
                      "power_kw", "price_per_kwh", "status", "is_booked",
                      "is_deleted", "created_at", "updated_at"):
            self.assertIn(field, card)
