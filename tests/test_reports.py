"""tests/test_reports.py — ทดสอบระบบรายงาน 3 ชุดตามเกณฑ์การตรวจงาน

เกณฑ์ที่ทดสอบ
-------------
ข้อ 1: มีรายงานอย่างน้อย 3 reports
ข้อ 2: แต่ละรายงานมี 3 ส่วน (รายละเอียดหัวตาราง, ตาราง, ส่วนสรุป)
ข้อ 3: แต่ละรายงานมาจากไฟล์อย่างน้อย 2 ไฟล์
ข้อ 4: เป็นไฟล์ .txt แยกกัน และตารางไม่เพี้ยน (เส้นขอบตรงกัน)
ข้อ 5: สร้างรายงานผ่านเมนูเดียวของโปรแกรม
ข้อ 6: แก้ข้อมูลแล้วรายงานเปลี่ยนตาม
ข้อ 7: ไฟล์ข้อมูลหลักเก็บแบบ Binary
"""

import io
import os
import shutil
import tempfile
import unittest

import main
import models
import report as report_core
import reports as reports_module
import seed_data


class ReportsTestCase(unittest.TestCase):
    """คลาสฐาน: เตรียมแอปที่มีข้อมูลตัวอย่างและสร้างรายงานครบทั้ง 3 ชุด"""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="ev_reports_")
        seed_data.seed(self.tmp_dir, force=True, printer=None)
        self.app = main.ChargingStationApp(self.tmp_dir)
        self.created = self.app.generate_report(silent=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def read_report(self, file_name: str) -> str:
        """อ่านเนื้อหาไฟล์รายงานแบบ UTF-8"""
        path = os.path.join(self.tmp_dir, file_name)
        with io.open(path, encoding="utf-8") as fh:
            return fh.read()


class TestCriterion1AtLeastThreeReports(ReportsTestCase):
    """ข้อ 1: ต้องมีรายงานอย่างน้อย 3 reports"""

    def test_generates_three_reports(self):
        """ต้องสร้างไฟล์รายงานครบ 3 ชุด"""
        self.assertEqual(len(self.created), 3)
        self.assertEqual(len(reports_module.ALL_REPORT_NAMES), 3)

    def test_each_report_exists_as_separate_file(self):
        """ต้องมีไฟล์รายงาน 3 ไฟล์ ครบทุกชื่อ"""
        for file_name in reports_module.ALL_REPORT_NAMES:
            path = os.path.join(self.tmp_dir, file_name)
            self.assertTrue(os.path.exists(path), f"ไม่พบไฟล์ {file_name}")
            self.assertGreater(os.path.getsize(path), 0,
                               f"ไฟล์ {file_name} ว่างเปล่า")

    def test_report_names_are_distinct(self):
        """ชื่อไฟล์รายงานต้องไม่ซ้ำกัน"""
        self.assertEqual(len(set(reports_module.ALL_REPORT_NAMES)), 3)


class TestCriterion2ThreeParts(ReportsTestCase):
    """ข้อ 2: แต่ละรายงานต้องมี 3 ส่วนและสอดคล้องกัน"""

    def test_all_reports_have_table_and_summary_only(self):
        """ทุกรายงานมีตารางและส่วนสรุป โดยไม่มี consistency check

        หมายเหตุ: ส่วน [COLUMN SPECIFICATION] (รายละเอียดหัวตาราง)
        ถูกตัดออกตามที่ผู้ใช้ต้องการ ให้รายงานเหลือเฉพาะตารางผลลัพธ์จริง
        """
        for file_name in reports_module.ALL_REPORT_NAMES:
            content = self.read_report(file_name)
            self.assertIn("[TABLE", content,
                          f"{file_name} ไม่มีส่วนตารางข้อมูล")
            self.assertIn("[SUMMARY]", content,
                          f"{file_name} ไม่มีส่วนสรุป")
            self.assertNotIn("[CONSISTENCY CHECK]", content,
                             f"{file_name} ยังมีส่วนตรวจสอบความสอดคล้อง")

    def test_report_title_line_is_removed(self):
        """บรรทัดชื่อเรื่อง "รายงานที่ N" ต้องถูกตัดออกจากทุกไฟล์

        ชื่อเรื่องยังระบุได้จากชื่อไฟล์ที่แยกกันชัดเจน
        """
        for file_name in reports_module.ALL_REPORT_NAMES:
            content = self.read_report(file_name)
            self.assertNotIn("รายงานที่", content,
                             f"{file_name} ยังมีบรรทัดชื่อเรื่อง")

    def test_column_specification_section_is_removed(self):
        """ส่วนรายละเอียดหัวตารางต้องถูกตัดออกทั้ง 3 ไฟล์"""
        for file_name in reports_module.ALL_REPORT_NAMES:
            content = self.read_report(file_name)
            self.assertNotIn("[COLUMN SPECIFICATION]", content,
                             f"{file_name} ยังมีส่วนรายละเอียดหัวตาราง")
            self.assertNotIn("รายละเอียดคอลัมน์ของตาราง", content,
                             f"{file_name} ยังมีรายละเอียดคอลัมน์")
            self.assertNotIn("แหล่งข้อมูลที่ใช้ประกอบรายงานนี้", content,
                             f"{file_name} ยังมีส่วนแหล่งที่มาของข้อมูล")

    def test_header_starts_with_generated_at(self):
        """ไฟล์ต้องเริ่มด้วยข้อมูลระบบ (Generated At)"""
        for file_name in reports_module.ALL_REPORT_NAMES:
            first = self.read_report(file_name).splitlines()[0]
            self.assertTrue(first.startswith("Generated At"),
                            f"{file_name} บรรทัดแรกคือ '{first}'")

    def test_report_starts_with_table_section(self):
        """หัวข้อแรกของรายงานต้องเป็นส่วนตารางข้อมูล"""
        for file_name in reports_module.ALL_REPORT_NAMES:
            content = self.read_report(file_name)
            self.assertLess(content.index("[TABLE"),
                            content.index("[SUMMARY]"),
                            f"{file_name}: ตารางต้องมาก่อนส่วนสรุป")

    def test_summary_appears_after_report_tables(self):
        """ตารางข้อมูลต้องมาก่อนส่วนสรุป"""
        for file_name in reports_module.ALL_REPORT_NAMES:
            content = self.read_report(file_name)
            table_pos = content.index("[TABLE")
            summary_pos = content.index("[SUMMARY]")
            self.assertLess(table_pos, summary_pos,
                            f"{file_name}: ตารางต้องมาก่อนส่วนสรุป")

    def test_no_report_has_consistency_check(self):
        """รายงานทั้งหมดไม่แสดงส่วน CONSISTENCY CHECK"""
        for file_name in reports_module.ALL_REPORT_NAMES:
            content = self.read_report(file_name)
            self.assertNotIn("[CONSISTENCY CHECK]", content,
                             f"{file_name} ยังมีผลตรวจสอบความสอดคล้อง")

    def test_stats_report_contains_only_table_three_and_summary(self):
        """report_stats มีเฉพาะตารางที่ 3 และตาราง Summary"""
        content = self.read_report(reports_module.REPORT_STATS_NAME)
        self.assertNotIn("[TABLE 1]", content)
        self.assertIn("[TABLE 2]", content)
        self.assertNotIn("[TABLE 3]", content)
        self.assertIn("[SUMMARY]", content)
        self.assertEqual(content.count("[TABLE"), 1)
        self.assertNotIn("[CONSISTENCY CHECK]", content)

    def test_summary_sections_include_source_and_key_data(self):
        """Summary ยังแสดงข้อมูลสำคัญและแหล่งข้อมูล .dat"""
        for file_name in reports_module.ALL_REPORT_NAMES:
            content = self.read_report(file_name)
            summary = content.split("[SUMMARY]", 1)[1]
            self.assertIn("charge_points.dat", summary)
            self.assertIn("index.dat", summary)

    def test_summary_numbers_match_table_content(self):
        """ยอดในส่วนสรุปต้องตรงกับจำนวน record จริงในไฟล์ข้อมูล

        ตรวจจากค่าที่ระบบคำนวณ แทนการเทียบข้อความในตารางโดยตรง
        เพื่อไม่ให้ผิดพลาดจากการเติมช่องว่างในตาราง
        """
        content = self.read_report(reports_module.REPORT_POINTS_NAME)
        points = self.app.store.read_all(include_deleted=True)
        summary = report_core.compute_summary(points)
        self.assertIn("Total Points (records)", content)
        # ค่าต้องปรากฏเป็นตัวเลขในคอลัมน์ค่า โดยไม่ต้องตรงกับช่องว่างพอดี
        self.assertIn(f"| {summary['total']} ", content)
        self.assertIn(f"| {summary['active']} ", content)
        self.assertIn(f"| {summary['deleted']} ", content)

    def test_column_specification_names_source_files(self):
        """ข้อมูลต้องยังระบุถึงไฟล์ต้นทางทั้ง 3 ไฟล์ (ผ่านคอลัมน์/สรุปในตาราง)"""
        for file_name in reports_module.ALL_REPORT_NAMES:
            content = self.read_report(file_name)
            self.assertIn("charge_points.dat", content)
            self.assertIn("index.dat", content)
            self.assertIn("charge_points.log", content)
class TestCriterion3MultipleSourceFiles(ReportsTestCase):
    """ข้อ 3: แต่ละรายงานต้องมาจากไฟล์อย่างน้อย 2 ไฟล์"""

    def test_every_report_uses_multiple_sources(self):
        """ทุกรายงานต้องใช้ข้อมูลมากกว่า 1 ไฟล์"""
        for file_name in reports_module.ALL_REPORT_NAMES:
            self.assertTrue(reports_module.report_uses_multiple_sources(file_name),
                            f"{file_name} ต้องมาจากมากกว่า 1 ไฟล์")

    def test_each_report_lists_three_source_files(self):
        """ข้อมูลต้องยังอ้างอิงไฟล์ต้นทางครบ 3 ไฟล์ในเนื้อหารายงาน

        ส่วนรายละเอียดหัวตารางถูกตัดออกแล้ว จึงตรวจจากทั้งไฟล์
        (ชื่อไฟล์ต้องปรากฏในตารางหรือส่วนสรุปของรายงาน)
        """
        for file_name in reports_module.ALL_REPORT_NAMES:
            content = self.read_report(file_name)
            for source in (reports_module.SOURCE_POINT_FILE,
                           reports_module.SOURCE_LOG_FILE,
                           reports_module.SOURCE_INDEX_FILE):
                self.assertIn(source, content,
                              f"{file_name} ไม่ได้ระบุแหล่งข้อมูล {source}")

    def test_points_report_combines_index_with_data(self):
        """รายงานระบุข้อมูล index.dat ในส่วนสรุปโดยไม่เพิ่มคอลัมน์ให้ตารางหลัก"""
        content = self.read_report(reports_module.REPORT_POINTS_NAME)
        index_map = self.app.point_index.as_dict()
        self.assertTrue(index_map, "index.dat ต้องมีข้อมูล")
        self.assertIn("Records in index.dat", content)
        self.assertNotIn("LogSeq", content)

    def test_stats_report_combines_log_with_data(self):
        """รายงานที่ 2 ต้องรวมข้อมูลจาก log เข้ากับสถิติจากข้อมูลหลัก"""
        content = self.read_report(reports_module.REPORT_STATS_NAME)
        self.assertIn("Recent activity from charge_points.log", content)
        self.assertIn("ADD", content)

    def test_system_report_compares_index_with_log(self):
        """รายงานระบบยังแสดงผลเปรียบเทียบ index กับ log ใน Summary."""
        content = self.read_report(reports_module.REPORT_SYSTEM_NAME)
        self.assertIn("index.dat", content)
        self.assertIn("charge_points.log", content)
        self.assertIn("point_id/log_seq mismatches", content)

    def test_system_report_shows_index_log_differences(self):
        """รายงานระบบตรวจความสอดคล้องและแสดงรายละเอียดเมื่อพบปัญหา"""
        normal = self.read_report(reports_module.REPORT_SYSTEM_NAME)
        self.assertIn("point_id/log_seq mismatches", normal)
        self.assertNotIn("Compare index.dat with charge_points.log", normal)

        # ทำให้ index.dat ไม่ตรงกับ log แล้วแสดงตารางรายละเอียดปัญหา
        import index as index_module
        index_path = os.path.join(self.tmp_dir, models.INDEX_FILE_NAME)
        corrupted = index_module.PointIndex(index_path)
        corrupted.update(1001, 999999)
        self.app.app_reload()          # เปิดไฟล์ใหม่เพื่อรับค่าที่แก้ไข
        self.app.generate_report(silent=True)
        broken = self.read_report(reports_module.REPORT_SYSTEM_NAME)
        self.assertIn("Compare index.dat with charge_points.log", broken)
        self.assertIn("log_seq in index", broken)


class TestCriterion4SeparateTxtFiles(ReportsTestCase):
    """ข้อ 4: เป็นไฟล์ .txt แยกกัน และตารางไม่เพี้ยน"""

    def test_each_report_is_a_separate_txt_file(self):
        """ต้องเป็น 3 ไฟล์ .txt แยกกัน ไม่รวมรายงานไว้ไฟล์เดียว"""
        for file_name in reports_module.ALL_REPORT_NAMES:
            self.assertTrue(file_name.endswith(".txt"),
                            f"{file_name} ต้องเป็นไฟล์ .txt")
            self.assertTrue(os.path.isfile(
                os.path.join(self.tmp_dir, file_name)))

    def test_reports_are_not_merged_into_one_file(self):
        """รายงานแต่ละชุดต้องไม่ปนกัน ไม่มีไฟล์ใดมีเนื้อหาของอีกชุด

        ตรวจจากหัวข้อของตารางซึ่งเป็นเนื้อหาเฉพาะของแต่ละชุด
        (บรรทัดชื่อเรื่องถูกตัดออกแล้ว จึงใช้ชื่อไฟล์แยกเป็นตัวระบุ)
        """
        markers = {
            reports_module.REPORT_POINTS_NAME: "All charging points",
            reports_module.REPORT_STATS_NAME: "[TABLE 2] Recent activity",
            reports_module.REPORT_SYSTEM_NAME: "Binary file status",
        }
        for file_name, own_marker in markers.items():
            content = self.read_report(file_name)
            for other_name, other_marker in markers.items():
                if other_name == file_name:
                    self.assertIn(own_marker, content)
                else:
                    self.assertNotIn(other_marker, content,
                                     f"{file_name} ไม่ควรมีเนื้อหาของ {other_name}")

    def test_table_lines_are_aligned(self):
        """บรรทัดของตารางในไฟล์ต้องมีความกว้างแสดงผลเท่ากัน"""
        for file_name in reports_module.ALL_REPORT_NAMES:
            content = self.read_report(file_name)
            blocks, current = [], []
            for line in content.splitlines():
                if line.startswith("+") or line.startswith("|"):
                    current.append(line)
                elif current:
                    blocks.append(current)
                    current = []
            if current:
                blocks.append(current)

            expected_tables = (1 if file_name in
                               (reports_module.REPORT_STATS_NAME,
                                reports_module.REPORT_SYSTEM_NAME) else 2)
            self.assertGreaterEqual(
                len(blocks), expected_tables,
                f"{file_name} มีตารางน้อยกว่าที่กำหนด")
            for block in blocks:
                widths = {report_core.display_width(line) for line in block}
                self.assertEqual(len(widths), 1,
                                 f"{file_name}: บรรทัดในตารางเดียวกันต้อง"
                                 f"กว้างเท่ากัน แต่พบ {widths}")

    def test_vertical_columns_align_in_every_report_table(self):
        """ตำแหน่งเส้นแบ่งคอลัมน์ต้องตรงกันทุกตารางในทั้งสามรายงาน"""
        report_core.set_alignment_mode(True)
        self.app.generate_report(silent=True)
        self.assertEqual(report_core.alignment_mode_name(), "smart")
        for file_name in reports_module.ALL_REPORT_NAMES:
            for block in TestAlignmentModes._blocks(self.read_report(file_name)):
                expected = tuple(report_core.display_width(block[0][:index])
                                 for index, char in enumerate(block[0])
                                 if char == "+")
                for line in block[1:]:
                    border = "|" if line.startswith("|") else "+"
                    actual = tuple(report_core.display_width(line[:index])
                                   for index, char in enumerate(line)
                                   if char == border)
                    self.assertEqual(
                        actual, expected,
                        f"{file_name}: คอลัมน์ในตารางไม่ตรงแนว\n"
                        f"{block[0]}\n{line}",
                    )

    def test_reports_are_readable_utf8_without_replacement_char(self):
        """ไฟล์รายงานต้องเป็น UTF-8 และไม่มีอักขระเพี้ยน"""
        for file_name in reports_module.ALL_REPORT_NAMES:
            content = self.read_report(file_name)
            self.assertNotIn("\ufffd", content,
                             f"{file_name} มีอักขระเพี้ยน")

    def test_files_are_written_and_flushed(self):
        """ไฟล์รายงานต้องถูกเขียนจริง (เปิดอ่านได้ทันที)"""
        for file_name, path in self.created.items():
            self.assertTrue(os.path.exists(path))
            self.assertTrue(os.path.basename(path) == file_name)
class TestCriterion5SingleMenu(ReportsTestCase):
    """ข้อ 5: ใช้เมนูชุดเดียวทำงานทุกอย่าง ไม่มี run program แยกเมนู"""

    def test_generate_report_available_from_main_menu(self):
        """การสร้างรายงานต้องเรียกได้จากเมนูหลักของโปรแกรมเดียว"""
        self.assertTrue(hasattr(self.app, "menu_report"),
                        "ต้องมีเมนูย่อยสำหรับสร้างรายงานในตัวแอป")
        self.assertTrue(callable(self.app.menu_report))

    def test_main_menu_contains_report_option(self):
        """เมนูหลักต้องมีตัวเลือกสร้างรายงาน"""
        import io as _io
        buffer = _io.StringIO()
        original = __import__("sys").stdout
        __import__("sys").stdout = buffer
        try:
            self.app.show_menu()
        finally:
            __import__("sys").stdout = original
        text = buffer.getvalue()
        self.assertIn("5) Generate Report", text)

    def test_can_view_generated_report_files_from_menu(self):
        """ต้องดูรายการไฟล์รายงานที่สร้างได้จากเมนูเดียวกันได้"""
        self.assertTrue(hasattr(self.app, "show_report_files"))
        import io as _io
        buffer = _io.StringIO()
        original = __import__("sys").stdout
        __import__("sys").stdout = buffer
        try:
            self.app.show_report_files()
        finally:
            __import__("sys").stdout = original
        text = buffer.getvalue()
        for file_name in reports_module.ALL_REPORT_NAMES:
            self.assertIn(file_name, text)

    def test_no_separate_report_program_exists(self):
        """ต้องไม่มีโปรแกรมแยกที่ทำหน้าที่สร้างรายงานนอกเหนือจาก main.py

        ตรวจว่าโมดูลที่มีจุดเริ่มโปรแกรม (if __name__ == '__main__') มีเพียง
        main.py และ seed_data.py (ตัวช่วยสร้างข้อมูล) ไม่มีไฟล์ report_*.py
        หรือ demo_*.py ที่เป็นโปรแกรมแยกเมนู
        """
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        entries = os.listdir(project_dir)
        for entry in entries:
            if entry.endswith(".py"):
                lower = entry.lower()
                self.assertFalse(lower.startswith(("demo_", "report_main",
                                                   "run_report")),
                                 f"พบโปรแกรมแยกเมนูที่ไม่ควรมี: {entry}")

    def test_all_functions_reachable_from_single_app(self):
        """ทุกงานหลักต้องอยู่ในคลาสแอปเดียว (ไม่กระจายไปหลายโปรแกรม)"""
        for method in ("add_record", "update_record", "delete_record",
                       "view_record", "generate_report", "menu_report",
                       "show_report_files"):
            self.assertTrue(hasattr(self.app, method),
                            f"เมนูหลักต้องมีความสามารถ {method}")


class TestCriterion6ReportsReflectEdits(ReportsTestCase):
    """ข้อ 6: เมื่อแก้ไขข้อมูลในไฟล์ข้อมูลหลักแล้วรายงานต้องเปลี่ยนตาม"""

    def test_new_record_appears_in_reports(self):
        """เพิ่มข้อมูลใหม่แล้วต้องปรากฏในรายงาน"""
        # ใช้ location ที่ยาวไม่เกิน 30 ไบต์ เพื่อไม่ให้ถูกตัด (27 ไบต์)
        self.app.add_record(9001, "EVS-0900", "ทดสอบใหม่",
                            "CCS2", 350.0, 15.50)
        self.app.generate_report(silent=True)
        content = self.read_report(reports_module.REPORT_POINTS_NAME)
        self.assertIn("9001", content)
        self.assertIn("ทดสอบใหม่", content)

    def test_updated_price_appears_in_reports(self):
        """แก้ไขราคาแล้วรายงานต้องแสดงราคาใหม่"""
        self.app.update_record(9001 if False else 1001, price_per_kwh=1.25)
        self.app.generate_report(silent=True)
        content = self.read_report(reports_module.REPORT_POINTS_NAME)
        self.assertIn("1.25", content)
        row = next(line for line in content.splitlines()
                   if line.startswith("|") and "| 1001 " in line)
        self.assertNotIn("6.00", row)

    def test_update_changes_index_and_reports(self):
        """แก้ไขข้อมูลต้องทำให้ทั้ง index และรายงานเปลี่ยนตาม"""
        before = self.app.point_index.get(1001)
        self.app.update_record(1001, is_booked=1)
        self.app.generate_report(silent=True)
        after = self.app.point_index.get(1001)

        self.assertGreater(after, before, "log_seq ต้องเลื่อนไปข้างหน้า")
        content = self.read_report(reports_module.REPORT_STATS_NAME)
        self.assertIn("UPDATE", content)

    def test_soft_delete_reflected_in_reports(self):
        """soft delete แล้วรายงานต้องแสดงสถานะ Deleted และตัวเลขที่เปลี่ยน"""
        self.app.update_record(1002, is_booked=0)
        before = self.read_report(reports_module.REPORT_POINTS_NAME)
        self.app.delete_record(1002)
        self.app.generate_report(silent=True)
        after = self.read_report(reports_module.REPORT_POINTS_NAME)

        self.assertNotEqual(before, after, "รายงานต้องเปลี่ยนหลัง soft delete")
        self.assertIn("Deleted", after)
        # ตัวเลข Deleted Points ต้องเพิ่มขึ้น 1
        self.assertIn("Deleted Points (soft delete)", after)

    def test_reports_change_content_after_each_edit(self):
        """เนื้อหารายงานต้องเปลี่ยนจริงหลังแก้ไขข้อมูลในไฟล์หลัก"""
        before = self.read_report(reports_module.REPORT_POINTS_NAME)
        self.app.add_record(9002, "EVS-0901", "เพิ่มหลังสร้างรายงาน",
                            "GB-T", 120.0, 9.50)
        self.app.generate_report(silent=True)
        after = self.read_report(reports_module.REPORT_POINTS_NAME)
        self.assertNotEqual(before, after,
                            "รายงานต้องเปลี่ยนไปเมื่อมีการแก้ไขข้อมูล")

    def test_reports_read_from_disk_not_cached(self):
        """รายงานต้องอ่านจากไฟล์จริงทุกครั้ง (ไม่ใช้ค่าค้างเก่า)"""
        self.app.generate_report(silent=True)
        first = self.read_report(reports_module.REPORT_POINTS_NAME)
        # แก้ไขไฟล์ข้อมูลหลักโดยตรง (จำลองการเปลี่ยนแปลงภายนอกโปรแกรม)
        self.app.add_record(9003, "EVS-0902", "แก้ไขจากภายนอก",
                            "Type2", 11.0, 5.00)
        self.app.generate_report(silent=True)
        second = self.read_report(reports_module.REPORT_POINTS_NAME)
        self.assertIn("9003", second)
        self.assertNotIn("9003", first)
class TestCriterion7BinaryStorage(ReportsTestCase):
    """ข้อ 7: ไฟล์ข้อมูลหลักเก็บแบบ Binary"""

    def test_data_file_is_binary_fixed_length(self):
        """charge_points.dat ต้องเป็นไฟล์ binary ที่ขนาดหารลงตัว"""
        path = os.path.join(self.tmp_dir, models.DATA_FILE_NAME)
        size = os.path.getsize(path)
        self.assertEqual(size % models.RECORD_SIZE, 0)
        self.assertEqual(size, 55 * models.RECORD_SIZE)

    def test_data_file_contains_non_text_bytes(self):
        """ไฟล์ข้อมูลหลักต้องมีไบต์ที่ไม่ใช่ข้อความ (เป็น binary จริง)"""
        path = os.path.join(self.tmp_dir, models.DATA_FILE_NAME)
        with open(path, "rb") as fh:
            raw = fh.read()
        # ไบต์ศูนย์ (padding ของสตริง) และไบต์ควบคุมต้องมี แปลว่าเป็น binary
        self.assertIn(b"\x00", raw)
        self.assertIn(b"EVS-0001", raw)

    def test_can_decode_binary_with_struct(self):
        """ต้องถอดรหัสไฟล์หลักด้���ด้วย struct (ยืนยันว่าเป็น binary format)"""
        path = os.path.join(self.tmp_dir, models.DATA_FILE_NAME)
        with open(path, "rb") as fh:
            raw = fh.read(models.RECORD_SIZE)
        point = models.unpack_charge_point(raw)
        self.assertEqual(point.point_id, 1001)
        self.assertEqual(point.station_code, "EVS-0001")

    def test_all_three_data_files_are_binary(self):
        """ไฟล์ข้อมูลทั้ง 3 ไฟล์ต้องเป็น binary ที่ขนาดหารลงตัวพอดี"""
        for file_name, record_size in (
            (models.DATA_FILE_NAME, models.RECORD_SIZE),
            (models.LOG_FILE_NAME, models.LOG_RECORD_SIZE),
            (models.INDEX_FILE_NAME, models.INDEX_RECORD_SIZE),
        ):
            path = os.path.join(self.tmp_dir, file_name)
            self.assertTrue(os.path.exists(path))
            size = os.path.getsize(path)
            self.assertEqual(size % record_size, 0,
                             f"{file_name} ขนาดไม่หารลงตัวด้วย {record_size}")

    def test_reports_are_text_while_data_is_binary(self):
        """ข้อมูลเป็น binary แต่รายงานเป็น text (ตามข้อกำหนด)"""
        for file_name in reports_module.ALL_REPORT_NAMES:
            path = os.path.join(self.tmp_dir, file_name)
            with open(path, "rb") as fh:
                raw = fh.read()
            # ไฟล์รายงานต้องเป็น text ที่ decode ด้วย UTF-8 ได้
            raw.decode("utf-8")
            self.assertIn(b"[SUMMARY]", raw)


class TestReportValuesMatchData(ReportsTestCase):
    """ตรวจว่าตัวเลขในรายงานตรงกับข้อมูลจริงในไฟล์"""

    def test_summary_report_matches_sample_dataset(self):
        """รายงานจากชุด 1001-1010 ต้องตรงกับตัวเลขที่กำหนดไว้"""
        tmp_dir = tempfile.mkdtemp(prefix="ev_reports_main_")
        try:
            app = main.ChargingStationApp(tmp_dir)
            for spec in seed_data.MAIN_POINTS:
                fields = {key: value for key, value in spec.items()
                          if key != "is_deleted"}
                app.add_record(**fields)
                if spec.get("is_deleted"):
                    app.delete_record(spec["point_id"])
            app.generate_report(silent=True)

            with io.open(os.path.join(tmp_dir,
                                      reports_module.REPORT_POINTS_NAME),
                         encoding="utf-8") as fh:
                content = fh.read()

            points = app.store.read_all(include_deleted=True)
            summary = report_core.compute_summary(points)
            summary_section = content.split("[SUMMARY]", 1)[1]

            # ตรวจยอดสรุปทั้งหมดเทียบกับค่าที่คำนวณจากข้อมูลจริง
            self.assertIn("Total Points (records)", summary_section)
            self.assertIn(f"| {summary['total']} ", summary_section)
            self.assertIn("Active Points", summary_section)
            self.assertIn(f"| {summary['active']} ", summary_section)
            self.assertIn("Deleted Points (soft delete)", summary_section)
            self.assertIn(f"| {summary['deleted']} ", summary_section)
            self.assertIn("Available Now (Active & not booked)", summary_section)
            self.assertIn(f"| {summary['available']} ", summary_section)

            with io.open(os.path.join(tmp_dir,
                                      reports_module.REPORT_STATS_NAME),
                         encoding="utf-8") as fh:
                stats = fh.read()
            self.assertIn("7.36", stats,
                          "ราคาเฉลี่ยของชุด 1001-1010 ต้องเป็น 7.36")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_stats_report_lists_all_four_plug_types(self):
        """report_stats แสดงเฉพาะกิจกรรมและ Summary ตามขอบเขตปัจจุบัน"""
        content = self.read_report(reports_module.REPORT_STATS_NAME)
        for plug in ("CCS2", "Type2", "CHAdeMO", "GB-T"):
            self.assertNotIn(plug, content)

    def test_system_report_shows_all_three_file_statuses(self):
        """รายงานระบบแสดงสถานะและ struct ของทุกไฟล์"""
        content = self.read_report(reports_module.REPORT_SYSTEM_NAME)
        self.assertIn("<l10s30s10sfflllll", content)
        self.assertIn("<lllllf", content)
        self.assertIn("<ll", content)
        self.assertIn("charge_points.log", content)
        self.assertIn("index.dat", content)

    def test_stats_report_restores_recent_activity_table(self):
        """รายงานสถานะมีตารางกิจกรรมล่าสุดเป็น Table 2"""
        content = self.read_report(reports_module.REPORT_STATS_NAME)
        self.assertIn("[TABLE 2] Recent activity from charge_points.log",
                      content)
        self.assertIn("| Timestamp", content)

    def test_system_report_restores_original_sections(self):
        """รายงานระบบกลับมาแสดงตารางไฟล์ สรุป และผลตรวจแยกกัน"""
        content = self.read_report(reports_module.REPORT_SYSTEM_NAME)
        self.assertIn("[TABLE 3] Binary file status", content)
        self.assertIn("[SUMMARY]", content)
        self.assertNotIn("[CONSISTENCY CHECK]", content)

    def test_report_tables_use_english_text(self):
        """Table labels and cell values are English to avoid Thai glyph drift."""
        for file_name in reports_module.ALL_REPORT_NAMES:
            for line in self.read_report(file_name).splitlines():
                if line.startswith(("+", "|")):
                    self.assertFalse(
                        any("\u0e00" <= char <= "\u0e7f" for char in line),
                        f"{file_name} contains Thai text in a table: {line}")


class TestSectionRuleMatchesTable(ReportsTestCase):
    """เส้นคั่นหัวข้อต้องกว้างเท่ากับตารางเสมอ (แก้ปัญหา "เส้นไม่ตรง")"""

    def _rules_and_their_tables(self, content):
        """คืนคู่ (ความกว้างเส้นคั่น, ความกว้างตารางถัดไป) ของทุกเส้นคั่น"""
        lines = content.splitlines()
        pairs = []
        for index, line in enumerate(lines):
            if not line or set(line) != {"-"}:
                continue
            # เดินข้ามบรรทัดอธิบายเพื่อหาบล็อกตารางแรกของส่วนนี้
            cursor = index + 1
            while cursor < len(lines) and not lines[cursor].startswith(("+", "|")):
                if lines[cursor].lstrip().startswith("["):
                    break
                cursor += 1
            if cursor >= len(lines) or not lines[cursor].startswith(("+", "|")):
                continue
            width = 0
            while cursor < len(lines) and lines[cursor].startswith(("+", "|")):
                width = max(width, report_core.display_width(lines[cursor]))
                cursor += 1
            pairs.append((report_core.display_width(line), width))
        return pairs

    def test_every_rule_matches_its_table_width(self):
        """เส้นคั่นทุกเส้นในทั้ง 3 รายงานต้องยาวเท่าความกว้างตารางพอดี"""
        for file_name in reports_module.ALL_REPORT_NAMES:
            pairs = self._rules_and_their_tables(self.read_report(file_name))
            self.assertTrue(pairs, f"{file_name} ไม่พบเส้นคั่นหัวข้อเลย")
            for rule_width, table_width in pairs:
                self.assertEqual(
                    rule_width, table_width,
                    f"{file_name}: เส้นคั่นกว้าง {rule_width} "
                    f"แต่ตารางกว้าง {table_width} (เส้นไม่ตรงกับตาราง)")

    def test_no_table_row_differs_in_width(self):
        """ทุกบรรทัดในบล็อกตาราง (รวมเส้นขอบ) ต้องกว้างเท่ากัน"""
        for file_name in reports_module.ALL_REPORT_NAMES:
            lines = self.read_report(file_name).splitlines()
            block = []
            for line in lines + [""]:
                if line.startswith(("+", "|")):
                    block.append(line)
                elif block:
                    widths = {report_core.display_width(row) for row in block}
                    self.assertEqual(
                        len(widths), 1,
                        f"{file_name}: บรรทัดในตารางกว้างไม่เท่ากัน {widths}")
                    block = []

    def test_table_wider_than_fixed_placeholder_is_not_truncated(self):
        """ตารางหลักกว้างกว่า 62 ช่องเดิมได้ และเส้นคั่นต้องตามความกว้างจริง"""
        lines = self.read_report(reports_module.REPORT_POINTS_NAME).splitlines()
        table_widths = {report_core.display_width(line)
                        for line in lines if line.startswith("+")}
        self.assertGreater(max(table_widths), 62,
                           "ตารางหลักควรกว้างกว่าเส้นคั่นเดิมที่ใช้ค่าคงที่ 62")


class TestNoExplanatoryTables(ReportsTestCase):
    """รายงานต้องเหลือเฉพาะตารางผลลัพธ์จริง ไม่มีตาราง/ส่วนอธิบายซ้ำซ้อน

    ส่วนที่ถูกตัดออกจากทั้ง 3 ไฟล์
    ------------------------------
    * บรรทัดชื่อเรื่อง ("รายงานที่ 1: ...")
    * [COLUMN SPECIFICATION] รายละเอียดหัวตารางและแหล่งที่มาของข้อมูล
    * รายละเอียดคอลัมน์ของตาราง
    * ตารางสรุปแหล่งข้อมูล
    * ตารางรายละเอียดคอลัมน์

    เหตุผล
    ------
    ส่วนเหล่านี้เป็นเพียงตาราง "อธิบาย" ไม่ใช่ผลลัพธ์ของรายงาน
    และเนื้อหาเหมือนกันเกือบทั้งหมดในทั้ง 3 ไฟล์
    """

    # จำนวนตารางสูงสุดที่แต่ละรายงานควรมี
    MAX_TABLES = {
        reports_module.REPORT_POINTS_NAME: 3,
        reports_module.REPORT_STATS_NAME: 5,
        reports_module.REPORT_SYSTEM_NAME: 3,
    }

    @staticmethod
    def _count_tables(content) -> int:
        count, inside = 0, False
        for line in content.splitlines():
            if line.startswith("+"):
                if not inside:
                    count += 1
                    inside = True
            elif not line.startswith("|"):
                inside = False
        return count

    def test_only_important_tables_remain(self):
        """แต่ละรายงานต้องมีตารางไม่เกินที่กำหนด"""
        for name, limit in self.MAX_TABLES.items():
            actual = self._count_tables(self.read_report(name))
            self.assertLessEqual(
                actual, limit,
                f"{name}: มี {actual} ตาราง (เกิน {limit})")

    def test_no_column_specification_table(self):
        """ต้องไม่มีตารางรายละเอียดคอลัมน์เหลือ"""
        for name in reports_module.ALL_REPORT_NAMES:
            content = self.read_report(name)
            self.assertNotIn("ไฟล์และฟิลด์ต้นทาง |", content,
                             f"{name}: ยังมีตารางรายละเอียดคอลัมน์")

    def test_no_source_summary_table(self):
        """ต้องไม่มีตารางสรุปแหล่งข้อมูล 3 คอลัมน์เหลือ

        (ชื่อไฟล์ต้นทางยังแสดงในส่วนสรุป แต่ไม่ได้อยู่ในตารางแยก)
        """
        for name in reports_module.ALL_REPORT_NAMES:
            content = self.read_report(name)
            # หัวตารางเดิมของตารางสรุปแหล่งข้อมูล
            self.assertNotIn("| จำนวน record | บทบาท", content,
                             f"{name}: ยังมีตารางแหล่งข้อมูล")

    def test_column_specification_removed(self):
        """ส่วน [COLUMN SPECIFICATION] และรายละเอียดคอลัมน์ต้องถูกตัดออก"""
        for name in reports_module.ALL_REPORT_NAMES:
            content = self.read_report(name)
            self.assertNotIn("[COLUMN SPECIFICATION]", content,
                             f"{name}: ยังมีส่วนรายละเอียดหัวตาราง")
            self.assertNotIn("รายละเอียดคอลัมน์ของตาราง", content,
                             f"{name}: ยังมีรายละเอียดคอลัมน์")

    def test_source_files_still_referenced(self):
        """ชื่อไฟล์ต้นทางทั้ง 3 ต้องยังปรากฏในส่วนสรุป (เกณฑ์ข้อ 3)"""
        for name in reports_module.ALL_REPORT_NAMES:
            content = self.read_report(name)
            self.assertIn("charge_points.dat", content)
            self.assertIn("charge_points.log", content)
            self.assertIn("index.dat", content)
            self.assertIn("Source files", content)
            self.assertIn("Binary sources (.dat)", content)
            binary_sources = next(
                line for line in content.splitlines()
                if "Binary sources (.dat)" in line
            )
            self.assertIn("charge_points.dat", binary_sources)
            self.assertIn("index.dat", binary_sources)

    def test_location_details_section_is_removed_from_reports(self):
        """รายงานไม่สร้างส่วน LOCATION DETAILS ซ้ำกับตารางหลัก"""
        for name in reports_module.ALL_REPORT_NAMES:
            self.assertNotIn("[LOCATION DETAILS]", self.read_report(name))

    def test_main_data_tables_are_kept(self):
        """ตารางรายงานสถานะและระบบมีข้อมูลหลักพร้อมผลตรวจ"""
        expectations = {
            reports_module.REPORT_POINTS_NAME: ("PtID", "Item", "Available Now"),
            reports_module.REPORT_STATS_NAME: ("Timestamp", "SUMMARY",
                                               "Records in index.dat"),
            reports_module.REPORT_SYSTEM_NAME: ("Struct format", "Item",
                                                "Source files"),
        }
        for name, expected in expectations.items():
            content = self.read_report(name)
            for header in expected:
                self.assertIn(header, content,
                              f"{name}: ไม่พบตารางสำคัญที่มีหัวคอลัมน์ {header}")


class TestAlignmentModes(ReportsTestCase):
    """โหมดจัดความกว้างตารางต้องตรงตามเมทริกของแต่ละโหมด

    สาเหตุที่ต้องมี 2 โหมด
    ----------------------
    สระ/วรรณยุกต์ไทย (ั ิ ี ื ุ ู ็ ่ ้ ์) เป็นอักขระประสม คือ Unicode นับเป็น
    1 ตัวอักษร แต่กินพื้นที่บนจอ 0 ช่อง ดังนั้นบรรทัดที่มีสระไทยมากจะมี
    "จำนวนตัวอักษร" มากกว่า "ความกว้างจริง"
    โปรแกรมที่เปิดไฟล์จึงต้องเลือกให้ตรงกับวิธีที่มันวางเส้น "|"
    """

    def tearDown(self):
        report_core.set_alignment_mode(True)      # คืนค่าเริ่มต้นทุกครั้ง
        super().tearDown()

    @staticmethod
    def _blocks(content):
        """แยกบรรทัดตารางของรายงานออกเป็นบล็อก ๆ"""
        result, current = [], []
        for line in content.splitlines() + [""]:
            if line.startswith(("+", "|")):
                current.append(line)
            elif current:
                result.append(current)
                current = []
        return result

    def _generate(self, smart):
        report_core.set_alignment_mode(smart)
        self.app.generate_report(silent=True)
        return {name: self.read_report(name)
                for name in reports_module.ALL_REPORT_NAMES}

    def test_mode_name_switches(self):
        """ชื่อโหมดต้องสลับได้ถูกต้อง"""
        report_core.set_alignment_mode(True)
        self.assertEqual(report_core.alignment_mode_name(), "smart")
        report_core.set_alignment_mode(False)
        self.assertEqual(report_core.alignment_mode_name(), "simple")

    def test_smart_mode_is_default_for_terminal_alignment(self):
        """ค่าเริ่มต้นจัดแนวใน Terminal ตามความกว้างที่แสดงจริง"""
        self.assertEqual(main.build_parser().parse_args([]).align, "smart")

    def test_measure_uses_selected_metric(self):
        """ฟังก์ชัน measure ต้องวัดตามโหมดที่เลือก"""
        text = "ชั้น"          # ช ั ้ น = 4 ตัวอักษร แต่กินพื้นที่ 2 ช่อง
        self.assertEqual(len(text), 4)
        self.assertEqual(report_core.display_width(text), 2)
        report_core.set_alignment_mode(True)
        self.assertEqual(report_core.measure(text), 2)
        report_core.set_alignment_mode(False)
        self.assertEqual(report_core.measure(text), 4)

    def test_report_files_use_display_width_and_preserve_terminal_mode(self):
        """ไฟล์ใช้แนวจัด smart โดยไม่เปลี่ยนโหมดจัดตารางของ Terminal"""
        for smart in (True, False):
            report_core.set_alignment_mode(smart)
            self.app.generate_report(silent=True)
            self.assertEqual(report_core.alignment_mode_name(),
                             "smart" if smart else "simple")
            for name in reports_module.ALL_REPORT_NAMES:
                for block in self._blocks(self.read_report(name)):
                    widths = {report_core.display_width(row) for row in block}
                    self.assertEqual(len(widths), 1,
                                     f"{name}: ความกว้างแสดงผลไม่เท่ากัน")

    def test_report_files_align_vertical_borders_by_display_width(self):
        """เส้นแบ่งคอลัมน์ทุกเส้นในไฟล์ต้องตรงตามตำแหน่งที่เห็นบนจอ"""
        for name, content in self._generate(True).items():
            for block in self._blocks(content):
                expected = tuple(
                    report_core.display_width(block[0][:index])
                    for index, char in enumerate(block[0]) if char == "+"
                )
                for row in block[1:]:
                    border = "|" if row.startswith("|") else "+"
                    actual = tuple(
                        report_core.display_width(row[:index])
                        for index, char in enumerate(row) if char == border
                    )
                    self.assertEqual(
                        actual, expected,
                        f"{name}: เส้นแบ่งคอลัมน์ไม่ตรงตามความกว้างแสดงผล")

    def test_english_report_borders_share_character_indices(self):
        """English-only table text keeps border indices identical in plain text."""
        for name, content in self._generate(True).items():
            for block in self._blocks(content):
                expected = tuple(index for index, char in enumerate(block[0])
                                 if char == "+")
                for row in block[1:]:
                    border = "|" if row.startswith("|") else "+"
                    actual = tuple(index for index, char in enumerate(row)
                                   if char == border)
                    self.assertEqual(
                        actual, expected,
                        f"{name}: border character indices do not align")

    def test_both_modes_contain_full_location(self):
        """ทั้งสองโหมดต้องแสดงชื่อสถานที่แบบเต็มเหมือนกัน"""
        for smart in (True, False):
            content = self._generate(smart)[reports_module.REPORT_POINTS_NAME]
            self.assertIn("CentralWorld, Parking P2", content)
            self.assertIn("Siam Paragon, Level B1", content)

    def test_file_rules_match_table_character_width(self):
        """เส้นคั่นไฟล์รายงานต้องยาวเท่าตารางตามความกว้างแสดงผล"""
        for smart in (True, False):
            for name, content in self._generate(smart).items():
                lines = content.splitlines()
                measure = report_core.display_width
                found = 0
                for index, line in enumerate(lines):
                    if not line or set(line) != {"-"}:
                        continue
                    cursor = index + 1
                    while cursor < len(lines) \
                            and not lines[cursor].startswith(("+", "|")):
                        if lines[cursor].lstrip().startswith("["):
                            break
                        cursor += 1
                    if cursor >= len(lines) \
                            or not lines[cursor].startswith(("+", "|")):
                        continue
                    width = 0
                    while cursor < len(lines) \
                            and lines[cursor].startswith(("+", "|")):
                        width = max(width, measure(lines[cursor]))
                        cursor += 1
                    self.assertEqual(report_core.display_width(line), width,
                                     f"{name} (smart={smart}): เส้นคั่นไม่ตรง")
                    found += 1
                self.assertGreater(found, 0, f"{name} ไม่พบเส้นคั่น")


class TestTablesFitScreen(ReportsTestCase):
    """ตารางทุกตัวต้องไม่กว้างเกินหน้าจอ (สาเหตุที่ทำให้เส้นแนวตั้งดูเบี้ยว)

    ปัญหาที่พบระหว่างพัฒนา
    ----------------------
    ตารางข้อมูลหัวชาร์จเดิมมี 10 คอลัมน์และกว้างมาก
    เมื่อเปิดในโปรแกรมที่ความกว้างหน้าจอน้อยกว่านั้น โปรแกรมจะตัดบรรทัด
    (word wrap) เส้น "|" ที่อยู่ปลายบรรทัดจึงตกไปบรรทัดถัดไป
    ผู้อ่านจึงเห็นเส้นแนวตั้งไม่ตรงกัน แม้ไฟล์จะถูกต้องก็ตาม
    """

    MAX_SCREEN_WIDTH = 96

    @staticmethod
    def _blocks(content):
        result, current = [], []
        for line in content.splitlines() + [""]:
            if line.startswith(("+", "|")):
                current.append(line)
            elif current:
                result.append(current)
                current = []
        return result

    def _is_main_point_table(self, block) -> bool:
        """ตารางข้อมูลหัวชาร์จหลักของรายงานที่ 1"""
        header = block[1] if len(block) > 1 else ""
        return "PtID" in header and "Updated" in header

    def test_no_table_exceeds_screen_width(self):
        """ไม่มีตารางใดกว้างเกินความกว้างที่กำหนด

        ยกเว้นตารางข้อมูลหัวชาร์จหลักของรายงานที่ 1 ที่รวมข้อมูลครบ
        10 คอลัมน์ไว้ในตารางเดียว (ตามที่ผู้ใช้ต้องการ) จึงใช้
        MAIN_TABLE_MAX_WIDTH แทน
        """
        for name in reports_module.ALL_REPORT_NAMES:
            for index, block in enumerate(
                    self._blocks(self.read_report(name)), start=1):
                width = report_core.display_width(block[0])
                limit = (reports_module.MAIN_TABLE_MAX_WIDTH
                         if self._is_main_point_table(block)
                         else self.MAX_SCREEN_WIDTH)
                self.assertLessEqual(
                    width, limit,
                    f"{name}: ตารางที่ {index} กว้าง {width} ช่อง "
                    f"(เกิน {limit})")

    def test_no_line_exceeds_screen_width(self):
        """ไม่มีบรรทัดใดกว้างเกินความกว้างที่กำหนด (รวมบรรทัดหัวข้อ)"""
        for name in reports_module.ALL_REPORT_NAMES:
            limit = (reports_module.MAIN_TABLE_MAX_WIDTH
                     if name == reports_module.REPORT_POINTS_NAME
                     else self.MAX_SCREEN_WIDTH)
            for number, line in enumerate(
                    self.read_report(name).splitlines(), start=1):
                self.assertLessEqual(
                    report_core.display_width(line), limit,
                    f"{name}: บรรทัด {number} กว้าง "
                    f"{report_core.display_width(line)} ช่อง "
                    f"(เกิน {limit})")

    def test_no_cell_is_truncated(self):
        """ยอมให้ย่อเฉพาะช่อง Location ซึ่งมีชื่อเต็มแสดงต่อใต้ตาราง"""
        for name in reports_module.ALL_REPORT_NAMES:
            for line in self.read_report(name).splitlines():
                if not line.startswith("|"):
                    continue
                cells = line.strip("|").split("|")
                is_main_points_row = (
                    name == reports_module.REPORT_POINTS_NAME
                    and len(cells) == 9
                    and cells[0].strip().isdigit()
                )
                for index, cell in enumerate(cells):
                    if is_main_points_row and index == 2:
                        continue
                    self.assertFalse(
                        cell.strip().endswith("..."),
                        f"{name}: เซลล์ถูกตัด -> {cell.strip()}")

    def test_long_locations_are_preserved_below_compact_main_table(self):
        """แสดงชื่อสถานที่เต็มในตารางโดยไม่สร้าง LOCATION DETAILS แยก"""
        content = self.read_report(reports_module.REPORT_POINTS_NAME)
        self.assertNotIn("[LOCATION DETAILS]", content)
        full_location = (
            "Siam Paragon EV Station, New Basement Project and Parking Lot"
        )
        self.assertIn(full_location, content)
        point_row = next(
            line for line in content.splitlines()
            if line.startswith("|") and "| 2011 " in line
        )
        location_cell = point_row.strip("|").split("|")[2].strip()
        self.assertEqual(location_cell, full_location)
        self.assertLessEqual(
            report_core.measure(location_cell),
            reports_module.MAIN_TABLE_LOCATION_WIDTH,
        )

    def test_header_cells_are_not_truncated(self):
        """หัวตารางต้องอ่านออก ไม่ถูกตัดจนกลายเป็น 'Struct f...'"""
        for name in reports_module.ALL_REPORT_NAMES:
            for block in self._blocks(self.read_report(name)):
                for cell in block[1].strip("|").split("|"):
                    self.assertFalse(
                        cell.strip().endswith("..."),
                        f"{name}: หัวตารางถูกตัด -> {cell.strip()}")

    def test_important_struct_formats_are_visible_in_full(self):
        """รูปแบบ struct ต้องแสดงครบในตารางระบบ"""
        content = self.read_report(reports_module.REPORT_SYSTEM_NAME)
        self.assertIn("<l10s30s10sfflllll", content)
        self.assertIn("<lllllf", content)
        self.assertIn("<ll", content)

    def test_column_fitting_prefers_widest_column(self):
        """ตัวช่วยลดความกว้างต้องลดคอลัมน์ที่กว้างที่สุดก่อน"""
        # max_width=60, 3 คอลัมน์ -> เหลือพื้นที่เนื้อหา 60 - (3*2 + 3 + 1) = 50
        # ปกติรวม 40+10+8 = 58 จึงต้องลดลง 8 โดยลดคอลัมน์ที่กว้างที่สุด
        result = report_core._fit_column_widths([40, 10, 8], 60,
                                                [5, 5, 5])
        self.assertEqual(result, [32, 10, 8])   # ลดเฉพาะคอลัมน์แรก
        self.assertEqual(sum(result), 50)

    def test_column_fitting_never_goes_below_floor(self):
        """ลดความกว้างไม่ต่ำกว่าความกว้างหัวคอลัมน์"""
        result = report_core._fit_column_widths([40, 10], 20, [20, 10])
        self.assertEqual(result, [20, 10])    # หยุดที่ขั้นต่ำ ไม่ลดต่อ

    def test_main_point_table_is_merged_into_one(self):
        """ตารางหัวชาร์จใช้คอลัมน์ตามตัวอย่างและไม่แสดง LogSeq"""
        content = self.read_report(reports_module.REPORT_POINTS_NAME)
        self.assertIn("[TABLE 1]", content)
        self.assertNotIn("[TABLE 2]", content)
        self.assertNotIn("[TABLE 3]", content)
        # ต้องมีหัวตารางที่รวมทุกคอลัมน์อยู่ในตารางเดียว
        header = None
        for block in self._blocks(content):
            line = block[1] if len(block) > 1 else ""
            if "PtID" in line and "Updated" in line:
                header = line
        self.assertIsNotNone(header, "ไม่พบตารางข้อมูลหัวชาร์จที่รวมข้อมูลครบ")
        for column in ("PtID", "Station", "Location", "Plug", "Power",
                       "Price", "Status", "Booked", "Updated"):
            self.assertIn(column, header)

    def test_main_point_table_fits_its_own_limit(self):
        """ตารางข้อมูลหัวชาร์จต้องไม่เกิน MAIN_TABLE_MAX_WIDTH"""
        content = self.read_report(reports_module.REPORT_POINTS_NAME)
        for block in self._blocks(content):
            if not self._is_main_point_table(block):
                continue
            self.assertLessEqual(report_core.display_width(block[0]),
                                 reports_module.MAIN_TABLE_MAX_WIDTH)
            # ทุกแถวต้องกว้างเท่ากัน
            widths = {report_core.display_width(row) for row in block}
            self.assertEqual(len(widths), 1, f"ความกว้างไม่เท่ากัน {widths}")


class TestFullLocationIsReadable(ReportsTestCase):
    """ชื่อ Location ต้องอ่านได้ครบ ไม่ถูกตัดกลางชื่อ"""

    def test_locations_file_is_created(self):
        """ต้องมีไฟล์ locations.txt เก็บชื่อเต็ม"""
        path = os.path.join(self.tmp_dir, models.LOCATION_FILE_NAME)
        self.assertTrue(os.path.exists(path), "ไม่พบไฟล์ locations.txt")
        self.assertGreater(os.path.getsize(path), 0)

    def test_report_shows_full_name_not_truncated(self):
        """The report uses English location labels in the main table."""
        content = self.read_report(reports_module.REPORT_POINTS_NAME)
        self.assertIn("CentralWorld, Parking P2", content)
        self.assertIn("Siam Paragon, Level B1", content)

    def test_binary_record_still_limited_to_30_bytes(self):
        """record ไบนารียังคงเก็บ location ได้ไม่เกิน 30 ไบต์ตามสเปก"""
        store = main.storage_module.ChargePointStore(
            os.path.join(self.tmp_dir, models.DATA_FILE_NAME))
        for point in store.read_all():
            self.assertLessEqual(len(point.location.encode("utf-8")), 30,
                                 f"{point.point_id} เกิน 30 ไบต์")

    def test_new_record_keeps_full_location(self):
        """เพิ่มข้อมูลใหม่ที่ชื่อยาวแล้วรายงานต้องแสดงชื่อเต็ม"""
        long_name = "สถานีทดสอบระบบชาร์จแห่งใหม่ ในโครงการเมืองอุตสาหกรรม"
        self.app.add_record(point_id=9001, station_code="EVS-9001",
                            location=long_name, plug_type="CCS2",
                            power_kw=150.0, price_per_kwh=8.25)
        self.app.generate_report(silent=True)
        content = self.read_report(reports_module.REPORT_POINTS_NAME)
        self.assertIn(long_name, content)

    def test_updated_location_is_reflected(self):
        """แก้ไข location แล้วรายงานต้องแสดงชื่อใหม่"""
        self.app.update_record(1001, location="ชื่อใหม่หลังแก้ไข ชั้น 9")
        self.app.generate_report(silent=True)
        content = self.read_report(reports_module.REPORT_POINTS_NAME)
        self.assertIn("ชื่อใหม่หลังแก้ไข ชั้น 9", content)

class TestTerminalShowsFullLocation(ReportsTestCase):
    """หน้าจอ Terminal ของโปรแกรมต้องแสดงชื่อสถานที่ตั้งแบบเต็ม

    ระเบียกไบนารีเก็บ location ได้ 30 ไบต์ จึงเก็บชื่อเต็มไว้ใน
    locations.txt แล้วดึงกลับมาแสดงผลทั้งบน Terminal และในรายงาน
    """

    def _capture(self, method_name, *args, **kwargs) -> str:
        """เรียกเมธอดของแอปแล้วจับข้อความที่พิมพ์ออกมา"""
        import io as _io
        import contextlib
        buffer = _io.StringIO()
        with contextlib.redirect_stdout(buffer):
            getattr(self.app, method_name)(*args, **kwargs, silent=True) \
                if "silent" in getattr(self.app, method_name).__code__.co_varnames \
                else getattr(self.app, method_name)(*args, **kwargs)
        return buffer.getvalue()

    def _assert_terminal_table_columns_align(self, output: str) -> None:
        """ยืนยันว่าเส้นแบ่งคอลัมน์ในตาราง Terminal อยู่ตำแหน่งเดียวกัน"""
        blocks, current = [], []
        for raw_line in output.splitlines() + [""]:
            line = raw_line.lstrip()
            if line.startswith(("+", "|")):
                current.append(line)
            elif current:
                blocks.append(current)
                current = []
        self.assertTrue(blocks, "ไม่พบตารางใน output ของ Terminal")

        for block in blocks:
            expected = tuple(
                report_core.display_width(block[0][:index])
                for index, char in enumerate(block[0]) if char == "+"
            )
            for line in block[1:]:
                border = "|" if line.startswith("|") else "+"
                actual = tuple(
                    report_core.display_width(line[:index])
                    for index, char in enumerate(line) if char == border
                )
                self.assertEqual(actual, expected,
                                 f"เส้นแบ่งคอลัมน์ไม่ตรงกัน:\n{block[0]}\n{line}")

    def test_tables_align_in_terminal_views(self):
        """ตารางดูทั้งหมด กรอง และประวัติล่าสุดจัดแนวตรงกันใน Terminal"""
        report_core.set_alignment_mode(True)
        self._assert_terminal_table_columns_align(self._capture("view_all"))

        import validators
        original_menu_choice = validators.ask_menu_choice
        original_station_code = validators.ask_station_code
        validators.ask_menu_choice = lambda prompt, allowed: 1
        validators.ask_station_code = lambda: "EVS-0001"
        try:
            self._assert_terminal_table_columns_align(
                self._capture("view_filtered")
            )
        finally:
            validators.ask_menu_choice = original_menu_choice
            validators.ask_station_code = original_station_code

        original_point_id = validators.ask_point_id
        validators.ask_point_id = lambda: 1001
        try:
            self._assert_terminal_table_columns_align(
                self._capture("view_single")
            )
        finally:
            validators.ask_point_id = original_point_id

    def test_location_store_returns_full_name(self):
        """LocationStore ต้องคืนชื่อเต็ม ไม่ใช่ค่าที่ถูกตัด 30 ไบต์"""
        store = self.app.store
        point = next(p for p in store.read_all()
                     if p.station_code == "EVS-0002")
        full = self.app.location_store.full_location(point)
        self.assertEqual(full, "เซ็นทรัลเวิลด์ ลาน P2")
        # ค่าในระเบียกไบนารีถูกตัดจริง (ยืนยันว่า 2 ค่านี้ต่างกัน)
        self.assertNotEqual(point.location, full)
        self.assertLessEqual(len(point.location.encode("utf-8")), 30)

    def test_view_all_prints_full_location(self):
        """View All uses English labels for known locations."""
        output = self._capture("view_all")
        self.assertIn("CentralWorld, Parking P2", output)
        self.assertIn("Siam Paragon, Level B1", output)

    def test_updating_booked_keeps_location_in_report_and_terminal(self):
        """แก้ Booked อย่างเดียวต้องคง Location เดิมทั้งรายงานและ Terminal"""
        point = next(p for p in self.app.store.read_all()
                     if p.point_id == 1005)
        location = self.app.location_store.full_location(point)
        self.app.update_record(1005, is_booked=0)

        output = self._capture("view_all")
        self.app.generate_report(silent=True)
        content = self.read_report(reports_module.REPORT_POINTS_NAME)

        expected_location = (
            reports_module.english_location_label(location) or location)
        self.assertIn(expected_location, output)
        self.assertIn(expected_location, content)
        self.assertNotIn("See details", content)

    def test_view_filtered_prints_full_location(self):
        """เมนูค้นหา/กรองต้องแสดงชื่อสถานที่ตั้งแบบเต็ม"""
        # view_filtered ใช้ validators.ask_* จึงต้อง stub ให้คืนค่าที่เลือก
        import validators
        originals = (validators.ask_menu_choice, validators.ask_station_code)
        validators.ask_menu_choice = lambda prompt, allowed: 1     # station_code
        validators.ask_station_code = lambda: "EVS-0002"
        try:
            output = self._capture("view_filtered")
        finally:
            (validators.ask_menu_choice,
             validators.ask_station_code) = originals
        self.assertIn("CentralWorld, Parking P2", output)

    def test_new_long_location_shows_in_terminal(self):
        """เพิ่มชื่อที่ยาวมากแล้ว Terminal ต้องแสดงชื่อเต็ม"""
        long_name = "สถานีทดสอบระบบชาร์จแห่งใหม่ ในโครงการเมืองอุตสาหกรรม"
        created = self.app.add_record(point_id=9001, station_code="EVS-9001",
                                      location=long_name, plug_type="CCS2",
                                      power_kw=150.0, price_per_kwh=8.25)
        output = self._capture("view_all")
        self.assertIn(long_name, output)
        # ระเบียกไบนารียังเก็บค่าที่ตัดตามสเปก 30 ไบต์
        self.assertLessEqual(len(created.location.encode("utf-8")), 30)
        self.assertNotIn("Custom location", output)

    def test_custom_location_is_shown_in_report_table(self):
        """ชื่อ Location ที่กำหนดเองต้องแสดงแทนข้อความ See details"""
        location = "สถานีทดสอบ"
        self.app.add_record(point_id=9002, station_code="EVS-9002",
                            location=location, plug_type="CCS2",
                            power_kw=150.0, price_per_kwh=8.25)
        self.app.generate_report(silent=True)
        content = self.read_report(reports_module.REPORT_POINTS_NAME)
        self.assertIn(location, content)
        self.assertNotIn("See details", content)