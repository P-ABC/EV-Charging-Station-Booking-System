"""tests/test_models.py — ทดสอบการ pack/unpack ของระเบียกทั้ง 3 ไฟล์

เน้นยืนยันว่า:
* ขนาดระเบียกตรงกับสเปก (82 / 24 / 8 ไบต์) และเป็น Little-Endian
* round-trip ข้อมูลไม่เสียหาย (ยกเว้นความแม่นยำ float32 ที่ยอมรับได้)
* สตริงถูก pad/ตัดตามขนาดฟิลด์ โดยไม่ตัดกลางอักขระ UTF-8
"""

import io
import struct
import unittest

import models


class TestRecordSizes(unittest.TestCase):
    """ตรวจขนาดระเบียกเทียบกับ struct.calcsize และสเปก"""

    def test_charge_point_record_is_82_bytes(self):
        """charge_points.dat: struct '<l10s30s10sfflllll' ต้องเป็น 82 ไบต์"""
        self.assertEqual(models.RECORD_SIZE, 82)
        self.assertEqual(models.CHARGE_POINT_STRUCT.size,
                         struct.calcsize(models.CHARGE_POINT_FORMAT))

    def test_log_record_is_24_bytes(self):
        """charge_points.log: '<lllllf' ต้องเป็น 24 ไบต์ (5 long + 1 float)"""
        self.assertEqual(models.LOG_RECORD_SIZE, 24)
        self.assertEqual(models.LOG_STRUCT.size,
                         struct.calcsize(models.LOG_FORMAT))

    def test_index_record_is_8_bytes(self):
        """index.dat: '<ll' ต้องเป็น 8 ไบต์"""
        self.assertEqual(models.INDEX_RECORD_SIZE, 8)
        self.assertEqual(models.INDEX_STRUCT.size,
                         struct.calcsize(models.INDEX_FORMAT))

    def test_formats_are_little_endian(self):
        """ทุกไฟล์ต้องใช้ Little-Endian (prefix '<')"""
        for fmt in (models.CHARGE_POINT_FORMAT, models.LOG_FORMAT,
                    models.INDEX_FORMAT):
            self.assertTrue(fmt.startswith("<"), f"{fmt} ต้องเป็น Little-Endian")

    def test_verify_record_sizes_passes(self):
        """ฟังก์ชันตรวจขนาดระเบียกต้องผ่าน (ไม่ raise)"""
        models.verify_record_sizes()      # ไม่ควรเกิด RuntimeError


class TestChargePointPackUnpack(unittest.TestCase):
    """ทดสอบ pack/unpack ของระเบียกหัวชาร์จ"""

    def _sample(self, **overrides) -> models.ChargePoint:
        """สร้างระเบียกตัวอย่างที่ใช้ร่วมกันในเทสต์นี้"""
        data = {
            "point_id": 1001,
            "station_code": "EVS-0001",
            # ต้องยาวไม่เกิน 30 ไบต์ จึงจะ round-trip ได้โดยไม่ถูกตัด
            # ("สถานี" = 18 ไบต์ + "ยาม" = 6 ไบต์ = 24 ไบต์)
            "location": "สถานียาม",
            "plug_type": "Type2",
            "power_kw": 7.4,
            "price_per_kwh": 6.0,
            "status": 1,
            "is_booked": 0,
            "is_deleted": 0,
            "created_at": 1_700_000_000,
            "updated_at": 1_700_000_100,
        }
        data.update(overrides)
        return models.ChargePoint(**data)

    def test_packed_size_is_exactly_82(self):
        """ข้อมูลที่ pack ต้องมีขนาด 82 ไบต์เสมอ"""
        self.assertEqual(len(self._sample().to_bytes()), 82)
        self.assertEqual(len(models.pack_charge_point(self._sample())), 82)

    def test_round_trip_preserves_all_fields(self):
        """pack แล้ว unpack ต้องได้ค่าเดิมทุกฟิลด์"""
        original = self._sample()
        restored = models.unpack_charge_point(original.to_bytes())
        self.assertEqual(restored.point_id, original.point_id)
        self.assertEqual(restored.station_code, original.station_code)
        self.assertEqual(restored.location, original.location)
        self.assertEqual(restored.plug_type, original.plug_type)
        self.assertEqual(restored.status, original.status)
        self.assertEqual(restored.is_booked, original.is_booked)
        self.assertEqual(restored.is_deleted, original.is_deleted)
        self.assertEqual(restored.created_at, original.created_at)
        self.assertEqual(restored.updated_at, original.updated_at)
        # float ถูกเก็บเป็น float32 จึงเทียบแบบประมาณได้
        self.assertAlmostEqual(restored.power_kw, original.power_kw, places=4)
        self.assertAlmostEqual(restored.price_per_kwh, original.price_per_kwh,
                               places=4)

    def test_float_is_32_bit(self):
        """ค่า float ในไฟล์ต้องเป็น 4 ไบต์ (float32)"""
        payload = self._sample(power_kw=1.0, price_per_kwh=1.0).to_bytes()
        offset = 4 + 10 + 30 + 10          # ข้ามฟิลด์ก่อนหน้า
        self.assertEqual(struct.unpack_from("<f", payload, offset)[0], 1.0)
        self.assertEqual(struct.unpack_from("<f", payload, offset + 4)[0], 1.0)

    def test_field_order_matches_spec(self):
        """ลำดับฟิลด์ในไฟล์ต้องเป็นตามสเปก (ตรวจจาก offset ของแต่ละฟิลด์)"""
        point = self._sample(point_id=7777, station_code="EVS-0099",
                             location="ABC", plug_type="GB-T",
                             power_kw=11.0, price_per_kwh=9.5,
                             status=1, is_booked=1, is_deleted=1,
                             created_at=111, updated_at=222)
        payload = point.to_bytes()
        self.assertEqual(struct.unpack_from("<l", payload, 0)[0], 7777)
        self.assertEqual(payload[4:14].split(b"\x00")[0], b"EVS-0099")
        self.assertEqual(payload[14:44].split(b"\x00")[0], b"ABC")
        self.assertEqual(payload[44:54].split(b"\x00")[0], b"GB-T")
        self.assertEqual(struct.unpack_from("<f", payload, 54)[0], 11.0)
        self.assertEqual(struct.unpack_from("<f", payload, 58)[0], 9.5)
        self.assertEqual(struct.unpack_from("<l", payload, 62)[0], 1)
        self.assertEqual(struct.unpack_from("<l", payload, 66)[0], 1)
        self.assertEqual(struct.unpack_from("<l", payload, 70)[0], 1)
        self.assertEqual(struct.unpack_from("<l", payload, 74)[0], 111)
        self.assertEqual(struct.unpack_from("<l", payload, 78)[0], 222)

    def test_unpack_rejects_wrong_length(self):
        """ข้อมูลที่สั้น/ยาวผิดต้องถูกปฏิเสธ (struct.error)"""
        with self.assertRaises(struct.error):
            models.unpack_charge_point(b"\x00" * 81)
        with self.assertRaises(struct.error):
            models.unpack_charge_point(b"\x00" * 83)

    def test_decode_from_bytesio(self):
        """ถอดรหัสระเบียกจาก io.BytesIO ได้ (ใช้จริงใน unit test)"""
        point = self._sample()
        buffer = io.BytesIO(point.to_bytes())
        restored = models.unpack_charge_point(buffer.read())
        self.assertEqual(restored.point_id, point.point_id)
class TestTextFieldEncoding(unittest.TestCase):
    """ทดสอบการเข้ารหัส/ถอดรหัสสตริง UTF-8 แบบความยาวคงที่"""

    def test_pad_short_string_with_null(self):
        """สตริงที่สั้นกว่าฟิลด์ต้องเติม \\x00 จนครบ"""
        raw = models.encode_text("AB", 5)
        self.assertEqual(len(raw), 5)
        self.assertEqual(raw, b"AB\x00\x00\x00")
        self.assertEqual(models.decode_text(raw), "AB")

    def test_exact_length_is_unchanged(self):
        """สตริงที่ยาวพอดีไม่ต้องเติมและไม่ถูกตัด"""
        raw = models.encode_text("EVS-0001", 10)
        self.assertEqual(len(raw), 10)
        self.assertEqual(models.decode_text(raw), "EVS-0001")

    def test_long_string_is_truncated_to_field_size(self):
        """สตริงที่ยาวเกินต้องถูกตัดให้เหลือพอดีขนาดฟิลด์"""
        raw = models.encode_text("A" * 50, 10)
        self.assertEqual(len(raw), 10)
        self.assertEqual(raw, b"A" * 10)

    def test_truncation_does_not_split_thai_character(self):
        """ห้ามตัดกลางอักขระ UTF-8 (ภาษาไทย 1 ตัว = 3 ไบต์)

        30 ไบต์ หารด้วย 3 ได้พอดี จึงได้ 10 ตัวอักษรไทยเต็ม ๆ
        แต่ถ้าเหลือเศษ 1-2 ไบต์ อักขระที่ถูกตัดครึ่งต้องถูกทิ้งไป (errors='ignore')
        """
        text = "ก" * 20                 # 60 ไบต์
        raw = models.encode_text(text, 30)
        self.assertEqual(len(raw), 30)
        self.assertEqual(raw.decode("utf-8"), "ก" * 10)

        # 29 ไบต์ = 9 ตัว (27 ไบต์) + 2 ไบต์ที่เหลือซึ่งเป็นอักขระครึ่ง
        raw = models.encode_text("ก" * 10, 29)
        self.assertLessEqual(len(raw), 29)
        # อักขระครึ่งตัวถูกทิ้งไป แล้วเติม \x00 ให้ครบ 29 ไบต์
        self.assertEqual(raw[:27].decode("utf-8"), "ก" * 9)
        self.assertEqual(raw[27:], b"\x00\x00")
        self.assertEqual(models.decode_text(raw), "ก" * 9)

    def test_no_replacement_character_after_truncation(self):
        """หลังตัดห้ามมีอักขระเพี้ยน (U+FFFD) ปนอยู่ในข้อมูล"""
        raw = models.encode_text("สถานีชาร์จไฟฟ้าสยามพารากอน", 30)
        self.assertNotIn(b"\xef\xbf\xbd", raw)     # ไบต์ของ U+FFFD
        self.assertNotIn("\ufffd", models.decode_text(raw))

    def test_decode_strips_trailing_nulls(self):
        """การอ่านต้องตัด \\x00 ท้ายสตริงออก"""
        self.assertEqual(models.decode_text(b"EVS-0001\x00\x00\x00"), "EVS-0001")

    def test_text_byte_length_counts_utf8_bytes(self):
        """text_byte_length ต้องคืนจำนวนไบต์จริงของ UTF-8"""
        self.assertEqual(models.text_byte_length("abc"), 3)
        self.assertEqual(models.text_byte_length("ก"), 3)
        self.assertEqual(models.text_byte_length(""), 0)

    def test_truncate_display_matches_encode_rule(self):
        """truncate_display ต้องให้ผลเดียวกับสิ่งที่ encode_text บันทึกจริง"""
        text = "สถานีชาร์จไฟฟ้าสยามพารากอนชั้นใต้ดิน"
        shown = models.truncate_display(text, 30)
        stored = models.decode_text(models.encode_text(text, 30))
        self.assertEqual(shown, stored)
        self.assertLessEqual(models.text_byte_length(stored), 30)


class TestLogAndIndexPack(unittest.TestCase):
    """ทดสอบ pack/unpack ของ audit log (24 ไบต์) และดัชนี (8 ไบต์)"""

    def test_log_entry_size_and_round_trip(self):
        """ระเบียก log ต้อง 24 ไบต์ และ round-trip ได้ครบ"""
        entry = models.LogEntry(ts=1_700_000_000, op_code=models.OP_UPDATE,
                                point_id=1001, status_after=1,
                                is_booked_after=1, price_after_thb=7.25)
        raw = models.pack_log_entry(entry)
        self.assertEqual(len(raw), 24)

        restored = models.unpack_log_entry(raw)
        self.assertEqual(restored.ts, entry.ts)
        self.assertEqual(restored.op_code, entry.op_code)
        self.assertEqual(restored.point_id, entry.point_id)
        self.assertEqual(restored.status_after, entry.status_after)
        self.assertEqual(restored.is_booked_after, entry.is_booked_after)
        self.assertAlmostEqual(restored.price_after_thb, 7.25, places=4)

    def test_log_field_order_matches_spec(self):
        """ลำดับฟิลดี��� log ต้องเป็น long x5 แล้วจึงเป็น float (ข้อสมมติฐานของโจทย์)"""
        raw = models.pack_log_entry(models.LogEntry(
            ts=11, op_code=2, point_id=33, status_after=1,
            is_booked_after=0, price_after_thb=1.5))
        self.assertEqual(struct.unpack_from("<l", raw, 0)[0], 11)
        self.assertEqual(struct.unpack_from("<l", raw, 4)[0], 2)
        self.assertEqual(struct.unpack_from("<l", raw, 8)[0], 33)
        self.assertEqual(struct.unpack_from("<l", raw, 12)[0], 1)
        self.assertEqual(struct.unpack_from("<l", raw, 16)[0], 0)
        self.assertEqual(struct.unpack_from("<f", raw, 20)[0], 1.5)

    def test_operation_names_map_from_op_code(self):
        """op_code ต้องแปลงเป็นชื่อ ADD/UPDATE/DELETE/VIEW ได้ถูกต้อง"""
        cases = {models.OP_ADD: "ADD", models.OP_UPDATE: "UPDATE",
                 models.OP_DELETE: "DELETE", models.OP_VIEW: "VIEW"}
        for code, name in cases.items():
            self.assertEqual(models.OPERATION_NAMES[code], name)

    def test_log_delete_status_text_is_deleted(self):
        """รายงานต้องแสดง Status = "Deleted" เมื่อ op_code = DELETE (3)"""
        entry = models.LogEntry(ts=1, op_code=models.OP_DELETE, point_id=1,
                                status_after=1, is_booked_after=0,
                                price_after_thb=1.0)
        self.assertEqual(entry.status_text, "Deleted")

    def test_index_entry_size_and_round_trip(self):
        """ระเบียกดัชนีต้อง 8 ไบต์ และ round-trip ได้ครบ"""
        raw = models.pack_index_entry(models.IndexEntry(point_id=1001,
                                                       log_seq=42))
        self.assertEqual(len(raw), 8)
        restored = models.unpack_index_entry(raw)
        self.assertEqual(restored.point_id, 1001)
        self.assertEqual(restored.log_seq, 42)

