from __future__ import annotations

import csv
import os
import tempfile
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .result_schema import RESULT_FIELDS, serialize_csv_value, validate_result
from .presentation import EXCEL_FIELDS, format_excel_text


EXPORT_FIELDS = ("condition", "source", "model", "reasoning_effort", *RESULT_FIELDS)
CONDITION_ORDER = {"WITH_SKILL": 0, "WITHOUT_SKILL": 1}
WORKSHEET_TITLE = "A 결과"
EXCEL_WIDTHS = (28, 13, 34, 16, 10, 48, 56, 56, 56)


def build_with_skill_workbook(result: dict[str, Any]) -> bytes:
    """Build a one-row user-facing XLSX while retaining typed amount and date cells."""
    validate_result(result, str(result.get("thread_id", "")))
    workbook, sheet = _new_workbook()
    _append_result_row(sheet, result)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class WithSkillExcelStore:
    """Append validated WITH_SKILL results to one durable XLSX file."""

    def __init__(self, output_path: Path, allowed_root: Path) -> None:
        self.output_path = output_path.resolve()
        self.allowed_root = allowed_root.resolve()
        if self.output_path.suffix.lower() != ".xlsx":
            raise ValueError("누적 Excel 파일은 .xlsx 확장자를 사용해야 합니다.")
        if self.allowed_root != self.output_path.parent and self.allowed_root not in self.output_path.parents:
            raise ValueError("누적 Excel 파일은 지정된 runtime 경로 안에 있어야 합니다.")

    def append_with_skill_result(self, result: dict[str, Any]) -> int:
        validate_result(result, str(result.get("thread_id", "")))
        workbook, sheet = self._load_or_create()
        row_number = _append_result_row(sheet, result)
        self._save_atomic(workbook)
        return row_number

    def read_bytes(self) -> bytes | None:
        if not self.output_path.is_file():
            return None
        workbook, _ = self._load_existing()
        workbook.close()
        return self.output_path.read_bytes()

    def _load_or_create(self) -> tuple[Workbook, Any]:
        if not self.output_path.exists():
            return _new_workbook()
        return self._load_existing()

    def _load_existing(self) -> tuple[Workbook, Any]:
        try:
            workbook = load_workbook(self.output_path)
        except Exception as exc:
            raise ValueError(f"기존 누적 Excel 파일을 열 수 없습니다: {exc}") from exc
        if WORKSHEET_TITLE not in workbook.sheetnames:
            workbook.close()
            raise ValueError(f"기존 Excel에 '{WORKSHEET_TITLE}' sheet가 없습니다.")
        sheet = workbook[WORKSHEET_TITLE]
        header = tuple(sheet.cell(row=1, column=index).value for index in range(1, len(EXCEL_FIELDS) + 1))
        if header != EXCEL_FIELDS:
            workbook.close()
            raise ValueError("기존 Excel 헤더가 현재 A 결과 schema와 다릅니다.")
        return workbook, sheet

    def _save_atomic(self, workbook: Workbook) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{self.output_path.stem}.", suffix=".xlsx", dir=self.output_path.parent,
        )
        os.close(descriptor)
        temp_path = Path(temp_name)
        try:
            workbook.save(temp_path)
            workbook.close()
            temp_path.replace(self.output_path)
        except Exception:
            workbook.close()
            temp_path.unlink(missing_ok=True)
            raise


def _new_workbook() -> tuple[Workbook, Any]:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = WORKSHEET_TITLE
    sheet.append(EXCEL_FIELDS)
    sheet.freeze_panes = "A2"
    header_fill = PatternFill("solid", fgColor="D9EAF7")
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for index, width in enumerate(EXCEL_WIDTHS, start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = width
    sheet.auto_filter.ref = f"A1:I1"
    return workbook, sheet


def _append_result_row(sheet: Any, result: dict[str, Any]) -> int:
    row: list[Any] = []
    for field in EXCEL_FIELDS:
        if field == "날짜":
            row.append(date.fromisoformat(result[field]))
        elif field == "금액":
            row.append(result[field])
        else:
            row.append(_safe_excel_text(format_excel_text(field, result)))
    sheet.append(row)
    row_number = sheet.max_row
    for cell in sheet[row_number]:
        cell.alignment = Alignment(vertical="top", wrap_text=True)
    sheet.cell(row=row_number, column=2).number_format = "yyyy-mm-dd"
    sheet.cell(row=row_number, column=4).number_format = "#,##0"
    sheet.auto_filter.ref = f"A1:I{row_number}"
    return row_number


def _safe_excel_text(value: str) -> str:
    if value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


class ABResultExcelRepository:
    """Upsert validated, deterministically ordered Excel-compatible CSV rows."""

    def __init__(self, output_path: Path, allowed_root: Path) -> None:
        self.output_path = output_path.resolve()
        self.allowed_root = allowed_root.resolve()
        if self.output_path.suffix.lower() != ".csv":
            raise ValueError("A/B export path must use the .csv extension.")
        if self.allowed_root not in self.output_path.parents:
            raise ValueError("A/B export must stay inside the configured experiment root.")

    def append_result(
        self,
        condition: str,
        source: str,
        thread_id: str,
        model: str,
        reasoning_effort: str,
        result: dict[str, Any],
    ) -> Path:
        return self.upsert_results([{
            "condition": condition,
            "source": source,
            "thread_id": thread_id,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "result": result,
        }])

    def upsert_results(self, records: list[dict[str, Any]]) -> Path:
        existing = self._read_existing()
        return self._save_records(records, existing)

    def replace_results(self, records: list[dict[str, Any]]) -> Path:
        """Replace the result set after validating every supplied record."""
        return self._save_records(records, {})

    def _save_records(
        self,
        records: list[dict[str, Any]],
        existing: dict[tuple[str, str], dict[str, Any]],
    ) -> Path:
        for record in records:
            condition = str(record["condition"])
            if condition not in CONDITION_ORDER:
                raise ValueError(f"unsupported A/B condition: {condition}")
            result = validate_result(record["result"], str(record["thread_id"]))
            row = {
                "condition": condition,
                "source": str(record["source"]),
                "model": str(record["model"]),
                "reasoning_effort": str(record["reasoning_effort"]),
                **{field: serialize_csv_value(field, result[field]) for field in RESULT_FIELDS},
            }
            existing[(result["thread_id"], condition)] = row
        rows = sorted(
            existing.values(),
            key=lambda row: (row["thread_id"], CONDITION_ORDER[row["condition"]]),
        )
        self._write_atomic(rows)
        return self.output_path

    def _read_existing(self) -> dict[tuple[str, str], dict[str, Any]]:
        if not self.output_path.exists():
            return {}
        with self.output_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != EXPORT_FIELDS:
                raise ValueError("existing CSV schema does not match the normalized export schema")
            rows = list(reader)
        return {(row["thread_id"], row["condition"]): row for row in rows}

    def _write_atomic(self, rows: list[dict[str, Any]]) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{self.output_path.name}.", suffix=".tmp", dir=self.output_path.parent,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=EXPORT_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            Path(temp_name).replace(self.output_path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise
