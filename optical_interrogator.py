import socket
import threading
import time
import struct

class OpticalInterrogator:
    def __init__(self, host="192.168.1.2", port=49361, callback=None):
        self.host = host
        self.port = port
        self.callback = callback
        self.running = False
        self.sock = None
        self.thread = None
        self.channel_index = 0  # padrão: canal 0
        self.available_wavelengths = []

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self.read_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
            except Exception:
                pass

    def read_loop(self):
        try:
            self.sock = socket.create_connection((self.host, self.port))
            self.sock.settimeout(2.0)
            print(f"[INFO] Conectado ao SM130 em {self.host}:{self.port}")
            t0 = time.perf_counter()

            while self.running:
                # Header: 2 bytes (0xAA55) + 1 byte (número de canais)
                header = self._recv_exact(3)
                if not header or header[0:2] != b'\xAA\x55':
                    print("[ERRO] Header inválido ou conexão perdida.")
                    break

                num_channels = header[2]
                data_bytes = self._recv_exact(4 * num_channels)
                if not data_bytes:
                    break

                wavelengths = list(struct.unpack(f">{num_channels}f", data_bytes))  # big endian
                self.available_wavelengths = wavelengths

                if self.channel_index < len(wavelengths):
                    selected_value = wavelengths[self.channel_index]
                    t_now = (time.perf_counter() - t0) * 1000
                    if self.callback:
                        self.callback(t_now, [selected_value], f"Canal {self.channel_index}")

        except Exception as e:
            print(f"[Erro TCP com SM130] {e}")

    def _recv_exact(self, n):
        buf = b''
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

    def get_available_wavelengths(self):
        return self.available_wavelengths
