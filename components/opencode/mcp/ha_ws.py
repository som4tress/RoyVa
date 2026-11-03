"""Minimal dependency-free Home Assistant websocket client (registry reads only)."""
import base64, json, os, socket, ssl, struct, urllib.parse

_MAX = 1 << 26


class WSError(ValueError):
    pass


def _http_upgrade(url, timeout):
    u = urllib.parse.urlsplit(url)
    host = u.hostname
    port = u.port or (443 if u.scheme == 'wss' else 80)
    path = u.path or '/api/websocket'
    sock = socket.create_connection((host, port), timeout=timeout)
    if u.scheme == 'wss':
        sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
    key = base64.b64encode(os.urandom(16)).decode()
    sock.sendall(
        ('GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
         'Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n' % (path, host, port, key)).encode()
    )
    buf = b''
    while b'\r\n\r\n' not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise WSError('Home Assistant websocket handshake failed.')
        buf += chunk
    head, rest = buf.split(b'\r\n\r\n', 1)
    if b' 101 ' not in head.split(b'\r\n')[0]:
        raise WSError('Home Assistant websocket rejected the upgrade.')
    return sock, rest


def _send(sock, text):
    data = text.encode()
    header = bytearray([0x81])
    n = len(data)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126)
        header += struct.pack('!H', n)
    else:
        header.append(0x80 | 127)
        header += struct.pack('!Q', n)
    mask = os.urandom(4)
    header += mask
    sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))


class _Reader:
    def __init__(self, sock, rest):
        self.sock = sock
        self.buf = bytearray(rest)

    def _need(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise WSError('Home Assistant websocket closed unexpectedly.')
            self.buf += chunk

    def frame(self):
        payload = b''
        while True:
            self._need(2)
            b0, b1 = self.buf[0], self.buf[1]
            fin, opcode = b0 & 0x80, b0 & 0x0F
            masked, ln = b1 & 0x80, b1 & 0x7F
            used = 2
            if ln == 126:
                self._need(4)
                ln = struct.unpack('!H', bytes(self.buf[2:4]))[0]
                used = 4
            elif ln == 127:
                self._need(10)
                ln = struct.unpack('!Q', bytes(self.buf[2:10]))[0]
                used = 10
            if ln > _MAX:
                raise WSError('Home Assistant websocket frame too large.')
            mask = b''
            if masked:
                self._need(used + 4)
                mask = bytes(self.buf[used:used + 4])
                used += 4
            self._need(used + ln)
            chunk = bytes(self.buf[used:used + ln])
            del self.buf[:used + ln]
            if mask:
                chunk = bytes(c ^ mask[i % 4] for i, c in enumerate(chunk))
            if opcode == 0x8:
                raise WSError('Home Assistant websocket closed the connection.')
            if opcode == 0x9:
                self.sock.sendall(b'\x8a' + bytes([0x80]) + os.urandom(4))
                continue
            if opcode == 0xA:
                continue
            payload += chunk
            if fin:
                return payload.decode('utf-8', 'replace')


def call(url, token, cmds, timeout=8):
    """Send commands over one authenticated HA websocket; return {id: result}."""
    sock, rest = _http_upgrade(url, timeout)
    try:
        sock.settimeout(timeout)
        reader = _Reader(sock, rest)
        hello = json.loads(reader.frame())
        if hello.get('type') != 'auth_required':
            raise WSError('Unexpected Home Assistant websocket handshake.')
        _send(sock, json.dumps({'type': 'auth', 'access_token': token}))
        auth = json.loads(reader.frame())
        if auth.get('type') != 'auth_ok':
            raise WSError('Home Assistant registry authentication failed.')
        for cmd in cmds:
            _send(sock, json.dumps(cmd))
        out = {}
        pending = len(cmds)
        while pending:
            msg = json.loads(reader.frame())
            if 'id' not in msg:
                continue
            if not msg.get('success'):
                raise WSError('Home Assistant registry read failed: %s'
                              % (msg.get('error') or {}).get('code', 'unknown'))
            out[msg['id']] = msg.get('result')
            pending -= 1
        return out
    finally:
        try:
            sock.close()
        except OSError:
            pass
