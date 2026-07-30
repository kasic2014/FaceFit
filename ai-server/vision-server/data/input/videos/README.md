# Local video inputs

Supported extensions: `.mp4`, `.mov`, `.m4v`, `.avi`, `.mkv`, `.webm`.

Inputs must be consented local files. The analyzer never modifies the input,
stores video bytes in JSON, or uploads media. OpenCV must open the file, report
positive width, height, and FPS, and decode at least one frame.

Generated smoke assets are stored in `generated/`. The standard smoke input is:

```text
generated/SPK001_FRONT_SHOULDERS_STATIC_SMOKE_01.mp4
generated/SPK001_FRONT_SHOULDERS_STATIC_SMOKE_01.manifest.json
```

This video repeats the approved static positive-detection image for three
seconds at 10 FPS. It is valid only for video-pipeline smoke testing. It is not
valid for temporal motion, tracking accuracy, smoothing, gaze, head pose,
shoulder-angle, or posture-change validation.
