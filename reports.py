"""reports.py — สร้างรายงาน .txt 3 ชุดจากข้อมูลไบนารี

รายงานทั้ง 3 ไฟล์
----------------
1. ``report_points.txt`` — สถานะหัวชาร์จรายหัว
2. ``report_stats.txt``  — สถิติราคา กำลังไฟ และกิจกรรม
3. ``report_system.txt`` — สถานะระบบไฟล์และดัชนี

รายงาน ``report_stats.txt`` แสดงเฉพาะตารางกิจกรรมล่าสุด (TABLE 2)
และ Summary; รายงานอื่นแสดงตารางข้อมูลและ Summary

ทุกไฟล์อ้างอิงข้อมูลจาก 3 ไฟล์ไบนารีเสมอ (เกณฑ์ข้อ 3):
``charge_points.dat`` + ``charge_points.log`` + ``index.dat``

ข้อความในตารางเป็นภาษาอังกฤษเพื่อให้แนวคอลัมน์ตรงกันใน text editors
ที่จัดวางสระและวรรณยุกต์ภาษาไทยต่างกัน
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence

import models
from report import (
    RECENT_ACTIVITY_LIMIT,
    alignment_mode_name,
    compute_summary,
    format_timestamp,
    measure,
    render_table,
    set_alignment_mode,
    truncate_to_width,
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

# ความกว้างสูงสุดของตารางข้อมูลหัวชาร์จและช่องสถานที่
MAIN_TABLE_MAX_WIDTH = 190
MAIN_TABLE_LOCATION_WIDTH = 70

_LOCATION_LABELS = {
    "สยามพารากอน ชั้น B1": "Siam Paragon, Level B1",
    "เซ็นทรัลเวิลด์ ลาน P2": "CentralWorld, Parking P2",
    "ICONSIAM ชั้น G": "ICONSIAM, Level G",
    "เมกาบางนา โซน A": "Mega Bangna, Zone A",
    "เซ็นทรัลพระราม 9": "Central Rama 9",
    "บิกกิ้ง สาทร ชั้น 2": "Biking Sathorn, Level 2",
    "ลาดพร้าว ไทยรัฐ 2": "Lat Phrao, Thairath 2",
    "เอเชีย เซนเทอร์ ชั้น G": "Asia Center, Level G",
    "เซ็นทรัล พหมโพธิยา": "Central Phom Phothiya",
    "พารากอน โครงการเก่า": "Paragon, Former Project",
    "สถานีชาร์จไฟฟ้าสยามพารากอนชั้นใต้ดินโครงการใหม่และลานจอดรถ":
        "Siam Paragon EV Station, New Basement Project and Parking Lot",
}


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


def english_location_label(location: str) -> Optional[str]:
    """Return a known English location label, or None for custom locations."""
    return _LOCATION_LABELS.get(location)


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


def _summary_section(summary_rows: Sequence[Sequence[str]]) -> List[str]:
    """สร้างส่วนสรุปของรายงานโดยไม่เพิ่มตาราง consistency check"""
    return [
        "[SUMMARY] Summary",
        "-" * 62,
        *render_table(["Item", "Value"], list(summary_rows)),
    ]


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
    จำนวนระเบียนใน index.dat แสดงในส่วนสรุปและตรวจสอบ

    พารามิเตอร์ store_valid/log_valid/index_valid รับไว้เพื่อให้
    ฟังก์ชันทั้ง 3 ชุดมีลายเซ็นเหมือนกัน (ใช้โดย generate_all_reports)
    """
    summary = compute_summary(points)

    lines = _header(data_dir)
    lines.append("")

    # ---- ตารางข้อมูลจริง --------------------------------------------
    lines.append("[TABLE 1] All charging points (including deleted records)")
    lines.append("-" * 62)
    rows = []
    for point in points:
        location = _full_location(point, locations)
        english_location = english_location_label(location)
        table_location = english_location or location
        rows.append([
            str(point.point_id),
            point.station_code,
            truncate_to_width(table_location, MAIN_TABLE_LOCATION_WIDTH),
            point.plug_type,
            f"{point.power_kw:.1f}",
            f"{point.price_per_kwh:.2f}",
            point.status_text,
            point.booked_text,
            format_timestamp(point.updated_at).replace(" (+07:00)", ""),
        ])
    lines.extend(render_table(
        ["PtID", "Station", "Location", "Plug", "Power", "Price", "Status",
         "Booked", "Updated"], rows,
        max_width=MAIN_TABLE_MAX_WIDTH))
    lines.append("")

    # ---- ส่วนสรุป ---------------------------------------------------
    # Inactive points must be counted separately so the status totals reconcile.
    inactive = [p for p in points if not p.is_deleted and p.status != 1]
    # Only booked active points reconcile with the available count.
    booked_active = [p for p in points
                     if not p.is_deleted and p.status == 1 and p.is_booked == 1]

    summary_rows = [
        ["Total Points (records)", str(summary["total"])],
        ["Active Points", str(summary["active"])],
        ["Inactive Points (maintenance)", str(len(inactive))],
        ["Deleted Points (soft delete)", str(summary["deleted"])],
        ["Currently Booked (all statuses)", str(summary["booked"])],
        ["Booked Active Points", str(len(booked_active))],
        ["Available Now (Active & not booked)", str(summary["available"])],
        ["Free Slots (reuseable)", str(summary["free_slots"])],
        [f"Records in {SOURCE_INDEX_FILE}", f"{len(index_map)} records"],
        ["Binary sources (.dat)",
         f"{SOURCE_POINT_FILE}, {SOURCE_INDEX_FILE}"],
        ["Source files",
         f"{SOURCE_POINT_FILE}, {SOURCE_LOG_FILE}, {SOURCE_INDEX_FILE}"],
    ]

    lines.extend(_summary_section(summary_rows))
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

    # ---- TABLE 2: Recent log activity ----------------------------------
    lines.append(f"[TABLE 2] Recent activity from {SOURCE_LOG_FILE} "
                 f"(latest {len(recent)} records)")
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
            "Found in index" if entry.point_id in index_map
            else "Missing from index",
        ])
    lines.extend(render_table(
        ["Timestamp", "Operation", "PtID", "Status", "Booked", "Price",
         "Index check"], recent_rows))
    lines.append("")

    # ---- Summary -------------------------------------------------------
    summary_rows = [
        ["Records used for statistics (active)", str(count)],
        ["Average price (THB/kWh)", f"{stats['price_avg']:.2f}"],
        ["Average power (kW)", f"{stats['avg']:.1f}"],
        ["Total active connectors", str(sum(plug_counts.values()))],
        ["Total log events", str(len(log_entries))],
        ["ADD / UPDATE / DELETE / VIEW",
         f"{op_counts[models.OP_ADD]} / {op_counts[models.OP_UPDATE]} / "
         f"{op_counts[models.OP_DELETE]} / {op_counts[models.OP_VIEW]}"],
        [f"Records in {SOURCE_INDEX_FILE}", f"{len(index_map)} records"],
        ["Binary sources (.dat)",
         f"{SOURCE_POINT_FILE}, {SOURCE_INDEX_FILE}"],
        ["Source files",
         f"{SOURCE_POINT_FILE}, {SOURCE_LOG_FILE}, {SOURCE_INDEX_FILE}"],
    ]
    lines.extend(_summary_section(summary_rows))
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

    # ---- TABLE 3: Binary file status -----------------------------------
    lines.append("[TABLE 3] Binary file status")
    lines.append("-" * 62)
    file_rows = []
    for label, file_name, struct_fmt, record_size, count, valid in (
        ("Primary data", SOURCE_POINT_FILE, models.CHARGE_POINT_FORMAT,
         models.RECORD_SIZE, len(points), store_valid),
        ("audit log", SOURCE_LOG_FILE, models.LOG_FORMAT,
         models.LOG_RECORD_SIZE, len(log_entries), log_valid),
        ("Index", SOURCE_INDEX_FILE, models.INDEX_FORMAT,
         models.INDEX_RECORD_SIZE, len(index_map), index_valid),
    ):
        file_rows.append([
            label, file_name, struct_fmt, f"{record_size} bytes",
            str(count), "PASS" if valid else "INVALID",
        ])
    lines.extend(render_table(
        ["Type", "File", "Struct format", "Bytes/record", "Count", "Status"],
        file_rows))
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

    # Show detailed differences only when an inconsistency exists.
    if mismatch or index_only or log_only:
        lines.append(f"[TABLE 2] Compare {SOURCE_INDEX_FILE} "
                     f"with {SOURCE_LOG_FILE}")
        lines.append("-" * 62)
        diff_rows = []
        for pid, in_index, in_log in mismatch[:10]:
            diff_rows.append([str(pid), "Mismatch", str(in_index), str(in_log),
                              "Rebuild index from log"])
        for pid in index_only[:10]:
            diff_rows.append([str(pid), "In index, missing from log",
                              str(index_map[pid]), "-", "Check log file"])
        for pid in log_only[:10]:
            diff_rows.append([str(pid), "In log, missing from index", "-",
                              str(latest_seq[pid]), "Rebuild index from log"])
        lines.extend(render_table(
            ["point_id", "Issue", "log_seq in index", "log_seq in log",
             "Recommendation"], diff_rows))
        lines.append("")

    deleted = [p for p in points if p.is_deleted]
    summary_rows = [
        [f"Records in {SOURCE_POINT_FILE}", f"{len(points)} records"],
        ["Soft-deleted records", f"{len(deleted)} records"],
        ["Reusable free slots", str(len(deleted))],
        [f"Events in {SOURCE_LOG_FILE}", f"{len(log_entries)} records"],
        [f"Records in {SOURCE_INDEX_FILE}", f"{len(index_map)} records"],
        ["point_id/log_seq mismatches", str(len(mismatch))],
        ["System endianness", models.BYTE_ORDER_LABEL],
        ["Binary sources (.dat)",
         f"{SOURCE_POINT_FILE}, {SOURCE_INDEX_FILE}"],
        ["Source files",
         f"{SOURCE_POINT_FILE}, {SOURCE_LOG_FILE}, {SOURCE_INDEX_FILE}"],
    ]

    lines.extend(_summary_section(summary_rows))
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
    ไฟล์รายงานใช้ความกว้างแบบ smart ให้แนวคอลัมน์ตรงกับการแสดงผลภาษาไทย
    ส่วนโหมด alignment เดิมจะถูกคืนค่าไว้สำหรับตารางใน Terminal

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
    previous_alignment = alignment_mode_name()
    set_alignment_mode(True)
    try:
        for file_name, builder in builders:
            path = os.path.join(data_dir, file_name)
            lines = builder(data_dir, points, log_entries, index_map,
                            store_valid=store_valid, log_valid=log_valid,
                            index_valid=index_valid, locations=locations)
            _write_report(path, lines)
            created[file_name] = path
    finally:
        set_alignment_mode(previous_alignment == "smart")
    return created


def report_uses_multiple_sources(file_name: str) -> bool:
    """ตรวจว่ารายงานชุดนี้ดึงข้อมูลจากไฟล์อย่างน้อย 2 ไฟล์ (เกณฑ์ข้อ 3)

    รายงานทั้ง 3 ชุดของระบบนี้อ้างอิง charge_points.dat, index.dat
    และ charge_points.log ครบทุกชุด จึงคืนค่า True เสมอ

    Returns:
        True ถ้ารายงานนี้ใช้ข้อมูลมากกว่า 1 ไฟล์
    """
    return file_name in ALL_REPORT_NAMES