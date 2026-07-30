"""Create the held-out Stage 2 multi-speaker recording plan.

This planning-only tool does not record, convert, transcribe, analyze audio,
load models, or modify the frozen SESSION001 development pilot.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
SPEAKERS = ("SPK002", "SPK003", "SPK004", "SPK005")
SCRIPTS = ("SCRIPT001", "SCRIPT002")
SCRIPT_TITLES = {
    "SCRIPT001": "책임감과 협업 방식",
    "SCRIPT002": "데이터 저장 문제 해결 경험",
}
CONDITIONS = ("clean", "natural")
REPETITIONS = (1, 2, 3)
DEVICES = ("DEV_PC_MIC_01", "DEV_PHONE_01")
DATASET_STAGE = "stage2"
DATASET_ROLE = "held_out_validation"
CAPTURE_PATTERN = re.compile(
    r"^SPK00[2-5]_SESSION001_SCRIPT00[12]_(clean|natural)_R0[1-3]$"
)
PLAN_FIELDS = (
    "plan_id",
    "dataset_stage",
    "dataset_role",
    "speaker_code",
    "session_id",
    "script_id",
    "script_title",
    "recording_condition",
    "repetition_index",
    "device_code",
    "capture_group_id",
    "paired_sample_id",
    "sample_id",
    "simultaneous_capture",
    "device_start_order",
    "expected_original_filename",
    "expected_analysis_wav_filename",
    "planned_mouth_distance_cm",
    "actual_mouth_distance_cm",
    "room_environment",
    "device_position_note",
    "agc_or_processing_note",
    "unexpected_noise_note",
    "recording_status",
    "consent_confirmed",
    "exclusion_reason",
)
CAPTURE_CHECKLIST_FIELDS = (
    "capture_group_id",
    "dataset_role",
    "speaker_code",
    "session_id",
    "script_id",
    "recording_condition",
    "repetition_index",
    "device_start_order",
    "consent_confirmed",
    "simultaneous_capture_confirmed",
    "pc_actual_mouth_distance_cm",
    "phone_actual_mouth_distance_cm",
    "pc_device_position_note",
    "phone_device_position_note",
    "room_environment",
    "background_noise_note",
    "notification_or_external_speech_note",
    "pc_agc_or_processing_note",
    "phone_agc_or_processing_note",
    "capture_status",
    "exclusion_reason",
    "post_capture_note",
)
PROHIBITED_PERSONAL_FIELDS = {
    "real_name",
    "name",
    "email",
    "phone_number",
    "telephone",
    "birth_date",
    "date_of_birth",
    "address",
    "gender",
    "age",
}


class Stage2PlanError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def strict_json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)


def load_script_references(path: Path | str) -> dict[str, str]:
    source = Path(path)
    if not source.is_file():
        raise Stage2PlanError("SCRIPT_REFERENCE_NOT_FOUND", str(source))
    try:
        payload = json.loads(
            source.read_text(encoding="utf-8-sig"),
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"Non-finite JSON constant: {token}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise Stage2PlanError(
            "SCRIPT_REFERENCE_INVALID",
            f"{type(exc).__name__}: {exc}",
        ) from exc
    scripts = payload.get("scripts") if isinstance(payload, dict) else None
    if not isinstance(scripts, dict) or any(
        not isinstance(scripts.get(script), str)
        or not scripts[script].strip()
        for script in SCRIPTS
    ):
        raise Stage2PlanError(
            "SCRIPT_REFERENCE_INVALID",
            "SCRIPT001 and SCRIPT002 text are required.",
        )
    return {script: scripts[script] for script in SCRIPTS}


def device_start_order(repetition: int) -> str:
    return "PHONE_FIRST" if repetition == 2 else "PC_FIRST"


def device_row_order(repetition: int) -> tuple[str, str]:
    return (
        ("DEV_PHONE_01", "DEV_PC_MIC_01")
        if repetition == 2
        else ("DEV_PC_MIC_01", "DEV_PHONE_01")
    )


def capture_group_id(
    speaker: str, script: str, condition: str, repetition: int
) -> str:
    return (
        f"{speaker}_SESSION001_{script}_{condition}_R{repetition:02d}"
    )


def sample_id(
    speaker: str,
    script: str,
    device: str,
    condition: str,
    repetition: int,
) -> str:
    return (
        f"{speaker}_SESSION001_{script}_{device}_{condition}_R{repetition:02d}"
    )


def filenames(
    speaker: str,
    script: str,
    device: str,
    condition: str,
    repetition: int,
) -> tuple[str, str]:
    stem = (
        f"{speaker}_{script}_SESSION001_{device}_{condition}_R{repetition:02d}"
    )
    return f"{stem}.m4a", f"{stem}.wav"


def generate_stage2_plan() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    plan_index = 0
    for speaker in SPEAKERS:
        session_id = f"{speaker}_SESSION001"
        for script in SCRIPTS:
            for condition in CONDITIONS:
                for repetition in REPETITIONS:
                    capture = capture_group_id(
                        speaker, script, condition, repetition
                    )
                    samples = {
                        device: sample_id(
                            speaker,
                            script,
                            device,
                            condition,
                            repetition,
                        )
                        for device in DEVICES
                    }
                    for device in device_row_order(repetition):
                        plan_index += 1
                        other = (
                            "DEV_PHONE_01"
                            if device == "DEV_PC_MIC_01"
                            else "DEV_PC_MIC_01"
                        )
                        original, analysis = filenames(
                            speaker,
                            script,
                            device,
                            condition,
                            repetition,
                        )
                        rows.append(
                            {
                                "plan_id": f"STAGE2_PLAN{plan_index:03d}",
                                "dataset_stage": DATASET_STAGE,
                                "dataset_role": DATASET_ROLE,
                                "speaker_code": speaker,
                                "session_id": session_id,
                                "script_id": script,
                                "script_title": SCRIPT_TITLES[script],
                                "recording_condition": condition,
                                "repetition_index": repetition,
                                "device_code": device,
                                "capture_group_id": capture,
                                "paired_sample_id": samples[other],
                                "sample_id": samples[device],
                                "simultaneous_capture": True,
                                "device_start_order": device_start_order(
                                    repetition
                                ),
                                "expected_original_filename": original,
                                "expected_analysis_wav_filename": analysis,
                                "planned_mouth_distance_cm": 30,
                                "actual_mouth_distance_cm": "",
                                "room_environment": "",
                                "device_position_note": "",
                                "agc_or_processing_note": "",
                                "unexpected_noise_note": "",
                                "recording_status": "planned",
                                "consent_confirmed": False,
                                "exclusion_reason": "",
                            }
                        )
    validate_stage2_plan(rows)
    return rows


def generate_capture_checklist(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    validate_stage2_plan(rows)
    captures: dict[str, dict[str, Any]] = {}
    for row in rows:
        capture = str(row["capture_group_id"])
        if capture not in captures:
            captures[capture] = {
                "capture_group_id": capture,
                "dataset_role": row["dataset_role"],
                "speaker_code": row["speaker_code"],
                "session_id": row["session_id"],
                "script_id": row["script_id"],
                "recording_condition": row["recording_condition"],
                "repetition_index": row["repetition_index"],
                "device_start_order": row["device_start_order"],
                "consent_confirmed": False,
                "simultaneous_capture_confirmed": False,
                "pc_actual_mouth_distance_cm": "",
                "phone_actual_mouth_distance_cm": "",
                "pc_device_position_note": "",
                "phone_device_position_note": "",
                "room_environment": "",
                "background_noise_note": "",
                "notification_or_external_speech_note": "",
                "pc_agc_or_processing_note": "",
                "phone_agc_or_processing_note": "",
                "capture_status": "planned",
                "exclusion_reason": "",
                "post_capture_note": "",
            }
    checklist = [captures[key] for key in sorted(captures)]
    if len(checklist) != 48:
        raise Stage2PlanError(
            "CAPTURE_CHECKLIST_INVALID",
            f"Expected 48 rows, found {len(checklist)}.",
        )
    return checklist


def _require_unique(rows: list[dict[str, Any]], field: str) -> None:
    values = [str(row[field]) for row in rows]
    if len(values) != len(set(values)):
        raise Stage2PlanError(
            "DUPLICATE_PLAN_VALUE", f"{field} contains duplicates."
        )


def validate_stage2_plan(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rows) != 96:
        raise Stage2PlanError(
            "PLAN_ROW_COUNT_INVALID", f"Expected 96 rows, found {len(rows)}."
        )
    required = set(PLAN_FIELDS)
    for index, row in enumerate(rows, 1):
        if set(row) != required:
            raise Stage2PlanError(
                "PLAN_SCHEMA_INVALID",
                f"Row {index} does not match the fixed schema.",
            )
        prohibited = set(row).intersection(PROHIBITED_PERSONAL_FIELDS)
        if prohibited:
            raise Stage2PlanError(
                "PROHIBITED_PERSONAL_FIELD",
                ", ".join(sorted(prohibited)),
            )
        if row["speaker_code"] == "SPK001":
            raise Stage2PlanError(
                "DEVELOPMENT_PILOT_INCLUDED",
                "SPK001 must not appear in the Stage 2 new collection plan.",
            )
        if row["speaker_code"] not in SPEAKERS:
            raise Stage2PlanError(
                "SPEAKER_INVALID", str(row["speaker_code"])
            )
        if row["dataset_role"] != DATASET_ROLE:
            raise Stage2PlanError(
                "DATASET_ROLE_INVALID", str(row["dataset_role"])
            )
        if row["dataset_stage"] != DATASET_STAGE:
            raise Stage2PlanError(
                "DATASET_STAGE_INVALID", str(row["dataset_stage"])
            )
        if row["session_id"] != f"{row['speaker_code']}_SESSION001":
            raise Stage2PlanError(
                "SESSION_ID_INVALID", str(row["session_id"])
            )
        if not CAPTURE_PATTERN.fullmatch(str(row["capture_group_id"])):
            raise Stage2PlanError(
                "CAPTURE_GROUP_ID_INVALID", str(row["capture_group_id"])
            )
        repetition = int(row["repetition_index"])
        if row["device_start_order"] != device_start_order(repetition):
            raise Stage2PlanError(
                "DEVICE_START_ORDER_INVALID", str(row["plan_id"])
            )
        if row["simultaneous_capture"] is not True:
            raise Stage2PlanError(
                "SIMULTANEOUS_CAPTURE_INVALID", str(row["plan_id"])
            )
        if row["consent_confirmed"] is not False:
            raise Stage2PlanError(
                "CONSENT_DEFAULT_INVALID", str(row["plan_id"])
            )
        if row["recording_status"] != "planned":
            raise Stage2PlanError(
                "RECORDING_STATUS_INVALID", str(row["plan_id"])
            )
        if not str(row["expected_original_filename"]).endswith(".m4a"):
            raise Stage2PlanError(
                "ORIGINAL_FILENAME_INVALID", str(row["plan_id"])
            )
        if not str(row["expected_analysis_wav_filename"]).endswith(".wav"):
            raise Stage2PlanError(
                "ANALYSIS_FILENAME_INVALID", str(row["plan_id"])
            )

    for field in (
        "plan_id",
        "sample_id",
        "expected_original_filename",
        "expected_analysis_wav_filename",
    ):
        _require_unique(rows, field)

    speaker_counts = Counter(row["speaker_code"] for row in rows)
    device_counts = Counter(row["device_code"] for row in rows)
    condition_counts = Counter(row["recording_condition"] for row in rows)
    if speaker_counts != Counter({speaker: 24 for speaker in SPEAKERS}):
        raise Stage2PlanError(
            "SPEAKER_DISTRIBUTION_INVALID", str(dict(speaker_counts))
        )
    if device_counts != Counter(
        {"DEV_PC_MIC_01": 48, "DEV_PHONE_01": 48}
    ):
        raise Stage2PlanError(
            "DEVICE_DISTRIBUTION_INVALID", str(dict(device_counts))
        )
    if condition_counts != Counter({"clean": 48, "natural": 48}):
        raise Stage2PlanError(
            "CONDITION_DISTRIBUTION_INVALID", str(dict(condition_counts))
        )

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_sample = {str(row["sample_id"]): row for row in rows}
    for row in rows:
        groups[str(row["capture_group_id"])].append(row)
    if len(groups) != 48:
        raise Stage2PlanError(
            "CAPTURE_COUNT_INVALID",
            f"Expected 48 captures, found {len(groups)}.",
        )
    speaker_capture_counts = Counter(
        group[0]["speaker_code"] for group in groups.values()
    )
    if speaker_capture_counts != Counter(
        {speaker: 12 for speaker in SPEAKERS}
    ):
        raise Stage2PlanError(
            "SPEAKER_CAPTURE_DISTRIBUTION_INVALID",
            str(dict(speaker_capture_counts)),
        )
    for capture, pair in groups.items():
        devices = {row["device_code"] for row in pair}
        if len(pair) != 2 or devices != set(DEVICES):
            raise Stage2PlanError("DEVICE_PAIR_INCOMPLETE", capture)
        for row in pair:
            paired = by_sample.get(str(row["paired_sample_id"]))
            if (
                paired is None
                or paired["paired_sample_id"] != row["sample_id"]
                or paired["capture_group_id"] != capture
                or paired["device_code"] == row["device_code"]
            ):
                raise Stage2PlanError(
                    "PAIRED_SAMPLE_LINK_INVALID", str(row["sample_id"])
                )

    return {
        "new_speaker_count": len(speaker_counts),
        "plan_row_count": len(rows),
        "capture_group_count": len(groups),
        "audio_file_count": len(rows),
        "device_counts": dict(device_counts),
        "condition_counts": dict(condition_counts),
        "speaker_file_counts": dict(speaker_counts),
        "speaker_capture_counts": dict(speaker_capture_counts),
        "complete_pair_count": len(groups),
        "missing_pair_count": 0,
        "sample_id_duplicate_count": 0,
        "filename_duplicate_count": 0,
        "prohibited_personal_field_count": 0,
        "development_pilot_row_count": 0,
        "dataset_role_counts": {DATASET_ROLE: len(rows)},
    }


def _atomic_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding=encoding, newline="\n") as stream:
            stream.write(text.rstrip() + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise Stage2PlanError(
            "OUTPUT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def write_csv_atomic(
    path: Path | str,
    rows: list[dict[str, Any]],
    fields: tuple[str, ...],
) -> None:
    output = Path(path)
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        field: (
                            str(row.get(field)).lower()
                            if isinstance(row.get(field), bool)
                            else row.get(field, "")
                        )
                        for field in fields
                    }
                )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    except (OSError, csv.Error) as exc:
        temporary.unlink(missing_ok=True)
        raise Stage2PlanError(
            "OUTPUT_WRITE_FAILED", f"{type(exc).__name__}: {exc}"
        ) from exc


def recording_guide(script_texts: dict[str, str]) -> str:
    return f"""# Stage 2 Recording Guide

이 문서는 SPK002~SPK005 held-out validation 수집을 위한 프로젝트 내부 가이드다.
녹음·변환·분석은 계획 생성 도구가 실행하지 않는다.

## 수집 구조

- 화자별 동시 발화 12회, PC·PHONE 파일 24개
- R01 PC_FIRST, R02 PHONE_FIRST, R03 PC_FIRST
- 버튼 순서만 교차하며 두 장치는 같은 발화를 동시에 녹음한다.
- 계획 거리 30 cm를 목표로 하되 강제하지 않는다. 실제 거리는 장치별로 반드시 기록한다.

## SCRIPT001 — {SCRIPT_TITLES['SCRIPT001']}

{script_texts['SCRIPT001']}

## SCRIPT002 — {SCRIPT_TITLES['SCRIPT002']}

{script_texts['SCRIPT002']}

## Clean

- 대본을 그대로 읽고 명확하게 발음한다.
- 속도나 억양을 의도적으로 과장하지 않는다.
- 오류가 나면 다시 녹음하되 실패 파일을 덮어쓰지 않고 제외 사유를 기록한다.

## Natural

- 단어와 순서를 가능한 유지하고 실제 면접 답변처럼 자연스럽게 말한다.
- 자연스러운 호흡과 짧은 멈춤을 허용한다.
- filler, 생략, 반복, 늘어짐을 의도적으로 만들지 않는다.
- 실제 발생한 현상은 녹음 후 post-capture note에 기록한다.

## Capture별 환경 기록

- PC·PHONE 동시 녹음 확인
- 입과 각 장치 사이 실제 거리
- 각 장치 방향과 위치
- 방 상태와 창문·선풍기·에어컨 등 배경 소음
- 알림음 또는 외부 발화
- 아는 범위에서 장치 자동 음량 조절·후처리 상태

## 파일

- 계획표의 sample_id, capture_group_id, paired_sample_id를 기준으로 연결한다.
- 파일 순서나 생성 시간으로 sample을 추론하지 않는다.
- 예상 원본은 `.m4a`, 분석용은 별도 `.wav`다.
- 장치가 다른 원본 형식을 생성하면 실제 확장자를 유지하고 기록을 갱신한다.
"""


DATASET_SPLIT_TEXT = """# Stage 2 Dataset Split

## 역할 분리

- SPK001은 `development_pilot`이며 독립 검증 표본이 아니다.
- SPK002~SPK005는 `held_out_validation` 신규 화자 검증에 사용한다.
- SPK001과 신규 화자를 같은 검증 역할로 합치지 않는다.

## 동결 및 비교 원칙

- SESSION001 결과를 보고 Stage 2 기준이나 임계값을 임의로 조정하지 않는다.
- 알고리즘 변경이 필요하면 변경 전 기준과 변경 후 결과를 모두 보존한다.
- Stage 2 성능은 전체 5명과 신규 4명 결과를 분리하여 보고한다.
- 화자별 결과를 숨기고 전체 중앙값만 제시하지 않는다.
- 실패 파일, 제외 파일과 제외 사유도 함께 기록한다.

## 보고 단위

- Development pilot: SPK001
- Held-out validation: SPK002, SPK003, SPK004, SPK005
- 전체 요약은 역할별·화자별 결과와 함께 제시할 때만 보조적으로 사용한다.
"""


CONSENT_TEXT = """# Stage 2 Consent and Privacy Checklist

이 문서는 법률 문서가 아니라 Face-Fit 프로젝트 내부 음성 수집 체크리스트다.
관련 법률·기관 정책 검토를 대체하지 않는다.

## 설명 및 동의

- [ ] 녹음 목적을 설명했다.
- [ ] 음성 분석 목적을 설명했다.
- [ ] 연구·개발용 사용 범위를 설명했다.
- [ ] 원본 저장 위치를 설명했다.
- [ ] 보관 기간을 설명했다.
- [ ] 삭제 요청 방법을 설명했다.
- [ ] 외부 공개 여부를 설명했다.
- [ ] 음성 복제 학습에는 사용하지 않음을 설명했다.
- [ ] 익명 speaker code를 사용한다.
- [ ] 동의하지 않은 파일은 분석 대상에서 제외한다.

## 개인정보 최소화

- 실명, 이메일, 전화번호, 생년월일, 주소를 계획 파일이나 파일명에 기록하지 않는다.
- 파일명에는 SPK002~SPK005 익명 코드만 사용한다.
- 동의 확인 전 `consent_confirmed`는 false로 유지한다.
- 철회 또는 제외 시 원본을 임의로 덮어쓰지 않고 프로젝트 절차에 따라 처리한다.
"""


def write_stage2_outputs(
    script_reference_path: Path | str,
    output_directory: Path | str,
) -> dict[str, Any]:
    scripts = load_script_references(script_reference_path)
    rows = generate_stage2_plan()
    validation = validate_stage2_plan(rows)
    checklist = generate_capture_checklist(rows)
    output = Path(output_directory)
    csv_path = output / "stage2_collection_plan.csv"
    json_path = output / "stage2_collection_plan.json"
    checklist_path = output / "stage2_capture_checklist.csv"
    guide_path = output / "STAGE2_RECORDING_GUIDE.md"
    split_path = output / "STAGE2_DATASET_SPLIT.md"
    consent_path = output / "STAGE2_CONSENT_AND_PRIVACY_CHECKLIST.md"
    write_csv_atomic(csv_path, rows, PLAN_FIELDS)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "dataset_stage": DATASET_STAGE,
        "description": (
            "Held-out Stage 2 multi-speaker simultaneous PC/PHONE "
            "collection plan. Planning only; no recording or analysis."
        ),
        "existing_development_pilot": {
            "speaker_code": "SPK001",
            "dataset_role": "development_pilot",
            "actual_utterance_count": 12,
            "audio_file_count": 24,
            "included_in_new_plan_rows": False,
        },
        "new_collection": {
            "speaker_codes": list(SPEAKERS),
            "dataset_role": DATASET_ROLE,
            "actual_utterance_count": 48,
            "audio_file_count": 96,
            "pc_file_count": 48,
            "phone_file_count": 48,
        },
        "combined_scope": {
            "speaker_count": 5,
            "actual_utterance_count": 60,
            "audio_file_count": 120,
        },
        "script_references": {
            script: {
                "title": SCRIPT_TITLES[script],
                "text": scripts[script],
            }
            for script in SCRIPTS
        },
        "fields": list(PLAN_FIELDS),
        "validation_summary": validation,
        "plan_rows": rows,
        "error": None,
    }
    _atomic_text(json_path, strict_json_text(payload))
    write_csv_atomic(
        checklist_path, checklist, CAPTURE_CHECKLIST_FIELDS
    )
    _atomic_text(guide_path, recording_guide(scripts))
    _atomic_text(split_path, DATASET_SPLIT_TEXT)
    _atomic_text(consent_path, CONSENT_TEXT)
    return {
        "output_directory": str(output),
        "created_files": [
            str(csv_path),
            str(json_path),
            str(checklist_path),
            str(guide_path),
            str(split_path),
            str(consent_path),
        ],
        "validation_summary": validation,
        "capture_checklist_row_count": len(checklist),
        "recording_or_analysis_executed": False,
        "error": None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script-references", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        result = write_stage2_outputs(
            args.script_references, args.output_dir
        )
    except Stage2PlanError as exc:
        print(strict_json_text({"error": {"code": exc.code, "detail": exc.detail}}))
        return 1
    except Exception as exc:
        print(
            strict_json_text(
                {
                    "error": {
                        "code": "STAGE2_PLAN_FAILED",
                        "detail": f"{type(exc).__name__}: {exc}",
                    }
                }
            )
        )
        return 1
    print(strict_json_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
