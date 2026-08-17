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

VIEWPORT = (1600, 1400)


def main():
    url, out_png = sys.argv[1], sys.argv[2]
    css_file = sys.argv[3] if len(sys.argv) > 3 else None
    probe_file = sys.argv[4] if len(sys.argv) > 4 else None

    proc = subprocess.Popen(
        [CHROME, '--headless=new', '--disable-gpu', '--no-sandbox', '--no-first-run',
         '--hide-scrollbars', '--force-device-scale-factor=1',
         f'--user-data-dir={PROFILE}', f'--remote-debugging-port={PORT}',
         f'--window-size={VIEWPORT[0]},{VIEWPORT[1]}', 'about:blank'],
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
              'deviceScaleFactor': 1, 'mobile': False})
        call('Page.navigate', {'url': url})

        for _ in range(50):
            time.sleep(0.5)
            if js("document.querySelector('#itemDetailPage:not(.hide)')?'y':'n'") == 'y':
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
                 'document.head.appendChild(s);"ok"', 'returnByValue': True})
            time.sleep(2.5)
            print('injiziert:', js("document.getElementById('la-local')?'ja':'nein'"),
                  '| tokens sichtbar:',
                  js("getComputedStyle(document.documentElement).getPropertyValue('--la-hero-height').trim()") or '(leer)')

        if probe_file:
            print(js(open(probe_file, encoding='utf-8').read()))

        # Lazy images only start loading when scrolled into view, and capturing
        # before they finish shows blurhash placeholders that look exactly like a
        # washed-out theme bug. Walk the page, then wait for them to settle.
        js("window.scrollTo(0, document.body.scrollHeight); 1")
        time.sleep(2)
        js("window.scrollTo(0, 0); 1")
        # .blurhash-canvas stays in the DOM for good once created, so counting it
        # never reaches zero — only genuinely incomplete <img> elements count.
        for _ in range(25):
            time.sleep(1)
            pending = js("[].slice.call(document.images)"
                         ".filter(function(i){return !i.complete;}).length")
            if not pending:
                break
        time.sleep(6)
        print('unfertige <img> beim Ausloesen:', pending)

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
