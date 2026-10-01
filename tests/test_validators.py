"""tests/test_validators.py — ทดสอบการตรวจสอบอินพุตทุกจุด (เชิงลบเป็นหลัก)

ครอบคลุม:
* รูปแบบ point_id / station_code / plug_type
* ค่า float ที่ต้อง > 0 และค่า 0/1 ของ status / is_booked
* location: ห้ามว่าง และการเตือน+ตัดเมื่อเกิน 30 ไบต์
* การวนถามใหม่เมื่อผิด และการจัดการ EOFError / KeyboardInterrupt
"""

import unittest

import models
import validators


class TestValidatePointId(unittest.TestCase):
    """point_id ต้องเป็นจำนวนเต็มบวก"""

    def test_valid_positive_integer(self):
        """จำนวนเต็มบวกถือว่าถูกต้อง"""
        self.assertEqual(validators.validate_point_id(1001), 1001)
        self.assertEqual(validators.validate_point_id("1001"), 1001)
        self.assertEqual(validators.validate_point_id(1), 1)

    def test_reject_zero_and_negative(self):
        """0 และเลขติดลบต้องถูกปฏิเสธ"""
        for bad in (0, -1, -100):
            with self.assertRaises(validators.ValidationError):
                validators.validate_point_id(bad)

    def test_reject_non_numeric(self):
        """ค่าที่ไม่ใช่ตัวเลขต้องถูกปฏิเสธ"""
        for bad in ("abc", "", "12.5", "EVS-0001"):
            with self.assertRaises(validators.ValidationError):
                validators.validate_point_id(bad)

    def test_error_type_is_value_error_subclass(self):
        """ValidationError ต้องสืบทอดจาก ValueError (ให้ except ValueError ได้)"""
        self.assertTrue(issubclass(validators.ValidationError, ValueError))


class TestValidateStationCode(unittest.TestCase):
    """station_code ต้องเป็นรูปแบบ EVS-NNNN"""

    def test_valid_codes(self):
        """รหัสที่ถูกต้องถือว่าผ่าน"""
        self.assertEqual(validators.validate_station_code("EVS-0001"), "EVS-0001")
        self.assertEqual(validators.validate_station_code("EVS-9999"), "EVS-9999")

    def test_case_and_space_are_normalised(self):
        """ตัวพิมพ์เล็กและช่องว่างรอบ ๆ ถูกปรับให้อัตโนมัติ"""
        self.assertEqual(validators.validate_station_code("  evs-0002 "), "EVS-0002")

    def test_reject_wrong_format(self):
        """รูปแบบผิดต้องถูกปฏิเสธทุกกรณี"""
        for bad in ("EVS-001", "EVS-00001", "EVS0001", "ABC-0001",
                    "EVS-ABCD", "", "EVS-", "0001"):
            with self.assertRaises(validators.ValidationError):
                validators.validate_station_code(bad)


class TestValidatePlugType(unittest.TestCase):
    """plug_type ต้องอยู่ในรายการที่กำหนด"""

    def test_all_allowed_plug_types(self):
        """ทุกประเภทหัวที่กำหนดต้องผ่าน"""
        for plug in models.PLUG_TYPES:
            self.assertEqual(validators.validate_plug_type(plug), plug)

    def test_case_insensitive(self):
        """พิมพ์ตัวพิมพ์เล็กถือว่าถูกต้อง"""
        self.assertEqual(validators.validate_plug_type("ccs2"), "CCS2")

    def test_reject_unknown_plug(self):
        """ประเภทหัวที่ไม่รู้จักถูกปฏิเสธ"""
        for bad in ("Type1", "Tesla", "", "CCS"):
            with self.assertRaises(validators.ValidationError):
                validators.validate_plug_type(bad)


class TestValidateNumbers(unittest.TestCase):
    """power_kw / price_per_kwh ต้อง > 0 และ status/is_booked ต้องเป็น 0 หรือ 1"""

    def test_positive_float_accepted(self):
        """ค่าบวกถือว่าถูกต้อง"""
        self.assertEqual(validators.validate_positive_float(7.4, "Power"), 7.4)
        self.assertEqual(validators.validate_positive_float("150", "Power"), 150.0)
        self.assertEqual(validators.validate_positive_float(0.01, "Price"), 0.01)

    def test_zero_and_negative_rejected(self):
        """0 และเลขติดลบถูกปฏิเสธ (ต้องมากกว่า 0)"""
        for bad in (0, -5, "-0.1"):
            with self.assertRaises(validators.ValidationError):
                validators.validate_positive_float(bad, "Power")

    def test_non_numeric_rejected(self):
        """ค่าที่ไม่ใช่ตัวเลขถูกปฏิเสธ"""
        for bad in ("abc", "", "7.4 kW"):
            with self.assertRaises(validators.ValidationError):
                validators.validate_positive_float(bad, "Power")

    def test_binary_accepts_only_zero_or_one(self):
        """status และ is_booked รับเฉพาะ 0 หรือ 1"""
        self.assertEqual(validators.validate_binary(0, "Status"), 0)
        self.assertEqual(validators.validate_binary(1, "Status"), 1)
        self.assertEqual(validators.validate_binary("1", "Booked"), 1)

    def test_binary_rejects_other_values(self):
        """ค่านอกเหนือจาก 0/1 ถูกปฏิเสธ"""
        for bad in (2, -1, "yes", "", "1.0"):
            with self.assertRaises(validators.ValidationError):
                validators.validate_binary(bad, "Status")
class TestValidateLocation(unittest.TestCase):
    """location: ห้ามว่าง และไม่เกิน 30 ไบต์ (เตือนก่อนตัด)"""

    def test_normal_location_unchanged(self):
        """ข้อความที่สั้นถูกคืนค่าเดิม"""
        self.assertEqual(validators.validate_location("สยาม B1"), "สยาม B1")

    def test_empty_location_rejected(self):
        """location ห้ามว่างหรือมีแต่ช่องว่าง"""
        for bad in ("", "   ", None):
            with self.assertRaises(validators.ValidationError):
                validators.validate_location(bad)

    def test_exactly_30_bytes_is_kept(self):
        """ข้อความที่ยาวพอดี 30 ไบต์ไม่ถูกตัด"""
        text = "ก" * 10                     # 30 ไบต์
        self.assertEqual(validators.validate_location(text), text)
        self.assertEqual(models.text_byte_length(text), 30)

    def test_over_30_bytes_is_truncated_and_warns(self):
        """ข้อความยาวเกินต้องถูกตัดพอดี 30 ไบต์ และมีคำเตือน"""
        warnings = []
        text = "สถานีชาร์จไฟฟ้าสยามพารากอนชั้นใต้ดิน"   # ยาวมาก
        result = validators.validate_location(text, warn=warnings.append)

        self.assertLessEqual(models.text_byte_length(result), 30)
        self.assertTrue(warnings, "ต้องมีคำเตือนก่อนตัด")
        self.assertIn("30", warnings[0])

    def test_truncation_never_splits_thai_character(self):
        """หลังตัด ต้องถอดรหัสได้โดยไม่มีอักขระเพี้ยน"""
        result = validators.validate_location("ก" * 20)     # 60 ไบต์
        result.encode("utf-8").decode("utf-8")             # ไม่ error
        self.assertNotIn("\ufffd", result)
        self.assertEqual(result, "ก" * 10)


class TestAskFunctions(unittest.TestCase):
    """ทดสอบฟังก์ชันถามผู้ใช้ (ส่ง reader ปลอม ไม่ต้องใช้ stdin จริง)"""

    @staticmethod
    def make_reader(responses):
        """สร้างฟังก์ชัน reader ที่คืนค่าจากลิสต์ที่กำหนดไว้ทีละบรรทัด"""
        iterator = iter(responses)

        def reader(prompt=""):
            try:
                return next(iterator)
            except StopIteration:
                raise EOFError("หมดข้อมูลทดสอบ")

        return reader

    def test_ask_point_id_retries_until_valid(self):
        """ถ้ากรอกผิด ระบบต้องแจ้งและถามใหม่จนกว่าจะถูกต้อง"""
        messages = []
        reader = self.make_reader(["abc", "-5", "1001"])
        result = validators.ask_point_id(reader, messages.append)
        self.assertEqual(result, 1001)
        self.assertEqual(len(messages), 2, "ต้องแจ้งข้อผิดพลาด 2 ครั้ง")

    def test_ask_station_code_retries(self):
        """รหัสสถานีผิดรูปแบบต้องถูกถามซ้ำ"""
        reader = self.make_reader(["XYZ-1", "EVS-0042"])
        self.assertEqual(validators.ask_station_code(reader, print), "EVS-0042")

    def test_ask_plug_type_accepts_menu_number(self):
        """เมนู plug_type รับเลข 1-4 และแปลงเป็นชื่อประเภท"""
        reader = self.make_reader(["2"])
        self.assertEqual(validators.ask_plug_type(reader, print), "CCS2")

    def test_ask_plug_type_accepts_name_directly(self):
        """พิมพ์ชื่อประเภทหัวตรง ๆ ก็ได้"""
        reader = self.make_reader(["GB-T"])
        self.assertEqual(validators.ask_plug_type(reader, print), "GB-T")

    def test_ask_power_and_price_retry(self):
        """ค่าตัวเลขผิดต้องถูกถามซ้ำ"""
        reader = self.make_reader(["abc", "0", "7.4"])
        self.assertEqual(validators.ask_power_kw(reader, print), 7.4)

        reader = self.make_reader(["-1", "6.5"])
        self.assertEqual(validators.ask_price_per_kwh(reader, print), 6.5)

    def test_ask_binary_rejects_non_binary(self):
        """ค่า status/is_booked ที่ไม่ใช่ 0/1 ต้องถูกถามซ้ำ"""
        messages = []
        reader = self.make_reader(["5", "x", "1"])
        self.assertEqual(validators.ask_binary("Status", reader, messages.append), 1)
        self.assertEqual(len(messages), 2)

    def test_ask_location_warns_and_truncates(self):
        """location ยาวเกินต้องเตือนและตัด"""
        messages = []
        reader = self.make_reader(["ก" * 30])
        result = validators.ask_location(reader, messages.append)
        self.assertEqual(models.text_byte_length(result), 30)
        self.assertTrue(messages)

    def test_ask_yes_no_variants(self):
        """คำตอบ y/n หลายรูปแบบต้องถูกตีความถูกต้อง"""
        for answer, expected in (("y", True), ("Y", True), ("yes", True),
                                 ("ใช่", True), ("n", False), ("NO", False),
                                 ("ไม่", False)):
            reader = self.make_reader([answer])
            self.assertEqual(
                validators.ask_yes_no("ยืนยัน?", reader=reader, printer=print),
                expected, f"คำตอบ '{answer}' ต้องได้ {expected}")

    def test_ask_yes_no_empty_uses_default(self):
        """กด Enter เว้นว่างต้องใช้ค่าเริ่มต้นที่กำหนด"""
        reader = self.make_reader([""])
        self.assertTrue(validators.ask_yes_no("?", default=True,
                                              reader=reader, printer=print))
        reader = self.make_reader([""])
        self.assertFalse(validators.ask_yes_no("?", default=False,
                                               reader=reader, printer=print))

    def test_ask_menu_choice_retries_on_invalid(self):
        """ตัวเลือกเมนูนอกช่วงต้องถูกถามซ้ำ"""
        messages = []
        reader = self.make_reader(["9", "abc", "3"])
        result = validators.ask_menu_choice("เลือก: ", (0, 1, 2, 3),
                                            reader, messages.append)
        self.assertEqual(result, 3)
        self.assertEqual(len(messages), 2)

    def test_eof_raises_user_abort_not_crash(self):
        """EOFError ต้องถูกแปลงเป็น UserAbort (ไม่ใช่หยุดโปรแกรมแบบไม่มีข้อความ)"""
        def reader(prompt=""):
            raise EOFError("ปิด stdin")

        with self.assertRaises(validators.UserAbort):
            validators.ask_point_id(reader, print)

    def test_keyboard_interrupt_raises_user_abort(self):
        """Ctrl+C ต้องถูกแปลงเป็น UserAbort เช่นกัน"""
        def reader(prompt=""):
            raise KeyboardInterrupt

        with self.assertRaises(validators.UserAbort):
            validators.ask_point_id(reader, print)

