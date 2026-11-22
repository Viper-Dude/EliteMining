"""Check that the EDDN listener reconnects after a silent connection."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import zmq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

import eddn_listener
from eddn_listener import EDDNListener


class FakeSocket:
    def __init__(self, owner):
        self.owner = owner
        self.closed = False
        owner.sockets.append(self)

    def connect(self, *_): pass
    def subscribe(self, *_): pass
    def setsockopt(self, *_): pass

    def recv(self):
        self.owner.recv_calls += 1
        if len(self.owner.sockets) >= 2:
            self.owner.listener.running = False
        raise zmq.Again()

    def close(self, linger=None):
        self.closed = True


class FakeContext:
    def __init__(self, owner): self.owner = owner
    def socket(self, _kind): return FakeSocket(self.owner)
    def term(self): pass


class ReconnectChecks(unittest.TestCase):
    def test_silent_connection_reconnects(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            self.listener = listener = EDDNListener(str(Path(folder) / 'c.db'))
            self.sockets, self.recv_calls = [], 0
            listener.running = True
            listener.SILENT_RECONNECT_SECS = 0
            with patch.object(eddn_listener.zmq, 'Context', lambda: FakeContext(self)):
                listener._listen_loop()
            self.assertEqual(len(self.sockets), 2)
            self.assertTrue(self.sockets[0].closed)

    def test_short_silence_keeps_connection(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            self.listener = listener = EDDNListener(str(Path(folder) / 'c.db'))
            self.sockets, self.recv_calls = [], 0
            listener.running = True

            def recv(sock):
                if self.recv_calls >= 3:
                    listener.running = False
                self.recv_calls += 1
                raise zmq.Again()
            with patch.object(FakeSocket, 'recv', recv), \
                 patch.object(eddn_listener.zmq, 'Context', lambda: FakeContext(self)):
                listener._listen_loop()
            self.assertEqual(len(self.sockets), 1)


if __name__ == '__main__':
    unittest.main()
