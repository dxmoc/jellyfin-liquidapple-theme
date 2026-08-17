# tools

Render a page of a **live** Jellyfin with the local build swapped in, so the
theme can be judged and measured against the real client instead of a mock.

    python tools/shot.py <page-url> out.png dist/liquidapple.css [probe.js]

`shot.py` disables whatever Custom CSS the server injects and injects
`dist/liquidapple.css` instead, so nothing on the server has to change. Pass a
JS file as the 4th argument to print measurements (computed styles, box
geometry) alongside the screenshot.

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

## Two traps worth remembering

- **`captureBeyondViewport` grabs the full scroll width.** Horizontal rows (cast,
  "similar") make that several times the viewport, and the real 1600px layout
  then renders as a narrow column that looks exactly like a broken layout. Always
  clip to the viewport width.
- **Lazy images need scrolling and time.** Capturing early shows blurhash
  placeholders, which look exactly like washed-out artwork. `.blurhash-canvas`
  stays in the DOM permanently, so it is useless as a ready signal — wait on
  incomplete `<img>` elements instead.
