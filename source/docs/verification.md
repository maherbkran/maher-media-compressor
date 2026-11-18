# MediaPress 2.1 · approved desktop design verification

## Delivered scope

The owner-supplied MediaPress.html is the design source. Its base CSS is retained with LF line endings and a recorded SHA-256 in assets/ui/reference.json. The layout, typography, portrait, Phosphor icons, palette, glass slider lenses, image comparison and game artwork come from that reference. Native additions are isolated in native.css and use the same tokens and component shapes.

The application entry point is launcher.py -> desktop_window.py. The earlier widgets UI is compatibility/test scaffolding and is not the shipped user journey.

Covered surfaces: add files/folder, native drag/drop, mixed queue, image/video controls, transactional advanced settings, output location, original/result/split image comparison, expanded preview, native video playback/seek/mute, importing, progress/cancel, completed/partial/error states, CSV, profile/contact/help, light/dark, reduced effects, and the approved Snake/memory overlays.

## Preserved product behavior

- Native FFmpeg/Pillow export remains unchanged: all videos MP4/H.264/AAC, all images JPEG, white matte/first frame for image sequences, protected originals and collision-safe names.
- The default destination follows each original. A native folder picker can select a shared destination. Report and open-result controls use actual saved paths.
- There is no artificial video input-size cap or probe/encode time limit. Zero disables the optional output ceiling.
- The UI never reads a large video into a JavaScript ArrayBuffer or WebAssembly heap. It submits file identities/settings to the native worker.
- Image preview sizes are measured native temporary exports, not estimates. Original/result images are bounded preview renders; the saved file retains the requested export dimensions. Larger outputs are explicitly labeled as an increase.
- Qt Multimedia plays native local files, independently of the browser engine's codec support. Its display tracks the approved video stage and hides/pauses under overlays. Closing games does not cancel compression.
- Advanced settings/presets are drafts until Apply. Cancel discards them. Changing a saved item's settings makes the queue label that change rather than implying the old output uses the new options.

## Runtime boundary

The embedded view uses an ephemeral Qt WebEngine profile. Static assets and token-registered previews are served only on 127.0.0.1 with no upload or arbitrary-path endpoint. Byte-range reads are streamed in bounded chunks, including offsets beyond 2 GiB. Content policy and request interception prevent external network requests or navigation to another page. Credits/contact open in the user's browser only after a user action. File selection and output paths are native decisions; the web interface cannot supply arbitrary filesystem paths.

Native file-only FFmpeg protocols and the Chromium sandbox remain enabled. No sandbox-disabling flag is used. Headless QA disables GPU for its virtual display only. The raw personal photograph is not distributed.

## Verification evidence

The suite covers actual encoders, original hashes, HEIC/AVIF/CMYK/GIF/16-bit images, video rotation/HDR/audio/formats, output caps, mixed folders, cancellation, and sparse >2 GiB containers. New desktop tests exercise real exports, native playback/seek, renderer-child local drops, both themes, imported stylesheet/font integrity, advanced cancellation/apply, large virtual queues, and all ten approved memory levels. Local-media tests cover private routes, ranges and >2 GiB offsets.

The packaged-app self-test loads the approved view/font, processes a mixed five-file queue beside its originals, reopens a retained memory game, decodes native video frames and checks both theme colors. It is run against the bundled executable and tools.

Visual checks use 1366×768, 1100×720 and 960×650 content areas. The file list scrolls internally. Small-height adaptations retain the same layout/concept; only spacing and queue height are reduced. Settings/output/help/game overlays use the same themes. The original design's reduced-motion, reduced-effects, transparency and forced-color fallbacks remain in the retained stylesheet.

Snapshots are Qt-rendered captures, and geometry/contrast-state checks come from the actual embedded document. They are not an independent user study or a general GPU/display benchmark. No universal frame-rate, cross-browser, mobile, or Windows 10 verification is claimed. Source smoke and packaged smoke reports are kept with release QA evidence; README screenshots show the delivered interface.

## Design review boundaries

This is a personal Windows utility. Applicable checks include Arabic RTL/English mixing, readable text, keyboard/focus, clear actions, truthful progress, recovery, protected originals, bounded scrolling, reduced effects and local processing. UAE government identity, web authentication/SEO and mobile-device certification are not applicable. The owner's approved reference takes precedence over generic visual preferences. Its optical glass treatment is retained as designed rather than claimed as an Apple platform material.

## Limits

Export is lossy; size/quality depends on content and duration. Preview may be scaled and decoder coverage differs by format. Files that are encrypted, corrupted or unsupported by the supplied decoders may fail individually without blocking the rest of the queue. Disk space, memory and processing time remain physical constraints. Sparse >2 GiB fixtures validate boundaries and streaming, not the speed of encoding 2 GiB of camera footage. Game state is retained within the current session, not after application restart.

Final source suite: **58 tests passed**. The bundled Windows executable passed its desktop/encoder smoke test, including five native exports, both themes and native video frames.
