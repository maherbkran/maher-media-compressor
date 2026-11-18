"""MediaLite's local-only compression engine. No network code or shell commands."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib

from PIL import Image, ImageOps, ImageCms, UnidentifiedImageError
from io import BytesIO
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

IMAGE_EXTS = {".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".webp", ".bmp", ".dib", ".tif", ".tiff", ".gif",
              ".heic", ".heif", ".heics", ".heifs", ".hif", ".avif", ".avifs", ".jp2", ".j2k", ".jpx",
              ".ico", ".icns", ".psd", ".pcx", ".ppm", ".pgm", ".pbm", ".pam", ".tga", ".dds", ".qoi", ".hdr", ".exr"}
VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".qt", ".mkv", ".avi", ".webm", ".wmv", ".asf", ".mts", ".m2ts", ".m2t", ".ts",
              ".3gp", ".3g2", ".flv", ".f4v", ".vob", ".mpg", ".mpeg", ".mpe", ".m2v", ".mpv", ".mxf", ".ogv", ".ogg", ".ogm",
              ".rm", ".rmvb", ".divx", ".xvid", ".h264", ".264", ".h265", ".265", ".hevc", ".av1", ".dv", ".mod", ".tod", ".nut", ".y4m", ".mjpeg", ".mjpg"}
SUPPORTED = IMAGE_EXTS | VIDEO_EXTS
MAX_IMAGE_BYTES = 256 * 1024 * 1024
MAX_PNG_DECODED = 512 * 1024 * 1024
CREATE_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class Cancelled(Exception):
    pass


class SkipFile(Exception):
    pass


@dataclass(frozen=True)
class ExportSettings:
    image_quality: int = 85
    image_max_mb: float = 0.0
    image_max_width: int = 1080
    image_max_height: int = 1920
    video_quality: int = 80
    video_max_mb: float = 0.0
    video_max_width: int = 1920
    video_max_height: int = 1920

    def validate(self):
        for quality in (self.image_quality, self.video_quality):
            if not isinstance(quality, int) or not 1 <= quality <= 100:
                raise ValueError("الجودة يجب أن تكون بين 1 و100%.")
        for size in (self.image_max_mb, self.video_max_mb):
            if not math.isfinite(size) or not 0 <= size <= 1000 or 0 < size < 0.01:
                raise ValueError("الحجم يجب أن يكون بين 0.01 و1000 MB، أو صفراً بدون حد.")
        for dimension in (self.image_max_width, self.image_max_height, self.video_max_width, self.video_max_height):
            if not isinstance(dimension, int) or not 16 <= dimension <= 16384:
                raise ValueError("العرض والارتفاع يجب أن يكونا بين 16 و16384 بكسل.")


@dataclass
class Result:
    source: str
    status: str
    before: int = 0
    after: int = 0
    output: str = ""
    message: str = ""
    seconds: float = 0.0

    def as_dict(self):
        return asdict(self)


def resource_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def tool(name: str) -> str:
    path = resource_dir() / "tools" / (name + (".exe" if os.name == "nt" else ""))
    if not path.is_file():
        raise RuntimeError(f"أداة {name} غير موجودة. فك ضغط مجلد التطبيق بالكامل.")
    return str(path)


class Compressor:
    def __init__(self, cancel: threading.Event | None = None, progress=None, target_mb: float = 0,
                 settings: ExportSettings | None = None):
        self.cancel = cancel or threading.Event()
        self.progress = progress or (lambda fraction: None)
        self.settings = settings or ExportSettings(video_max_mb=target_mb)
        self.target_mb = self.settings.video_max_mb

    def check_cancel(self):
        if self.cancel.is_set():
            raise Cancelled()

    def run_process(self, args: list[str], duration: float = 0, timeout: float | None = None) -> str:
        """Drain the pipe in a reader thread, allowing cancellation even without output."""
        self.check_cancel()
        tail = deque(maxlen=100)
        proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, creationflags=CREATE_FLAGS,
                                text=True, encoding="utf-8", errors="replace")

        def drain():
            assert proc.stdout is not None
            for line in proc.stdout:
                tail.append(line)
                if duration and line.startswith("out_time_us="):
                    try:
                        self.progress(min(0.98, max(0.0, int(line.split("=", 1)[1]) / 1e6 / duration)))
                    except (ValueError, OverflowError):
                        pass

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        started = time.monotonic()
        try:
            while proc.poll() is None:
                self.check_cancel()
                if timeout and time.monotonic() - started > timeout:
                    raise RuntimeError("انتهت مهلة قراءة الملف.")
                self.cancel.wait(0.08)
            self.check_cancel()
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            reader.join(timeout=3)
            if proc.stdout:
                proc.stdout.close()
        output = "".join(tail)
        if proc.returncode:
            raise RuntimeError(output[-1800:].strip() or "تعذّرت معالجة الملف.")
        return output

    def probe(self, source: Path) -> dict:
        # stdout is JSON: preserve the full document rather than the bounded log tail.
        self.check_cancel()
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            args = [tool("ffprobe"), "-v", "error", "-protocol_whitelist", "file,pipe",
                    "-show_format", "-show_streams", "-show_chapters", "-of", "json", str(source)]
            proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=output,
                                    stderr=errors, creationflags=CREATE_FLAGS)
            try:
                while proc.poll() is None:
                    self.check_cancel()
                    self.cancel.wait(0.08)
                if proc.returncode:
                    errors.seek(0)
                    err = errors.read()
                    raise RuntimeError(err.decode("utf-8", "replace")[-1600:])
                output.seek(0)
                return json.load(output)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()

    def compress(self, source: Path, destination: Path, mode: str = "lossless") -> Result:
        start = time.monotonic()
        source = Path(source).resolve()
        destination = Path(destination).resolve()
        before = 0
        temporary: Path | None = None
        try:
            self.check_cancel()
            if mode not in {"lossless", "visual", "instagram"}:
                raise ValueError("خيار ضغط غير معروف.")
            if mode == "instagram":
                self.settings.validate()
            if not source.is_file():
                raise RuntimeError("الملف غير موجود أو غير متاح.")
            before = source.stat().st_size
            if not before:
                raise RuntimeError("الملف فارغ.")
            kind = self.media_kind(source)
            destination.mkdir(parents=True, exist_ok=True)
            if kind == "image":
                if mode != "instagram" and before > MAX_IMAGE_BYTES:
                    raise SkipFile("الصورة أكبر من حد المعالجة الآمن (256 MB).")
                output_suffix = self.image_suffix(source, mode)
            else:
                output_suffix = ".mp4" if mode == "instagram" else source.suffix.lower() if mode == "lossless" else self.video_suffix(source)
            fd, name = tempfile.mkstemp(prefix=".medialite-", suffix=".part" + output_suffix, dir=destination)
            os.close(fd)
            temporary = Path(name)
            if kind == "image":
                self.compress_image(source, temporary, mode)
            else:
                if mode == "instagram":
                    self.compress_instagram_video(source, temporary)
                else:
                    self.compress_video(source, temporary, mode)
            self.check_cancel()
            after = temporary.stat().st_size
            if after <= 0:
                raise RuntimeError("لم تُنتج المعالجة ملفاً صالحاً.")
            if after >= before and mode != "instagram":
                return Result(str(source), "unchanged", before, before,
                              message="الملف مضغوط جيداً؛ تم الاحتفاظ بالأصل فقط.",
                              seconds=time.monotonic() - start)
            # On Windows rename fails if the target exists: never replace another file.
            for i in range(1, 100000):
                suffix = "" if i == 1 else f"_{i}"
                final = destination / f"{source.stem}_compressed{suffix}{output_suffix}"
                if final.exists():
                    continue
                try:
                    if os.name == "nt":
                        temporary.rename(final)
                    else:
                        os.link(temporary, final)
                        temporary.unlink()
                    temporary = None
                    break
                except FileExistsError:
                    continue
            else:
                raise RuntimeError("تعذّر اختيار اسم جديد للنتيجة.")
            self.progress(1.0)
            return Result(str(source), "compressed" if after < before else "converted", before, after, str(final),
                          self.result_message(mode, source, kind), time.monotonic() - start)
        except Cancelled:
            return Result(str(source), "cancelled", before, before, message="تم الإيقاف؛ الأصل محفوظ.")
        except (SkipFile, Image.DecompressionBombError) as exc:
            return Result(str(source), "skipped", before, before, message=str(exc))
        except Exception as exc:
            return Result(str(source), "error", before, before, message=str(exc))
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def media_kind(self, source: Path) -> str:
        if source.suffix.lower() in IMAGE_EXTS:
            return "image"
        if source.suffix.lower() in VIDEO_EXTS:
            return "video"
        try:
            with Image.open(source):
                return "image"
        except (UnidentifiedImageError, OSError):
            info = self.probe(source)
            if any(s.get("codec_type") == "video" for s in info.get("streams", [])):
                return "video"
            raise SkipFile("الملف لا يحتوي صورة أو فيديو قابلاً للقراءة.")

    def result_message(self, mode: str, source: Path, kind: str) -> str:
        if mode != "instagram":
            return "تم حفظ نسخة أصغر."
        is_video = kind == "video"
        maximum = self.settings.video_max_mb if is_video else self.settings.image_max_mb
        limit = f" ضمن حد {maximum:g} MB" if maximum else " بدون حد حجم"
        return "تم التصدير بإعداداتك" + limit + (". يتضمن مسار الصورة والصوت الأساسيين." if is_video else ".")

    def image_suffix(self, source: Path, mode: str) -> str:
        ext = source.suffix.lower()
        if mode == "instagram":
            return ".jpg"
        if ext == ".gif":
            raise SkipFile("GIF يُترك كما هو للحفاظ على الإطارات والتوقيت.")
        with Image.open(source) as image:
            if getattr(image, "n_frames", 1) != 1:
                raise SkipFile("الصورة متحركة أو متعددة الصفحات؛ تُترك كما هي.")
            if mode == "instagram":
                if image.mode not in {"RGB", "RGBA", "L", "LA", "P"}:
                    raise SkipFile("فضاء أو عمق الصورة يحتاج معالجة خاصة؛ جرّب بلا فقدان.")
                return ".png" if "A" in image.getbands() or "transparency" in image.info else ".jpg"
            if mode == "lossless":
                if ext in {".jpg", ".jpeg", ".png", ".webp"}:
                    return ext
                if image.mode not in {"1", "L", "LA", "P", "RGB", "RGBA", "I;16", "I;16B"}:
                    raise SkipFile("لون أو عمق صورة غير مدعوم للضغط بلا فقدان.")
                # TIFF metadata is not transferable to PNG without semantic changes.
                if ext in {".tif", ".tiff"}:
                    raise SkipFile("TIFF يُترك كما هو في وضع بلا فقدان للحفاظ على بياناته.")
                return ".png"
            if ext in {".jpg", ".jpeg"}:
                return ".jpg"
            if image.mode not in {"RGB", "RGBA", "L", "LA", "P"}:
                raise SkipFile("لن يتم تحويل الصور ذات عمق أو فضاء لون خاص.")
            if max(image.size) > 16383:
                raise SkipFile("أبعاد الصورة تتجاوز حد صيغة WebP؛ جرّب وضع بلا فقدان.")
            return ".webp"

    def compress_image(self, source: Path, temporary: Path, mode: str):
        ext = source.suffix.lower()
        if mode == "instagram":
            self.compress_export_image(source, temporary)
            return
        if mode == "lossless" and ext in {".jpg", ".jpeg"}:
            self.optimize_jpeg(source, temporary)
            return
        if mode == "lossless" and ext == ".png":
            self.optimize_png(source, temporary)
            return
        with Image.open(source) as image:
            self.check_cancel()
            image.load()
            metadata = {k: image.info[k] for k in ("icc_profile", "exif", "xmp") if image.info.get(k)}
            if temporary.suffix == ".jpg":
                image.save(temporary, "JPEG", quality=95, subsampling=0,
                           optimize=True, progressive=True, **metadata)
            elif temporary.suffix == ".webp":
                target = image.convert("RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB")
                target.save(temporary, "WEBP", lossless=mode == "lossless", quality=92,
                            method=6, exact=True, **metadata)
            else:
                image.save(temporary, "PNG", optimize=True, **metadata)

    def compress_export_image(self, source: Path, temporary: Path):
        """Apply an upper quality, dimension ceilings and an optional measured byte ceiling."""
        settings = self.settings
        maximum = int(settings.image_max_mb * 1_000_000) if settings.image_max_mb else 0
        try:
            original = Image.open(source)
        except (Image.DecompressionBombError, UnidentifiedImageError, OSError):
            self.export_image_ffmpeg(source, temporary)
            return
        with original:
            if original.mode in {"I;16", "I;16B", "I;16L", "I", "F"}:
                self.export_image_ffmpeg(source, temporary)
                return
            if original.format == "JPEG":
                original.draft("RGB", (settings.image_max_width, settings.image_max_height))
            image = ImageOps.exif_transpose(original)
            metadata = {}
            profile = image.info.get("icc_profile")
            if profile:
                try:
                    srgb = ImageCms.createProfile("sRGB")
                    # Preserve alpha until the explicit JPEG white-background composite.
                    output_mode = "RGBA" if "A" in image.getbands() else "RGB"
                    image = ImageCms.profileToProfile(image, BytesIO(profile), srgb, outputMode=output_mode)
                    metadata["icc_profile"] = ImageCms.ImageCmsProfile(srgb).tobytes()
                except (ImageCms.PyCMSError, OSError, ValueError):
                    pass
            if "A" in image.getbands() or "transparency" in image.info:
                rgba = image.convert("RGBA")
                target = Image.new("RGB", image.size, "white")
                target.paste(rgba, mask=rgba.getchannel("A"))
            else:
                target = image.convert("RGB")
            target.thumbnail((settings.image_max_width, settings.image_max_height), Image.Resampling.LANCZOS)

            def save(quality: int):
                self.check_cancel()
                if temporary.suffix == ".png":
                    target.save(temporary, "PNG", optimize=True, **metadata)
                else:
                    target.save(temporary, "JPEG", quality=quality, subsampling=2,
                                optimize=True, progressive=True, **metadata)
                return temporary.stat().st_size

            for attempt in range(12):
                actual = save(settings.image_quality)
                if not maximum or actual <= maximum:
                    return
                if temporary.suffix == ".jpg":
                    # Find the best quality up to the requested setting which fits this size.
                    floor = min(20, settings.image_quality)
                    lo, hi, best = floor, settings.image_quality - 1, 0
                    while lo <= hi:
                        quality = (lo + hi) // 2
                        actual = save(quality)
                        if actual <= maximum:
                            best = quality
                            lo = quality + 1
                        else:
                            hi = quality - 1
                    if best:
                        if save(best) <= maximum:
                            return
                    actual = save(floor)
                # Transparent PNG keeps lossless color/alpha; meeting a size cap uses resizing.
                factor = min(0.85, math.sqrt(maximum / actual) * 0.92)
                width = max(1, int(target.width * factor))
                height = max(1, int(target.height * factor))
                if (width, height) == target.size:
                    break
                target.thumbnail((width, height), Image.Resampling.LANCZOS)
            raise SkipFile("الحجم المحدد أصغر من الممكن للصورة وبيانات ألوانها. ارفع الحد أو اختر بدون حد.")

    def export_image_ffmpeg(self, source: Path, temporary: Path):
        """Decode large/less common stills outside the GUI process, without reading the file into Python."""
        settings = self.settings
        bound_w, bound_h = settings.image_max_width, settings.image_max_height
        maximum = int(settings.image_max_mb * 1_000_000) if settings.image_max_mb else 0
        quality = max(2, min(31, round(32 - settings.image_quality * 0.30)))
        for attempt in range(12):
            scale = f"scale=w='min(iw,{bound_w})':h='min(ih,{bound_h})':force_original_aspect_ratio=decrease"
            filters = (f"[0:v:0]{scale},format=rgba,split[fg][bg];"
                       "[bg]lutrgb=r=255:g=255:b=255,format=rgb24[white];"
                       "[white][fg]overlay=shortest=1:format=auto,format=rgb24[out]")
            self.run_process([tool("ffmpeg"), "-v", "error", "-nostdin", "-y", "-protocol_whitelist", "file,pipe",
                              "-i", str(source), "-filter_complex", filters, "-map", "[out]", "-frames:v", "1",
                              "-q:v", str(quality), "-update", "1", str(temporary)])
            actual = temporary.stat().st_size
            if not maximum or actual <= maximum:
                return
            factor = min(0.85, math.sqrt(maximum / actual) * 0.92)
            bound_w, bound_h = max(1, int(bound_w * factor)), max(1, int(bound_h * factor))
        raise SkipFile("الصورة لا تناسب حد الحجم المختار؛ ارفع الحد أو اختر بدون حد.")

    def optimize_jpeg(self, source: Path, temporary: Path):
        # jpegtran's Windows filename handling is ANSI; file handles support Arabic paths.
        with source.open("rb") as input_file, temporary.open("wb") as output_file, tempfile.TemporaryFile() as errors:
            proc = subprocess.Popen([tool("jpegtran"), "-copy", "all", "-optimize", "-progressive"],
                                    stdin=input_file, stdout=output_file, stderr=errors,
                                    creationflags=CREATE_FLAGS)
            try:
                while proc.poll() is None:
                    self.check_cancel()
                    self.cancel.wait(0.08)
                if proc.returncode:
                    errors.seek(0)
                    raise RuntimeError(errors.read().decode("utf-8", "replace")[-1600:])
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()

    def optimize_png(self, source: Path, temporary: Path):
        """Recompress the original filtered pixel bytes; keep every non-IDAT chunk intact."""
        data = source.read_bytes()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("ملف PNG غير صالح.")
        chunks = []
        idat = []
        pos = 8
        while pos < len(data):
            self.check_cancel()
            if pos + 12 > len(data):
                raise ValueError("ملف PNG غير مكتمل.")
            size = struct.unpack_from(">I", data, pos)[0]
            end = pos + size + 12
            if end > len(data):
                raise ValueError("ملف PNG غير مكتمل.")
            raw = data[pos:end]
            kind = raw[4:8]
            payload = raw[8:-4]
            if zlib.crc32(kind + payload) & 0xffffffff != struct.unpack(">I", raw[-4:])[0]:
                raise ValueError("فشل التحقق من سلامة PNG.")
            if kind == b"acTL":
                raise SkipFile("PNG متحرك؛ يُترك كما هو للحفاظ على الحركة.")
            chunks.append((kind, raw))
            if kind == b"IDAT":
                idat.append(payload)
            pos = end
            if kind == b"IEND":
                break
        if not chunks or chunks[-1][0] != b"IEND" or not idat:
            raise ValueError("ملف PNG غير مكتمل.")
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(b"".join(idat), MAX_PNG_DECODED + 1)
        if len(pixels) > MAX_PNG_DECODED or decoder.unconsumed_tail:
            raise SkipFile("بيانات PNG تتجاوز حد الذاكرة الآمن.")
        if not decoder.eof:
            raise ValueError("بيانات PNG غير مكتملة.")
        self.check_cancel()
        packed = zlib.compress(pixels, level=9)
        raw_idat = (struct.pack(">I", len(packed)) + b"IDAT" + packed
                    + struct.pack(">I", zlib.crc32(b"IDAT" + packed) & 0xffffffff))
        with temporary.open("wb") as output:
            output.write(data[:8])
            wrote = False
            for kind, raw in chunks:
                if kind == b"IDAT":
                    if not wrote:
                        output.write(raw_idat)
                        wrote = True
                else:
                    output.write(raw)
            output.write(data[pos:])

    def video_suffix(self, source: Path) -> str:
        info = self.probe(source)
        streams = info.get("streams", [])
        videos = [s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")]
        if not videos:
            raise SkipFile("لم يتم العثور على مسار فيديو.")
        if len(videos) != 1 or any(s.get("codec_type") not in {"video", "audio"} for s in streams):
            raise SkipFile("الفيديو يتضمن ترجمة أو مسارات خاصة؛ استخدم بلا فقدان للحفاظ عليها.")
        if any(s.get("disposition", {}).get("attached_pic") for s in streams):
            raise SkipFile("الفيديو يتضمن غلافاً مرفقاً؛ استخدم بلا فقدان.")
        video = videos[0]
        pixel = video.get("pix_fmt", "")
        if pixel not in {"yuv420p", "yuvj420p", "nv12"}:
            raise SkipFile("فيديو HDR أو عمق/لون خاص؛ استخدم بلا فقدان للحفاظ على الألوان.")
        if video.get("color_transfer") in {"smpte2084", "arib-std-b67"} or video.get("color_primaries") == "bt2020":
            raise SkipFile("فيديو HDR؛ استخدم بلا فقدان للحفاظ على الألوان.")
        if video.get("field_order") not in {None, "unknown", "progressive"}:
            raise SkipFile("الفيديو متداخل الإطارات؛ استخدم بلا فقدان.")
        safe_audio = {"aac", "mp3", "alac", "ac3", "eac3"}
        return ".mp4" if all(s.get("codec_name") in safe_audio for s in streams if s.get("codec_type") == "audio") else ".mkv"

    def compress_video(self, source: Path, temporary: Path, mode: str):
        original = self.probe(source)
        try:
            duration = float(original.get("format", {}).get("duration", 0))
        except (TypeError, ValueError):
            duration = 0
        args = [tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-protocol_whitelist", "file,pipe", "-noautorotate", "-i", str(source),
                "-map", "0", "-map_metadata", "0", "-map_chapters", "0", "-c", "copy"]
        if mode == "visual":
            # Stream-copy every audio track; preserve timing, dimensions and rotation metadata.
            args += ["-c:v:0", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
                     "-fps_mode:v:0", "passthrough", "-threads:v:0", "4"]
            video = next(s for s in original["streams"] if s.get("codec_type") == "video")
            for key, flag in (("color_range", "-color_range"), ("color_space", "-colorspace"),
                              ("color_transfer", "-color_trc"), ("color_primaries", "-color_primaries")):
                if video.get(key) not in {None, "unknown", "reserved"}:
                    args += [flag, str(video[key])]
        if temporary.suffix in {".mp4", ".mov", ".m4v"}:
            args += ["-movflags", "+faststart+use_metadata_tags"]
        args += ["-progress", "pipe:1", "-nostats", str(temporary)]
        self.run_process(args, duration)
        self.check_cancel()
        result = self.probe(temporary)
        before_streams, after_streams = original.get("streams", []), result.get("streams", [])
        if len(before_streams) != len(after_streams):
            raise RuntimeError("لم تتطابق مسارات الناتج؛ تم تجاهل النسخة لحماية المحتوى.")
        for a, b in zip(before_streams, after_streams):
            if a.get("codec_type") != b.get("codec_type"):
                raise RuntimeError("اختلفت مسارات الناتج؛ لم يتم حفظه.")
            if a.get("codec_type") == "video" and (a.get("width"), a.get("height")) != (b.get("width"), b.get("height")):
                raise RuntimeError("اختلفت أبعاد الناتج؛ لم يتم حفظه.")
        try:
            after_duration = float(result.get("format", {}).get("duration", 0))
            if duration and abs(after_duration - duration) > max(1.0, duration * 0.01):
                raise RuntimeError("اختلفت مدة الفيديو؛ تم تجاهل النسخة.")
        except (TypeError, ValueError):
            pass

    def compress_instagram_video(self, source: Path, temporary: Path):
        """Quality-based MP4 export, followed by two-pass encoding only if a byte cap needs it."""
        settings = self.settings
        info = self.probe(source)
        streams = info.get("streams", [])
        videos = [s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")]
        if not videos:
            raise SkipFile("لم يتم العثور على مسار فيديو قابل للقراءة.")
        video = next((v for v in videos if v.get("disposition", {}).get("default")), videos[0])
        try:
            duration = float(info.get("format", {}).get("duration") or video.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0
        if not math.isfinite(duration) or duration <= 0:
            duration = 0
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        target_bytes = int(settings.video_max_mb * 1_000_000) if settings.video_max_mb else 0
        audio_bitrate = 96000 if target_bytes and target_bytes <= 5_000_000 else 128000
        video_bitrate = 0
        if target_bytes:
            if not duration:
                raise SkipFile("مدة الفيديو غير متاحة. اختر بدون حد حجم لتحويله.")
            video_bitrate = int(target_bytes * 8 * 0.92 / duration - (audio_bitrate if has_audio else 0))
            video_bitrate = min(video_bitrate, 50_000_000)
            if video_bitrate < 100_000:
                raise SkipFile("المقطع طويل جداً لهذا الحجم. ارفع الحد أو اختر بدون حد.")
        width, height = video.get("width", 0), video.get("height", 0)
        rotation = next((s.get("rotation", 0) for s in video.get("side_data_list", []) if "rotation" in s), video.get("tags", {}).get("rotate", 0))
        try:
            if abs(round(float(rotation))) % 180 == 90:
                width, height = height, width
        except (ValueError, TypeError):
            pass
        bound_w, bound_h = settings.video_max_width, settings.video_max_height
        # Respect the requested ceilings, then use smaller frames for a constrained budget.
        if target_bytes and video_bitrate < 1_500_000:
            if height > width:
                adaptive_w, adaptive_h = 720, 1280
            elif width > height:
                adaptive_w, adaptive_h = 1280, 720
            else:
                adaptive_w, adaptive_h = 720, 720
            bound_w, bound_h = min(bound_w, adaptive_w), min(bound_h, adaptive_h)
        filters = []
        is_hdr = video.get("color_transfer") in {"smpte2084", "arib-std-b67"}
        if is_hdr:
            filters += ["zscale=t=linear:npl=100", "format=gbrpf32le", "zscale=p=bt709",
                        "tonemap=tonemap=hable:desat=0", "zscale=t=bt709:m=bt709:r=tv"]
        filters += ["scale=trunc(iw*sar/2)*2:ih", "setsar=1",
                    f"scale=w='min(iw,{bound_w})':h='min(ih,{bound_h})':force_original_aspect_ratio=decrease:force_divisible_by=2",
                    "fps=30", "format=yuv420p"]
        if video.get("field_order") not in {None, "unknown", "progressive"}:
            filters.insert(0, "yadif=mode=send_frame:parity=auto:deint=all")
        crf = round(36 - settings.video_quality * 0.20)
        progress = self.progress
        with tempfile.TemporaryDirectory(prefix=".medialite-pass-", dir=temporary.parent) as pass_folder:
            log = str(Path(pass_folder) / "encode")
            common = [tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                      "-protocol_whitelist", "file,pipe", "-i", str(source),
                      "-map", f"0:{video['index']}", "-vf", ",".join(filters),
                      "-c:v", "libx264", "-preset", "medium", "-profile:v", "high",
                      "-pix_fmt", "yuv420p", "-threads:v", "4", "-g", "60",
                      "-map_metadata", "-1", "-map_chapters", "-1", "-sn", "-dn"]
            if is_hdr:
                common += ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
                           "-x264-params", "colorprim=bt709:transfer=bt709:colormatrix=bt709"]

            def output_args():
                args = (["-map", "0:a:0", "-c:a", "aac", "-b:a", str(audio_bitrate), "-ac", "2", "-ar", "48000"]
                        if has_audio else ["-an"])
                return args + ["-movflags", "+faststart", "-metadata:s:v:0", "rotate=0",
                               "-progress", "pipe:1", "-nostats", str(temporary)]

            try:
                self.progress = lambda value: progress(value * (0.30 if target_bytes else 0.98))
                self.run_process(common + ["-crf", str(crf)] + output_args(), duration)
                if target_bytes and temporary.stat().st_size > target_bytes:
                    common += ["-passlogfile", log]
                    self.progress = lambda value: progress(0.30 + value * 0.30)
                    self.run_process(common + ["-b:v", str(video_bitrate), "-pass", "1", "-an",
                                              "-progress", "pipe:1", "-nostats", "-f", "null", os.devnull], duration)
                    for attempt in range(3):
                        self.check_cancel()
                        self.progress = lambda value: progress(0.60 + value * 0.38)
                        self.run_process(common + ["-b:v", str(video_bitrate), "-pass", "2"] + output_args(), duration)
                        actual = temporary.stat().st_size
                        if actual <= target_bytes:
                            break
                        video_bitrate = int(video_bitrate * target_bytes / actual * 0.86)
                        if video_bitrate < 80_000:
                            raise SkipFile("تعذّر الوصول للحجم المطلوب. ارفع الحد أو اختر بدون حد.")
                    else:
                        raise RuntimeError("لم يتحقق حد الحجم؛ لم يتم حفظ نسخة فوق الحد.")
            finally:
                self.progress = progress
        result = self.probe(temporary)
        output_video = next(s for s in result["streams"] if s.get("codec_type") == "video")
        if output_video.get("codec_name") != "h264" or output_video.get("pix_fmt") != "yuv420p":
            raise RuntimeError("لم تتطابق صيغة الفيديو الناتج مع إعداد التصدير.")
        if output_video["width"] > settings.video_max_width or output_video["height"] > settings.video_max_height:
            raise RuntimeError("تجاوزت أبعاد الناتج الحدود المختارة؛ لم يتم حفظه.")
        if target_bytes and temporary.stat().st_size > target_bytes:
            raise RuntimeError("تجاوز الناتج حد الحجم؛ لم يتم حفظه.")
        after_duration = float(result.get("format", {}).get("duration", 0))
        if duration and abs(after_duration - duration) > max(0.5, duration * 0.01):
            raise RuntimeError("اختلفت مدة الناتج؛ لم يتم حفظه.")
        if has_audio and not any(s.get("codec_type") == "audio" for s in result["streams"]):
            raise RuntimeError("لم يتم العثور على الصوت في النسخة الناتجة.")
