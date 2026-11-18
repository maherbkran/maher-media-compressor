"""Boundary tests for >2 GiB media containers and long duration, using sparse padding."""
from pathlib import Path
import ctypes
import os
import subprocess
import tempfile
import unittest

from PIL import Image
from engine import Compressor, ExportSettings, tool, CREATE_FLAGS


def make_sparse(file):
    if os.name == "nt":
        import msvcrt
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.DeviceIoControl.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
                                          ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
        returned = ctypes.c_ulong()
        kernel.DeviceIoControl(msvcrt.get_osfhandle(file.fileno()), 0x900C4, None, 0, None, 0,
                               ctypes.byref(returned), None)


class LargeFileTests(unittest.TestCase):
    def ff(self, args):
        subprocess.run([tool("ffmpeg"), "-v", "error", "-nostdin", "-y"] + args,
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=CREATE_FLAGS)

    def test_video_above_two_gibibytes_exports_mp4(self):
        with tempfile.TemporaryDirectory(prefix="maher-large-") as directory:
            root = Path(directory)
            source = root / "فيديو أكبر من 2 جيغا.MOV"
            self.ff(["-f", "lavfi", "-i", "testsrc2=size=160x120:rate=30:duration=1",
                     "-c:v", "libx264", "-crf", "0", "-preset", "ultrafast", str(source)])
            prefix = source.read_bytes()
            padding = 2 * 1024 ** 3
            with source.open("r+b") as file:
                make_sparse(file)
                file.seek(0, os.SEEK_END)
                file.write((padding + 8).to_bytes(4, "big") + b"free")
                file.seek(padding - 1, os.SEEK_CUR)
                file.write(b"\0")
            size = source.stat().st_size
            self.assertGreater(size, 2 * 1024 ** 3)
            result = Compressor().compress(source, root, "instagram")
            self.assertEqual(result.status, "compressed", result.message)
            self.assertEqual(Path(result.output).suffix, ".mp4")
            self.assertEqual(source.stat().st_size, size)
            with source.open("rb") as file:
                self.assertEqual(file.read(len(prefix)), prefix)
            self.assertEqual(Compressor().probe(Path(result.output))["streams"][0]["codec_name"], "h264")

    def test_long_video_unlimited_by_default(self):
        with tempfile.TemporaryDirectory(prefix="maher-duration-") as directory:
            root = Path(directory)
            source = root / "twelve-minutes.mkv"
            self.ff(["-f", "lavfi", "-i", "color=c=blue:size=32x32:rate=1/10:duration=720",
                     "-c:v", "libx264", "-preset", "ultrafast", str(source)])
            self.assertEqual(ExportSettings().video_max_mb, 0)
            result = Compressor().compress(source, root, "instagram")
            self.assertIn(result.status, {"compressed", "converted"}, result.message)
            info = Compressor().probe(Path(result.output))
            self.assertAlmostEqual(float(info["format"]["duration"]), 720, delta=1)

    def test_image_above_old_256mb_limit_exports_jpeg(self):
        with tempfile.TemporaryDirectory(prefix="maher-large-image-") as directory:
            root = Path(directory)
            source = root / "large.png"
            Image.new("RGB", (64, 64), "green").save(source)
            with source.open("r+b") as file:
                make_sparse(file)
                file.seek(300 * 1024 ** 2)
                file.write(b"\0")
            result = Compressor().compress(source, root, "instagram")
            self.assertEqual(result.status, "compressed", result.message)
            with Image.open(result.output) as image:
                self.assertEqual(image.format, "JPEG")


if __name__ == "__main__":
    unittest.main(verbosity=2)
