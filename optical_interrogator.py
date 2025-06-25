import time 
import math
import threading
import random

class OpticalInterrogator:
    def __init__(self, callback, freq=0.01):
        self.running = False
        self.callback = callback
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.t0 = None
        self.freq = freq

    def start(self):
        self.running = True
        self.t0 = time.perf_counter()
        self.thread.start()

    def stop(self):
        self.running = False

    def run(self):
        while self.running:
            t_now = (time.perf_counter() - self.t0) * 1000
            values = [
                1550 + 0.5 * math.sin(time.time() * 2 * math.pi * 0.1 + i) + random.uniform(-0.05, 0.05)
                for i in range(3)
            ]
            self.callback(t_now, values)
            time.sleep(self.freq)
        