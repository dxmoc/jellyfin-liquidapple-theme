"""Render a live Jellyfin page with a local stylesheet swapped in.

    python shot.py <url> <out.png> [css-file] [probe.js]

Disables whatever Custom CSS the server currently injects and injects the local
build instead, so the theme can be reviewed against the real client without
touching any server setting. Reuses the WS client from cdp.py.

Environment:
    LA_VIEWPORT=430x932   the emulated device viewport (default 1600x1400)
    LA_SCROLL=1200        scroll this far down before capturing; a value <= 1 is
                          read as a fraction of the page
    LA_FULLPAGE=1         capture the whole page instead of one viewport, by
                          growing the viewport to the page height first
    LA_LANG=en-US         claim this browser language; jellyfin's display
                          language is Auto, so the client follows it
    LA_QUALITY=88         encoder quality for .webp / .jpg output (the format
                          comes from the output file's extension)
    LA_AUTOPLAY=1         let a probe start playback: a scripted click is not a
                          user gesture, so chrome blocks the video otherwise
    LA_MOTION=1           emulate prefers-reduced-motion: no-preference. Windows
                          animations are off on this machine, so reduce is
                          otherwise always on and the motion path — springs,
                          entrances — cannot be reviewed at all
"""

import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

from cdp import CHROME, PORT, PROFILE, WS

# LA_VIEWPORT=420x900 renders the mobile layout. Jellyfin picks .layout-mobile
# from its own detection, so mobile:true has to be passed through as well.
_vp = os.environ.get('LA_VIEWPORT', '1600x1400').split('x')
VIEWPORT = (int(_vp[0]), int(_vp[1]))
MOBILE = VIEWPORT[0] < 800
SCROLL = float(os.environ.get('LA_SCROLL', 0))
FULLPAGE = os.environ.get('LA_FULLPAGE') not in (None, '', '0')
MOTION = os.environ.get('LA_MOTION') not in (None, '', '0')
# The display language is a per-user setting, and this server's is set to Auto —
# meaning jellyfin reads it off the browser. So the readme's english shots need
# no change on the server, only a browser claiming to be english.
LANG = os.environ.get('LA_LANG')
# A probe that starts playback clicks the button from script, which chrome does
# not count as a user gesture — without this the video never leaves paused.
AUTOPLAY = os.environ.get('LA_AUTOPLAY') not in (None, '', '0')
QUALITY = int(os.environ.get('LA_QUALITY', 88))
MAX_HEIGHT = 6000


def main():
    url, out_png = sys.argv[1], sys.argv[2]
    css_file = sys.argv[3] if len(sys.argv) > 3 else None
    probe_file = sys.argv[4] if len(sys.argv) > 4 else None

    proc = subprocess.Popen(
        [CHROME, '--headless=new', '--disable-gpu', '--no-sandbox', '--no-first-run',
         '--hide-scrollbars', '--force-device-scale-factor=1',
         f'--user-data-dir={PROFILE}', f'--remote-debugging-port={PORT}',
         f'--window-size={VIEWPORT[0]},{VIEWPORT[1]}']
        # --lang alone moves chrome's own UI; jellyfin reads navigator.language,
        # which follows --accept-lang.
        + ([f'--lang={LANG}', f'--accept-lang={LANG}'] if LANG else [])
        + (['--autoplay-policy=no-user-gesture-required'] if AUTOPLAY else [])
        # Jellyfin picks .layout-mobile from the user agent, not the window size,
        # so a narrow viewport alone renders the desktop layout squeezed thin.
        + ([('--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)'
             ' AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0'
             ' Mobile/15E148 Safari/604.1')] if MOBILE else [])
        + ['about:blank'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        target = None
        for _ in range(60):
            time.sleep(0.5)
            try:
                pages = json.loads(urllib.request.urlopen(
                    f'http://127.0.0.1:{PORT}/json', timeout=5).read())
                target = next((p for p in pages if p.get('type') == 'page'), None)
                if target:
                    break
            except Exception:
                continue
        if not target:
            sys.exit('no debuggable page appeared')

        ws = WS(target['webSocketDebuggerUrl'])
        counter = [0]

        def call(method, params=None):
            counter[0] += 1
            mine = counter[0]
            ws.send({'id': mine, 'method': method, 'params': params or {}})
            while True:
                res = ws.recv()
                if res.get('id') == mine:
                    return res

        def js(expr):
            # awaitPromise lets a probe be async — decoding an image, waiting on
            # a load event — without changing anything for plain expressions.
            r = call('Runtime.evaluate', {'expression': expr, 'returnByValue': True,
                                          'awaitPromise': True})
            det = r.get('result', {}).get('exceptionDetails')
            if det:
                print('JS-Fehler:', json.dumps(det)[:600])
            return r.get('result', {}).get('result', {}).get('value')

        call('Page.enable')
        call('Runtime.enable')
        call('Emulation.setDeviceMetricsOverride',
             {'width': VIEWPORT[0], 'height': VIEWPORT[1],
              'deviceScaleFactor': 1, 'mobile': MOBILE})
        # Without this a headless page reports document.hasFocus() === false:
        # el.focus() still moves activeElement, but not one :focus rule applies,
        # so every focus-state measurement silently reads the resting style.
        call('Emulation.setFocusEmulationEnabled', {'enabled': True})
        if LANG:
            call('Emulation.setLocaleOverride', {'locale': LANG})
        if MOTION:
            call('Emulation.setEmulatedMedia',
                 {'features': [{'name': 'prefers-reduced-motion',
                                'value': 'no-preference'}]})
        call('Page.navigate', {'url': url})

        for _ in range(50):
            time.sleep(0.5)
            # Any visible page, not just the item page — this tool is used on
            # home, library, dashboard and login too.
            if js("document.querySelector('.page:not(.hide)')?'y':'n'") == 'y':
                break
        time.sleep(3)

        if css_file:
            css = open(css_file, encoding='utf-8').read()
            # Turn off the server's Custom CSS (jellyfin injects it as a <style>
            # holding an @import) so it cannot fight the build under review.
            killed = js("""
              (function(){
                var n=0;
                document.querySelectorAll('style,link[rel=stylesheet]').forEach(function(el){
                  var t=(el.textContent||'')+(el.href||'');
                  if(/jsdelivr|github\\.io|ElegantFin|liquidapple|paste\\./i.test(t)){
                    if(el.sheet) el.sheet.disabled=true;
                    el.remove(); n++;
                  }
                });
                return n;
              })()""")
            print('deaktivierte Custom-CSS-Knoten:', killed)
            call('Runtime.evaluate', {'expression':
                 'var s=document.createElement("style");'
                 's.id="la-local";s.textContent=' + json.dumps(css) + ';'
                 # Jellyfin links themes/dark/theme.css from inside <body> and
                 # injects Custom CSS there too, so a <style> in <head> loses
                 # every equal-specificity tie. Appending to body reproduces the
                 # real cascade position instead of a stricter one.
                 'document.body.appendChild(s);"ok"', 'returnByValue': True})
            time.sleep(2.5)
            print('injiziert:', js("document.getElementById('la-local')?'ja':'nein'"),
                  '| tokens sichtbar:',
                  js("getComputedStyle(document.documentElement).getPropertyValue('--la-hero-height').trim()") or '(leer)')

        if probe_file:
            print(js(open(probe_file, encoding='utf-8').read()))

        # Lazy loading is viewport-driven, and most jellyfin cards carry their
        # artwork as a CSS background-image — which never appears in
        # document.images, so counting incomplete <img> misses them entirely.
        # Walk the page in steps so every row enters the viewport, then confirm
        # the card backgrounds have actually resolved to a URL. Cards sitting
        # outside the viewport *horizontally* (the off-screen half of every
        # "overflow" row) never load no matter how far the page scrolls, so
        # counting them means waiting out the full timeout on every single run.
        def settle(walk=True):
            # The walk parks the page back at the top when it is done, so anything
            # that wants a specific scroll position has to settle first and scroll
            # afterwards — see the LA_SCROLL branch below.
            if walk:
                for frac in (0.0, 0.25, 0.5, 0.75, 1.0, 0.5, 0.0):
                    js(f"window.scrollTo(0, document.body.scrollHeight*{frac}); 1")
                    time.sleep(1.2)
            pending = None
            for _ in range(30):
                time.sleep(1)
                pending = js("""(function(){
                    var imgs=[].slice.call(document.images)
                        .filter(function(i){return !i.complete;}).length;
                    var cards=[].slice.call(
                        document.querySelectorAll('.cardImageContainer,.listItemImage'))
                        .filter(function(e){
                            var r=e.getBoundingClientRect();
                            if(r.right<=0 || r.left>=innerWidth) return false;
                            return getComputedStyle(e).backgroundImage === 'none';
                        }).length;
                    return imgs + cards;
                })()""")
                if not pending:
                    break
            time.sleep(4)
            return pending

        print('ausstehend beim Ausloesen:', settle())

        if FULLPAGE:
            # captureBeyondViewport does NOT re-paint CSS background images: the
            # synthetic raster falls back to jellyfin's blurhash canvas, so a
            # full-page shot came out as placeholder mush while the DOM insisted
            # every image was loaded. Growing the real viewport is the only way
            # the artwork below the fold actually paints — at the price of vh
            # units now resolving against the page height, so hero sizing in a
            # LA_FULLPAGE shot is NOT to be trusted. Measure those in the
            # default one-viewport mode.
            height = min(js('document.documentElement.scrollHeight') or VIEWPORT[1],
                         MAX_HEIGHT)
            call('Emulation.setDeviceMetricsOverride',
                 {'width': VIEWPORT[0], 'height': int(height),
                  'deviceScaleFactor': 1, 'mobile': MOBILE})
            time.sleep(2)
            print('Vollseite: Viewport auf', VIEWPORT[0], 'x', int(height),
                  '| ausstehend:', settle())
        elif SCROLL:
            # settle() above already walked the page; walking again here would
            # park it back at the top and the capture would silently be taken at
            # y=0 — which is exactly what every scrolled shot used to be.
            js('window.scrollTo(0, %s); 1' % (
                f'document.body.scrollHeight*{SCROLL}' if SCROLL <= 1 else SCROLL))
            time.sleep(2)
            settle(walk=False)
            print('gescrollt auf y =', js('Math.round(window.scrollY)'))

        # A plain viewport capture. Horizontal scrollers (cast, "similar") make
        # scrollWidth several times the viewport width, and captureBeyondViewport
        # would grab all of it — rendering the real layout as a narrow column
        # that looks exactly like a layout bug.
        # Chrome encodes webp itself, so the readme's assets need no pillow and
        # no second pass — the extension picks the encoder.
        fmt = 'png' if out_png.lower().endswith('.png') else (
              'jpeg' if out_png.lower().endswith(('.jpg', '.jpeg')) else 'webp')
        params = {'format': fmt}
        if fmt != 'png':
            params['quality'] = QUALITY
        shot = call('Page.captureScreenshot', params)
        data = shot.get('result', {}).get('data')
        if not data:
            sys.exit('screenshot failed: ' + json.dumps(shot)[:300])
        with open(out_png, 'wb') as fh:
            fh.write(base64.b64decode(data))
        print('geschrieben:', out_png, os.path.getsize(out_png), 'bytes', f'({fmt})')
    finally:
        proc.terminate()


if __name__ == '__main__':
    main()
