"""Headless portable-build smoke test; creates synthetic media only when requested."""
from pathlib import Path
import hashlib
import json
import subprocess
import traceback

from PIL import Image
from engine import Compressor, tool, CREATE_FLAGS


def run_smoke_test(folder: Path) -> int:
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    report = {"ok": False, "checks": []}
    try:
        source = folder / "صورة تجريبية.png"
        image = Image.new("RGBA", (320, 240), (12, 160, 85, 127))
        image.save(source, compress_level=0)
        original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        result = Compressor().compress(source, folder / "نتائج")
        assert result.status == "compressed", result.message
        with Image.open(result.output) as compressed:
            assert compressed.tobytes() == image.tobytes(), "PNG pixels changed"
        assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
        report["checks"].append({"name": "Lossless PNG / Arabic paths / unchanged original", **result.as_dict()})
        jpeg = folder / "صورة تجريبية.jpg"
        image.convert("RGB").save(jpeg, quality=100, optimize=False)
        result = Compressor().compress(jpeg, folder / "نتائج")
        assert result.status == "compressed", result.message
        with Image.open(jpeg) as a, Image.open(result.output) as b:
            assert a.tobytes() == b.tobytes(), "JPEG pixels changed"
        report["checks"].append({"name": "Lossless JPEG / bundled jpegtran", **result.as_dict()})
        for extension, format in (("heic", "HEIF"), ("avif", "AVIF")):
            still = folder / ("صورة إضافية." + extension)
            image.convert("RGB").save(still, format=format)
            converted = Compressor().compress(still, folder / "نتائج", "instagram")
            assert converted.status in {"compressed", "converted"}, converted.message
            with Image.open(converted.output) as exported:
                assert exported.format == "JPEG"
            report["checks"].append({"name": format + " to JPEG / bundled decoder", **converted.as_dict()})
        video = folder / "فيديو تجريبي.mp4"
        subprocess.run([tool("ffmpeg"), "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                        "testsrc2=size=320x240:rate=24:duration=2", "-f", "lavfi", "-i",
                        "sine=frequency=440:sample_rate=48000:duration=2", "-c:v", "libx264",
                        "-crf", "0", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a",
                        "aac", "-shortest", str(video)], check=True, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=CREATE_FLAGS)
        engine = Compressor()
        # Legal free atom increases only the source container, ensuring an output is saved.
        with video.open("ab") as padded:
            padded.write((8_000_000 + 8).to_bytes(4, "big") + b"free" + bytes(8_000_000))
        result = engine.compress(video, folder / "نتائج", "instagram")
        assert result.status == "compressed", result.message
        info = engine.probe(Path(result.output))
        assert len(info["streams"]) == 2
        assert (info["streams"][0]["width"], info["streams"][0]["height"]) == (320, 240)
        assert info["streams"][0]["avg_frame_rate"] == "30/1"
        assert info["streams"][1]["codec_name"] == "aac"
        assert result.after <= 10_000_000
        report["checks"].append({"name": "Instagram MP4 / 10 MB ceiling / 30fps / AAC", **result.as_dict()})
        report["ok"] = True
    except Exception:
        report["error"] = traceback.format_exc()
    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
