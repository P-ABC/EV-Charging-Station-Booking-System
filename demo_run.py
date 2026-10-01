"""demo_run.py — สคริปต์ตัวอย่างการใช้งานเมนูแบบอัตโนมัติ (ไม่ต้องพิมพ์เอง)

ใช้ส่งคำตอบเข้า stdin ของ main.py ตามลำดับ เพื่อสาธิตการทำงานครบทุกเมนู:
Add -> Update -> Delete (ถูกปฏิเสธเพราะถูกจอง) -> View -> Report -> Exit

วิธีใช้:  python demo_run.py
"""

import os
import shutil
import subprocess
import sys

# ลำดับคำตอบ (หนึ่งบรรทัดต่อคำถาม)
# หมายเหตุ: บรรทัดว่าง "" = กด Enter เพื่อ "คงค่าเดิม" ในเมนู Update
ANSWERS = [
    "1",                   # Add
    "3001",
    "EVS-0300",
    "สยามพารากอน ชั้น B1",   # location ยาว 49 ไบต์ -> ระบบจะเตือนและตัด
    "1",                   # plug type = Type2
    "22",                  # power
    "7.5",                 # price
    "1", "0",              # status, booked
    "2",                   # Update
    "3001",
    "",                    # station code -> คงเดิม
    "",                    # location    -> คงเดิม
    "",                    # plug type   -> คงเดิม
    "",                    # power       -> คงเดิม
    "7.25",                # price       -> เปลี่ยนเป็น 7.25
    "",                    # status      -> คงเดิม
    "1",                   # is_booked   -> จองหัวชาร์จ
    "3",                   # Delete
    "3001",                # -> จะถูกปฏิเสธเพราะกำลังถูกจองอยู่
    "4", "2",              # View -> ดูทั้งหมด
    "4", "4",              # View -> สถิติโดยสรุป
    "4", "1", "3001",      # View -> ดูรายการเดียว + ประวัติผ่าน index.dat
    "5",                   # Generate Report
    "0",                   # Exit
]

DATA_DIR = "_demo"


def main() -> int:
    """ส่งคำตอบเข้า main.py แล้วแสดงผลลัพธ์"""
    # เริ่มจากโฟลเดอร์ว่างเสมอ เพื่อให้ผลลัพธ์ทำซ้ำได้เหมือนเดิม
    shutil.rmtree(DATA_DIR, ignore_errors=True)

    stdin_text = "\n".join(ANSWERS) + "\n"
    result = subprocess.run(
        [sys.executable, "main.py", "--data-dir", DATA_DIR],
        input=stdin_text.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    # ถอดรหัสผลลัพธ์เป็น UTF-8 แล้วเขียนลงไฟล์ (console อาจแสดงไทยไม่ผิด)
    output = result.stdout.decode("utf-8", errors="replace")
    with open("demo_output.txt", "w", encoding="utf-8") as fh:
        fh.write(output)
    print(output)
    print(f"[demo] exit code = {result.returncode}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
