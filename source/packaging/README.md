# Offline ready-folder packaging

The repository root ships a small Windows x64 launcher and the complete native application archive in `_internal/MediaPress.runtime.*`. Each part is below GitHub's 100 MiB file limit. **Code → Download ZIP includes the working offline package**, not just source code.

`MediaPress.exe` verifies the embedded manifest hash and each part's SHA-256, opens the parts as one seekable ZIP stream, and extracts into an owned staging directory under `_runtime`. The staged runtime is renamed into place only after completion. A matching marker and critical-file lengths allow later launches to reuse it. Cancelled or failed extraction cleans only that launcher's staging directory. Incomplete previous runtime folders are preserved when repaired. No downloader, account, server or internet access is used by the launcher.

The large media encoder still receives original file paths through the native application; this packaging change does not change its settings or encoding behavior.

Windows 10/11 x64 with .NET Framework 4.8, tested on Windows 11. The standard Windows framework compiler builds the launcher; no extra compiler download is required on the verified machine.

From the native application source folder:

```powershell
python packaging/run_tests.py --build-dir ../launcher-build
python packaging/build_ready.py --runtime-zip ../native-portable.zip --out ../ready --build-dir ../launcher-build --icon app.ico
```

`native-portable.zip` must contain one root folder, with the native `MediaPress.exe` and its complete `_internal` directory. The builder streams it into 90 MiB parts, generates the manifest and embeds its hash in the compiled launcher. Add the root guide, README and license files before publishing. Keep `_runtime` and launch error logs out of Git.

The ready ZIP and GitHub source ZIP have the same top-level user flow: extract the whole folder and run the visible `MediaPress.exe`. To build the native application itself, follow `../BUILD.txt`; its FFmpeg tools are inside the prepared application's `_internal/tools`, not the outer package-parts directory.
