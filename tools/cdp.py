"""Minimal Chrome DevTools Protocol client: stdlib only, no websockets package.

    python cdp.py <url> <js-expression-file>

Launches headless Chrome with the authenticated profile, navigates, waits, then
evaluates the expression and prints the JSON result. Enough CDP to run
Runtime.evaluate, which is all the measuring needs.
"""

import base64
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.request

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
# LA_PROFILE lets the login page be rendered from a signed-out profile.
PROFILE = os.environ.get('LA_PROFILE') or os.path.expandvars(r'%LOCALAPPDATA%\liquidapple-dev-chrome')
# LA_PORT lets two renders run at once — each needs its own debugging port
# *and* its own LA_PROFILE, because chrome locks the profile with LevelDB.
PORT = int(os.environ.get('LA_PORT', 9333))


class WS:
    """Just enough RFC 6455 for text frames on a trusted local socket."""

    def __init__(self, url):
        _, rest = url.split('://', 1)
        hostport, path = rest.split('/', 1)
        host, port = hostport.split(':')
        self.sock = socket.create_connection((host, int(port)), timeout=40)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            f'GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\n'
            f'Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n'
            'Sec-WebSocket-Version: 13\r\n\r\n'.encode())
        buf = b''
        while b'\r\n\r\n' not in buf:
            buf += self.sock.recv(4096)
        self.buf = buf.split(b'\r\n\r\n', 1)[1]

    def send(self, obj):
        payload = json.dumps(obj).encode()
        header = b'\x81'
        n = len(payload)
        if n < 126:
            header += struct.pack('!B', n | 0x80)
        elif n < 65536:
            header += struct.pack('!BH', 126 | 0x80, n)
        else:
            header += struct.pack('!BQ', 127 | 0x80, n)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(header + mask + masked)

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError('socket closed')
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        while True:
            b1, b2 = self._read(2)
            opcode, length = b1 & 0x0F, b2 & 0x7F
            if length == 126:
                length = struct.unpack('!H', self._read(2))[0]
            elif length == 127:
                length = struct.unpack('!Q', self._read(8))[0]
            data = self._read(length)
            if opcode == 1:
                return json.loads(data)
            if opcode == 8:
                raise EOFError('server closed')


def main():
    url, js_file = sys.argv[1], sys.argv[2]
    expression = open(js_file, encoding='utf-8').read()

    proc = subprocess.Popen(
        [CHROME, '--headless=new', '--disable-gpu', '--no-sandbox', '--no-first-run',
         '--hide-scrollbars', '--force-device-scale-factor=1',
         f'--user-data-dir={PROFILE}', f'--remote-debugging-port={PORT}',
         '--window-size=1600,1000', 'about:blank'],
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
        msg_id = [0]

        def call(method, params=None, wait=True):
            msg_id[0] += 1
            mine = msg_id[0]
            ws.send({'id': mine, 'method': method, 'params': params or {}})
            if not wait:
                return None
            while True:
                res = ws.recv()
                if res.get('id') == mine:
                    return res

        call('Page.enable')
        call('Runtime.enable')
        call('Page.navigate', {'url': url})
        # The SPA renders after its own fetches; polling beats a fixed sleep.
        for _ in range(40):
            time.sleep(0.5)
            r = call('Runtime.evaluate', {
                'expression': "document.querySelector('#itemDetailPage:not(.hide)') ? 'ready' : 'wait'",
                'returnByValue': True})
            if r.get('result', {}).get('result', {}).get('value') == 'ready':
                break
        time.sleep(3)

        r = call('Runtime.evaluate', {'expression': expression, 'returnByValue': True,
                                      'awaitPromise': True})
        result = r.get('result', {})
        if 'exceptionDetails' in result:
            print('JS-Fehler:', json.dumps(result['exceptionDetails'])[:800])
        print(result.get('result', {}).get('value'))
    finally:
        proc.terminate()


if __name__ == '__main__':
    main()
