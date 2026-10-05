"""reports.py — สร้างรายงาน .txt 3 ชุดจากข้อมูลไบนารี

รายงานทั้ง 3 ไฟล์
----------------
1. ``report_points.txt`` — สถานะหัวชาร์จรายหัว
2. ``report_stats.txt``  — สถิติราคา กำลังไฟ และกิจกรรม
3. ``report_system.txt`` — สถานะระบบไฟล์และดัชนี

โครงสร้างของแต่ละไฟล์
--------------------
    [TABLE...]            ตารางผลลัพธ์จริง
    [SUMMARY]             ส่วนสรุปตัวเลข
    [CONSISTENCY CHECK]   ผลตรวจสอบความสอดคล้องของข้อมูล

ทุกไฟล์อ้างอิงข้อมูลจาก 3 ไฟล์ไบนารีเสมอ (เกณฑ์ข้อ 3):
``charge_points.dat`` + ``charge_points.log`` + ``index.dat``
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence

import models
from report import (
    RECENT_ACTIVITY_LIMIT,
    compute_summary,
    format_timestamp,
    measure,
    render_table,
)

# ---------------------------------------------------------------------------
# ค่าคงที่ชื่อไฟล์และแหล่งที่มาของข้อมูล
# ---------------------------------------------------------------------------
REPORT_POINTS_NAME = "report_points.txt"
REPORT_STATS_NAME = "report_stats.txt"
REPORT_SYSTEM_NAME = "report_system.txt"
ALL_REPORT_NAMES = (REPORT_POINTS_NAME, REPORT_STATS_NAME, REPORT_SYSTEM_NAME)

SOURCE_POINT_FILE = models.DATA_FILE_NAME     # charge_points.dat
SOURCE_LOG_FILE = models.LOG_FILE_NAME        # charge_points.log
SOURCE_INDEX_FILE = models.INDEX_FILE_NAME    # index.dat

# ความกว้างสูงสุดของตารางข้อมูลหัวชาร์จ (รายงานที่ 1)
# ตารางนี้รวมข้อมูลครบทั้ง 10 คอลัมน์ไว้ในตารางเดียว จึงต้องกว้างกว่าตารางอื่น
# เพื่อให้ชื่อสถานที่ตั้งแบบเต็มและข้อมูลทุกฟิลด์แสดงได้ครบโดยไม่ถูกตัด
MAIN_TABLE_MAX_WIDTH = 150


def _full_location(point: models.ChargePoint,
                   locations: Optional[Dict[int, str]]) -> str:
    """คืน "ชื่อสถานที่ตั้งแบบเต็ม" ของ record สำหรับแสดงในรายงาน

    ฟิลด์ location ใน record ไบนารีจำกัดไว้ 30 ไบต์ จึงเก็บได้ภาษาไทยเพียง
    ~10 ตัวอักษร (เช่น "เซ็นทรัลเวิลด์ ลาน P2" ถูกตัดเหลือ "เซ็นทรัลเว")
    ชื่อเต็มจึงถูกเก็บแยกไว้ในไฟล์ locations.txt แล้วนำกลับมาแสดงที่นี่

    Args:
        point: record หัวชาร์จ
        locations: dict {point_id: ชื่อเต็ม} (ถ้าไม่มีจะใช้ค่าใน record แทน)

    Returns:
        ชื่อสถานที่ตั้งแบบเต็มที่อ่านได้
    """
    if locations:
        full = locations.get(point.point_id)
        if full:
            return full
    return point.location


def _header(data_dir: str) -> List[str]:
    """สร้างส่วนหัวของรายงาน (ข้อมูลระบบ + เวลา)

    หมายเหตุ: เดิมมีบรรทัดชื่อเรื่อง ("รายงานที่ 1: ...") แต่ถูกตัดออก
    ตามที่ผู้ใช้ต้องการ ให้ไฟล์เริ่มต้นด้วยข้อมูลระบบโดยตรง
    ชื่อเรื่องของแต่ละชุดยังระบุได้จาก **ชื่อไฟล์** ที่แยกกันชัดเจน
    (report_points.txt / report_stats.txt / report_system.txt)

    Args:
        data_dir: โฟลเดอร์ที่เก็บไฟล์ข้อมูล

    Returns:
        บรรทัดส่วนหัวของรายงาน
    """
    return [
        f"Generated At : {format_timestamp(models.now_timestamp())}",
        f"App Version  : {models.APP_VERSION}",
        f"Endianness   : {models.BYTE_ORDER_LABEL}",
        f"Encoding     : {models.ENCODING_LABEL} (ไฟล์รายงานใช้ UTF-8)",
        f"Data Dir     : {data_dir}",
    ]


def _rule(width: int) -> str:
    """สร้างเส้นคั่นหัวข้อที่กว้างตามที่กำหนด

    Args:
        width: ความกว้างเป็นจำนวนช่อง (วัดด้วย display_width)
    """
    return "-" * width


def _footer_section(summary_rows: Sequence[Sequence[str]],
                    check_rows: Sequence[Sequence[str]]) -> List[str]:
    """สร้างส่วนสรุปและผลตรวจสอบ (ส่วนท้ายของรายงาน)

    Args:
        summary_rows: แถวสรุปตัวเลข
        check_rows: แถวผลการตรวจสอบความสอดคล้อง (Check / Expected / Result)
    """
    summary_table = render_table(["รายการ", "ค่า"], list(summary_rows))
    check_table = render_table(["รายการตรวจสอบ", "ค่าที่คาดหวัง", "ผลลัพธ์"],
                               list(check_rows))
    lines: List[str] = []
    lines.append("[SUMMARY] ส่วนสรุป")
    lines.append("-" * 62)
    lines.extend(summary_table)
    lines.append("")
    lines.append("[CONSISTENCY CHECK] ผลการตรวจสอบความสอดคล้องของข้อมูล")
    lines.append("-" * 62)
    lines.extend(check_table)
    return lines


def _align_section_rules(lines: Sequence[str]) -> List[str]:
    """ปรับเส้นคั่นหัวข้อให้ยาวเท่ากับตารางที่อยู่ถัดไป

    ถ้าใช้เส้นคั่นความยาวคงที่ จะไม่ตรงกับตารางจริงที่กว้างไม่เท่ากัน
    ทำให้ไฟล์ดูไม่เป็นมาตรฐาน ฟังก์ชันนี้จึงวัดความกว้างจริงของบล็อกตาราง
    แล้วปรับเส้นคั่นให้พอดีเสมอ

    Args:
        lines: บรรทัดทั้งหมดของรายงาน

    Returns:
        บรรทัดที่ปรับความยาวเส้นคั่นเรียบร้อยแล้ว
    """
    result = list(lines)
    index = 0
    while index < len(result) - 1:
        line = result[index]
        # หัวข้อส่วนขึ้นต้นด้วย "[" เช่น [TABLE 1] ... ตามด้วยเส้นคั่น
        if (line.lstrip().startswith("[") and not line.startswith(("+", "|"))
                and result[index + 1] and set(result[index + 1]) == {"-"}):
            rule_index = index + 1
            # เดินหน้าข้ามบรรทัดอธิบายเพื่อไปหาบล็อกตารางแรกของส่วนนี้
            cursor = rule_index + 1
            table_start = None
            while cursor < len(result):
                current = result[cursor]
                if current.startswith(("+", "|")):
                    table_start = cursor
                    break
                if current.lstrip().startswith("["):
                    break          # เจอหัวข้อส่วนถัดไป
                cursor += 1

            table_width = 0
            if table_start is not None:
                cursor = table_start
                while cursor < len(result) and result[cursor].startswith(("+", "|")):
                    table_width = max(table_width, measure(result[cursor]))
                    cursor += 1

            # ยึด "ความกว้างตาราง" เป็นหลักเพื่อให้เส้นคั่นตรงกับตารางเสมอ
            target_width = table_width if table_width else measure(line)
            if table_width and len(result[rule_index]) != target_width:
                result[rule_index] = _rule(target_width)
            index = cursor
            continue
        index += 1
    return result


def _write_report(path: str, lines: Sequence[str]) -> str:
    """เขียนรายงานลงไฟล์ .txt แล้ว flush + os.fsync (เกณฑ์ข้อ 4)

    ก่อนเขียนจะเรียก :func:`_align_section_rules` เพื่อให้เส้นคั่นหัวข้อ
    กว้างเท่ากับตารางเสมอ

    Returns:
        ข้อความรายงานที่เขียนลงไฟล์
    """
    content = "\n".join(_align_section_rules(lines)) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    return content


def build_report_points(data_dir: str,
                        points: Sequence[models.ChargePoint],
                        log_entries: Sequence[models.LogEntry],
                        index_map: Dict[int, int],
                        store_valid: bool = True,
                        log_valid: bool = True,
                        index_valid: bool = True,
                        locations: Optional[Dict[int, str]] = None) -> List[str]:
    """สร้างรายงานชุดที่ 1: สถานะหัวชาร์จรายหัว (report_points.txt)

    แหล่งข้อมูล: charge_points.dat + index.dat + charge_points.log (3 ไฟล์)
    คอลัมน์ LogSeq มาจาก index.dat ทำให้รายงานนี้ไม่ได้มาจากไฟล์เดียว

    พารามิเตอร์ store_valid/log_valid/index_valid รับไว้เพื่อให้
    ฟังก์ชันทั้ง 3 ชุดมีลายเซ็นเหมือนกัน (ใช้โดย generate_all_reports)
    """
    summary = compute_summary(points)

    lines = _header(data_dir)
    lines.append("")

    # ---- ตารางข้อมูลจริง --------------------------------------------
    lines.append("[TABLE] ตารางข้อมูลหัวชาร์จทั้งหมด (รวมรายการที่ถูกลบแล้ว)")
    lines.append("-" * 62)
    rows = []
    for point in points:
        rows.append([
            str(point.point_id),
            point.station_code,
            _full_location(point, locations),
            point.plug_type,
            f"{point.power_kw:.1f}",
            f"{point.price_per_kwh:.2f}",
            point.status_text,
            point.booked_text,
            str(index_map.get(point.point_id, "-")),
            format_timestamp(point.updated_at).replace(" (+07:00)", ""),
        ])
    # รวมข้อมูลทั้งหมดไว้ตารางเดียว
    lines.extend(render_table(
        ["PtID", "Station", "Location", "Plug", "Power", "Price", "Status",
         "Booked", "LogSeq", "Updated"], rows,
        max_width=MAIN_TABLE_MAX_WIDTH))
    lines.append("")

    # ---- ส่วนสรุป ---------------------------------------------------
    # ต้องแยก "Inactive" ออกมาชัดเจน เพราะสมการ
    # "Active + Deleted = Total" ไม่เป็นจริงเมื่อมีรายการที่ปิดซ่อมบำรุง
    inactive = [p for p in points if not p.is_deleted and p.status != 1]
    # จำนวนที่ถูกจอง "และยัง Active" เท่านั้น จึงจะบวกกับ Available ได้พอดี
    booked_active = [p for p in points
                     if not p.is_deleted and p.status == 1 and p.is_booked == 1]

    summary_rows = [
        ["Total Points (records)", str(summary["total"])],
        ["Active Points", str(summary["active"])],
        ["Inactive Points (ปิดซ่อมบำรุง)", str(len(inactive))],
        ["Deleted Points (soft delete)", str(summary["deleted"])],
        ["Currently Booked (ทุกสถานะ)", str(summary["booked"])],
        ["Booked ที่ยัง Active", str(len(booked_active))],
        ["Available Now (Active & not booked)", str(summary["available"])],
        ["Free Slots (reuseable)", str(summary["free_slots"])],
        ["ไฟล์ต้นทางที่ใช้ประกอบรายงานนี้",
         f"{SOURCE_POINT_FILE}, {SOURCE_LOG_FILE}, {SOURCE_INDEX_FILE}"],
    ]

    # ตรวจสอบความสอดคล้องระหว่างตารางกับดัชนีและ log
    active_ids = {p.point_id for p in points if not p.is_deleted}
    missing_index = sorted(active_ids - set(index_map))
    # หมายเหตุเรื่อง free-list: เมื่อนำช่องว่างที่เคย soft delete กลับมาใช้
    # index อาจยังมีระเบียนของรหัสเดิมที่ถูกใช้ทับแล้ว จึงนับแยกเป็น
    # "ข้อมูลประกอบ" ไม่ถือเป็นความผิดปกติ
    stale_index = sorted((set(index_map) - active_ids) - set(missing_index))
    expected_count = len(active_ids)
    check_rows = [
        ["จำนวน record ในตาราง = Total Points",
         f"{len(points)} = {summary['total']}",
         "ผ่าน" if len(points) == summary["total"] else "ไม่ผ่าน"],
        ["Active + Inactive + Deleted = Total",
         f"{summary['active']} + {len(inactive)} + {summary['deleted']}"
         f" = {summary['total']}",
         "ผ่าน" if summary["active"] + len(inactive)
         + summary["deleted"] == summary["total"] else "ไม่ผ่าน"],
        ["Booked(Active) + Available = Active",
         f"{len(booked_active)} + {summary['available']}"
         f" = {summary['active']}",
         "ผ่าน" if len(booked_active) + summary["available"]
         == summary["active"] else "ไม่ผ่าน"],
        ["Free Slots = จำนวน record ที่ถูก soft delete",
         f"{summary['free_slots']} = {summary['deleted']}",
         "ผ่าน" if summary["free_slots"] == summary["deleted"]
         else "ไม่ผ่าน"],
        ["point_id ที่ยังไม่ถูกลบ มี record ใน index.dat ครบทุกตัว",
         f"{expected_count - len(missing_index)} รายการ",
         "ผ่าน" if not missing_index
         else f"ไม่ผ่าน (ขาด {len(missing_index)})"],
        ["index.dat มี record อย่างน้อยเท่าจำนวนรายการที่ยังไม่ถูกลบ",
         f"{len(index_map)} >= {expected_count}",
         "ผ่าน" if len(index_map) >= expected_count else "ไม่ผ่าน"],
        ["(ข้อมูลประกอบ) record ใน index.dat ของรหัสที่ถูกลบแล้ว/ช่องถูกใช้ทับ",
         f"{len(stale_index)} รายการ", "ข้อมูล"],
    ]
    lines.extend(_footer_section(summary_rows, check_rows))
    return lines


def build_report_stats(data_dir: str,
                       points: Sequence[models.ChargePoint],
                       log_entries: Sequence[models.LogEntry],
                       index_map: Dict[int, int],
                       store_valid: bool = True,
                       log_valid: bool = True,
                       index_valid: bool = True,
                       locations: Optional[Dict[int, str]] = None) -> List[str]:
    """สร้างรายงานชุดที่ 2: สถิติราคา กำลังไฟ และกิจกรรม (report_stats.txt)

    แหล่งข้อมูล: charge_points.dat (สถิติราคา/กำลังไฟ)
    + charge_points.log (กิจกรรมและ op_code)
    + index.dat (ตรวจสอบว่าเหตุการณ์ล่าสุดมีในดัชนี)
    """
    active_points = [p for p in points
                     if not p.is_deleted and p.status == 1]
    powers = [p.power_kw for p in active_points]
    prices = [p.price_per_kwh for p in active_points]
    count = len(active_points)
    stats = {"count": count}
    if powers:
        stats["min"] = min(powers)
        stats["max"] = max(powers)
        stats["avg"] = sum(powers) / len(powers)
        stats["price_avg"] = sum(prices) / len(prices)
    else:
        stats["min"] = stats["max"] = stats["avg"] = 0.0
        stats["price_avg"] = 0.0

    plug_counts: Dict[str, int] = {}
    for point in active_points:
        plug_counts[point.plug_type] = plug_counts.get(point.plug_type, 0) + 1

    op_counts = {models.OP_ADD: 0, models.OP_UPDATE: 0,
                 models.OP_DELETE: 0, models.OP_VIEW: 0}
    for entry in log_entries:
        if entry.op_code in op_counts:
            op_counts[entry.op_code] += 1
    recent = list(log_entries[-RECENT_ACTIVITY_LIMIT:])
    points_by_id = {p.point_id: p for p in points}

    lines = _header(data_dir)
    lines.append("")

    # ---- TABLE 1: สถิติราคาและกำลังไฟ --------------------------------
    lines.append("[TABLE 1] สถิติราคาและกำลังไฟ (นับเฉพาะ Active ที่ไม่ถูกลบ)")
    lines.append("-" * 62)
    stat_rows = [
        ["จำนวนรายการ", str(count), str(count)],
        ["ค่าต่ำสุด (Min)", f"{min(prices):.2f}" if prices else "-",
         f"{stats['min']:.1f}"],
        ["ค่าสูงสุด (Max)", f"{max(prices):.2f}" if prices else "-",
         f"{stats['max']:.1f}"],
        ["ค่าเฉลี่ย (Avg)", f"{stats['price_avg']:.2f}",
         f"{stats['avg']:.1f}"],
    ]
    lines.extend(render_table(["สถิติ", "ราคา (THB/kWh)", "กำลังไฟ (kW)"],
                              stat_rows))
    lines.append("")

    # ---- TABLE 2: จำนวนหัวชาร์จแยกตามประเภทหัว -------------------------
    lines.append("[TABLE 2] จำนวนหัวชาร์จแยกตามประเภทหัว (นับเฉพาะ Active)")
    lines.append("-" * 62)
    plug_rows = []
    for plug in ("CCS2", "Type2", "CHAdeMO", "GB-T"):
        plug_count = plug_counts.get(plug, 0)
        percent = (plug_count / count * 100) if count else 0.0
        plug_rows.append([plug, str(plug_count), f"{percent:.1f}"])
    lines.extend(render_table(["ประเภทหัว", "จำนวน", "สัดส่วน (%)"], plug_rows))
    lines.append("")

    # ---- TABLE 3: กิจกรรมล่าสุดจาก log --------------------------------
    lines.append(f"[TABLE 3] กิจกรรมล่าสุดจาก {SOURCE_LOG_FILE} "
                 f"({len(recent)} รายการล่าสุด)")
    lines.append("-" * 62)
    recent_rows = []
    for entry in sorted(recent, key=lambda item: item.ts, reverse=True):
        point = points_by_id.get(entry.point_id)
        recent_rows.append([
            format_timestamp(entry.ts),
            entry.op_name,
            str(entry.point_id),
            point.status_text if point else "-",
            point.booked_text if point else "-",
            f"{point.price_per_kwh:.2f}" if point else "-",
            "พบใน index" if entry.point_id in index_map else "ไม่พบใน index",
        ])
    lines.extend(render_table(
        ["Timestamp", "Operation", "PtID", "Status", "Booked", "Price",
         "ตรวจสอบ index"], recent_rows))
    lines.append("")

    # ---- ส่วนสรุป -----------------------------------------------------
    total_ops = sum(op_counts.values())
    recent_ids_found = sum(1 for entry in recent
                           if entry.point_id in index_map)
    summary_rows = [
        ["รายการที่นำมาคำนวณสถิติ (Active)", str(count)],
        ["ราคาเฉลี่ย (THB/kWh)", f"{stats['price_avg']:.2f}"],
        ["กำลังไฟเฉลี่ย (kW)", f"{stats['avg']:.1f}"],
        ["รวมหัวชาร์จตามประเภทหัว", str(sum(plug_counts.values()))],
        ["รวมเหตุการณ์ใน log", str(len(log_entries))],
        ["ADD / UPDATE / DELETE / VIEW",
         f"{op_counts[models.OP_ADD]} / {op_counts[models.OP_UPDATE]} / "
         f"{op_counts[models.OP_DELETE]} / {op_counts[models.OP_VIEW]}"],
        [f"record ใน {SOURCE_INDEX_FILE}", f"{len(index_map)} รายการ"],
        ["ไฟล์ต้นทางที่ใช้ประกอบรายงานนี้",
         f"{SOURCE_POINT_FILE}, {SOURCE_LOG_FILE}, {SOURCE_INDEX_FILE}"],
    ]
    check_rows = [
        ["ผลรวมจำนวนตามประเภทหัว = จำนวน Active",
         f"{sum(plug_counts.values())} = {count}",
         "ผ่าน" if sum(plug_counts.values()) == count else "ไม่ผ่าน"],
        ["รวม op_code = จำนวนเหตุการณ์ใน log",
         f"{total_ops} = {len(log_entries)}",
         "ผ่าน" if total_ops == len(log_entries) else "ไม่ผ่าน"],
        ["ค่าเฉลี่ยที่แสดง = คำนวณจากรายการจริง",
         f"{stats['price_avg']:.2f}",
         "ผ่าน" if prices else "ไม่ผ่าน (ไม่มีข้อมูล)"],
        ["เหตุการณ์ล่าสุดทุกรายการมีใน index.dat",
         f"{recent_ids_found} = {len(recent)}",
         "ผ่าน" if recent_ids_found == len(recent) else "ไม่ผ่าน"],
        ["ราคาต่ำสุด <= เฉลี่ย <= ราคาสูงสุด",
         f"{min(prices):.2f} <= {stats['price_avg']:.2f} <= {max(prices):.2f}"
         if prices else "-",
         "ผ่าน" if prices and min(prices) <= stats["price_avg"] <= max(prices)
         else "ไม่ผ่าน (ไม่มีข้อมูล)"],
    ]
    lines.extend(_footer_section(summary_rows, check_rows))
    return lines


def build_report_system(data_dir: str,
                        points: Sequence[models.ChargePoint],
                        log_entries: Sequence[models.LogEntry],
                        index_map: Dict[int, int],
                        store_valid: bool = True,
                        log_valid: bool = True,
                        index_valid: bool = True,
                        locations: Optional[Dict[int, str]] = None) -> List[str]:
    """สร้างรายงานชุดที่ 3: สถานะระบบไฟล์และดัชนี (report_system.txt)

    แหล่งข้อมูล: charge_points.dat + index.dat + charge_points.log (3 ไฟล์)
    รายงานนี้ตรวจสอบ "สุขภาพ" ของระบบไฟล์ ทำให้เห็นว่าไฟล์ทั้งสามไฟล์
    สอดคล้องกันหรือไม่
    """
    lines = _header(data_dir)
    lines.append("")

    # ---- TABLE 1: สถานะไฟล์ไบนารีทั้ง 3 ไฟล์ ------------------------
    lines.append("[TABLE 1] สถานะไฟล์ไบนารีทั้ง 3 ไฟล์")
    lines.append("-" * 62)
    file_rows = []
    for label, file_name, struct_fmt, record_size, count, valid in (
        ("ข้อมูลหลัก", SOURCE_POINT_FILE, models.CHARGE_POINT_FORMAT,
         models.RECORD_SIZE, len(points), store_valid),
        ("audit log", SOURCE_LOG_FILE, models.LOG_FORMAT,
         models.LOG_RECORD_SIZE, len(log_entries), log_valid),
        ("ดัชนี", SOURCE_INDEX_FILE, models.INDEX_FORMAT,
         models.INDEX_RECORD_SIZE, len(index_map), index_valid),
    ):
        file_rows.append([
            label, file_name, struct_fmt, f"{record_size} ไบต์",
            str(count),
            "ผ่าน" if valid else "ผิดปกติ",
        ])
    # ตัดคอลัมน์ "ขนาดไฟล์" ออก เพราะเป็นผลคูณของ 2 คอลัมน์ก่อนหน้า
    # ทำให้ตารางกว้างลงจนไม่ต้องถูกตัดข้อมูลสำคัญ
    lines.extend(render_table(
        ["ประเภท", "ไฟล์", "Struct format", "ขนาด/record", "จำนวน",
         "สถานะ"], file_rows))
    lines.append("")

    # ตรวจความสอดคล้องระหว่างไฟล์: index กับ log
    latest_seq: Dict[int, int] = {}
    for seq, entry in enumerate(log_entries):
        latest_seq[entry.point_id] = seq
    mismatch = [
        (pid, index_map[pid], latest_seq[pid])
        for pid in index_map
        if pid in latest_seq and index_map[pid] != latest_seq[pid]
    ]
    index_only = sorted(set(index_map) - set(latest_seq))
    log_only = sorted(set(latest_seq) - set(index_map))

    # แสดงตารางเฉพาะเมื่อ "มีปัญหาจริง" เท่านั้น
    if mismatch or index_only or log_only:
        lines.append(f"[TABLE 2] ผลการเทียบข้อมูลระหว่าง {SOURCE_INDEX_FILE} "
                     f"กับ {SOURCE_LOG_FILE}")
        lines.append("-" * 62)
        diff_rows = []
        for pid, in_index, in_log in mismatch[:10]:
            diff_rows.append([str(pid), "ไม่ตรงกัน", str(in_index), str(in_log),
                              "ควรสร้างดัชนีใหม่จาก log"])
        for pid in index_only[:10]:
            diff_rows.append([str(pid), "มีใน index แต่ไม่มีใน log",
                              str(index_map[pid]), "-", "ต้องตรวจสอบไฟล์ log"])
        for pid in log_only[:10]:
            diff_rows.append([str(pid), "มีใน log แต่ไม่มีใน index", "-",
                              str(latest_seq[pid]),
                              "ต้องสร้างดัชนีใหม่จาก log"])
        lines.extend(render_table(
            ["point_id", "ปัญหา", "log_seq ใน index", "log_seq ใน log",
             "คำแนะนำ"], diff_rows))
        lines.append("")

    # ---- ส่วนสรุป -----------------------------------------------------

# ---- ส่วนสรุป -----------------------------------------------------
    deleted = [p for p in points if p.is_deleted]
    summary_rows = [
        [f"record ใน {SOURCE_POINT_FILE}", f"{len(points)} record"],
        ["record ที่ถูก soft delete", f"{len(deleted)} record"],
        ["ช่องว่างที่นำกลับมาใช้ได้ (Free Slots)", f"{len(deleted)} ช่อง"],
        [f"เหตุการณ์ใน {SOURCE_LOG_FILE}", f"{len(log_entries)} record"],
        [f"record ใน {SOURCE_INDEX_FILE}", f"{len(index_map)} record"],
        ["point_id ที่ log_seq ไม่ตรงกัน", f"{len(mismatch)} รายการ"],
        ["Endianness ที่ใช้ทั้งระบบ", models.BYTE_ORDER_LABEL],
        [f"ไฟล์ต้นทางที่ใช้ประกอบรายงานนี้",
         f"{SOURCE_POINT_FILE}, {SOURCE_LOG_FILE}, {SOURCE_INDEX_FILE}"],
    ]
    all_valid = store_valid and log_valid and index_valid
    diff_total = len(mismatch) + len(index_only) + len(log_only)
    check_rows = [
        [f"ขนาดไฟล์ข้อมูลหลักหารด้วย {models.RECORD_SIZE} ลงตัว", "ผ่าน",
         "ผ่าน" if store_valid else "ไม่ผ่าน"],
        [f"ขนาดไฟล์ log หารด้วย {models.LOG_RECORD_SIZE} ลงตัว", "ผ่าน",
         "ผ่าน" if log_valid else "ไม่ผ่าน"],
        [f"ขนาดไฟล์ index หารด้วย {models.INDEX_RECORD_SIZE} ลงตัว", "ผ่าน",
         "ผ่าน" if index_valid else "ไม่ผ่าน"],
        [f"{SOURCE_INDEX_FILE} สอดคล้องกับ {SOURCE_LOG_FILE}",
         "ไม่มีรายการไม่ตรงกัน",
         "ผ่าน" if diff_total == 0 else f"ไม่ผ่าน ({diff_total} รายการ)"],
        ["ระบบทั้งระบบอยู่ในสถานะปกติ", "ทุกไฟล์ถูกต้อง",
         "ผ่าน" if all_valid and diff_total == 0
         else "ตรวจสอบข้อมูลอีกครั้ง"],
    ]
    lines.extend(_footer_section(summary_rows, check_rows))
    return lines


def generate_all_reports(data_dir: str,
                         points: Sequence[models.ChargePoint],
                         log_entries: Sequence[models.LogEntry],
                         index_map: Dict[int, int],
                         store_valid: bool = True,
                         log_valid: bool = True,
                         index_valid: bool = True,
                         locations: Optional[Dict[int, str]] = None
                         ) -> Dict[str, str]:
    """สร้างรายงานทั้ง 3 ชุดเป็น **ไฟล์ .txt แยกกัน** (เกณฑ์ข้อ 1 และ 4)

    รายงานทุกชุดถูกสร้างจากข้อมูลของไฟล์อย่างน้อย 2 ไฟล์ (เกณฑ์ข้อ 3)

    Args:
        data_dir: โฟลเดอร์ที่เก็บไฟล์ข้อมูลและจะเขียนรายงานลงที่นั่น
        points: record หัวชาร์จทั้งหมด (อ่านจาก charge_points.dat)
        log_entries: เหตุการณ์ทั้งหมด (อ่านจาก charge_points.log)
        index_map: dict {point_id: log_seq} (อ่านจาก index.dat)
        store_valid / log_valid / index_valid: ผลตรวจ integrity ของแต่ละไฟล์
        locations: dict {point_id: ชื่อสถานที่แบบเต็ม} (อ่านจาก locations.txt)
            ใช้แสดงชื่อเต็มแทนค่าที่ถูกตัดถึง 30 ไบต์ใน record ไบนารี

    Returns:
        dict {ชื่อไฟล์รายงาน: พาธไฟล์เต็ม}
    """
    builders = (
        (REPORT_POINTS_NAME, build_report_points),
        (REPORT_STATS_NAME, build_report_stats),
        (REPORT_SYSTEM_NAME, build_report_system),
    )
    created: Dict[str, str] = {}
    for file_name, builder in builders:
        path = os.path.join(data_dir, file_name)
        lines = builder(data_dir, points, log_entries, index_map,
                        store_valid=store_valid, log_valid=log_valid,
                        index_valid=index_valid, locations=locations)
        _write_report(path, lines)
        created[file_name] = path
    return created


def report_uses_multiple_sources(file_name: str) -> bool:
    """ตรวจว่ารายงานชุดนี้ดึงข้อมูลจากไฟล์อย่างน้อย 2 ไฟล์ (เกณฑ์ข้อ 3)

    รายงานทั้ง 3 ชุดของระบบนี้อ้างอิง charge_points.dat, index.dat
    และ charge_points.log ครบทุกชุด จึงคืนค่า True เสมอ

    Returns:
        True ถ้ารายงานนี้ใช้ข้อมูลมากกว่า 1 ไฟล์
    """
    return file_name in ALL_REPORT_NAMES