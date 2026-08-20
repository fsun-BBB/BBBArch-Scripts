# Image Compressor

A single-file, browser-based batch image compressor. Drop images in, pick how hard to
squeeze, download the results as a ZIP.

Built for the everyday case of getting renders and screenshots under an email or upload
limit without opening Photoshop or handing files to an online service.

## Use it

Open `index.html` in a browser. That is the whole install — no build step, no server,
no dependencies.

## Why it is a single file

**Nothing leaves the machine.** There are no network calls of any kind: no CDN scripts,
no upload endpoint, no analytics. Every image is decoded, re-encoded and zipped locally
in the page. That matters because the files being compressed are usually unreleased
project renders.

The ZIP writer is hand-rolled (stored entries, since the payloads are already
compressed), which is why there is no JSZip dependency to fetch.

## Modes

| Mode | Result | Method |
| :-- | :-- | :-- |
| **Compress less** | ~25% smaller | Gentlest encode that reaches the target |
| **Compress more** | ~60% smaller | Still full resolution |
| **Compress max** | ~90% smaller | Resizes if quality alone cannot get there |
| **Target size** | A size you name | Binary-searches quality, then resolution |

Each mode reports what it actually achieved per file, and flags any image that missed
its target rather than silently under-delivering. Files that would have grown are kept
at their original size and marked.

Output is WebP where the browser supports it, JPEG otherwise. Quality and maximum
dimension can be overridden per run.

## Notes

- Encoding happens on the main thread via `createImageBitmap` and `canvas.toBlob`.
  A few hundred images is comfortable; several thousand will make the tab sluggish.
- Transparency is preserved in WebP and lost in the JPEG fallback, as usual.
- No EXIF is carried through — orientation is baked in during decode, metadata is
  dropped. Treat the output as delivery copies, not archival originals.
