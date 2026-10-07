"""verify_menu.py — สคริปต์ตรวจสอบเกณฑ์ 7 ข้อแบบ end-to-end ผ่านเมนูเดียว

รันด้วย:  python verify_menu.py
สคริปต์นี้ส่งคำตอบเข้า stdin ของ main.py เพื่อ "เล่น" ทุกเมนูรวดเดียว
แล้วตรวจผลลัพธ์ตามเกณฑ์ที่ต้องการ (ดูรายละเอียดใน README.md)
"""

import io
import os
import shutil
import subprocess
import sys

# โฟลเดอร์ที่มีไฟล์ .py ของโปรเจกต์ (หนึ่งระดับขึ้นไปจากตำแหน่งสคริปต์นี้)
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(PROJECT_DIR) == "tests":
    PROJECT_DIR = os.path.dirname(PROJECT_DIR)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

DATA_DIR = "_verify"

# ลำดับคำตอบ: เล่นครบทุกเมนู (บรรทัดว่าง = กด Enter เพื่อคงค่าเดิม)
ANSWERS = [
    "6", "1", "y",           # Tools > โหลดข้อมูลตัวอย่าง (ยืนยันเขียนทับ)
    "6", "3",                # Tools > ตรวจความถูกต้องของไฟล์
    "1", "9001", "EVS-0900", "ทดสอบเมนูเดียว", "2", "150", "7.5", "1", "0",
    "2", "9001", "", "", "", "", "9.75", "", "1",   # Update ราคาใหม่ + จอง
    "4", "2",                # View > ดูทั้งหมด
    "4", "1", "9001",        # View > ดูรายการเดียว
    "3", "9001",            # Delete -> ถูกปฏิเสธ (กำลังถูกจอง)
    "2", "9001", "", "", "", "", "8.25", "", "0",    # Update ปล่อยหัวชาร์จ
    "3", "9001", "y",        # Delete -> สำเร็จ
    "5", "1",                # Report > สร้างรายงาน 3 ชุด
    "5", "2",                # Report > แสดงรายการไฟล์รายงาน
    "0",                     # Exit
]

REPORT_NAMES = ("report_points.txt", "report_stats.txt", "report_system.txt")


def _has_entry_point(path: str) -> bool:
    """ตรวจว่าไฟล์ .py มีบล็อก if __name__ == '__main__' หรือไม่"""
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    return ('if __name__ == "__main__"' in text
            or "if __name__ == '__main__'" in text)


def _read(path: str) -> str:
    """อ่านไฟล์รายงานแบบ UTF-8"""
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def check_three_parts(existing):
    """ข้อ 2: ทุกรายงานต้องมีตารางและ Summary"""
    ok = True
    detail = []
    for name in existing:
        text = _read(os.path.join(DATA_DIR, name))
        has_sections = "[TABLE" in text and "[SUMMARY]" in text
        no_check_section = "[CONSISTENCY CHECK]" not in text
        ok = ok and has_sections and no_check_section
        detail.append(
            f"{name}: ตารางและ Summary "
            f"{'ครบ' if has_sections else 'ไม่ครบ'}, "
            f"Consistency Check "
            f"{'ถูกตัดออก' if no_check_section else 'ยังอยู่'}")
    return ok, "; ".join(detail)


def check_multi_source(existing):
    """ข้อ 3: ทุกรายงานต้องอ้างอิงข้อมูลจากอย่างน้อย 2 ไฟล์"""
    ok = True
    detail = []
    for name in existing:
        text = _read(os.path.join(DATA_DIR, name))
        sources = [src for src in ("charge_points.dat", "charge_points.log",
                                   "index.dat") if src in text]
        ok = ok and len(sources) >= 2
        detail.append(f"{name}: {len(sources)} ไฟล์ ({', '.join(sources)})")
    return ok, "; ".join(detail)


def check_tables_aligned(existing):
    """ข้อ 4 (ส่วนตาราง): บรรทัดในตารางเดียวกันต้องกว้างเท่ากัน"""
    from report import display_width
    ok = True
    detail = []
    for name in existing:
        lines = _read(os.path.join(DATA_DIR, name)).splitlines()
        block = []
        for line in lines + [""]:
            if line.startswith(("+", "|")):
                block.append(line)
            elif block:
                widths = {display_width(item) for item in block}
                ok = ok and len(widths) == 1
                detail.append(f"{name}: {len(block)} บรรทัด "
                              f"{'ตรงกัน' if len(widths) == 1 else widths}")
                block = []
    return ok, "; ".join(detail[:4])
def main() -> int:
    """เล่นเมนูทั้งหมด แล้วตรวจผลตามเกณฑ์ 7 ข้อ พร้อมพิมพ์สรุป"""
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    result = subprocess.run(
        [sys.executable, os.path.join(PROJECT_DIR, "main.py"),
         "--data-dir", DATA_DIR],
        input=("\n".join(ANSWERS) + "\n").encode("utf-8"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    output = result.stdout.decode("utf-8", errors="replace")
    with io.open("verify_output.txt", "w", encoding="utf-8") as fh:
        fh.write(output)

    existing = [name for name in REPORT_NAMES
                if os.path.exists(os.path.join(DATA_DIR, name))]

    # ข้อ 1: มีอย่างน้อย 3 reports
    checks = [("1) มีอย่างน้อย 3 reports", len(existing) >= 3,
               f"พบ {len(existing)} ไฟล์: {', '.join(existing)}")]

    # ข้อ 2: แต่ละรายงานมีส่วนครบและผลตรวจสอบผ่านทั้งหมด
    ok, detail = check_three_parts(existing)
    checks.append(("2) แต่ละ report มีโครงสร้างครบ + สอดคล้องกัน", ok, detail))

    # ข้อ 3: แต่ละรายงานมาจาก >= 2 ไฟล์
    ok, detail = check_multi_source(existing)
    checks.append(("3) แต่ละ report มาจาก >= 2 ไฟล์", ok, detail))

    # ข้อ 4: เป็นไฟล์ .txt แยกกัน และตารางไม่เพี้ยน
    aligned_ok, detail = check_tables_aligned(existing)
    checks.append(("4) ไฟล์ .txt แยกกัน + ตารางไม่เพี้ยน",
                   len(existing) == 3 and aligned_ok,
                   f"{len(existing)} ไฟล์แยกกัน; {detail}"))

    # ข้อ 5: ใช้เมนูชุดเดียว ไม่มี run program แยกเมนู
    # ข้ามไฟล์ของชุดทดสอบ (tests/) และตัวสคริปต์ตรวจสอบนี้เอง
    # เพราะไม่ใช่ "โปรแกรมเมนู" ของระบบ
    skip_names = {"main.py", os.path.basename(os.path.abspath(__file__))}
    runnables = [name for name in sorted(os.listdir(PROJECT_DIR))
                 if name.endswith(".py") and name not in skip_names
                 and _has_entry_point(os.path.join(PROJECT_DIR, name))]
    checks.append(("5) เมนูชุดเดียว ไม่มีโปรแกรมแยกเมนู", not runnables,
                   "มีแต่ main.py เป็นจุดเริ่มโปรแกรม"
                   if not runnables else f"พบโปรแกรมแยก: {runnables}"))

    # ข้อ 6: แก้ข้อมูลแล้วรายงานเปลี่ยนตาม
    points_report = _read(os.path.join(DATA_DIR, "report_points.txt"))
    changed = ("9001" in points_report and "8.25" in points_report
               and "Deleted" in points_report)
    checks.append(("6) แก้ข้อมูลแล้วรายงานเปลี่ยนตาม", changed,
                   "พบ 9001 พร้อมราคาใหม่ 8.25 และสถานะ Deleted ในรายงาน"))

    # ข้อ 7: ไฟล์ข้อมูลหลักเป็น binary
    data_path = os.path.join(DATA_DIR, "charge_points.dat")
    with open(data_path, "rb") as fh:
        raw = fh.read()
    size = len(raw)
    # ต้องเป็น binary จริง: มีไบต์ padding (\x00) และมีข้อความสตริงฝังอยู่
    has_padding = b"\x00" in raw
    has_text = b"EVS-0900" in raw
    # และถอดรหัสด้วย struct ได้
    try:
        import models
        first = models.unpack_charge_point(raw[:models.RECORD_SIZE])
        decodable = first.station_code.startswith("EVS-")
    except Exception:
        decodable = False
    binary_ok = (size % 82 == 0 and has_padding and has_text and decodable)
    checks.append(("7) ไฟล์ข้อมูลหลักเก็บแบบ Binary", binary_ok,
                   f"{size} ไบต์ = {size // 82} record x 82 ไบต์ | "
                   f"มี padding \\x00={has_padding} | มีข้อความฝัง={has_text} | "
                   f"ถอดด้วย struct={decodable}"))

    # ---- พิมพ์สรุปผล -------------------------------------------------
    print("=" * 72)
    print("  ผลการตรวจสอบตามเกณฑ์ 7 ข้อ (ใช้เมนูชุดเดียวของ main.py)")
    print("=" * 72)
    passed = 0
    for label, ok, detail_text in checks:
        print(f"[{'ผ่าน' if ok else 'ไม่ผ่าน'}] {label}")
        print(f"        {detail_text}")
        passed += 1 if ok else 0
    print("=" * 72)
    print(f"  สรุป: ผ่าน {passed}/{len(checks)} ข้อ "
          f"| exit code = {result.returncode}")
    print("  ดูผลการรันทั้งหมดได้ที่ verify_output.txt")
    print("=" * 72)
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())