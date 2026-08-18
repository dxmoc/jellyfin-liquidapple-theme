# tools

Render a page of a **live** Jellyfin with the local build swapped in, so the
theme can be judged and measured against the real client instead of a mock.

    python tools/shot.py <page-url> out.png dist/liquidapple.css [probe.js]

`shot.py` disables whatever Custom CSS the server injects and injects
`dist/liquidapple.css` instead, so nothing on the server has to change. Pass a
JS file as the 4th argument to print measurements (computed styles, box
geometry) alongside the screenshot. It may return a Promise.

By default it captures exactly one viewport — what the device actually shows.

| Variable | Effect |
| --- | --- |
| `LA_VIEWPORT=430x932` | emulated device viewport (default `1600x1400`). Under 800px wide also sends an iPhone user agent, because `.layout-mobile` comes from the UA, not the window size |
| `LA_SCROLL=1200` | scroll down before capturing; a value ≤ 1 is read as a fraction of the page |
| `LA_FULLPAGE=1` | capture the whole page (see the trap below — it distorts `vh`) |
| `LA_MOTION=1` | emulate `prefers-reduced-motion: no-preference` |
| `LA_LANG=en-US` | claim this browser language. The display language on this server is *Auto*, so the client follows the browser — english shots need no change on the server |
| `LA_AUTOPLAY=1` | drop chrome's gesture requirement, so a probe can start playback |
| `LA_QUALITY=88` | encoder quality for lossy output |

The output **format comes from the file extension** — `.png`, `.jpg` or `.webp`,
encoded by chrome itself. The readme's assets are webp straight out of a run;
nothing converts them afterwards, and there is still no dependency to install.

`LA_MOTION` matters more than it looks: Windows animations are off on this
machine, so `reduce` is permanently on and every spring, entrance and hover
transition silently falls back. Without this flag the motion work cannot be
reviewed at all — not in the browser, not here.

## One-time setup

Chrome needs a profile that is logged in. Credentials never touch the tooling —
you type them into the browser yourself:

    chrome.exe --user-data-dir=%LOCALAPPDATA%\liquidapple-dev-chrome \
               --new-window https://your-jellyfin/web/

Log in, close that window (the profile is locked while it runs), then use the
scripts. Revoke any time by deleting the profile directory or dropping the
session under Dashboard -> Devices.

`cdp.py` is the minimal DevTools-Protocol client the above builds on: a
stdlib-only WebSocket good enough for `Runtime.evaluate`, so there is no
dependency to install.

## Traps worth remembering

- **`captureBeyondViewport` does not paint CSS background images.** This one cost
  a whole session. Jellyfin cards carry their artwork as a `background-image`,
  and the synthetic oversized raster falls back to the blurhash canvas sitting
  behind it — so a full-page shot came out as placeholder mush while the DOM
  insisted all 14 images were loaded and their canvases hidden. Proof: remove
  the canvases and the same capture renders bare placeholder icons, not the
  artwork. A viewport capture of the identical page is sharp. Growing the real
  viewport is the only way the artwork below the fold paints, which is what
  `LA_FULLPAGE` does — at the price of `vh` units resolving against the page
  height. **Never measure hero geometry in a `LA_FULLPAGE` shot.**
- **It also grabs the full scroll *width*.** Horizontal rows (cast, "similar")
  make that several times the viewport, so the real 1600px layout renders as a
  narrow column that looks exactly like a broken layout. Another reason the
  plain viewport capture is the default.
- **Lazy images need scrolling and time**, and neither obvious ready signal
  works. `document.images` is *empty* on the mobile layout — the artwork is all
  `background-image`. `.blurhash-canvas` stays in the DOM permanently, so its
  presence means nothing (its `.lazy-hidden` class does: that is jellyfin's own
  "loaded" marker). Wait on `.cardImageContainer` having a background image.
- **Cards outside the viewport *horizontally* never load.** Every overflow row
  keeps most of its cards off to the right, and no amount of vertical scrolling
  brings them in. Counting them as pending means waiting out the full timeout on
  every run — the ready check has to skip them.
