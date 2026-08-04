from __future__ import annotations

from array import array
import contextlib
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import wave

import numpy as np


ANALYSIS_ROOT = Path(__file__).resolve().parents[1]
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))
SCRIPTS_ROOT = ANALYSIS_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from app.audio.audio_manifest_writer import strict_json_bytes, write_json_atomic  # noqa: E402
from app.audio.interval_audio_extractor import sha256_file  # noqa: E402
from app.speech.filler_candidate_analyzer import (  # noqa: E402
    analyze_filler_candidates,
    normalize_candidate,
)
from app.speech.pause_analyzer import analyze_timestamp_pauses  # noqa: E402
from app.speech.pitch_analyzer import analyze_pitch  # noqa: E402
from app.speech.speaking_rate_analyzer import analyze_speaking_rate  # noqa: E402
from app.speech.speech_analysis_service import (  # noqa: E402
    SpeechAnalysisError,
    SpeechAnalysisService,
    resolve_speech_session_input,
)
from app.speech.speech_contracts import (  # noqa: E402
    DEFAULT_PROFILE,
    SpeechAnswerInput,
    SpeechSessionInput,
    resolve_profile,
)
from app.speech.speech_metrics import load_pcm16_mono_wav  # noqa: E402
from app.speech.volume_analyzer import analyze_volume_and_silence  # noqa: E402
import analyze_speech_session as cli  # noqa: E402


def write_wav(
    path: Path,
    *,
    duration_ms: int = 1000,
    frequency: float = 200.0,
    amplitude: float = 0.5,
    silent_after_ms: int | None = None,
) -> None:
    sample_count = 16_000 * duration_ms // 1000
    values = array("h")
    for index in range(sample_count):
        if silent_after_ms is not None and index >= 16_000 * silent_after_ms // 1000:
            value = 0
        else:
            value = int(32767 * amplitude * math.sin(2 * math.pi * frequency * index / 16_000))
        values.append(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16_000)
        stream.writeframes(values.tobytes())


def make_words(start_session_ms: int = 2000) -> list[dict[str, object]]:
    return [
        {
            "wordId": "WRD_000001", "segmentId": "SEG_000001",
            "startMsRelative": 100, "endMsRelative": 300,
            "startMsSession": start_session_ms + 100,
            "endMsSession": start_session_ms + 300,
            "text": " 음,", "probability": 0.9,
        },
        {
            "wordId": "WRD_000002", "segmentId": "SEG_000001",
            "startMsRelative": 600, "endMsRelative": 900,
            "startMsSession": start_session_ms + 600,
            "endMsSession": start_session_ms + 900,
            "text": " 답변", "probability": 0.95,
        },
    ]


def make_transcript(answer_id: str = "ANS_000001", start_ms: int = 2000) -> dict[str, object]:
    words = make_words(start_ms)
    return {
        "sessionId": "SES_000001", "answerId": answer_id,
        "status": "COMPLETE", "audio": {"durationMs": 1000, "sampleCount": 16000,
                                             "sha256": "a" * 64},
        "answerInterval": {"startMs": start_ms, "endMs": start_ms + 1000},
        "text": " 음, 답변", "segments": [{
            "segmentId": "SEG_000001", "startMsRelative": 100, "endMsRelative": 900,
            "startMsSession": start_ms + 100, "endMsSession": start_ms + 900,
            "text": " 음, 답변", "wordCount": 2,
        }],
        "words": words, "warnings": [], "errors": [],
    }


class FakePitchAdapter:
    fail = False

    def estimate(self, _audio, _profile, _threshold):
        if type(self).fail:
            raise RuntimeError("pitch failed")
        return [190.0, None, 210.0, 200.0], 4


class PureAnalyzerTests(unittest.TestCase):
    def test_profile_is_measurement_only_and_has_no_approved_scoring(self) -> None:
        public = resolve_profile().public_dict()
        self.assertEqual(public["analysisMode"], "MEASUREMENT_ONLY")
        self.assertEqual(public["thresholdPurpose"], "TECHNICAL_VIEW_ONLY")
        self.assertFalse(public["scoringApproved"])
        self.assertEqual(public["pauseViewThresholdsMs"], [250, 500, 1000, 2000])

    def test_speaking_rate_and_articulation_use_distinct_durations(self) -> None:
        transcript = make_transcript()
        result, warnings = analyze_speaking_rate(transcript, 1000)
        self.assertEqual(result["wordCount"], 2)
        self.assertEqual(result["wordsPerMinute"], 120.0)
        self.assertEqual(result["detectedSpeechDurationMs"], 500)
        self.assertEqual(result["articulationWordsPerMinute"], 240.0)
        self.assertEqual(warnings, [])

    def test_empty_transcript_has_null_articulation_rate(self) -> None:
        result, warnings = analyze_speaking_rate({"text": "", "words": [], "segments": []}, 1000)
        self.assertIsNone(result["articulationWordsPerMinute"])
        self.assertIn("EMPTY_TRANSCRIPT", warnings)
        self.assertIn("WORD_TIMESTAMPS_UNAVAILABLE", warnings)

    def test_leading_trailing_positive_and_overlapping_word_gaps(self) -> None:
        words = [
            {"startMsRelative": 100, "endMsRelative": 300},
            {"startMsRelative": 250, "endMsRelative": 400},
            {"startMsRelative": 650, "endMsRelative": 800},
        ]
        result, warnings = analyze_timestamp_pauses(words, 1000, (250, 500, 1000, 2000))
        self.assertEqual(result["leadingGapMs"], 100)
        self.assertEqual(result["trailingGapMs"], 200)
        self.assertEqual(result["totalInterWordGapMs"], 250)
        self.assertEqual(result["overlappingWordPairCount"], 1)
        self.assertEqual(result["pauseCandidateViews"][0]["count"], 1)
        self.assertEqual(result["pauseCandidateViews"][1]["count"], 0)
        self.assertIn("OVERLAPPING_WORD_TIMESTAMPS", warnings)

    def test_no_words_does_not_invent_gap_values(self) -> None:
        result, warnings = analyze_timestamp_pauses([], 1000, (250, 500, 1000, 2000))
        self.assertIsNone(result["leadingGapMs"])
        self.assertIsNone(result["medianInterWordGapMs"])
        self.assertIn("WORD_TIMESTAMPS_UNAVAILABLE", warnings)

    def test_gap_summary_uses_positive_gaps_and_linear_p90(self) -> None:
        words = [
            {"startMsRelative": 0, "endMsRelative": 100},
            {"startMsRelative": 350, "endMsRelative": 450},
            {"startMsRelative": 950, "endMsRelative": 1000},
        ]
        result, _warnings = analyze_timestamp_pauses(words, 1000, (250, 500, 1000, 2000))
        self.assertEqual(result["meanInterWordGapMs"], 375)
        self.assertEqual(result["medianInterWordGapMs"], 375)
        self.assertEqual(result["maxInterWordGapMs"], 500)
        self.assertEqual(result["p90InterWordGapMs"], 475)

    def test_filler_candidate_is_normalized_but_not_definitively_classified(self) -> None:
        candidates, summary, warnings = analyze_filler_candidates(
            make_words(), 1000, DEFAULT_PROFILE
        )
        self.assertEqual(normalize_candidate(" 음,"), "음")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["candidateType"], "FILLER_CANDIDATE")
        self.assertTrue(candidates[0]["reviewRequired"])
        self.assertEqual(summary["classification"], "CANDIDATE_ONLY")
        self.assertIn("FILLER_CANDIDATE_REVIEW_REQUIRED", warnings)

    def test_lexicon_does_not_match_unlisted_content_word(self) -> None:
        words = [dict(make_words()[1])]
        candidates, summary, warnings = analyze_filler_candidates(
            words, 1000, DEFAULT_PROFILE
        )
        self.assertEqual(candidates, [])
        self.assertEqual(summary["fillerCandidateCount"], 0)
        self.assertEqual(warnings, [])


class AcousticAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_volume_rms_peak_and_silence_regions_from_pcm(self) -> None:
        path = self.root / "half-silent.wav"
        write_wav(path, silent_after_ms=500)
        volume, silence, warnings = analyze_volume_and_silence(
            load_pcm16_mono_wav(path), DEFAULT_PROFILE
        )
        self.assertAlmostEqual(volume["peakAmplitude"], 0.5, places=2)
        self.assertAlmostEqual(volume["rmsAmplitude"], 0.25, places=2)
        self.assertEqual(volume["clippingSampleCount"], 0)
        self.assertGreater(silence["candidateSilentFrameRatio"], 0.4)
        self.assertGreaterEqual(silence["candidateSilenceRegionCount"], 1)
        self.assertEqual(warnings, [])

    def test_clipping_and_zero_sample_ratios(self) -> None:
        path = self.root / "clipped.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16_000)
            stream.writeframes(array("h", [32767, -32768, 0, 0] * 100).tobytes())
        volume, _silence, warnings = analyze_volume_and_silence(
            load_pcm16_mono_wav(path), DEFAULT_PROFILE
        )
        self.assertEqual(volume["clippingSampleCount"], 200)
        self.assertEqual(volume["clippingSampleRatio"], 0.5)
        self.assertEqual(volume["zeroSampleRatio"], 0.5)
        self.assertIn("CLIPPING_CANDIDATE", warnings)

    def test_fully_silent_audio_uses_null_dbfs_not_infinity(self) -> None:
        path = self.root / "silent.wav"
        write_wav(path, amplitude=0)
        volume, _silence, warnings = analyze_volume_and_silence(
            load_pcm16_mono_wav(path), DEFAULT_PROFILE
        )
        self.assertIsNone(volume["rmsDbfs"])
        self.assertIsNone(volume["peakDbfs"])
        self.assertIn("AUDIO_NEAR_SILENT_CANDIDATE", warnings)
        strict_json_bytes(volume)

    def test_injected_pitch_adapter_excludes_unvoiced_frames(self) -> None:
        path = self.root / "tone.wav"
        write_wav(path)
        result, warnings = analyze_pitch(
            load_pcm16_mono_wav(path), DEFAULT_PROFILE, -60.0,
            adapter=FakePitchAdapter(),
        )
        self.assertEqual(result["voicedFrameCount"], 3)
        self.assertEqual(result["totalFrameCount"], 4)
        self.assertEqual(result["medianF0Hz"], 200.0)
        self.assertEqual(result["f0RangeHz"], 20.0)
        self.assertLess(result["p10P90RangeHz"], result["f0RangeHz"])
        self.assertEqual(result["unvoicedFrameRepresentation"], "EXCLUDED_NOT_ZERO")
        self.assertIn("INSUFFICIENT_VOICED_FRAMES", warnings)

    def test_default_pitch_adapter_measures_clean_200hz_tone(self) -> None:
        path = self.root / "tone.wav"
        write_wav(path, duration_ms=500, frequency=200.0)
        result, warnings = analyze_pitch(
            load_pcm16_mono_wav(path), DEFAULT_PROFILE, -60.0
        )
        self.assertGreater(result["voicedFrameCount"], 10)
        self.assertAlmostEqual(result["medianF0Hz"], 200.0, delta=3.0)
        self.assertNotIn("PITCH_UNAVAILABLE", warnings)

    def test_silent_audio_has_no_zero_hz_pitch_substitution(self) -> None:
        path = self.root / "silent-pitch.wav"
        write_wav(path, amplitude=0)
        result, warnings = analyze_pitch(
            load_pcm16_mono_wav(path), DEFAULT_PROFILE, -60.0
        )
        self.assertEqual(result["voicedFrameCount"], 0)
        self.assertIsNone(result["medianF0Hz"])
        self.assertIn("PITCH_UNAVAILABLE", warnings)


class ResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.pre = self.root / "pre"
        self.stt = self.root / "stt"
        session_pre = self.pre / "SES_000001"
        session_stt = self.stt / "SES_000001"
        audio_rows = []
        transcript_rows = []
        for index in range(1, 5):
            answer_id = f"ANS_{index:06d}"
            start_ms = index * 2000
            audio_path = session_pre / "intervals" / f"{answer_id}.wav"
            write_wav(audio_path)
            audio_sha = sha256_file(audio_path)
            audio_rows.append({
                "intervalType": "ANSWER", "answerId": answer_id,
                "startMs": start_ms, "endMs": start_ms + 1000,
                "actualDurationMs": 1000, "sampleCount": 16000,
                "audio": {"sha256": audio_sha},
            })
            transcript = make_transcript(answer_id, start_ms)
            transcript["audio"]["sha256"] = audio_sha
            transcript_path = session_stt / "answers" / f"{answer_id}.json"
            write_json_atomic(transcript_path, transcript)
            transcript_rows.append({
                "answerId": answer_id, "inputAudioSha256": audio_sha,
                "outputSha256": sha256_file(transcript_path),
            })
        write_json_atomic(session_pre / "interval_audio_manifest.json", {
            "sessionId": "SES_000001", "status": "stt_audio_preprocessing_ready",
            "intervals": audio_rows,
        })
        write_json_atomic(session_stt / "session_transcription_manifest.json", {
            "sessionId": "SES_000001", "status": "stt_session_transcription_ready",
            "answers": transcript_rows, "warnings": [],
        })

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def resolve(self):
        return resolve_speech_session_input(
            "SES_000001", preprocessing_root=self.pre, transcription_root=self.stt
        )

    def test_resolves_four_matching_audio_and_transcript_inputs(self) -> None:
        source = self.resolve()
        self.assertEqual([row.answer_id for row in source.answers],
                         [f"ANS_{index:06d}" for index in range(1, 5)])

    def test_audio_sha_mismatch_is_rejected_without_regeneration(self) -> None:
        target = self.pre / "SES_000001" / "intervals" / "ANS_000001.wav"
        target.write_bytes(b"corrupt")
        with self.assertRaises(SpeechAnalysisError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "AUDIO_INPUT_SHA_MISMATCH")

    def test_transcript_sha_mismatch_is_rejected(self) -> None:
        target = self.stt / "SES_000001" / "answers" / "ANS_000001.json"
        target.write_text("{}", encoding="utf-8")
        with self.assertRaises(SpeechAnalysisError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "TRANSCRIPT_INPUT_SHA_MISMATCH")

    def test_answer_set_mismatch_is_rejected(self) -> None:
        path = self.stt / "SES_000001" / "session_transcription_manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["answers"] = list(reversed(manifest["answers"]))
        write_json_atomic(path, manifest)
        with self.assertRaises(SpeechAnalysisError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "ANSWER_SET_MISMATCH")

    def test_stage24_not_ready_is_rejected(self) -> None:
        path = self.pre / "SES_000001" / "interval_audio_manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["status"] = "failed"
        write_json_atomic(path, manifest)
        with self.assertRaises(SpeechAnalysisError) as caught:
            self.resolve()
        self.assertEqual(caught.exception.code, "AUDIO_PREPROCESSING_NOT_READY")

    def test_invalid_session_id_is_rejected(self) -> None:
        with self.assertRaises(SpeechAnalysisError) as caught:
            resolve_speech_session_input("../SES_000001", preprocessing_root=self.pre,
                                         transcription_root=self.stt)
        self.assertEqual(caught.exception.code, "INVALID_SESSION_ID")


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        answers = []
        for index in range(1, 5):
            answer_id = f"ANS_{index:06d}"
            start_ms = index * 2000
            path = self.root / f"{answer_id}.wav"
            write_wav(path)
            transcript = make_transcript(answer_id, start_ms)
            audio_sha = sha256_file(path)
            transcript["audio"]["sha256"] = audio_sha
            answers.append(SpeechAnswerInput(
                session_id="SES_000001", answer_id=answer_id,
                audio_path=path, transcript_path=self.root / f"{answer_id}.json",
                audio_sha256=audio_sha, transcript_sha256=f"{index:064x}",
                start_ms=start_ms, end_ms=start_ms + 1000, duration_ms=1000,
                sample_count=16000, transcript=transcript,
            ))
        self.source = SpeechSessionInput(
            session_id="SES_000001", stage24_manifest_sha256="1" * 64,
            stage25_manifest_sha256="2" * 64,
            stage24_status="stt_audio_preprocessing_ready",
            stage25_status="stt_session_transcription_ready_with_warnings",
            stage25_warnings=("SEGMENT_BOUNDARY_EXPANDED_TO_WORDS",),
            answers=tuple(answers),
        )
        self.output = self.root / "output"
        FakePitchAdapter.fail = False
        self.service = SpeechAnalysisService(
            profile=DEFAULT_PROFILE, output_root=self.output,
            resolver=lambda _session_id, **_kwargs: self.source,
            pitch_adapter=FakePitchAdapter(),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_pipeline_writes_required_tree_and_measurement_contract(self) -> None:
        result = self.service.run("SES_000001")
        self.assertEqual(result["status"], "speech_characteristics_ready_with_warnings")
        root = self.output / "SES_000001"
        expected = [*(f"answers/ANS_{index:06d}.json" for index in range(1, 5)),
                    "session_speech_manifest.json", "speech_validation.json",
                    "speech_review.md", "speech_report.md"]
        self.assertTrue(all((root / item).is_file() for item in expected))
        answer = json.loads((root / expected[0]).read_text(encoding="utf-8"))
        self.assertFalse(answer["scoringAvailable"])
        self.assertIn("speakingRate", answer)
        self.assertIn("timestampPauses", answer)
        self.assertIn("acousticSilence", answer)
        self.assertIn("fillerCandidates", answer)
        self.assertIn("volume", answer)
        self.assertIn("pitch", answer)

    def test_no_forbidden_scores_paths_or_participant_ids_are_emitted(self) -> None:
        self.service.run("SES_000001")
        root = self.output / "SES_000001"
        forbidden = ["voiceScore", "speakingScore", "confidenceScore", "interviewScore",
                     "passProbability", "PTC_", str(self.root)]
        for path in root.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                for value in forbidden:
                    self.assertNotIn(value, text)

    def test_strict_json_has_no_nan_or_infinity(self) -> None:
        self.service.run("SES_000001")
        for path in (self.output / "SES_000001").rglob("*.json"):
            json.loads(path.read_text(encoding="utf-8"),
                       parse_constant=lambda value: self.fail(value))

    def test_identical_input_is_reused(self) -> None:
        self.assertFalse(self.service.run("SES_000001")["reused"])
        self.assertTrue(self.service.run("SES_000001")["reused"])

    def test_force_rebuild_runs_again(self) -> None:
        self.service.run("SES_000001")
        self.assertFalse(self.service.run("SES_000001", force_rebuild=True)["reused"])

    def test_corrupted_answer_or_artifact_rebuilds(self) -> None:
        self.service.run("SES_000001")
        answer = self.output / "SES_000001" / "answers" / "ANS_000001.json"
        answer.write_text("{}", encoding="utf-8")
        self.assertFalse(self.service.run("SES_000001")["reused"])
        validation = self.output / "SES_000001" / "speech_validation.json"
        validation.write_text("{}", encoding="utf-8")
        self.assertFalse(self.service.run("SES_000001")["reused"])

    def test_failed_force_rebuild_preserves_existing_result(self) -> None:
        self.service.run("SES_000001")
        manifest = self.output / "SES_000001" / "session_speech_manifest.json"
        before = hashlib.sha256(manifest.read_bytes()).hexdigest()
        FakePitchAdapter.fail = True
        with self.assertRaises(SpeechAnalysisError):
            self.service.run("SES_000001", force_rebuild=True)
        self.assertEqual(hashlib.sha256(manifest.read_bytes()).hexdigest(), before)
        self.assertEqual(list(self.output.glob(".*.tmp")), [])


class CliTests(unittest.TestCase):
    def test_cli_rejects_arbitrary_input_and_participant_options(self) -> None:
        for option, value in (("--audio-path", "x.wav"),
                              ("--transcript-path", "x.json"),
                              ("--video-path", "x.mp4"),
                              ("--participant-id", "PTC_000001")):
            with self.subTest(option=option), self.assertRaises(SystemExit):
                cli.build_parser().parse_args(["--session-id", "SES_000001", option, value])

    def test_cli_reports_missing_runtime_dependency(self) -> None:
        output = io.StringIO()
        with mock.patch.dict(sys.modules, {"app.speech.speech_analysis_service": None}), \
                contextlib.redirect_stdout(output):
            exit_code = cli.main(["--session-id", "SES_000001"])
        self.assertEqual(exit_code, 1)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "speech_characteristics_dependency_blocked")


if __name__ == "__main__":
    unittest.main()
