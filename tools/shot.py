"""Render a live Jellyfin page with a local stylesheet swapped in.

    python shot.py <url> <out.png> [css-file] [probe.js]

Disables whatever Custom CSS the server currently injects and injects the local
build instead, so the theme can be reviewed against the real client without
touching any server setting. Reuses the WS client from cdp.py.
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


def main():
    url, out_png = sys.argv[1], sys.argv[2]
    css_file = sys.argv[3] if len(sys.argv) > 3 else None
    probe_file = sys.argv[4] if len(sys.argv) > 4 else None

    proc = subprocess.Popen(
        [CHROME, '--headless=new', '--disable-gpu', '--no-sandbox', '--no-first-run',
         '--hide-scrollbars', '--force-device-scale-factor=1',
         f'--user-data-dir={PROFILE}', f'--remote-debugging-port={PORT}',
         f'--window-size={VIEWPORT[0]},{VIEWPORT[1]}']
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
            r = call('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
            det = r.get('result', {}).get('exceptionDetails')
            if det:
                print('JS-Fehler:', json.dumps(det)[:600])
            return r.get('result', {}).get('result', {}).get('value')

        call('Page.enable')
        call('Runtime.enable')
        call('Emulation.setDeviceMetricsOverride',
             {'width': VIEWPORT[0], 'height': VIEWPORT[1],
              'deviceScaleFactor': 1, 'mobile': MOBILE})
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
        # document.images, so counting incomplete <img> misses them entirely and
        # the capture lands on blurhash placeholders. Walk the page in steps so
        # every row enters the viewport, then confirm the card backgrounds have
        # actually resolved to a URL.
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0, 0.5, 0.0):
            js(f"window.scrollTo(0, document.body.scrollHeight*{frac}); 1")
            time.sleep(1.2)

        for _ in range(30):
            time.sleep(1)
            pending = js("""(function(){
                var imgs=[].slice.call(document.images)
                    .filter(function(i){return !i.complete;}).length;
                var cards=[].slice.call(
                    document.querySelectorAll('.cardImageContainer,.listItemImage'))
                    .filter(function(e){
                        return getComputedStyle(e).backgroundImage === 'none';
                    }).length;
                return imgs + cards;
            })()""")
            if not pending:
                break
        time.sleep(4)
        print('ausstehend beim Ausloesen:', pending)

        # Horizontal scrollers (cast, "similar") make scrollWidth several times
        # the viewport, and captureBeyondViewport grabs all of it — which renders
        # the real 1600px layout as a narrow column and looks like a layout bug.
        # Clip to the viewport width explicitly.
        height = js('Math.min(document.documentElement.scrollHeight, 6000)')
        shot = call('Page.captureScreenshot', {
            'format': 'png', 'captureBeyondViewport': True,
            'clip': {'x': 0, 'y': 0, 'width': VIEWPORT[0],
                     'height': height or VIEWPORT[1], 'scale': 1}})
        data = shot.get('result', {}).get('data')
        if not data:
            sys.exit('screenshot failed: ' + json.dumps(shot)[:300])
        with open(out_png, 'wb') as fh:
            fh.write(base64.b64decode(data))
        print('geschrieben:', out_png, os.path.getsize(out_png), 'bytes')
    finally:
        proc.terminate()


if __name__ == '__main__':
    main()
