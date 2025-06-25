import serial
import threading
import time

class SerialManager:
    def __init__(self, on_data_callback, on_error_callback, baud_rate=115200):
        self.serial_port = None
        self.baud_rate = baud_rate
        self.running = False
        self.thread = None
        self.on_data = on_data_callback
        self.on_error = on_error_callback

    def set_port(self, port):
        self.serial_port = port

    def start(self):
        if self.serial_port is None:
            self.on_error("[Erro] Porta Serial não definida.")
            return 
        
        self.running = True
        self.thread = threading.Thread(target=self.read_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def read_loop(self):
        try:
            with serial.Serial(self.serial_port, self.baud_rate) as ser:
                time.sleep(2)
                t0 = time.perf_counter()
                while self.running:
                    try:
                        line = ser.readline().decode(errors='ignore').strip()
                        parts = line.split(',')
                        if len(parts) >= 4 and all(p.strip().isdigit() for p in parts):
                            emg1, emg2, fsr1, fsr2 = map(int, parts)
                            t_now = (time.perf_counter() - t0) * 1000
                            self.on_data(t_now, emg1, emg2, fsr1, fsr2)
                    except Exception as e:
                        self.on_error(f"[Erro de Leitura Serial] {e}")
        except Exception as e:
            self.on_error(f"[Erro de Inicialização Serial] {e}")