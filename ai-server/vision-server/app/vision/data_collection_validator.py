"""Stage 13 fixture loader and end-to-end metadata contract validator."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from app.vision.annotation_agreement import (
    calculate_presence_agreement,
    compare_event_sets,
)
from app.vision.annotation_metric_hypotheses import (
    AnnotationMetricHypothesis,
    validate_metric_hypotheses,
)
from app.vision.annotation_models import (
    AnnotationEvent,
    AnnotationLabelDefinition,
    AnnotationRater,
    AnnotationRubric,
    AnnotationSession,
)
from app.vision.annotation_registry import AnnotationRegistry
from app.vision.annotation_validator import validate_annotation_contract
from app.vision.consent_models import (
    ConsentPurpose,
    ConsentReference,
    evaluate_consent_gate,
)
from app.vision.data_collection_models import (
    AnswerSample,
    DataCollectionProtocol,
    RecordingEnvironment,
    RecordingSession,
    ResearchParticipant,
)
from app.vision.dataset_manifest_models import (
    DatasetManifest,
    DatasetSplitAssignment,
)
from app.vision.dataset_splitter import (
    assign_participant_splits,
    validate_split_leakage,
)
from app.vision.metric_registry import build_stage10_metric_registry


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_DIRECTORY = ROOT / "config" / "data_collection" / "fixtures"
DEFAULT_OUTPUT_ROOT = (
    ROOT / "data" / "output"
    / "data_collection_annotation_contract_validation"
)
TECHNICAL_JUDGMENT = (
    "data_collection_annotation_contract_smoke_completed_with_metadata_fixtures"
)
FORBIDDEN_OUTPUT_FIELDS = frozenset(
    {
        "score",
        "posture_score",
        "interview_score",
        "grade",
        "pass",
        "fail",
        "hirability",
        "anxiety",
        "attention",
        "personality",
        "mental_health",
        "diagnosis",
        "threshold",
    }
)


class DataCollectionValidationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def dumps_strict(value: Any, *, indent: int | None = None) -> str:
    validate_no_forbidden_output_fields(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        indent=indent,
        sort_keys=True,
        separators=(",", ":") if indent is None else None,
    )


def load_strict_json(path: str | Path) -> Any:
    resolved = Path(path)
    try:
        return json.loads(
            resolved.read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(value)
            ),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise DataCollectionValidationError(
            "INVALID_STRICT_JSON", f"{resolved.name}: {exc}"
        ) from exc


def load_strict_jsonl(path: str | Path) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    raise ValueError(f"blank line at {line_number}")
                value = json.loads(
                    line,
                    parse_constant=lambda constant: (_ for _ in ()).throw(
                        ValueError(constant)
                    ),
                )
                if not isinstance(value, dict):
                    raise ValueError(f"non-object line at {line_number}")
                rows.append(value)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise DataCollectionValidationError(
            "INVALID_STRICT_JSONL", str(exc)
        ) from exc
    return tuple(rows)


def validate_no_forbidden_output_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_OUTPUT_FIELDS:
                raise ValueError(f"forbidden output field: {key}")
            validate_no_forbidden_output_fields(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            validate_no_forbidden_output_fields(item)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _items(payload: Any, key: str) -> list[dict[str, Any]]:
    values = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(values, list) or not all(
        isinstance(item, dict) for item in values
    ):
        raise DataCollectionValidationError(
            "INVALID_FIXTURE_COLLECTION", f"Expected object list: {key}"
        )
    return values


def _tuple_fields(payload: dict[str, Any], fields: Iterable[str]) -> dict[str, Any]:
    result = dict(payload)
    for field in fields:
        result[field] = tuple(result.get(field) or ())
    return result


class DataCollectionFixtureRegistry:
    REQUIRED_FILES = (
        "protocol_registry.json",
        "consents.json",
        "recording_registry.json",
        "annotation_registry.json",
        "annotation_events.json",
        "annotation_metric_hypotheses.json",
        "dataset_manifest.json",
        "split_assignments.json",
    )

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory).resolve()
        missing = [
            name for name in self.REQUIRED_FILES
            if not (self.directory / name).is_file()
        ]
        if missing:
            raise DataCollectionValidationError(
                "FIXTURE_FILE_MISSING", ", ".join(missing)
            )
        try:
            protocol_data = load_strict_json(
                self.directory / "protocol_registry.json"
            )
            consent_data = load_strict_json(self.directory / "consents.json")
            recording_data = load_strict_json(
                self.directory / "recording_registry.json"
            )
            annotation_data = load_strict_json(
                self.directory / "annotation_registry.json"
            )
            event_data = load_strict_json(
                self.directory / "annotation_events.json"
            )
            hypothesis_data = load_strict_json(
                self.directory / "annotation_metric_hypotheses.json"
            )
            manifest_data = load_strict_json(
                self.directory / "dataset_manifest.json"
            )
            split_data = load_strict_json(
                self.directory / "split_assignments.json"
            )
            self.protocols = tuple(
                DataCollectionProtocol(
                    **_tuple_fields(
                        item, ("body_regions", "prohibited_body_regions")
                    )
                )
                for item in _items(protocol_data, "protocols")
            )
            self.participants = tuple(
                ResearchParticipant(**item)
                for item in _items(protocol_data, "participants")
            )
            self.consents = tuple(
                ConsentReference(**item)
                for item in _items(consent_data, "consents")
            )
            self.environments = tuple(
                RecordingEnvironment(**item)
                for item in _items(recording_data, "environments")
            )
            self.recording_sessions = tuple(
                RecordingSession(**item)
                for item in _items(recording_data, "sessions")
            )
            self.answers = tuple(
                AnswerSample(**item)
                for item in _items(recording_data, "answers")
            )
            labels = tuple(
                AnnotationLabelDefinition(
                    **_tuple_fields(item, ("allowed_directions",))
                )
                for item in _items(annotation_data, "labels")
            )
            rubrics = tuple(
                AnnotationRubric(**_tuple_fields(item, ("label_ids",)))
                for item in _items(annotation_data, "rubrics")
            )
            self.annotation_registry = AnnotationRegistry(labels, rubrics)
            self.raters = tuple(
                AnnotationRater(**item)
                for item in _items(annotation_data, "raters")
            )
            self.annotation_sessions = tuple(
                AnnotationSession(**item)
                for item in _items(annotation_data, "annotation_sessions")
            )
            self.events = tuple(
                AnnotationEvent(**item)
                for item in _items(event_data, "events")
            )
            self.hypotheses = tuple(
                AnnotationMetricHypothesis(
                    **_tuple_fields(item, ("limitations",))
                )
                for item in _items(hypothesis_data, "hypotheses")
            )
            manifest_payload = dict(manifest_data["manifest"])
            manifest_payload = _tuple_fields(
                manifest_payload,
                ("participant_ids", "session_ids", "answer_ids"),
            )
            self.manifest = DatasetManifest(**manifest_payload)
            self.split_assignments = tuple(
                DatasetSplitAssignment(**item)
                for item in _items(split_data, "assignments")
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DataCollectionValidationError(
                "FIXTURE_MODEL_VALIDATION_FAILED", str(exc)
            ) from exc

    def validate(self) -> dict[str, int | bool]:
        protocols = {item.protocol_id: item for item in self.protocols}
        participants = {
            item.participant_id: item for item in self.participants
        }
        consents = {
            item.consent_reference_id: item for item in self.consents
        }
        environments = {
            item.environment_id: item for item in self.environments
        }
        sessions = {
            item.session_id: item for item in self.recording_sessions
        }
        collections = (
            (protocols, self.protocols, "protocol"),
            (participants, self.participants, "participant"),
            (consents, self.consents, "consent"),
            (environments, self.environments, "environment"),
            (sessions, self.recording_sessions, "session"),
        )
        for mapping, items, name in collections:
            if len(mapping) != len(items):
                raise ValueError(f"duplicate {name} identifier")
        for participant in self.participants:
            consent = consents.get(participant.consent_reference_id)
            if consent is None or consent.participant_id != participant.participant_id:
                raise ValueError("participant consent reference mismatch")
        for session in self.recording_sessions:
            if session.participant_id not in participants:
                raise ValueError("session references unknown participant")
            if session.protocol_id not in protocols:
                raise ValueError("session references unknown protocol")
            if session.environment_id not in environments:
                raise ValueError("session references unknown environment")
            consent = consents.get(session.consent_reference_id)
            if consent is None or consent.participant_id != session.participant_id:
                raise ValueError("session consent reference mismatch")
            for purpose in ConsentPurpose:
                gate = evaluate_consent_gate(consent, purpose.value)
                if not gate.allowed:
                    raise ValueError(
                        f"session consent gate denied: {gate.reason}"
                    )
        answer_ids: set[str] = set()
        by_session: dict[str, list[AnswerSample]] = {}
        for answer in self.answers:
            if answer.answer_id in answer_ids:
                raise ValueError("duplicate answer_id")
            answer_ids.add(answer.answer_id)
            session = sessions.get(answer.session_id)
            if session is None:
                raise ValueError("answer references unknown session")
            if answer.end_timestamp_ms > session.duration_ms:
                raise ValueError("answer exceeds session duration")
            by_session.setdefault(answer.session_id, []).append(answer)
        for values in by_session.values():
            ordered = sorted(values, key=lambda item: item.start_timestamp_ms)
            if any(
                left.end_timestamp_ms > right.start_timestamp_ms
                for left, right in zip(ordered, ordered[1:])
            ):
                raise ValueError("overlapping AnswerSample intervals")
        validate_annotation_contract(
            registry=self.annotation_registry,
            answers=self.answers,
            raters=self.raters,
            sessions=self.annotation_sessions,
            events=self.events,
        )
        validate_metric_hypotheses(
            self.hypotheses,
            annotation_registry=self.annotation_registry,
            metric_registry=build_stage10_metric_registry(),
        )
        if set(self.manifest.participant_ids) != set(participants):
            raise ValueError("manifest participant references mismatch")
        if set(self.manifest.session_ids) != set(sessions):
            raise ValueError("manifest session references mismatch")
        if set(self.manifest.answer_ids) != answer_ids:
            raise ValueError("manifest answer references mismatch")
        leakage = validate_split_leakage(
            self.split_assignments,
            self.recording_sessions,
            self.answers,
        )
        seeds = {item.seed for item in self.split_assignments}
        if len(seeds) != 1:
            raise ValueError("split assignments must share one fixed seed")
        expected = assign_participant_splits(
            participants, seed=next(iter(seeds))
        )
        if self.split_assignments != expected:
            raise ValueError(
                "fixture split assignments are not deterministic for the seed"
            )
        return leakage


def _write_json(path: Path, value: Any) -> None:
    path.write_text(dumps_strict(value, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(dumps_strict(row))
            stream.write("\n")


def _markdown(report: dict[str, Any]) -> str:
    counts = report["fixture_counts"]
    agreement = report["agreement_summary"]
    return "\n".join(
        (
            "# Stage 13 data collection and annotation contract validation",
            "",
            f"- Technical judgment: `{report['technical_judgment']}`",
            f"- Participants / sessions / answers: "
            f"{counts['participant_count']} / {counts['session_count']} / "
            f"{counts['answer_count']}",
            f"- Original raters: {counts['independent_rater_count']}",
            f"- Original / adjudicated events: "
            f"{counts['original_event_count']} / "
            f"{counts['adjudicated_event_count']}",
            f"- Matched event pairs: {agreement['matched_event_count']}",
            f"- Observed agreement: {agreement['observed_agreement']}",
            f"- Cohen's kappa: {agreement['cohen_kappa']}",
            f"- Split leakage detected: "
            f"{str(report['split_validation']['leakage_detected']).lower()}",
            "",
            "This smoke test uses synthetic metadata fixtures only. It does not "
            "collect people, contain media or direct identifiers, infer traits, "
            "approve thresholds, produce interview/posture scores, or train a model.",
            "",
        )
    )


class DataCollectionAnnotationContractValidator:
    OUTPUT_NAMES = (
        "validation_report.json",
        "validation_report.md",
        "loaded_protocol_registry.json",
        "loaded_annotation_registry.json",
        "fixture_annotation_events.jsonl",
        "fixture_agreement_results.json",
        "fixture_dataset_manifest.json",
        "fixture_split_assignments.json",
        "fixture_annotation_metric_hypotheses.json",
    )

    def validate(
        self,
        *,
        fixture_directory: str | Path = DEFAULT_FIXTURE_DIRECTORY,
        output_root: str | Path = DEFAULT_OUTPUT_ROOT,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        registry = DataCollectionFixtureRegistry(fixture_directory)
        try:
            split_validation = registry.validate()
        except ValueError as exc:
            raise DataCollectionValidationError(
                "CONTRACT_VALIDATION_FAILED", str(exc)
            ) from exc
        destination = Path(output_root).resolve()
        if destination.exists() and not overwrite:
            raise DataCollectionValidationError(
                "OUTPUT_ALREADY_EXISTS", str(destination)
            )

        original_layers = {"RATER_A_ORIGINAL", "RATER_B_ORIGINAL"}
        a_events = tuple(
            event for event in registry.events
            if event.layer == "RATER_A_ORIGINAL"
        )
        b_events = tuple(
            event for event in registry.events
            if event.layer == "RATER_B_ORIGINAL"
        )
        event_agreements = compare_event_sets(a_events, b_events)
        keys = [
            (answer.answer_id, label.label_id)
            for answer in registry.answers
            for label in registry.annotation_registry.labels
        ]
        a_presence = {
            (event.answer_id, event.label_id) for event in a_events
        }
        b_presence = {
            (event.answer_id, event.label_id) for event in b_events
        }
        presence = calculate_presence_agreement(
            (key in a_presence for key in keys),
            (key in b_presence for key in keys),
        )
        agreement_payload = {
            "schema_version": "1.0",
            "approval_cutoff_defined": False,
            "kappa_interpretation": None,
            "event_agreements": [
                item.to_dict() for item in event_agreements
            ],
            "presence_agreement": presence.to_dict(),
        }
        report = {
            "schema_version": "1.0",
            "validation_type": (
                "data_collection_annotation_contract_metadata_fixture_smoke"
            ),
            "status": "completed",
            "technical_judgment": TECHNICAL_JUDGMENT,
            "fixture_directory": str(Path(fixture_directory).resolve()),
            "metadata_fixtures_only": True,
            "real_people_or_media_collected": False,
            "direct_identifiers_present": False,
            "trait_inference_performed": False,
            "production_threshold_approved": False,
            "model_training_performed": False,
            "fixture_counts": {
                "protocol_count": len(registry.protocols),
                "participant_count": len(registry.participants),
                "consent_count": len(registry.consents),
                "environment_count": len(registry.environments),
                "session_count": len(registry.recording_sessions),
                "answer_count": len(registry.answers),
                "label_count": len(registry.annotation_registry.labels),
                "rubric_count": len(registry.annotation_registry.rubrics),
                "rater_count": len(registry.raters),
                "independent_rater_count": sum(
                    item.role == "INDEPENDENT_RATER"
                    for item in registry.raters
                ),
                "original_event_count": sum(
                    item.layer in original_layers for item in registry.events
                ),
                "adjudicated_event_count": sum(
                    item.layer == "ADJUDICATED_RESULT"
                    for item in registry.events
                ),
                "hypothesis_count": len(registry.hypotheses),
            },
            "agreement_summary": {
                "matched_event_count": sum(
                    item.match_status == "MATCHED"
                    for item in event_agreements
                ),
                "no_overlap_event_count": sum(
                    item.match_status == "NO_OVERLAP"
                    for item in event_agreements
                ),
                "missing_counterpart_count": sum(
                    item.match_status.startswith("MISSING_")
                    for item in event_agreements
                ),
                "observed_agreement": presence.observed_agreement,
                "positive_agreement": presence.positive_agreement,
                "negative_agreement": presence.negative_agreement,
                "cohen_kappa": presence.cohen_kappa,
            },
            "split_validation": split_validation,
            "outputs": list(self.OUTPUT_NAMES),
            "limitations": [
                "All records are synthetic metadata fixtures.",
                "Agreement values validate arithmetic and serialization only.",
                "Hypotheses are non-approved proxies referencing existing metrics.",
                "No production split ratio is defined.",
            ],
        }

        destination.parent.mkdir(parents=True, exist_ok=True)
        staged = Path(
            tempfile.mkdtemp(prefix=".stage13.", dir=destination.parent)
        )
        try:
            _write_json(
                staged / "loaded_protocol_registry.json",
                {
                    "schema_version": "1.0",
                    "protocols": [item.to_dict() for item in registry.protocols],
                    "participants": [
                        item.to_dict() for item in registry.participants
                    ],
                    "consents": [item.to_dict() for item in registry.consents],
                    "environments": [
                        item.to_dict() for item in registry.environments
                    ],
                    "sessions": [
                        item.to_dict() for item in registry.recording_sessions
                    ],
                    "answers": [item.to_dict() for item in registry.answers],
                },
            )
            annotation_payload = registry.annotation_registry.to_dict()
            annotation_payload["raters"] = [
                item.to_dict() for item in registry.raters
            ]
            annotation_payload["annotation_sessions"] = [
                item.to_dict() for item in registry.annotation_sessions
            ]
            _write_json(
                staged / "loaded_annotation_registry.json",
                annotation_payload,
            )
            _write_jsonl(
                staged / "fixture_annotation_events.jsonl",
                (item.to_dict() for item in registry.events),
            )
            _write_json(
                staged / "fixture_agreement_results.json",
                agreement_payload,
            )
            _write_json(
                staged / "fixture_dataset_manifest.json",
                {"schema_version": "1.0", "manifest": registry.manifest.to_dict()},
            )
            _write_json(
                staged / "fixture_split_assignments.json",
                {
                    "schema_version": "1.0",
                    "assignments": [
                        item.to_dict() for item in registry.split_assignments
                    ],
                    "leakage_validation": split_validation,
                    "production_ratio_defined": False,
                },
            )
            _write_json(
                staged / "fixture_annotation_metric_hypotheses.json",
                {
                    "schema_version": "1.0",
                    "hypotheses": [
                        item.to_dict() for item in registry.hypotheses
                    ],
                    "approved_hypothesis_count": 0,
                },
            )
            _write_json(staged / "validation_report.json", report)
            (staged / "validation_report.md").write_text(
                _markdown(report), encoding="utf-8"
            )
            if destination.exists():
                destination.mkdir(parents=True, exist_ok=True)
                for source in staged.iterdir():
                    os.replace(source, destination / source.name)
                staged.rmdir()
            else:
                os.replace(staged, destination)
            hashes = {
                name: sha256_file(destination / name)
                for name in self.OUTPUT_NAMES
            }
            result = dict(report)
            result["output_sha256"] = dict(sorted(hashes.items()))
            return result
        finally:
            if staged.exists():
                for path in staged.iterdir():
                    path.unlink()
                staged.rmdir()
