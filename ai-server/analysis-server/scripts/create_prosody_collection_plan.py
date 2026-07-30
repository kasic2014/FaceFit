"""Create a deterministic 24-row anonymous prosody recording plan."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PLAN_FIELDS = (
    "plan_id",
    "sample_id",
    "speaker_code",
    "session_id",
    "script_id",
    "repetition_index",
    "device_code",
    "environment_code",
    "recording_condition",
    "recording_order",
    "expected_original_filename",
    "expected_analysis_wav_filename",
    "recording_status",
    "transfer_status",
    "analysis_status",
    "notes",
)
PROHIBITED_PERSONAL_FIELDS = {
    "real_name",
    "email",
    "phone",
    "birth_date",
    "gender",
    "address",
    "account_id",
}
SCRIPTS = ("SCRIPT001", "SCRIPT002")
DEVICES = ("DEV_PC_MIC_01", "DEV_PHONE_01")
CONDITIONS = ("clean", "natural")
REPETITIONS = (1, 2, 3)

CHECKLIST_TEXT = """# Prosody recording checklist

이 체크리스트는 익명 코드 기반 반복성·장치 민감도 수집을 위한 것이다.
실제 이름이나 개인정보를 파일명과 notes에 기록하지 않는다.

## 녹음 전

- 실제 이름이나 개인정보를 파일명에 사용하지 않기
- 장치와 입 사이 거리 확인
- 방 안의 TV, 음악, 선풍기 상태 확인
- 스크립트와 조건 확인
- 장치 저장 공간 확인

## 녹음 중

- 녹음 시작 후 잠시 기다리고 발화
- 문장이 끝난 뒤 잠시 기다리고 종료
- 파일을 중간에 편집하지 않기
- 오류가 있으면 기존 파일을 덮어쓰지 말고 다시 녹음한 사실을 notes에 기록

## 녹음 후

- 원본 파일 보존
- 파일명 확인
- 휴대폰 파일을 PC로 복사
- 원본 해시 생성 전 편집 금지
- 분석용 WAV는 별도 파일로 생성
- 실제 등록 전 WAV, STT, metrics, prosody v2.1 산출물 확인

## clean 조건

- 조용한 환경
- 의도적인 속도·억양 조작 없음
- 의도적인 잡음 없음

## natural 조건

- 실제 면접 답변처럼 자연스럽게 발화
- 자연스러운 호흡과 멈춤 허용
- 감정이나 억양을 인위적으로 과장하지 않음

## 장치 교대 순서

- repetition 1: PC 먼저, 휴대폰 다음
- repetition 2: 휴대폰 먼저, PC 다음
- repetition 3: PC 먼저, 휴대폰 다음

PC WAV와 휴대폰 원본을 그대로 보존한다. 휴대폰 원본은 별도 분석용 WAV로
변환하되 이 계획 생성 도구는 녹음, 복사, 변환 또는 분석을 실행하지 않는다.
"""


class CollectionPlanError(Exception):
    """A classified plan generation or validation failure."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _device_order(repetition: int) -> tuple[str, str]:
    return (
        ("DEV_PHONE_01", "DEV_PC_MIC_01")
        if repetition == 2
        else ("DEV_PC_MIC_01", "DEV_PHONE_01")
    )


def _sample_id(
    speaker: str,
    session: str,
    script: str,
    device: str,
    condition: str,
    repetition: int,
) -> str:
    return (
        f"{speaker}_{session}_{script}_{device}_{condition}_R{repetition:02d}"
    )


def _filenames(
    speaker: str,
    session: str,
    script: str,
    device: str,
    condition: str,
    repetition: int,
) -> tuple[str, str]:
    stem = (
        f"{speaker}_{script}_{session}_{device}_{condition}_R{repetition:02d}"
    )
    original_extension = ".m4a" if device == "DEV_PHONE_01" else ".wav"
    return f"{stem}{original_extension}", f"{stem}.wav"


def generate_collection_plan() -> list[dict[str, Any]]:
    """Generate all 24 rows with alternating device order per repetition."""
    rows: list[dict[str, Any]] = []
    recording_order = 0
    for script in SCRIPTS:
        for condition in CONDITIONS:
            for repetition in REPETITIONS:
                for device in _device_order(repetition):
                    recording_order += 1
                    sample_id = _sample_id(
                        "SPK001",
                        "SESSION001",
                        script,
                        device,
                        condition,
                        repetition,
                    )
                    original, analysis_wav = _filenames(
                        "SPK001",
                        "SESSION001",
                        script,
                        device,
                        condition,
                        repetition,
                    )
                    rows.append(
                        {
                            "plan_id": f"PLAN{recording_order:03d}",
                            "sample_id": sample_id,
                            "speaker_code": "SPK001",
                            "session_id": "SESSION001",
                            "script_id": script,
                            "repetition_index": repetition,
                            "device_code": device,
                            "environment_code": "QUIET_ROOM",
                            "recording_condition": condition,
                            "recording_order": recording_order,
                            "expected_original_filename": original,
                            "expected_analysis_wav_filename": analysis_wav,
                            "recording_status": "pending",
                            "transfer_status": "pending",
                            "analysis_status": "pending",
                            "notes": "",
                        }
                    )
    validate_collection_plan(rows)
    return rows


def validate_collection_plan(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate counts, uniqueness, filenames, and benchmark device pairs."""
    if len(rows) != 24:
        raise CollectionPlanError(
            "PLAN_ROW_COUNT_INVALID", f"Expected 24 rows, found {len(rows)}."
        )
    field_set = set(PLAN_FIELDS)
    for index, row in enumerate(rows, 1):
        if set(row) != field_set:
            raise CollectionPlanError(
                "PLAN_SCHEMA_INVALID",
                f"Row {index} does not match the fixed field schema.",
            )
        prohibited = PROHIBITED_PERSONAL_FIELDS.intersection(row)
        if prohibited:
            raise CollectionPlanError(
                "PROHIBITED_PERSONAL_FIELD",
                ", ".join(sorted(prohibited)),
            )
        if (
            row["recording_status"],
            row["transfer_status"],
            row["analysis_status"],
        ) != ("pending", "pending", "pending"):
            raise CollectionPlanError(
                "INITIAL_STATUS_INVALID", f"Row {index} has a non-pending status."
            )

    def require_unique(field: str) -> None:
        values = [str(row[field]) for row in rows]
        if len(values) != len(set(values)):
            raise CollectionPlanError(
                "DUPLICATE_PLAN_VALUE", f"{field} contains duplicates."
            )

    for unique_field in (
        "plan_id",
        "sample_id",
        "expected_original_filename",
        "expected_analysis_wav_filename",
        "recording_order",
    ):
        require_unique(unique_field)

    device_counts = Counter(str(row["device_code"]) for row in rows)
    condition_counts = Counter(
        str(row["recording_condition"]) for row in rows
    )
    script_counts = Counter(str(row["script_id"]) for row in rows)
    repetition_counts = Counter(int(row["repetition_index"]) for row in rows)
    expected_counts = (
        (device_counts, {"DEV_PC_MIC_01": 12, "DEV_PHONE_01": 12}),
        (condition_counts, {"clean": 12, "natural": 12}),
        (script_counts, {"SCRIPT001": 12, "SCRIPT002": 12}),
        (repetition_counts, {1: 8, 2: 8, 3: 8}),
    )
    for actual, expected in expected_counts:
        if dict(actual) != expected:
            raise CollectionPlanError(
                "PLAN_DISTRIBUTION_INVALID",
                f"Expected {expected}, found {dict(actual)}.",
            )

    comparison_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(
        list
    )
    for row in rows:
        key = (
            row["speaker_code"],
            row["script_id"],
            row["session_id"],
            row["repetition_index"],
            row["recording_condition"],
        )
        comparison_groups[key].append(row)
    if len(comparison_groups) != 12:
        raise CollectionPlanError(
            "DEVICE_PAIR_COUNT_INVALID",
            f"Expected 12 comparison keys, found {len(comparison_groups)}.",
        )
    for key, pair in comparison_groups.items():
        devices = {str(row["device_code"]) for row in pair}
        if len(pair) != 2 or devices != set(DEVICES):
            raise CollectionPlanError(
                "DEVICE_PAIR_INCOMPLETE", f"{key}: {sorted(devices)}"
            )
        ordered = [
            str(row["device_code"])
            for row in sorted(pair, key=lambda item: item["recording_order"])
        ]
        if tuple(ordered) != _device_order(int(key[3])):
            raise CollectionPlanError(
                "DEVICE_ORDER_INVALID", f"{key}: {ordered}"
            )

    for row in rows:
        original = str(row["expected_original_filename"])
        analysis = str(row["expected_analysis_wav_filename"])
        if row["device_code"] == "DEV_PHONE_01":
            if not original.endswith(".m4a") or not analysis.endswith(".wav"):
                raise CollectionPlanError(
                    "PHONE_FILENAME_INVALID", str(row["plan_id"])
                )
        elif original != analysis or not original.endswith(".wav"):
            raise CollectionPlanError(
                "PC_FILENAME_INVALID", str(row["plan_id"])
            )

    return {
        "total_rows": len(rows),
        "sample_id_duplicate_count": 0,
        "plan_id_duplicate_count": 0,
        "device_counts": dict(device_counts),
        "condition_counts": dict(condition_counts),
        "script_counts": dict(script_counts),
        "repetition_counts": {
            str(key): value for key, value in repetition_counts.items()
        },
        "device_comparison_pair_count": len(comparison_groups),
        "expected_original_filename_duplicate_count": 0,
        "expected_analysis_wav_filename_duplicate_count": 0,
        "prohibited_personal_field_count": 0,
    }


def strict_json_text(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )


def _atomic_write(path: Path, text: str, *, encoding: str, newline: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding=encoding, newline=newline) as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise CollectionPlanError(
            "OUTPUT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def write_csv_atomic(path: Path | str, rows: list[dict[str, Any]]) -> None:
    output = Path(path)
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open(
            "w", encoding="utf-8-sig", newline=""
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=PLAN_FIELDS)
            writer.writeheader()
            writer.writerows(
                {field: row[field] for field in PLAN_FIELDS} for row in rows
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    except (OSError, csv.Error) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise CollectionPlanError(
            "OUTPUT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def write_json_atomic(path: Path | str, rows: list[dict[str, Any]]) -> None:
    validation = validate_collection_plan(rows)
    payload = {
        "schema_version": "1.0",
        "description": (
            "Anonymous 24-row recording plan for within-speaker repeatability "
            "and device sensitivity validation."
        ),
        "fields": list(PLAN_FIELDS),
        "validation_summary": validation,
        "plan_rows": rows,
        "error": None,
    }
    _atomic_write(
        Path(path),
        strict_json_text(payload) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_checklist_atomic(path: Path | str) -> None:
    _atomic_write(
        Path(path),
        CHECKLIST_TEXT,
        encoding="utf-8",
        newline="\n",
    )


def write_collection_plan(
    csv_path: Path | str,
    json_path: Path | str,
    checklist_path: Path | str,
) -> dict[str, Any]:
    destinations = [
        Path(csv_path).resolve(),
        Path(json_path).resolve(),
        Path(checklist_path).resolve(),
    ]
    if len(set(destinations)) != 3:
        raise CollectionPlanError(
            "OUTPUT_PATH_COLLISION", "All output paths must be different."
        )
    rows = generate_collection_plan()
    validation = validate_collection_plan(rows)
    write_csv_atomic(csv_path, rows)
    write_json_atomic(json_path, rows)
    write_checklist_atomic(checklist_path)
    return {
        "csv_output": str(csv_path),
        "json_output": str(json_path),
        "checklist_output": str(checklist_path),
        "validation_summary": validation,
        "error": None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--checklist-output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        result = write_collection_plan(
            args.output_csv,
            args.output_json,
            args.checklist_output,
        )
    except CollectionPlanError as exc:
        print(
            strict_json_text(
                {"error": {"code": exc.code, "detail": exc.detail}}
            )
        )
        return 1
    print(strict_json_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
