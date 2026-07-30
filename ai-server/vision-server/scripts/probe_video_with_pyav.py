"""Emit ffprobe-shaped strict JSON using the existing PyAV FFmpeg bindings."""

from __future__ import annotations

import json
import sys

import av


def main() -> int:
    if len(sys.argv) != 2:
        return 2
    with av.open(sys.argv[1]) as container:
        streams = []
        for stream in container.streams:
            item = {
                "codec_type": stream.type,
                "codec_name": stream.codec_context.name,
            }
            if stream.type == "video":
                item.update({
                    "width": stream.codec_context.width,
                    "height": stream.codec_context.height,
                    "avg_frame_rate": str(stream.average_rate),
                    "r_frame_rate": str(stream.base_rate),
                    "nb_frames": str(stream.frames),
                    "duration": str(float(stream.duration * stream.time_base)),
                })
            streams.append(item)
        payload = {
            "streams": streams,
            "format": {"duration": str(float(container.duration / av.time_base))},
        }
    print(json.dumps(payload, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
