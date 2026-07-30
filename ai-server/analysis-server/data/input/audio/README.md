# STT 테스트 음성 규격

테스트 음성은 WAV 컨테이너, `pcm_s16le`(16-bit little-endian PCM) 코덱, 16000 Hz, 모노(1 채널)를 사용한다. 권장 길이는 20~60초다. MP3, M4A, WebM, MP4 원본은 이후 FFmpeg로 이 WAV 규격으로 변환한다.

실제 음성 파일은 이 단계에서 만들지 않는다. 정답 대본 템플릿은 `transcripts`에 두며, 이후 각 음성 파일과 같은 기본 이름을 사용한다.

| 파일 | 목적 |
| --- | --- |
| `speech_01_clean.wav` | 조용한 환경의 정상 발화, 기본 STT 정확도 확인 |
| `speech_02_filler.wav` | 음·어·그 등 추임사 포함, 추임사 검출 확인 |
| `speech_03_silence.wav` | 중간 3초 이상 침묵 포함, 장시간 침묵 검출 확인 |
| `speech_04_fast.wav` | 빠른 속도 발화, 속도 계산 확인 |
| `speech_05_slow.wav` | 느린 속도 발화, 느린 발화 추정 확인 |
| `speech_06_noise.wav` | 약한 환경 소음 포함, 소음 환경 STT 결과 확인 |

예: `speech_01_clean.wav`의 정답본은 `speech_01_clean.txt`를 사용한다.

## 폴더 구조와 역할

| 폴더 | 역할 |
| --- | --- |
| `raw/` | 휴대폰 또는 Windows 녹음기로 녹음한 원본 MP3, M4A, WAV 파일 보관 |
| `standard/` | `convert_audio.py`로 변환한 16 kHz 모노 PCM WAV 파일 보관 |
| `transcripts/` | 사람이 직접 작성한 정답 대본 TXT 파일 보관 |

## 파일 대응 및 이름 규칙

원본 파일, 변환 파일, 정답 대본은 확장자를 제외한 기본 이름을 동일하게 사용한다. 정답 대본 이름은 `<음성 기본 이름>.txt` 형식이다.

```text
raw/speech_01_clean.m4a
standard/speech_01_clean.wav
transcripts/speech_01_clean.txt
```

## 원본 녹음 변환

원본 녹음 파일은 지원 형식(WAV, MP3, M4A, AAC, FLAC, OGG, WebM, MP4, MOV, MKV) 중 어느 것이어도 된다. 워크스페이스 루트에서 `convert_audio.py`로 표준 WAV로 변환하고, 이어서 `inspect_audio.py`로 규격을 확인한다.

```powershell
.\ai-server\analysis-server\.venv\Scripts\python.exe .\ai-server\analysis-server\scripts\convert_audio.py recording.m4a speech_01_clean.wav
.\ai-server\analysis-server\.venv\Scripts\python.exe .\ai-server\analysis-server\scripts\inspect_audio.py speech_01_clean.wav
```

원본 음성, 변환 음성, 사용자 음성에서 작성한 실제 정답 대본은 모두 Git에 커밋하지 않는다. 폴더 유지를 위한 `.gitkeep`, 이 문서, `test_manifest.example.json`만 저장소에서 유지한다.
