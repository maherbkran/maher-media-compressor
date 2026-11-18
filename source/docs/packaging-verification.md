# Ready-folder distribution verification

The root `MediaPress.exe` now works with the included `_internal/MediaPress.runtime.*` package. The exact native MediaPress 2.1.0 archive is retained inside those parts (SHA-256 `34f00c8ef6406235d6c31519bf6597de11b150d676044dcfe7cc767ab18b552e`). Its encoder and approved interface have not been rebuilt for this distribution change.

Eight launcher tests passed: split-boundary and ZIP-directory seeks; exact offline extraction in Arabic/space-containing paths and cached reopen; missing part; corrupted part; mixed manifest; ZIP traversal protection; cancellation cleanup and restart; repair while preserving the previous runtime.

The actual root executable was started from the ready repository with a self-test output path containing Arabic and spaces. It prepared the complete runtime, launched the bundled application, and passed five encoder checks plus desktop checks: both themes, the approved CSS hash, native video frames and reopening games with session state. A second prepare-only invocation returned successfully without changing the ready marker. The existing 58 native application tests and bundled release smoke results remain documented in `verification.md`.

The launcher verifies package hashes, uses bounded read buffers and a seekable stream across parts, and performs no network operations. The source ZIP includes ordinary Git binary files, not LFS pointers. Each package part is below 100 MiB. Local `_runtime` caches and launch logs are excluded from Git and the downloadable package.

Verified on the current Windows 11 x64 machine. No additional Windows 10 or display/GPU performance certification is claimed.
