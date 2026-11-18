# MediaPress 2.0.0 · interface and verification

## Result and scope

The rejected tall, scrolling interface is replaced by a compact native Windows media workspace: preview on the left, queue and two concise settings tabs on the right, persistent commands below. Only the queue scrolls. Dimensions open in a compact popup. The product is offline and does not require an account.

Covered surfaces: empty/add-choice, folder discovery, mixed file queue, image/video settings, advanced settings, original/result preview, playback/seek, importing, encoding, cancellation, errors/partial success, completion, open folder, CSV report, help/details, contact, themes, reduced effects, game chooser, Snake and memory.

The brand is MediaPress with the clickable English byline By Maher Bakran. Remove and clear actions have labels and sit on the left of the queue toolbar. The empty preview is keyboard/click accessible and opens a files-or-folder choice.

## Interaction and material

All buttons have a visible thin border, stable hit geometry, focus and pressed feedback. Hover uses a 130 ms transition and a repeating 1.6 s glass highlight while hovered. Primary-button highlights stay at the rim to preserve white-text contrast. Animations stop when hidden/disabled and in reduced-effects mode.

Regular glass is confined to the functional header and command dock. It samples the actual cached application backdrop, blurs that sample and slightly refracts the rim. Data, preview and forms remain opaque. No nested blur or full-screen continuous effects. Cache rebuilds follow backdrop/size changes, not hover frames.

Windows transparency, client-area animation and high-contrast settings select the conservative mode at startup. The in-app switch can reduce effects throughout the main window and popups. This does not claim a complete Windows high-contrast color-scheme implementation.

Explicit application palettes and themed popups prevent inherited dark native colors from colliding with light text styles. Numeric editors retain RTL control layout with LTR values; their widths are tested after theme changes. Dialog details and disabled controls use the same palette. Light and dark screenshots are provided.

## Games and compression

Starting compression opens a modeless game chooser. The progress bar observes actual batch progress; games do not control the worker. Closing, Escape, switching games and returning to the main app preserve the current game during the session. Snake pauses on deactivation/close; memory pauses unmatched-card timing while hidden. A visible Games button reopens the popup. A finished batch can be reviewed while play continues.

Memory has 10 levels with 3, 4, 5, 6, 8, 10, 12, 15, 18 and 20 pairs. Next level unlocks only after all pairs match. Snake advances through 10 speed levels, three food items per level, with collision/restart and keyboard/directional controls. State is retained during the application session, not across application restarts.

## Verification

- Automated engine, integration, interface and game checks: 48 tests in the final source suite; actual FFmpeg/Pillow conversions, not mock export results.
- A mixed corrupt-video/valid-image batch continues after the bad file, protects the original and exposes the successful result. Opening/closing games does not cancel that worker.
- Image/video control independence, optional output ceilings, routing beside each source, collisions, cancellation and source hashes are covered.
- Large-file boundary checks: valid sparse-padded MOV/MP4 above 2 GiB, a 12-minute clip and an image above the previous 256 MB boundary. This is not a performance benchmark of 2 GiB of actual camera footage.
- Main actions fit 1366×768, 1100×720 and 960×640 without a page scrollbar. Keyboard Tab/Delete, English/Arabic names, light/dark palettes, advanced-dialog cancellation and cached-glass/reduced-effects states are covered.
- Both games, all memory levels, collisions, next-level locking, retained state and real batch progress are checked.
- Packaged-app self-test uses actual bundled image/video encoders, decodes a real frame through Qt Multimedia, switches both themes and reopens a retained memory game.
- Visual evidence consists of Qt-rendered application captures. No claim of an independent user study or exhaustive hardware/display review.

Performance data is in performance.json: local offscreen render timing, not measured display FPS. The material is cached; a hover repaints its bounded control. Whole-window screenshot timing includes capture/copy overhead and varies with machine load. No universal 60 FPS claim is made.

## Applicable design checks

Native Windows scope: readable hierarchy, explicit actions, truthful progress, protected originals, recoverable errors, RTL/English mixing, keyboard focus, reduced effects, theme contrast and no unnecessary page scrolling. These checks apply to this personal utility in the UAE context without government or official-service styling. CSS browser support, web route/authentication/SEO, mobile safe areas and touch-device certification are not applicable and are not claimed.

## Limits

Windows x64 is the distribution target; this build was verified on the current Windows 11 machine. Windows 10 and other hardware have not been independently exercised. Playback support depends on the bundled Qt decoder and may differ from export support; external opening remains available. JPEG/MP4 export is lossy and quality/size depends on content and duration. Compression has no artificial input video-size or encoding-time cap; disk space, memory and processing time remain practical constraints. No unresolved functional blocker was found in the covered flows.
