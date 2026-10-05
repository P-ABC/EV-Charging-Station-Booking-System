"""main.py — เมนูหลักของโปรแกรม EV Charging Station Booking System

วิธีใช้งาน
----------
    python main.py                 # เข้าเมนูหลัก
    python main.py --seed          # สร้างข้อมูลตัวอย่างก่อน แล้วเข้าเมนู
    python main.py --data-dir X    # ใช้โฟลเดอร์เก็บข้อมูลอื่น
    python main.py --rebuild-index # สร้าง index.dat ใหม่จาก log แล้วออก
    python main.py --reset         # ลบไฟล์ข้อมูลทั้งหมด (เริ่มใหม่)

โครงสร้างเมนู (วนลูปจนกว่าจะเลือก 0)
-----------------------------------
    1) Add (เพิ่ม)
    2) Update (แก้ไข)
    3) Delete (ลบแบบ soft delete)
    4) View (ดู)  -> 4.1 / 4.2 / 4.3 / 4.4
    5) Generate Report (.txt)
    0) Exit (ปิดอย่างปลอดภัย: flush + os.fsync และสร้างรายงานอัตโนมัติ)
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

import index as index_module
import logger as logger_module
import models
import report as report_module
import reports as reports_module
import seed_data
import storage as storage_module
import validators

# เวลาอ้างอิงของระบบ (ใช้ตอนออกแบบเมนู ไม่ใช่เวลาจริงของเครื่อง)
TZ_NOTE = "+07:00"


class ChargingStationApp:
    """คลาสหลักของโปรแกรม เชื่อม storage / log / index / report เข้าด้วยกัน

    Attributes:
        data_dir: โฟลเดอร์ที่เก็บไฟล์ข้อมูลทั้ง 3 ไฟล์ + รายงาน
    """

    def __init__(self, data_dir: str = ".") -> None:
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.data_path = os.path.join(self.data_dir, models.DATA_FILE_NAME)
        self.log_path = os.path.join(self.data_dir, models.LOG_FILE_NAME)
        self.index_path = os.path.join(self.data_dir, models.INDEX_FILE_NAME)
        self.report_path = os.path.join(self.data_dir, models.REPORT_FILE_NAME)
        self.location_path = os.path.join(self.data_dir,
                                          models.LOCATION_FILE_NAME)

        self.store = storage_module.ChargePointStore(self.data_path)
        self.audit = logger_module.AuditLog(self.log_path)
        self.point_index = index_module.PointIndex(self.index_path)
        self.location_store = storage_module.LocationStore(self.location_path)

    # ------------------------------------------------------------------
    # การตรวจความถูกต้องของไฟล์ตอนเริ่มโปรแกรม
    # ------------------------------------------------------------------
    def startup_check(self, auto_repair: bool = True) -> List[str]:
        """ตรวจไฟล์ทั้ง 3 ไฟล์ตอนเริ่มโปรแกรม และซ่อมแซมที่ทำได้อัตโนมัติ

        ตรวจสอบ
            1. ขนาดไฟล์หารลงด้วย RECORD_SIZE ของแต่ละไฟล์หรือไม่
            2. index.dat สอดคล้องกับ charge_points.log หรือไม่ (ถ้าไม่ -> rebuild)

        Args:
            auto_repair: True = ตัด record ที่ไม่ครบและสร้าง index ใหม่อัตโนมัติ

        Returns:
            รายการข้อความที่แจ้งเตือนผู้ใช้ (ว่างเปล่า = ไม่มีปัญหา)
        """
        messages: List[str] = []

        for label, checker, truncate in (
            (models.DATA_FILE_NAME, self.store.integrity_check,
             self.store.truncate_incomplete),
            (models.LOG_FILE_NAME, self.audit.integrity_check,
             self.audit.truncate_incomplete),
            (models.INDEX_FILE_NAME, self.point_index.integrity_check,
             self.point_index.truncate_incomplete),
        ):
            valid, remainder = checker()
            if not valid:
                if auto_repair:
                    truncate()
                    messages.append(
                        f"[ซ่อมแซม] {label} เสียหาย (ท้ายไฟล์เหลือ {remainder} ไบต์ "
                        f"ที่ไม่ครบ record) — ตัดส่วนเกินทิ้งแล้ว"
                    )
                else:
                    messages.append(
                        f"[แจ้งเตือน] {label} ขนาดไม่หารลงตัว "
                        f"(เกิน {remainder} ไบต์) — โปรดตรวจสอบไฟล์"
                    )

        # สร้าง free-list ใหม่จากไฟล์ที่เพิ่งซ่อม เพื่อให้ slot ที่ว่างถูกต้อง
        self.store.refresh_free_slots()

        # ตรวจว่า index ตรงกับ log หรือไม่ -> ถ้าไม่ตรงให้สร้างใหม่
        log_entries = self.audit.read_all()
        problems = self.point_index.verify_against_log(log_entries)
        if problems:
            if auto_repair:
                rebuilt = self.point_index.rebuild(log_entries)
                messages.append(
                    f"[ซ่อมแซม] index.dat ไม่ตรงกับ log ({len(problems)} รายการ) "
                    f"— สร้างดัชนีใหม่จาก log แล้ว ({rebuilt} รายการ)"
                )
            else:
                messages.append(
                    f"[แจ้งเตือน] index.dat ไม่ตรงกับ log ({len(problems)} รายการ) "
                    f"— แนะนำให้ใช้คำสั่ง --rebuild-index"
                )
        return messages

    # ------------------------------------------------------------------
    # ฟังก์ชันช่วยเหลือ (บันทึก log + อัปเดต index ให้ตรงกันเสมอ)
    # ------------------------------------------------------------------
    def _record_event(self, point: models.ChargePoint,
                      op_code: int) -> int:
        """เขียน audit log 1 record แล้วอัปเดต index ให้ชี้ log_seq ล่าสุด

        ทุกเหตุการณ์ Add/Update/Delete/View ต้องเรียกฟังก์ชันนี้ เพื่อให้
        index.dat และ log ไม่หลุดจากกัน

        Returns:
            log_seq ที่บันทึกได้
        """
        seq = self.audit.append(point.point_id, op_code, point)
        self.point_index.update(point.point_id, seq)
        return seq

    # ------------------------------------------------------------------
    # ชั้นบริการ (service layer) — โค้ดหลักของ CRUD ที่ไม่ต้องโต้ตอบ
    # ------------------------------------------------------------------
    # เมนู Add/Update/Delete เรียกใช้ฟังก์ชันชุดนี้หลังรับค่าจากผู้ใช้เรียบร้อยแล้ว
    # ทำให้ตรรกะทั้งหมดทดสอบด้วย unittest ได้โดยไม่ต้องจำลอง stdin
    def add_record(self, point_id: int, station_code: str, location: str,
                   plug_type: str, power_kw: float, price_per_kwh: float,
                   status: int = 1, is_booked: int = 0) -> models.ChargePoint:
        """เพิ่มหัวชาร์จ 1 หัวลงไฟล์ + log + index (ตรรกะหลักของเมนู Add)

        Raises:
            DuplicatePointError: เมื่อ point_id ซ้ำกับ record ที่ยังไม่ถูกลบ
        """
        if self.store.exists(point_id):
            raise storage_module.DuplicatePointError(
                f"point_id {point_id} มีอยู่ในระบบแล้ว "
                f"(รหัสหัวชาร์จต้องไม่ซ้ำกัน)"
            )
        now = models.now_timestamp()
        point = models.ChargePoint(
            point_id=point_id,
            station_code=station_code,
            location=models.truncate_display(location, models.LOCATION_MAX_BYTES),
            plug_type=plug_type,
            power_kw=float(power_kw),
            price_per_kwh=float(price_per_kwh),
            status=int(status),
            is_booked=int(is_booked),
            is_deleted=0,
            created_at=now,
            updated_at=now,
        )
        # allocate_slot จะนำช่องว่างที่เคย soft delete ทิ้งมาใช้ซ้ำก่อนเสมอ
        self.store.allocate_slot(point)
        # เก็บชื่อสถานที่แบบเต็มไว้ในไฟล์ข้อความ เพื่อให้รายงานแสดงได้ครบ
        # (record ไบนารีเก็บค่าที่ตัดถึง 30 ไบต์ตามสเปก)
        self.location_store.set(point_id, location)
        self._record_event(point, models.OP_ADD)
        return point

    def update_record(self, point_id: int, **changes) -> models.ChargePoint:
        """แก้ไขหัวชาร์จ 1 หัว (ตรรกะหลักของเมนู Update)

        แก้ได้เฉพาะฟิลด์ที่ระบุใน ``changes`` (ค่าที่ไม่ได้ระบุจะคงเดิม)
        ห้ามแก้ point_id และ created_at ตามข้อกำหนด

        Args:
            point_id: รหัสหัวชาร์จที่ต้องการแก้
            **changes: ฟิลด์ที่แก้ (station_code, location, plug_type,
                power_kw, price_per_kwh, status, is_booked)

        Raises:
            PointNotFoundError: เมื่อไม่พบ point_id
            KeyError: เมื่อส่งฟิลด์ที่ไม่อนุญาตให้แก้
        """
        slot = self.store.find_slot(point_id)
        if slot is None:
            raise storage_module.PointNotFoundError(
                f"ไม่พบหัวชาร์จ point_id={point_id} ในระบบ (อาจถูกลบไปแล้ว)"
            )
        point = self.store.read_at(slot)

        allowed = ("station_code", "location", "plug_type", "power_kw",
                   "price_per_kwh", "status", "is_booked")
        for field in changes:
            if field not in allowed:
                raise KeyError(f"ไม่สามารถแก้ไขฟิลด์ '{field}' ได้")

        updated = models.ChargePoint(
            point_id=point.point_id,                     # ห้ามแก้ (Primary Key)
            station_code=changes.get("station_code", point.station_code),
            location=models.truncate_display(
                changes.get("location", point.location), models.LOCATION_MAX_BYTES),
            plug_type=changes.get("plug_type", point.plug_type),
            power_kw=float(changes.get("power_kw", point.power_kw)),
            price_per_kwh=float(changes.get("price_per_kwh", point.price_per_kwh)),
            status=int(changes.get("status", point.status)),
            is_booked=int(changes.get("is_booked", point.is_booked)),
            is_deleted=point.is_deleted,
            created_at=point.created_at,                 # ห้ามแก้
            updated_at=models.now_timestamp(),
        )
        self.store.write_at(slot, updated)               # seek + write ทับ record เดิม
        if "location" in changes:
            # อัปเดตชื่อสถานที่แบบเต็มด้วย (ถ้าผู้ใช้กรอกค่าใหม่)
            self.location_store.set(point_id, changes["location"])
        self._record_event(updated, models.OP_UPDATE)
        return updated

    def delete_record(self, point_id: int) -> models.ChargePoint:
        """ลบหัวชาร์จแบบ soft delete (ตรรกะหลักของเมนู Delete)

        Raises:
            PointNotFoundError: เมื่อไม่พบ point_id
            StorageError: เมื่อหัวชาร์จกำลังถูกจองอยู่ (is_booked=1) ซึ่งลบไม่ได้
        """
        slot = self.store.find_slot(point_id)
        if slot is None:
            raise storage_module.PointNotFoundError(
                f"ไม่พบหัวชาร์จ point_id={point_id} ในระบบ"
            )
        point = self.store.read_at(slot)

        # ห้ามลบหัวชาร์จที่กำลังถูกจองอยู่ (ข้อกำหนดด้านความถูกต้องของข้อมูล)
        if point.is_booked == 1:
            raise storage_module.StorageError(
                f"หัวชาร์จ {point_id} กำลังถูกจองอยู่ (is_booked=1) "
                f"— กรุณาปล่อยหัวชาร์จก่อนจึงจะลบได้"
            )

        deleted = models.ChargePoint(
            point_id=point.point_id,
            station_code=point.station_code,
            location=point.location,
            plug_type=point.plug_type,
            power_kw=point.power_kw,
            price_per_kwh=point.price_per_kwh,
            status=point.status,
            is_booked=point.is_booked,
            is_deleted=1,
            created_at=point.created_at,
            updated_at=models.now_timestamp(),
        )
        self.store.write_at(slot, deleted)
        self._record_event(deleted, models.OP_DELETE)

        # เพิ่ม slot นี้เข้า free-list เพื่อให้นำกลับมาใช้ได้ใน Add ครั้งถัดไป
        if slot not in self.store.free_slots:
            self.store.free_slots.append(slot)
            self.store.free_slots.sort()
        return deleted

    def view_record(self, point_id: int) -> Optional[models.ChargePoint]:
        """อ่านหัวชาร์จ 1 หัวพร้อมเขียน log (op=VIEW) ตามข้อกำหนด

        Returns:
            record ที่พบ หรือ None เมื่อไม่พบ (ค้นหารวม record ที่ถูก soft delete)
        """
        slot = self.store.find_slot(point_id, include_deleted=True)
        if slot is None:
            return None
        point = self.store.read_at(slot)
        self._record_event(point, models.OP_VIEW)
        return point

    def history_of(self, point_id: int, limit: int = 10) -> List[models.LogEntry]:
        """คืนประวัติของ point_id โดยอ่านผ่าน index.dat (เริ่มที่ log_seq ล่าสุด)

        สาธิตการใช้ index: ดัชนีให้ log_seq ล่าสุด จากนั้นจึง seek ไปที่
        log_seq * 24 ได้เลย โดยไม่ต้องไล่อ่าน log ทั้งไฟล์
        """
        log_seq = self.point_index.get(point_id)
        if log_seq is None:
            return []
        return self.audit.read_for_point(point_id, from_seq=log_seq, limit=limit)

    # ------------------------------------------------------------------
    # เมนู 1) Add
    # ------------------------------------------------------------------
    def add_point(self) -> Optional[models.ChargePoint]:
        """เพิ่มหัวชาร์จใหม่ 1 หัว (รับข้อมูลครบทุกฟิลด์)

        ขั้นตอน:
            1. รับและตรวจสอบข้อมูลทุกฟิลด์ (ถ้าผิดจะถามใหม่)
            2. ตรวจ point_id ซ้ำกับ record ที่ยังไม่ถูกลบหรือไม่
            3. จัดสรรช่อง (ใช้ช่องว่างที่เคยลบทิ้งก่อน ไม่งั้นต่อท้ายไฟล์)
            4. ตั้ง created_at/updated_at = เวลาปัจจุบัน
            5. เขียน log (op=ADD) และอัปเดต index

        Returns:
            record ที่สร้างสำเร็จ หรือ None เมื่อ point_id ซ้ำ
        """
        print("\n--- Add New Charge Point ---")
        point_id = validators.ask_point_id()

        # ตรวจซ้ำก่อนถามข้อมูลอื่น ประหยัดเวลาผู้ใช้
        if self.store.exists(point_id):
            print(f"   [ข้อผิดพลาด] point_id {point_id} มีอยู่ในระบบแล้ว "
                  f"(รหัสหัวชาร์จต้องไม่ซ้ำกัน)")
            return None

        station_code = validators.ask_station_code()
        location = validators.ask_location()
        plug_type = validators.ask_plug_type()
        power_kw = validators.ask_power_kw()
        price_per_kwh = validators.ask_price_per_kwh()
        print("   Status : 1 = Active, 0 = Inactive (ปิดซ่อมบำรุง)")
        status = validators.ask_binary("Status")
        print("   Booked : 1 = มีการจอง/กำลังชาร์จ, 0 = ว่าง")
        is_booked = validators.ask_binary("Booked")

        try:
            point = self.add_record(point_id, station_code, location, plug_type,
                                    power_kw, price_per_kwh, status, is_booked)
        except storage_module.DuplicatePointError as exc:
            print(f"   [ข้อผิดพลาด] {exc}")
            return None

        slot = self.store.find_slot(point_id)
        reused = slot is not None and slot < self.store.count_records() - 1
        message = ("นำช่องที่เคยถูกลบทิ้งกลับมาใช้ซ้ำ" if reused
                   else "เพิ่มต่อท้ายไฟล์")
        print(f"   [สำเร็จ] เพิ่มหัวชาร์จ {point_id} สำเร็จ "
              f"(slot={slot}, {message})")
        return point
    # ------------------------------------------------------------------
    # เมนู 2) Update
    # ------------------------------------------------------------------
    def update_point(self) -> Optional[models.ChargePoint]:
        """แก้ไขหัวชาร์จ 1 หัว (แก้ได้ทุกฟิลด์ ยกเว้น point_id และ created_at)

        รองรับการสลับ status และ is_booked (จอง/ปล่อยหัวชาร์จ)
        อัปเดต updated_at เป็นเวลาปัจจุบัน เขียนทับ record เดิมด้วย seek
        แล้วเขียน log (op=UPDATE) พร้อมอัปเดต index

        Returns:
            record หลังแก้ไข หรือ None เมื่อไม่พบ point_id
        """
        print("\n--- Update Charge Point ---")
        point_id = validators.ask_point_id()
        slot = self.store.find_slot(point_id)
        if slot is None:
            print(f"   [ไม่พบ] ไม่พบหัวชาร์จ point_id={point_id} "
                  f"ในระบบ (อาจถูกลบไปแล้ว)")
            return None

        point = self.store.read_at(slot)
        print("   ข้อมูลปัจจุบัน:")
        for line in report_module.render_point_card(point):
            print(f"     {line}")
        print("   (กด Enter เพื่อคงค่าเดิม)")

        station_code = self._ask_optional(
            "Station Code", point.station_code, validators.validate_station_code)
        location = self._ask_optional(
            "Location", point.location, validators.validate_location)
        plug_type = self._ask_optional(
            "Plug Type", point.plug_type, validators.validate_plug_type)
        power_kw = self._ask_optional(
            "Power (kW)", point.power_kw,
            lambda v: validators.validate_positive_float(v, "Power (kW)"))
        price = self._ask_optional(
            "Price (THB/kWh)", point.price_per_kwh,
            lambda v: validators.validate_positive_float(v, "Price (THB/kWh)"))
        status = self._ask_optional(
            "Status (1=Active, 0=Inactive)", point.status,
            lambda v: validators.validate_binary(v, "Status"))
        is_booked = self._ask_optional(
            "Booked (1=จอง, 0=ว่าง)", point.is_booked,
            lambda v: validators.validate_binary(v, "Booked"))

        # ส่งต่อให้ชั้นบริการ (update_record) เป็นผู้เขียนทับ + บันทึก log/index
        updated = self.update_record(
            point_id,
            station_code=station_code,
            location=location,
            plug_type=plug_type,
            power_kw=power_kw,
            price_per_kwh=price,
            status=status,
            is_booked=is_booked,
        )
        print(f"   [สำเร็จ] อัปเดตหัวชาร์จ {point_id} แล้ว (slot={slot})")
        return updated

    @staticmethod
    def _ask_optional(label: str, current_value, validator):
        """ถามค่าใหม่โดยมีค่าเดิมเป็นค่าเริ่มต้น (กด Enter = คงค่าเดิม)

        หากผู้ใช้กรอกค่าผิด จะแจ้งและถามใหม่ (ไม่ยกเลิกอัตโนมัติ)

        Args:
            label: ชื่อฟิลด์ที่แสดงใน prompt
            current_value: ค่าเดิม (แสดงเป็นค่าเริ่มต้นในวงเล็บ)
            validator: ฟังก์ชันตรวจสอบค่าใหม่

        Returns:
            ค่าใหม่ที่ผ่านการตรวจสอบแล้ว หรือค่าเดิมถ้ากด Enter

        Raises:
            validators.UserAbort: เมื่อ stdin หมด (EOF) หรือผู้ใช้กด Ctrl+C
        """
        while True:
            # ใช้ _read_line ของ validators เพื่อแปลง EOFError / KeyboardInterrupt
            # เป็น UserAbort เหมือนฟังก์ชัน ask_* อื่น ๆ (ไม่ให้โปรแกรม crash)
            raw = validators._read_line(
                f"   {label} [{current_value}] : ", input).strip()
            if raw == "":
                return current_value
            try:
                return validator(raw)
            except validators.ValidationError as exc:
                print(f"   [ข้อผิดพลาด] {exc}")

    # ------------------------------------------------------------------
    # เมนู 3) Delete (soft delete)
    # ------------------------------------------------------------------
    def delete_point(self) -> bool:
        """ลบหัวชาร์จแบบ soft delete (ตั้ง is_deleted=1) โดยต้องยืนยันก่อน

        ข้อกำหนด:
            * ต้องขอยืนยัน (y/n) ก่อนทำจริง
            * ห้ามลบหัวชาร์จที่ is_booked=1 (กำลังถูกจอง/ชาร์จอยู่)

        Returns:
            True เมื่อลบสำเร็จ, False เมื่อยกเลิก/ไม่พบ/ถูกจองอยู่
        """
        print("\n--- Delete Charge Point (soft delete) ---")
        point_id = validators.ask_point_id()
        slot = self.store.find_slot(point_id)
        if slot is None:
            print(f"   [ไม่พบ] ไม่พบหัวชาร์จ point_id={point_id} ในระบบ")
            return False

        point = self.store.read_at(slot)

        # ห้ามลบหัวที่กำลังถูกจองอยู่ (กติกาความปลอดภัยของข้อมูล)
        if point.is_booked == 1:
            print(f"   [ปฏิเสธ] หัวชาร์จ {point_id} กำลังถูกจองอยู่ "
                  f"(is_booked=1) — กรุณาปล่อยหัวชาร์จก่อนจึงจะลบได้")
            return False

        for line in report_module.render_point_card(point):
            print(f"     {line}")

        if not validators.ask_yes_no(f"   ยืนยันการลบ point_id={point_id} ?",
                                      default=False):
            print("   [ยกเลิก] ยกเลิกการลบแล้ว")
            return False

        # ส่งต่อให้ชั้นบริการ (delete_record) เขียน soft delete + log + free-list
        self.delete_record(point_id)
        print(f"   [สำเร็จ] ลบหัวชาร์จ {point_id} แบบ soft delete "
              f"(ช่องว่างที่นำกลับมาใช้ได้: {len(self.store.free_slots)})")
        return True

    # ------------------------------------------------------------------
    # เมนู 4.1) View รายการเดียว + ประวัติล่าสุดผ่าน index.dat
    # ------------------------------------------------------------------
    def view_single(self) -> None:
        """ดูหัวชาร์จ 1 หัวตาม point_id พร้อมแสดงประวัติล่าสุด

        การดูรายการเดียวต้องเขียน log (op=VIEW) ตามข้อกำหนด และแสดงประวัติ
        ล่าสุดของ point_id นั้น โดยอ่านผ่าน index.dat (seek ไปที่ log_seq*24)
        """
        print("\n--- View Single Charge Point ---")
        point_id = validators.ask_point_id()

        # view_record จะเขียน log (op=VIEW) และอัปเดต index ให้อัตโนมัติ
        point = self.view_record(point_id)
        if point is None:
            print(f"   [ไม่พบ] ไม่พบหัวชาร์จ point_id={point_id} ในระบบ")
            return

        for line in report_module.render_point_card(point):
            print(f"   {line}")

        # ดึงประวัติจาก index.dat: ใช้ log_seq ล่าสุดเป็นจุดเริ่มอ่านย้อนหลัง
        log_seq = self.point_index.get(point_id)
        print(f"\n   --- ประวัติล่าสุด (อ่านผ่าน index.dat, log_seq={log_seq}) ---")
        if log_seq is None:
            print("     (ไม่พบ record ใน index.dat — อาจต้องใช้ --rebuild-index)")
            return
        history = self.history_of(point_id, limit=10)
        if not history:
            print("     (ไม่มีประวัติ)")
            return
        rows = [
            (report_module.format_timestamp(entry.ts), entry.op_name,
             entry.status_text, entry.booked_text,
             f"{entry.price_after_thb:.2f}")
            for entry in history
        ]
        headers = ["Timestamp", "Operation", "Status", "Booked", "Price"]
        for line in report_module.render_table(headers, rows):
            print(f"   {line}")

    # ------------------------------------------------------------------
    # เมนู 4.2) View ทั้งหมด
    # ------------------------------------------------------------------
    def view_all(self) -> None:
        """ดูหัวชาร์จทั้งหมด (ขอรวม record ที่ถูก soft delete ด้วย)

        ตามข้อกำหนด: 4.2 เป็นเมนูที่ "รวมที่ลบแล้ว" จึงแสดง record ทั้งหมด
        คอลัมน์ Status จะแสดง Deleted สำหรับ record ที่ถูกลบ
        """
        print("\n--- View All Charge Points (including deleted) ---")
        points = self.store.read_all(include_deleted=True)
        if not points:
            print("   (ยังไม่มีข้อมูลในระบบ — เลือกเมนู 1 เพื่อเพิ่มข้อมูล)")
            return

        rows = [
            (str(point.point_id), point.station_code,
             self.location_store.full_location(point),
             point.plug_type, f"{point.power_kw:.1f}",
             f"{point.price_per_kwh:.2f}", point.status_text, point.booked_text)
            for point in points
        ]
        headers = ["PtID", "Station", "Location", "Plug", "Power(kW)",
                   "Price(THB/kWh)", "Status", "Booked"]
        # ไม่จำกัดความกว้างบน Terminal เพื่อให้ชื่อสถานที่ตั้งแสดงครบทุกตัวอักษร
        # (Terminal ปรับความกว้างเองได้ ต่างจากไฟล์ .txt ที่ต้องพอดีหน้าจอ)
        for line in report_module.render_table(headers, rows, max_width=None):
            print(line)
        print(f"   รวม {len(points)} record "
              f"(ข้อมูลในไฟล์: {self.store.count_records()} record)")

    # ------------------------------------------------------------------
    # เมนู 4.3) View แบบกรอง
    # ------------------------------------------------------------------
    def view_filtered(self) -> None:
        """ดูหัวชาร์จแบบกรองตาม station_code / plug_type / status / is_booked

        ใช้ตัวเลือกเมนู 1-4 เพื่อเลือกเงื่อนไข แล้วค่อยกรอกค่าที่ต้องการกรอง
        (กด Enter เว้นว่าง = ไม่กรองเงื่อนไขนั้น)
        """
        print("\n--- View Filtered Charge Points ---")
        print("   เลือกเงื่อนไขที่ต้องการกรอง:")
        print("     1) station_code")
        print("     2) plug_type")
        print("     3) status (1=Active, 0=Inactive)")
        print("     4) is_booked (1=จอง, 0=ว่าง)")
        choice = validators.ask_menu_choice("   เลือก [1-4] : ", (1, 2, 3, 4))

        points = self.store.read_all(include_deleted=False)
        field_name = ""
        if choice == 1:
            field_name = "station_code"
            value = validators.ask_station_code()
            points = [p for p in points if p.station_code.upper() == value.upper()]
        elif choice == 2:
            field_name = "plug_type"
            value = validators.ask_plug_type()
            points = [p for p in points if p.plug_type == value]
        elif choice == 3:
            field_name = "status"
            value = validators.ask_binary("Status")
            points = [p for p in points if p.status == value]
        else:
            field_name = "is_booked"
            value = validators.ask_binary("Booked")
            points = [p for p in points if p.is_booked == value]

        if not points:
            print(f"   ไม่พบข้อมูลที่ตรงกับเงื่อนไข "
                  f"{field_name}={value} (ระบบข้าม record ที่ถูกลบแล้ว)")
            return

        rows = [
            (str(point.point_id), point.station_code,
             self.location_store.full_location(point),
             point.plug_type, f"{point.power_kw:.1f}",
             f"{point.price_per_kwh:.2f}", point.status_text, point.booked_text)
            for point in points
        ]
        headers = ["PtID", "Station", "Location", "Plug", "Power(kW)",
                   "Price(THB/kWh)", "Status", "Booked"]
        print(f"   ผลลัพธ์ ({field_name}={value}): พบ {len(points)} record")
        # ไม่จำกัดความกว้างบน Terminal เพื่อให้ชื่อสถานที่ตั้งแสดงครบ
        for line in report_module.render_table(headers, rows, max_width=None):
            print(line)

    # ------------------------------------------------------------------
    # เมนู 4.4) สถิติโดยสรุป
    # ------------------------------------------------------------------
    def view_statistics(self) -> None:
        """แสดงสถิติโดยสรุปของระบบ (นับเฉพาะสถานะ Active ตามสเปกรายงาน)"""
        print("\n--- Summary Statistics ---")
        points = self.store.read_all(include_deleted=True)
        summary = report_module.compute_summary(points)
        stats = report_module.compute_price_stats(points)
        plugs = report_module.count_plug_types(points)

        print(f"   - Total Points (records) : {summary['total']}")
        print(f"   - Active Points          : {summary['active']}")
        print(f"   - Deleted Points         : {summary['deleted']}")
        print(f"   - Currently Booked       : {summary['booked']}")
        print(f"   - Available Now          : {summary['available']}")
        print(f"   - Free Slots             : {summary['free_slots']}")
        print(f"   - Price Min/Max/Avg      : {stats['min']:.2f} / "
              f"{stats['max']:.2f} / {stats['avg']:.2f} THB/kWh")
        print(f"   - CCS2: {plugs['CCS2']}, Type2: {plugs['Type2']}, "
              f"CHAdeMO: {plugs['CHAdeMO']}, GB-T: {plugs['GB-T']}")
        print(f"   - Log events             : {self.audit.count()} "
              f"| Index entries: {self.point_index.count()}")

    # ------------------------------------------------------------------
    # เมนู 4) View (ตัวเลือกเมนูย่อย)
    # ------------------------------------------------------------------
    def menu_view(self) -> None:
        """แสดงเมนูย่อยของ View (4.1 / 4.2 / 4.3 / 4.4)"""
        print("\n=== View Menu ===")
        print("   1) ดูรายการเดียว (ตาม point_id)")
        print("   2) ดูทั้งหมด")
        print("   3) ดูแบบกรอง (station_code / plug_type / status / is_booked)")
        print("   4) สถิติโดยสรุป")
        choice = validators.ask_menu_choice("   เลือก [1-4] : ", (1, 2, 3, 4))
        if choice == 1:
            self.view_single()
        elif choice == 2:
            self.view_all()
        elif choice == 3:
            self.view_filtered()
        else:
            self.view_statistics()

    # ------------------------------------------------------------------
    # เมนู 5) Generate Report
    # ------------------------------------------------------------------
    def generate_report(self, silent: bool = False) -> Dict[str, str]:
        """สร้างรายงานทั้ง 3 ชุดเป็นไฟล์ .txt แยกกัน จากข้อมูลปัจจุบัน

        อ่านข้อมูลสดจากทั้ง 3 ไฟล์ไบนารีทุกครั้งที่เรียก จึงสะท้อนผลการ
        แก้ไข/เพิ่ม/ลบข้อมูลล่าสุดเสมอ (เกณฑ์ข้อ 6)

        Returns:
            dict {ชื่อไฟล์รายงาน: พาธไฟล์เต็ม}
        """
        points = self.store.read_all(include_deleted=True)
        log_entries = self.audit.read_all()
        index_map = self.point_index.as_dict()
        store_valid = self.store.integrity_check()[0]
        log_valid = self.audit.integrity_check()[0]
        index_valid = self.point_index.integrity_check()[0]

        created = reports_module.generate_all_reports(
            self.data_dir, points, log_entries, index_map,
            store_valid=store_valid, log_valid=log_valid,
            index_valid=index_valid,
            locations=self.location_store.as_dict(),
        )
        if not silent:
            summary = report_module.compute_summary(points)
            print(f"   [สำเร็จ] สร้างรายงาน {len(created)} ชุด "
                  f"(record {summary['total']} รายการ | "
                  f"เหตุการณ์ใน log {len(log_entries)} รายการ):")
            for file_name, path in created.items():
                print(f"      - {file_name}")
        return created

    def show_report_files(self) -> None:
        """แสดงรายการไฟล์รายงานที่มีอยู่ในโฟลเดอร์ พร้อมขนาดและจำนวนบรรทัด

        ใช้ตรวจว่ารายงานแต่ละชุดเป็นไฟล์แยกกันจริง (เกณฑ์ข้อ 4)
        """
        print("\n--- รายงานที่สร้างไว้ในระบบ ---")
        found = False
        for file_name in reports_module.ALL_REPORT_NAMES:
            path = os.path.join(self.data_dir, file_name)
            if os.path.exists(path):
                found = True
                size = os.path.getsize(path)
                with open(path, "r", encoding="utf-8") as fh:
                    lines = fh.read().splitlines()
                has_spec = any("[COLUMN SPECIFICATION]" in line for line in lines)
                has_table = any(line.startswith("+") or line.startswith("|")
                                for line in lines)
                has_summary = any("[SUMMARY]" in line for line in lines)
                print(f"   {file_name}")
                print(f"      ขนาด {size} ไบต์ | {len(lines)} บรรทัด | "
                      f"แหล่งข้อมูลหลายไฟล์: "
                      f"{'ใช่' if reports_module.report_uses_multiple_sources(file_name) else 'ไม่ใช่'}")
                print(f"      ส่วนที่ 1 รายละเอียดหัวตาราง: "
                      f"{'มี' if has_spec else 'ไม่มี'} | "
                      f"ส่วนที่ 2 ตาราง: {'มี' if has_table else 'ไม่มี'} | "
                      f"ส่วนที่ 3 ส่วนสรุป: {'มี' if has_summary else 'ไม่มี'}")
        if not found:
            print("   (ยังไม่มีไฟล์รายงาน — เลือกเมนู 5 เพื่อสร้าง)")

    def menu_tools(self) -> None:
        """แสดงเมนูเครื่องมือ (เมนู 6) — รวมงานที่ต้องทำผ่านเมนูเดียวกัน

        เกณฑ์ข้อ 5: การโหลดข้อมูลตัวอย่างและการซ่อมแซมดัชนีต้องทำได้จาก
        เมนูนี้ ไม่ต้องรันโปรแกรมแยกอีก
        """
        print("\n=== Tools Menu ===")
        print("   1) โหลดข้อมูลตัวอย่าง (55 record) — เขียนทับข้อมูลเดิม")
        print("   2) สร้าง index.dat ใหม่จาก charge_points.log")
        print("   3) ตรวจสอบความถูกต้องของไฟล์ทั้ง 3 ไฟล์")
        print(f"   4) โหมดจัดความกว้างตาราง (ปัจจุบัน: {report_module.alignment_mode_name()})")
        choice = validators.ask_menu_choice("   เลือก [1-4] : ", (1, 2, 3, 4))

        if choice == 1:
            if self.store.count_records() and not validators.ask_yes_no(
                    "   มีข้อมูลเดิมอยู่ ต้องการเขียนทับหรือไม่?", default=False):
                print("   [ยกเลิก] ยกเลิกการโหลดข้อมูลตัวอย่าง")
                return
            result = seed_data.seed(self.data_dir, force=True, printer=print)
            # เปิดใหม่เพื่อรีเฟรชแคชของ store / log / index ให้ตรงกับไฟล์ใหม่
            self.store.refresh_free_slots()
            self.app_reload()
            print(f"   [สำเร็จ] โหลดข้อมูลตัวอย่าง {result['records']} record")
            print("           เลือกเมนู 5 เพื่อสร้างรายงานจากข้อมูลชุดนี้")
        elif choice == 2:
            rebuilt = seed_data.rebuild_index(self.log_path, self.index_path)
            self.point_index.load()
            print(f"   [สำเร็จ] สร้าง index.dat ใหม่จาก log แล้ว ({rebuilt} รายการ)")
        elif choice == 3:
            self.check_file_health()
        else:
            self.switch_alignment_mode()

    def switch_alignment_mode(self) -> None:
        """สลับโหมดจัดความกว้างตาราง แล้วสร้างรายงานใหม่ทันที

        ปัญหาที่แก้
        ---------
        สระ/วรรณยุกต์ไทยเป็นอักขระประสม (นับเป็น 1 ตัวอักษร แต่กินพื้นที่ 0 ช่อง)
        ทำให้ "จำนวนตัวอักษร" กับ "ความกว้างจริง" ของบรรทัดไม่เท่ากัน
        โปรแกรมที่เปิดไฟล์จึงวางเส้น "|" ไม่ตรงกันได้

        โหมดที่เลือกได้
        ---------------
        * smart  — นับสระ/วรรณยุกต์ไทยเป็น 0 ช่อง (ถูกต้องตามมาตรฐาน Unicode)
          เหมาะกับ Windows Terminal / VS Code / Notepad ที่จัดวางสระไทยได้
        * simple — นับทุกตัวอักษรเป็น 1 ช่อง
          เหมาะกับโปรแกรมที่ไม่จัดวางสระไทยหรือไม่มีฟอนต์ไทย (จะเห็นเป็นกล่องสี่เหลี่ยม)
        """
        current = report_module.alignment_mode_name()
        new_mode = "simple" if current == "smart" else "smart"
        print("\n--- โหมดจัดความกว้างตาราง ---")
        print(f"   ปัจจุบัน : {current}")
        print(f"   เปลี่ยนเป็น: {new_mode}")
        print("   smart  = สระไทยกิน 0 ช่อง (Windows Terminal / VS Code / Notepad)")
        print("   simple = ทุกตัวอักษรกิน 1 ช่อง (โปรแกรมไม่จัดวางสระไทย)")
        report_module.set_alignment_mode(new_mode == "smart")
        print(f"   [สำเร็จ] เปลี่ยนเป็นโหมด {new_mode} แล้ว")
        print("           เลือกเมนู 5 เพื่อสร้างรายงานใหม่ด้วยโหมดนี้")

    def app_reload(self) -> None:
        """เปิดไฟล์ทั้ง 3 ใหม่เพื่อรีเฟรชแคชในหน่วยความจำ

        จำเป็นเมื่อไฟล์ถูกเขียนทับจากภายนอก (เช่น โหลดข้อมูลตัวอย่าง)
        """
        self.store = storage_module.ChargePointStore(self.data_path)
        self.audit = logger_module.AuditLog(self.log_path)
        self.point_index = index_module.PointIndex(self.index_path)
        self.location_store = storage_module.LocationStore(self.location_path)
        self.store.refresh_free_slots()

    def check_file_health(self) -> None:
        """ตรวจความถูกต้องของไฟล์ไบนารีทั้ง 3 ไฟล์และรายงานผล"""
        print("\n--- ผลตรวจความถูกต้องของไฟล์ ---")
        for label, checker, path, record_size in (
            (models.DATA_FILE_NAME, self.store.integrity_check,
             self.data_path, models.RECORD_SIZE),
            (models.LOG_FILE_NAME, self.audit.integrity_check,
             self.log_path, models.LOG_RECORD_SIZE),
            (models.INDEX_FILE_NAME, self.point_index.integrity_check,
             self.index_path, models.INDEX_RECORD_SIZE),
        ):
            valid, remainder = checker()
            size = os.path.getsize(path)
            status = "ผ่าน" if valid else f"ผิดปกติ (เกิน {remainder} ไบต์)"
            print(f"   {label}: {size} ไบต์ = {size // record_size} record "
                  f"x {record_size} ไบต์ | {status}")

        problems = self.point_index.verify_against_log(self.audit.read_all())
        if problems:
            print(f"   index.dat ไม่สอดคล้องกับ log ({len(problems)} รายการ):")
            for problem in problems[:5]:
                print(f"      - {problem}")
            print("   แนะนำ: เลือก 6) Tools > 2) สร้าง index.dat ใหม่")
        else:
            print("   index.dat สอดคล้องกับ charge_points.log ทั้งหมด")
        print(f"   ช่องว่างที่นำกลับมาใช้ได้: {self.store.free_slot_count()} ช่อง")

    def menu_report(self) -> None:
        """แสดงเมนูย่อยของการสร้างรายงาน (เมนู 5 ของเมนูหลัก)

        เกณฑ์ข้อ 5: ทุกงานรวมถึงการดูรายงานต้องทำผ่านเมนูชุดเดียวกัน
        โดยไม่ต้องรันโปรแกรมแยกอีก
        """
        print("\n=== Generate Report Menu ===")
        print("   1) สร้างรายงานทั้ง 3 ชุด (ไฟล์ .txt แยกกัน)")
        print("   2) แสดงรายการไฟล์รายงานที่มีอยู่")
        choice = validators.ask_menu_choice("   เลือก [1-2] : ", (1, 2))
        if choice == 1:
            self.generate_report()
        else:
            self.show_report_files()

    # ------------------------------------------------------------------
    # เมนูหลัก + การออกอย่างปลอดภัย
    # ------------------------------------------------------------------
    @staticmethod
    def show_menu() -> None:
        """แสดงเมนูหลักของโปรแกรม"""
        print("\n" + "=" * 62)
        print("  EV Charging Station Booking System  (v"
              f"{models.APP_VERSION})")
        print("=" * 62)
        print("  1) Add (เพิ่ม)")
        print("  2) Update (แก้ไข)")
        print("  3) Delete (ลบแบบ soft delete)")
        print("  4) View (ดู)")
        print("  5) Generate Report (.txt x3)")
        print("  6) Tools (ข้อมูลตัวอย่าง / ซ่อมดัชนี / ตรวจไฟล์)")
        print("  0) Exit (ออกจากโปรแกรม)")

    def run(self) -> int:
        """วนลูปเมนูหลักจนกว่าผู้ใช้เลือก 0 หรือเกิดข้อผิดพลาดระดับระบบ

        ครอบคลุมข้อยกเว้นทั้งหมดที่อาจเกิดได้ เพื่อไม่ให้โปรแกรมหยุดทำงาน
        ตามข้อกำหนด: ValueError, EOFError, KeyboardInterrupt

        Returns:
            รหัสจบการทำงาน (0 = ปกติ)
        """
        while True:
            self.show_menu()
            try:
                choice = validators.ask_menu_choice(
                    "เลือกเมนู [0-6] : ", (0, 1, 2, 3, 4, 5, 6))
                if choice == 1:
                    self.add_point()
                elif choice == 2:
                    self.update_point()
                elif choice == 3:
                    self.delete_point()
                elif choice == 4:
                    self.menu_view()
                elif choice == 5:
                    self.menu_report()
                elif choice == 6:
                    self.menu_tools()
                else:
                    # เลือก 0 = ออกอย่างปลอดภัย (สร้างรายงาน + flush + os.fsync)
                    self._shutdown()
                    return 0
            except validators.UserAbort as exc:
                # EOF หรือ Ctrl+C -> ออกจากโปรแกรมอย่างปลอดภัย
                print(f"\n   [ยกเลิก] {exc}")
                self._shutdown()
                return 0
            except KeyboardInterrupt:
                print("\n   [ยกเลิก] ผู้ใช้กด Ctrl+C")
                self._shutdown()
                return 0
            except (ValueError, struct_error()) as exc:
                # กันพลาดกรณีข้อมูลผิดรูปแบบ (เช่น struct.error) ไม่ให้โปรแกรม crash
                print(f"\n   [ข้อผิดพลาด] {exc}")
            except UnicodeError as exc:
                # กรณีคอนโซลไม่รองรับ UTF-8 (เช่น cmd.exe codepage 874)
                print(f"\n   [ข้อผิดพลาดการเข้ารหัสตัวอักษร] {exc}\n"
                      f"   ลองเปิด Windows Terminal หรือรันคำสั่ง chcp 65001 ก่อน")
            except storage_module.StorageError as exc:
                print(f"\n   [ข้อผิดพลาดในการจัดการไฟล์] {exc}")
            except OSError as exc:
                print(f"\n   [ข้อผิดพลาดระบบไฟล์] {exc}")

    def _shutdown(self) -> None:
        """ปิดโปรแกรมอย่างปลอดภัย: สร้างรายงานอัตโนมัติ + flush/fsync ทุกไฟล์

        ทุกฟังก์ชันของ storage/logger/index ปิดไฟล์ด้วย context manager อยู่แล้ว
        จึงไม่มี handle ค้างอยู่ แต่การเรียก fsync ซ้ำที่นี่เป็นการยืนยันว่า
        ข้อมูลถูกเขียนถึงดิสก์เรียบร้อยก่อนออกจากโปรแกรม
        """
        print("\n   [ออกจากโปรแกรม] กำลังสร้างรายงานสุดท้ายและซีลข้อมูล...")
        try:
            created = self.generate_report(silent=True)
            for file_name in created:
                print(f"   [บันทึกรายงาน] {file_name}")
        except (OSError, ValueError) as exc:
            print(f"   [คำเตือน] สร้างรายงานไม่สำเร็จ: {exc}")

        for path in (self.data_path, self.log_path, self.index_path):
            self._fsync_file(path)

        print(f"   [ข้อมูล] {models.DATA_FILE_NAME}: {self.store.file_size()} ไบต์ "
              f"| {models.LOG_FILE_NAME}: {os.path.getsize(self.log_path)} ไบต์ "
              f"| {models.INDEX_FILE_NAME}: "
              f"{os.path.getsize(self.index_path)} ไบต์")
        print("   [จบการทำงาน] ขอบคุณครับ/ค่ะ ^_^")

    @staticmethod
    def _fsync_file(path: str) -> None:
        """เรียก os.fsync กับไฟล์หนึ่ง เพื่อบังคับให้ข้อมูลถูกเขียนลงดิสก์

        หมายเหตุเรื่อง Windows
        ----------------------
        บน Windows ไฟล์ที่เปิดด้วยโหมด "rb" จะ **ไม่สามารถ fsync ได้**
        (ได้ OSError: Bad file descriptor) เพราะ handle เปิดแบบอ่านอย่างเดียว
        จึงต้องเปิดด้วยโหมด "r+b" ซึ่งได้ handle แบบอ่าน+เขียน แล้วจึงเรียก
        os.fsync ได้ทุกแพลตฟอร์ม (ถ้าเปิดแบบ r+b ไม่ได้ เช่น ไฟล์ read-only
        ก็จะข้ามไปอย่างปลอดภัยแทนที่จะทำให้โปรแกรมหยุดทำงาน)
        """
        try:
            with open(path, "r+b") as fh:
                os.fsync(fh.fileno())
        except OSError:
            # บางกรณี (เช่นไฟล์ถูกเปิดแบบอ่านอย่างเดียว หรือไฟล์ read-only)
            # ให้ลองเปิดแบบ "rb" เป็นทางสำรอง แล้วข้ามไปเงียบ ๆ หากยังไม่ได้
            try:
                with open(path, "rb") as fh:
                    os.fsync(fh.fileno())
            except OSError:
                pass


def configure_console_encoding() -> None:
    """ตั้งค่า encoding ของ stdin/stdout เป็น UTF-8 เทียวที

    เหตุผล
    ------
    บน Windows console มาตรฐาน (เช่น cmd.exe ที่ใช้ codepage 874) Python จะ
    เข้ารหัส/ถอดรหัสข้อความที่รับเข้า-ส่งออกด้วย encoding ของระบบ ทำให้
    **พิมพ์ชื่อสถานีภาษาไทยแล้วเกิด UnicodeEncodeError / UnicodeDecodeError**
    ฟังก์ชันนี้เรียก ``reconfigure()`` (Python 3.7+) เพื่อบังคับให้ทั้ง
    stdin และ stdout ใช้ UTF-8 ตลอดการทำงาน

    หากแพลตฟอร์มไม่รองรับ (เช่น stream ถูกแทนที่ด้วย StringIO ในเทสต์)
    จะข้ามไปอย่างเงียบ ๆ โดยไม่ทำให้โปรแกรมล้ม
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue                       # stream ที่ไม่รองรับ (เช่น StringIO)
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass                           # ปิด stream อยู่ หรือเปลี่ยนไม่ได้


def struct_error():
    """คืนคลาสข้อผิดพลาดของ struct (แยกเป็นฟังก์ชันเพื่อให้ except อ่านง่าย)"""
    import struct
    return struct.error


def print_banner(app: ChargingStationApp) -> None:
    """พิมพ์ข้อมูลสเปกและผลการตรวจไฟล์ตอนเริ่มโปรแกรม"""
    print("=" * 62)
    print("  EV Charging Station Booking System  (v" f"{models.APP_VERSION})")
    print("  Python File I/O - struct + fixed-length binary records")
    print("=" * 62)
    print(models.describe_spec())
    print(f"  โฟลเดอร์ข้อมูล : {os.path.abspath(app.data_dir)}")
    print(f"  เขตเวลาแสดงผล : {TZ_NOTE}")

    for message in app.startup_check():
        print(f"  {message}")

    summary_total = app.store.count_records()
    print(f"  ข้อมูลปัจจุบัน : {summary_total} record | "
          f"log {app.audit.count()} เหตุการณ์ | "
          f"index {app.point_index.count()} รายการ | "
          f"ช่องว่าง {app.store.free_slot_count()}")
    print("=" * 62)

def build_parser() -> argparse.ArgumentParser:
    """สร้างตัว parse อาร์กิวเมนต์ของโปรแกรม (ใช้โมดูล argparse ตามข้อกำหนด)"""
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="ระบบจองสถานีชาร์จ EV (EV Charging Station Booking System) "
                    "- โปรแกรม CLI สำหรับวิชา Python File I/O",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="ตัวอย่างการใช้งาน:\n"
               "  python main.py --seed          สร้างข้อมูลตัวอย่างแล้วเข้าเมนู\n"
               "  python main.py --rebuild-index สร้าง index.dat ใหม่จาก log\n"
               "  python main.py --report-only   สร้างรายงานแล้วออก\n"
               "  python main.py --spec          แสดงสเปกระเบียนทั้ง 3 ไฟล์",
    )
    parser.add_argument("--data-dir", default=".",
                        help="โฟลเดอร์เก็บไฟล์ข้อมูล (ค่าเริ่มต้น: โฟลเดอร์ปัจจุบัน)")
    parser.add_argument("--seed", action="store_true",
                        help="สร้างข้อมูลตัวอย่าง (>50 record) ก่อนเข้าเมนู")
    parser.add_argument("--reset", action="store_true",
                        help="ลบไฟล์ข้อมูลทั้งหมดก่อนเริ่ม (เริ่มใหม่แบบว่าง)")
    parser.add_argument("--rebuild-index", action="store_true",
                        help="สร้าง index.dat ใหม่จาก charge_points.log แล้วออก")
    parser.add_argument("--report-only", action="store_true",
                        help="สร้างรายงาน .txt จากข้อมูลปัจจุบันแล้วออก")
    parser.add_argument("--spec", action="store_true",
                        help="แสดงสเปกระเบียนของไฟล์ไบนารีทั้ง 3 ไฟล์แล้วออก")
    parser.add_argument("--align", choices=("smart", "simple"),
                        default="smart",
                        help="วิธีจัดความกว้างตารางในรายงาน: "
                             "smart = นับสระ/วรรณยุกต์ไทยเป็น 0 ช่อง "
                             "(ถูกต้องใน Terminal/VS Code/Notepad), "
                             "simple = นับทุกตัวอักษรเป็น 1 ช่อง "
                             "(ใช้เมื่อเปิดด้วยโปรแกรมที่ไม่จัดวางสระไทย)")
    parser.add_argument("--version", action="version",
                        version=f"EV Charging Station Booking System "
                                f"{models.APP_VERSION}")
    return parser


def reset_data_dir(data_dir: str) -> None:
    """ลบไฟล์ข้อมูลและไฟล์รายงานทั้งหมดในโฟลเดอร์ (ใช้กับ --reset)"""
    names = [models.DATA_FILE_NAME, models.LOG_FILE_NAME,
             models.INDEX_FILE_NAME, models.REPORT_FILE_NAME,
             models.LOCATION_FILE_NAME]
    names.extend(reports_module.ALL_REPORT_NAMES)
    for name in names:
        path = os.path.join(data_dir, name)
        if os.path.exists(path):
            os.remove(path)
            print(f"   ลบไฟล์: {name}")


def main(argv: Optional[List[str]] = None) -> int:
    """จุดเข้าหลักของโปรแกรม (entry point)

    ตรวจขนาดระเบียนก่อนทุกครั้งที่รัน เพื่อยืนยันว่า struct format
    ตรงกับสเปก (82 / 24 / 8 ไบต์) ตามข้อกำหนด
    """
    # บังคับให้ stdin/stdout ใช้ UTF-8 เพื่อรองรับการกรอกข้อมูลภาษาไทย
    configure_console_encoding()

    args = build_parser().parse_args(argv)

    # เลือกวิธีจัดความกว้างตารางก่อนสร้างรายงาน (ต้องทำก่อนทุกการเรียกรายงาน)
    report_module.set_alignment_mode(args.align == "smart")

    # ตรวจขนาดระเบียนเทียบกับ struct.calcsize ตอนเริ่มโปรแกรม
    models.verify_record_sizes()

    # โหมดแสดงสเปก: ไม่ต้องเข้าเมนู
    if args.spec:
        print(models.describe_spec())
        print(f"Total bytes -> {models.RECORD_SIZE}, "
              f"{models.LOG_RECORD_SIZE}, {models.INDEX_RECORD_SIZE}")
        return 0

    if args.reset:
        print("กำลังลบไฟล์ข้อมูลเดิม...")
        reset_data_dir(args.data_dir)

    if args.seed:
        print("กำลังสร้างข้อมูลตัวอย่าง...")
        seed_data.seed(args.data_dir, force=True)

    # โหมดซ่อมแซมดัชนี: สร้างใหม่จาก log แล้วออก (ไม่เข้าเมนู)
    if args.rebuild_index:
        rebuilt = seed_data.rebuild_index(
            os.path.join(args.data_dir, models.LOG_FILE_NAME),
            os.path.join(args.data_dir, models.INDEX_FILE_NAME),
        )
        print(f"สร้าง index.dat ใหม่จาก log สำเร็จ: {rebuilt} รายการ")
        return 0

    app = ChargingStationApp(args.data_dir)

    # โหมดสร้างรายงานอย่างเดียว
    if args.report_only:
        print_banner(app)
        app.generate_report()
        return 0

    print_banner(app)
    try:
        return app.run()
    except validators.UserAbort as exc:
        print(f"\n   [ยกเลิก] {exc}")
        app._shutdown()
        return 0


if __name__ == "__main__":
    sys.exit(main())

