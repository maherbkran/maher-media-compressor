"""Integration tests exercise real codecs and file safety, not mocked commands."""
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile
import threading
import unittest

from PIL import Image, PngImagePlugin
from engine import Compressor, ExportSettings, CREATE_FLAGS, tool


class CompressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="medialite-tests-")
        cls.root = Path(cls.tmp.name) / "ملفات تجريبية"
        cls.root.mkdir()
        cls.out = cls.root / "نتائج"
        cls.out.mkdir()
        cls.jpeg = cls.root / "صورة جميلة.jpg"
        image = Image.new("RGB", (480, 320))
        image.putdata([((x // 8) * 3 % 256, (y // 5) * 3 % 256, (x + y) % 256)
                       for y in range(320) for x in range(480)])
        exif = Image.Exif()
        exif[274] = 6
        exif[315] = "MediaLite test"
        image.save(cls.jpeg, quality=98, optimize=False, exif=exif)
        cls.png = cls.root / "شفافية.png"
        rgba = Image.new("RGBA", (480, 320), (23, 88, 62, 0))
        rgba.paste((200, 50, 20, 127), (40, 40, 200, 250))
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("Comment", "Keep this metadata intact")
        rgba.save(cls.png, compress_level=0, pnginfo=metadata)
        cls.video = cls.root / "فيديو بصوت.mp4"
        cls.ff(["-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24:duration=3",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=3",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "0", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", str(cls.video)])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def ff(args):
        return subprocess.check_output([tool("ffmpeg"), "-v", "error", "-nostdin", "-y"] + args,
                                       stderr=subprocess.STDOUT, creationflags=CREATE_FLAGS)

    def assert_original_unchanged(self, source, before):
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
        self.assertFalse(list(self.out.glob(".medialite-*")))

    def test_jpeg_lossless_pixels_exif_original_and_collision(self):
        original_hash = hashlib.sha256(self.jpeg.read_bytes()).hexdigest()
        one = Compressor().compress(self.jpeg, self.out)
        two = Compressor().compress(self.jpeg, self.out)
        self.assertEqual(one.status, "compressed", one.message)
        self.assertEqual(two.status, "compressed", two.message)
        self.assertNotEqual(one.output, two.output)
        with Image.open(self.jpeg) as a, Image.open(one.output) as b:
            self.assertEqual(a.tobytes(), b.tobytes())
            self.assertEqual(a.size, b.size)
            self.assertEqual(a.getexif()[274], b.getexif()[274])
            self.assertEqual(a.getexif()[315], b.getexif()[315])
        self.assert_original_unchanged(self.jpeg, original_hash)

    def test_png_lossless_alpha_metadata_and_pixels(self):
        original_hash = hashlib.sha256(self.png.read_bytes()).hexdigest()
        result = Compressor().compress(self.png, self.out)
        self.assertEqual(result.status, "compressed", result.message)
        with Image.open(self.png) as a, Image.open(result.output) as b:
            self.assertEqual(a.mode, b.mode)
            self.assertEqual(a.tobytes(), b.tobytes())
            self.assertEqual(a.info["Comment"], b.info["Comment"])
        self.assert_original_unchanged(self.png, original_hash)

    def test_webp_lossless_preserves_transparent_rgb_and_exif(self):
        source = self.root / "alpha.webp"
        with Image.open(self.png) as image:
            image.save(source, "WEBP", lossless=True, exact=True, method=0,
                       exif=Image.Exif().tobytes())
        result = Compressor().compress(source, self.out)
        self.assertIn(result.status, {"compressed", "unchanged"}, result.message)
        if result.output:
            with Image.open(source) as a, Image.open(result.output) as b:
                self.assertEqual(a.tobytes(), b.tobytes())

    def test_png_16bit(self):
        source = self.root / "16bit.png"
        image = Image.new("I;16", (200, 100))
        image.putdata([i % 65536 for i in range(20000)])
        image.save(source, compress_level=0)
        result = Compressor().compress(source, self.out)
        self.assertEqual(result.status, "compressed", result.message)
        with Image.open(source) as a, Image.open(result.output) as b:
            self.assertEqual(a.tobytes(), b.tobytes())
            self.assertEqual(a.mode, b.mode)

    def test_already_small_no_output(self):
        source = self.root / "tiny.png"
        Image.new("RGB", (1, 1)).save(source, optimize=True)
        result = Compressor().compress(source, self.out)
        self.assertEqual(result.status, "unchanged", result.message)
        self.assertFalse(result.output)

    def test_visual_image_keeps_dimensions_and_alpha(self):
        result = Compressor().compress(self.png, self.out, "visual")
        self.assertEqual(result.status, "compressed", result.message)
        self.assertEqual(Path(result.output).suffix, ".webp")
        with Image.open(self.png) as a, Image.open(result.output) as b:
            self.assertEqual(a.size, b.size)
            self.assertEqual(a.getchannel("A").tobytes(), b.getchannel("A").tobytes())

    def test_visual_jpeg(self):
        result = Compressor().compress(self.jpeg, self.out, "visual")
        self.assertEqual(result.status, "compressed", result.message)
        with Image.open(self.jpeg) as a, Image.open(result.output) as b:
            self.assertEqual(a.size, b.size)
            self.assertEqual(a.getexif()[274], b.getexif()[274])

    def test_animation_and_multiframe_skipped(self):
        source = self.root / "animation.webp"
        first, second = Image.new("RGB", (32, 32), "red"), Image.new("RGB", (32, 32), "blue")
        first.save(source, save_all=True, append_images=[second], duration=100, loop=0)
        for mode in ("lossless", "visual"):
            result = Compressor().compress(source, self.out, mode)
            self.assertEqual(result.status, "skipped")
            self.assertFalse(result.output)

    def test_corrupt_file_and_cleanup(self):
        source = self.root / "broken.jpg"
        source.write_bytes(b"not an image")
        result = Compressor().compress(source, self.out)
        self.assertEqual(result.status, "error")
        self.assertFalse(list(self.out.glob(".medialite-*")))

    def test_cancel_before_start(self):
        cancel = threading.Event()
        cancel.set()
        result = Compressor(cancel).compress(self.video, self.out, "visual")
        self.assertEqual(result.status, "cancelled")
        self.assertFalse(list(self.out.glob(".medialite-*")))

    def test_visual_video_audio_hash_dimensions_duration(self):
        original_hash = hashlib.sha256(self.video.read_bytes()).hexdigest()
        engine = Compressor()
        result = engine.compress(self.video, self.out, "visual")
        self.assertEqual(result.status, "compressed", result.message)
        original, compressed = engine.probe(self.video), engine.probe(Path(result.output))
        for key in ("width", "height", "avg_frame_rate"):
            self.assertEqual(original["streams"][0][key], compressed["streams"][0][key])
        self.assertAlmostEqual(float(original["format"]["duration"]), float(compressed["format"]["duration"]), delta=0.1)
        a = self.ff(["-i", str(self.video), "-map", "0:a", "-c", "copy", "-f", "hash", "-hash", "sha256", "-"])
        b = self.ff(["-i", result.output, "-map", "0:a", "-c", "copy", "-f", "hash", "-hash", "sha256", "-"])
        self.assertEqual(a, b)
        self.assert_original_unchanged(self.video, original_hash)

    def test_lossless_video_packet_hashes(self):
        # Pad the MP4 container with a legal free atom so a remux definitely saves bytes.
        source = self.root / "padded.mp4"
        source.write_bytes(self.video.read_bytes() + (1048576 + 8).to_bytes(4, "big") + b"free" + bytes(1048576))
        result = Compressor().compress(source, self.out)
        self.assertEqual(result.status, "compressed", result.message)
        a = self.ff(["-i", str(source), "-map", "0", "-c", "copy", "-f", "streamhash", "-hash", "sha256", "-"])
        b = self.ff(["-i", result.output, "-map", "0", "-c", "copy", "-f", "streamhash", "-hash", "sha256", "-"])
        self.assertEqual(a, b)

    def test_cancel_while_encoding_removes_partial(self):
        cancel = threading.Event()
        engine = Compressor(cancel, lambda _: cancel.set())
        result = engine.compress(self.video, self.out, "visual")
        self.assertEqual(result.status, "cancelled", result.message)
        self.assertFalse(list(self.out.glob(".medialite-*")))

    def test_hdr_skipped_in_visual_mode(self):
        source = self.root / "hdr.mp4"
        self.ff(["-i", str(self.video), "-c:v", "libx264", "-pix_fmt", "yuv420p10le",
                 "-c:a", "copy", "-x264-params", "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc", str(source)])
        result = Compressor().compress(source, self.out, "visual")
        self.assertEqual(result.status, "skipped", result.message)

    def test_instagram_target_mp4_30fps_aac_and_no_original_changes(self):
        source = self.root / "IG export.mp4"
        source.write_bytes(self.video.read_bytes() + (12_000_000 + 8).to_bytes(4, "big") + b"free" + bytes(12_000_000))
        original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        engine = Compressor(target_mb=5)
        result = engine.compress(source, self.out, "instagram")
        self.assertEqual(result.status, "compressed", result.message)
        self.assertLessEqual(result.after, 5_000_000)
        info = engine.probe(Path(result.output))
        self.assertEqual(info["streams"][0]["codec_name"], "h264")
        self.assertEqual(info["streams"][0]["avg_frame_rate"], "30/1")
        self.assertEqual(info["streams"][1]["codec_name"], "aac")
        self.assertAlmostEqual(float(info["format"]["duration"]), 3.0, delta=0.1)
        self.assert_original_unchanged(source, original_hash)

    def test_instagram_rotation_is_baked_without_crop(self):
        source = self.root / "rotated.mp4"
        self.ff(["-display_rotation:v:0", "90", "-i", str(self.video), "-c", "copy", str(source)])
        with source.open("ab") as padded:
            padded.write((8_000_000 + 8).to_bytes(4, "big") + b"free" + bytes(8_000_000))
        engine = Compressor(target_mb=5)
        result = engine.compress(source, self.out, "instagram")
        self.assertEqual(result.status, "compressed", result.message)
        video = engine.probe(Path(result.output))["streams"][0]
        self.assertEqual((video["width"], video["height"]), (240, 320))
        self.assertFalse(any(abs(s.get("rotation", 0)) % 360 for s in video.get("side_data_list", [])))

    def test_instagram_hdr_tonemaps_to_sdr(self):
        source = self.root / "hdr_for_instagram.mp4"
        self.ff(["-i", str(self.video), "-c:v", "libx264", "-pix_fmt", "yuv420p10le", "-c:a", "copy",
                 "-x264-params", "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc", str(source)])
        with source.open("ab") as padded:
            padded.write((8_000_000 + 8).to_bytes(4, "big") + b"free" + bytes(8_000_000))
        engine = Compressor(target_mb=5)
        result = engine.compress(source, self.out, "instagram")
        self.assertEqual(result.status, "compressed", result.message)
        video = engine.probe(Path(result.output))["streams"][0]
        self.assertEqual(video["color_transfer"], "bt709")
        self.assertEqual(video["pix_fmt"], "yuv420p")

    def test_instagram_image_orientation_and_dimensions(self):
        result = Compressor().compress(self.jpeg, self.out, "instagram")
        self.assertEqual(result.status, "compressed", result.message)
        with Image.open(result.output) as image:
            self.assertEqual(image.size, (320, 480))
            self.assertNotIn(274, image.getexif())

    def test_custom_image_quality_has_real_effect(self):
        source = self.root / "photo_noise.bmp"
        Image.effect_noise((640, 480), 70).convert("RGB").save(source)
        low = Compressor(settings=ExportSettings(image_quality=30, image_max_mb=0)).compress(source, self.out, "instagram")
        high = Compressor(settings=ExportSettings(image_quality=95, image_max_mb=0)).compress(source, self.out, "instagram")
        self.assertEqual(low.status, "compressed", low.message)
        self.assertEqual(high.status, "compressed", high.message)
        self.assertGreater(high.after, low.after * 1.5)
        with Image.open(low.output) as a, Image.open(high.output) as b:
            self.assertEqual(a.size, b.size)

    def test_custom_image_size_ceiling_and_dimensions(self):
        source = self.root / "size_noise.bmp"
        Image.effect_noise((1200, 800), 70).convert("RGB").save(source)
        settings = ExportSettings(image_quality=95, image_max_mb=0.025, image_max_width=500, image_max_height=300)
        result = Compressor(settings=settings).compress(source, self.out, "instagram")
        self.assertEqual(result.status, "compressed", result.message)
        self.assertLessEqual(result.after, 25_000)
        with Image.open(result.output) as image:
            self.assertLessEqual(image.width, 500)
            self.assertLessEqual(image.height, 300)
            self.assertAlmostEqual(image.width / image.height, 1.5, delta=0.02)

    def test_transparent_png_exports_jpeg_with_white_background_and_size_cap(self):
        source = self.root / "alpha_noise.png"
        image = Image.effect_noise((600, 400), 70).convert("RGBA")
        image.putalpha(127)
        image.save(source, compress_level=0)
        settings = ExportSettings(image_max_mb=0.03, image_max_width=600, image_max_height=400)
        result = Compressor(settings=settings).compress(source, self.out, "instagram")
        self.assertEqual(result.status, "compressed", result.message)
        self.assertLessEqual(result.after, 30_000)
        self.assertEqual(Path(result.output).suffix, ".jpg")
        with Image.open(result.output) as image:
            self.assertEqual(image.mode, "RGB")
            self.assertLessEqual(image.width, 600)

    def test_custom_video_quality_has_real_effect_without_size_cap(self):
        low = Compressor(settings=ExportSettings(video_quality=20, video_max_mb=0)).compress(self.video, self.out, "instagram")
        high = Compressor(settings=ExportSettings(video_quality=95, video_max_mb=0)).compress(self.video, self.out, "instagram")
        self.assertEqual(low.status, "compressed", low.message)
        self.assertEqual(high.status, "compressed", high.message)
        self.assertGreater(high.after, low.after * 1.2)

    def test_custom_video_dimensions_and_fractional_size_ceiling(self):
        settings = ExportSettings(video_quality=100, video_max_mb=0.11, video_max_width=160, video_max_height=120)
        engine = Compressor(settings=settings)
        result = engine.compress(self.video, self.out, "instagram")
        self.assertEqual(result.status, "compressed", result.message)
        self.assertLessEqual(result.after, 110_000)
        video = engine.probe(Path(result.output))["streams"][0]
        self.assertEqual((video["width"], video["height"]), (160, 120))

    def test_custom_video_tiny_ceiling_is_skipped_without_partial_output(self):
        settings = ExportSettings(video_max_mb=0.01)
        result = Compressor(settings=settings).compress(self.video, self.out, "instagram")
        self.assertEqual(result.status, "skipped", result.message)
        self.assertFalse(list(self.out.glob(".medialite-*")))

    def test_conversion_saved_even_when_source_is_smaller(self):
        source = self.root / "small-transparent.png"
        Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(source)
        result = Compressor().compress(source, self.out, "instagram")
        self.assertEqual(result.status, "converted", result.message)
        with Image.open(result.output) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertTrue(all(channel > 245 for channel in image.getpixel((0, 0))))

    def test_heic_avif_gif_and_cmyk_to_jpeg(self):
        from pillow_heif import register_heif_opener
        register_heif_opener()
        for ext, format in (("heic", "HEIF"), ("avif", "AVIF"), ("gif", "GIF"), ("tiff", "TIFF")):
            with self.subTest(format=format):
                source = self.root / ("convert." + ext)
                Image.new("RGB", (64, 64), "red").save(source, format=format)
                result = Compressor().compress(source, self.out, "instagram")
                self.assertIn(result.status, {"compressed", "converted"}, result.message)
                with Image.open(result.output) as image:
                    self.assertEqual(image.format, "JPEG")
                    self.assertEqual(image.size, (64, 64))
        source = self.root / "print-cmyk.jpg"
        Image.new("CMYK", (64, 64), (0, 255, 255, 0)).save(source)
        result = Compressor().compress(source, self.out, "instagram")
        self.assertIn(result.status, {"compressed", "converted"}, result.message)
        with Image.open(result.output) as image:
            self.assertEqual(image.mode, "RGB")

    def test_flv_and_mxf_to_mp4(self):
        for ext, codec in (("flv", "flv"), ("mxf", "mpeg2video")):
            with self.subTest(ext=ext):
                source = self.root / ("sample." + ext)
                self.ff(["-i", str(self.video), "-r", "25", "-c:v", codec, "-an", str(source)])
                result = Compressor().compress(source, self.out, "instagram")
                self.assertIn(result.status, {"compressed", "converted"}, result.message)
                self.assertEqual(Path(result.output).suffix, ".mp4")

    def test_unknown_extension_detected_from_contents(self):
        source = self.root / "camera_unknown.bin"
        source.write_bytes(self.video.read_bytes())
        result = Compressor().compress(source, self.out, "instagram")
        self.assertIn(result.status, {"compressed", "converted"}, result.message)
        self.assertEqual(Path(result.output).suffix, ".mp4")

    def test_ffmpeg_still_fallback_composites_alpha_on_white(self):
        source = self.root / "fallback-alpha.png"
        Image.new("RGBA", (64, 64), (255, 0, 0, 0)).save(source)
        output = self.out / "fallback-white.jpg"
        Compressor().export_image_ffmpeg(source, output)
        with Image.open(output) as image:
            self.assertTrue(all(channel > 245 for channel in image.getpixel((32, 32))))

    def test_16bit_image_to_jpeg(self):
        source = self.root / "16-bit-export.png"
        Image.new("I;16", (64, 64), 32768).save(source)
        result = Compressor().compress(source, self.out, "instagram")
        self.assertIn(result.status, {"compressed", "converted"}, result.message)
        with Image.open(result.output) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertTrue(100 < image.getpixel((32, 32))[0] < 160)


if __name__ == "__main__":
    unittest.main(verbosity=2)
