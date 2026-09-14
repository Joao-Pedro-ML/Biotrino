"""Gerenciamento robusto da conexao serial com a placa BioTrino."""

import threading
import time

import serial


class SerialManager:
    """Le a serial em uma thread e entrega apenas pacotes validados.

    O callback de dados recebe:
      host_time_ms, emg1, emg2, fsr1, fsr2, sample_number, device_time_us

    Os dois ultimos valores sao ``None`` para o protocolo legado de quatro
    colunas. Callbacks de estado e metadados sao opcionais para manter o uso
    por interfaces antigas.
    """

    DEFAULT_BAUD_RATE = 921600
    NO_DATA_TIMEOUT_S = 1.5

    def __init__(
        self,
        on_data_callback,
        on_error_callback,
        baud_rate=DEFAULT_BAUD_RATE,
        on_state_callback=None,
        on_metadata_callback=None,
    ):
        self.serial_port = None
        self.baud_rate = int(baud_rate)
        self.on_data = on_data_callback
        self.on_error = on_error_callback
        self.on_state = on_state_callback
        self.on_metadata = on_metadata_callback

        self.thread = None
        self._serial = None
        self._stop_event = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._stats_lock = threading.Lock()
        self._state = "disconnected"
        self._started_perf = None
        self._reset_stats()

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    @property
    def state(self):
        with self._stats_lock:
            return self._state

    def set_port(self, port):
        if self.running:
            raise RuntimeError("Nao e possivel trocar a porta durante a conexao.")
        self.serial_port = port

    def set_baud_rate(self, baud_rate):
        if self.running:
            raise RuntimeError("Nao e possivel trocar o baud rate durante a conexao.")
        self.baud_rate = int(baud_rate)

    def start(self):
        with self._lifecycle_lock:
            if not self.serial_port:
                self.on_error("Porta serial nao definida.")
                return False
            if self.thread is not None and self.thread.is_alive():
                self.on_error("A placa ja esta conectando ou conectada.")
                return False

            self._stop_event.clear()
            self._reset_stats()
            self._started_perf = time.perf_counter()
            self._set_state("connecting")
            self.thread = threading.Thread(
                target=self._read_loop,
                name="biotrino-serial-reader",
                daemon=True,
            )
            self.thread.start()
            return True

    def stop(self, join_timeout=1.5):
        """Solicita parada, desbloqueia readline e aguarda a thread encerrar."""
        self._stop_event.set()
        ser = self._serial
        if ser is not None:
            try:
                ser.cancel_read()
            except (AttributeError, OSError, serial.SerialException):
                pass

        thread = self.thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(join_timeout)
            if thread.is_alive() and ser is not None:
                try:
                    ser.close()
                except (OSError, serial.SerialException):
                    pass
                thread.join(0.5)

        if thread is None or not thread.is_alive():
            self.thread = None

    def _read_loop(self):
        had_error = False
        started_at = self._started_perf or time.perf_counter()
        last_valid_at = started_at
        no_data_reported = False

        try:
            with serial.Serial(
                self.serial_port,
                self.baud_rate,
                timeout=0.2,
                write_timeout=1.0,
            ) as ser:
                self._serial = ser
                try:
                    ser.reset_input_buffer()
                except (OSError, serial.SerialException):
                    pass
                self._set_state("connected")

                while not self._stop_event.is_set():
                    try:
                        raw_line = ser.readline()
                    except (OSError, serial.SerialException) as exc:
                        if not self._stop_event.is_set():
                            had_error = True
                            self.on_error("Falha durante a leitura serial: {}".format(exc))
                            self._set_state("error")
                        break

                    now = time.perf_counter()
                    if not raw_line:
                        if (
                            not no_data_reported
                            and now - last_valid_at >= self.NO_DATA_TIMEOUT_S
                        ):
                            no_data_reported = True
                            self._set_state("no_data")
                        continue

                    try:
                        line = raw_line.decode("ascii").strip()
                    except UnicodeDecodeError:
                        self._mark_invalid_line()
                        if (
                            not no_data_reported
                            and now - last_valid_at >= self.NO_DATA_TIMEOUT_S
                        ):
                            no_data_reported = True
                            self._set_state("no_data")
                        continue

                    packet_type, payload = self.parse_line(line)
                    if packet_type == "metadata":
                        with self._stats_lock:
                            self._metadata = dict(payload)
                        if self.on_metadata is not None:
                            self.on_metadata(dict(payload))
                        continue

                    if packet_type != "sample":
                        if packet_type == "invalid":
                            self._mark_invalid_line()
                            if (
                                not no_data_reported
                                and now - last_valid_at >= self.NO_DATA_TIMEOUT_S
                            ):
                                no_data_reported = True
                                self._set_state("no_data")
                        continue

                    last_valid_at = now
                    if no_data_reported or self.state != "receiving":
                        no_data_reported = False
                        self._set_state("receiving")

                    sequence, device_time_us, emg1, emg2, fsr1, fsr2 = payload
                    host_time_ms = (now - started_at) * 1000.0
                    self._register_sample(sequence, device_time_us, host_time_ms)
                    self.on_data(
                        host_time_ms,
                        emg1,
                        emg2,
                        fsr1,
                        fsr2,
                        sequence,
                        device_time_us,
                    )

        except (OSError, serial.SerialException, ValueError) as exc:
            if not self._stop_event.is_set():
                had_error = True
                self.on_error(
                    "Nao foi possivel abrir a porta {} a {} baud: {}".format(
                        self.serial_port, self.baud_rate, exc
                    )
                )
                self._set_state("error")
        finally:
            self._serial = None
            if not had_error:
                self._set_state("disconnected")

    @staticmethod
    def parse_line(line):
        """Interpreta uma linha dos protocolos BioTrino atual e legado."""
        if not line:
            return "empty", None

        if line.startswith("#BIOTRINO"):
            parts = [part.strip() for part in line.split(",")]
            if len(parts) != 4 or parts[0] != "#BIOTRINO":
                return "invalid", None
            try:
                metadata = {
                    "protocol": int(parts[1]),
                    "sample_rate_hz": int(parts[2]),
                    "channels": int(parts[3]),
                }
            except ValueError:
                return "invalid", None
            return "metadata", metadata

        parts = [part.strip() for part in line.split(",")]
        if len(parts) not in (4, 6):
            return "invalid", None

        try:
            values = [int(part) for part in parts]
        except ValueError:
            return "invalid", None

        if len(values) == 6:
            sequence, device_time_us, emg1, emg2, fsr1, fsr2 = values
            if sequence < 0 or device_time_us < 0:
                return "invalid", None
        else:
            sequence = None
            device_time_us = None
            emg1, emg2, fsr1, fsr2 = values

        adc_values = (emg1, emg2, fsr1, fsr2)
        if any(value < 0 or value > 4095 for value in adc_values):
            return "invalid", None

        return "sample", (
            sequence,
            device_time_us,
            emg1,
            emg2,
            fsr1,
            fsr2,
        )

    def stats_snapshot(self):
        with self._stats_lock:
            received = self._received
            host_span_ms = self._last_host_ms - self._first_host_ms
            receive_rate_hz = None
            if received > 1 and host_span_ms > 0:
                receive_rate_hz = (received - 1) * 1000.0 / host_span_ms

            device_rate_hz = None
            if (
                self._first_sequence is not None
                and self._last_sequence is not None
                and self._first_device_us is not None
                and self._last_device_us is not None
            ):
                time_span_us = self._last_device_us - self._first_device_us
                sequence_span = self._last_sequence - self._first_sequence
                if time_span_us > 0 and sequence_span >= 0:
                    device_rate_hz = sequence_span * 1000000.0 / time_span_us

            return {
                "state": self._state,
                "received": received,
                "lost": self._lost,
                "loss_detection": self._first_sequence is not None,
                "invalid": self._invalid,
                "receive_rate_hz": receive_rate_hz,
                "device_rate_hz": device_rate_hz,
                "metadata": dict(self._metadata),
            }

    def connection_elapsed_ms(self):
        if self._started_perf is None:
            return 0.0
        return (time.perf_counter() - self._started_perf) * 1000.0

    def _reset_stats(self):
        with self._stats_lock:
            self._received = 0
            self._lost = 0
            self._invalid = 0
            self._last_sequence = None
            self._first_sequence = None
            self._first_device_us = None
            self._last_device_us = None
            self._first_host_ms = 0.0
            self._last_host_ms = 0.0
            self._metadata = {}

    def _register_sample(self, sequence, device_time_us, host_time_ms):
        with self._stats_lock:
            if self._received == 0:
                self._first_host_ms = host_time_ms
                self._first_sequence = sequence
                self._first_device_us = device_time_us

            if sequence is not None and self._last_sequence is not None:
                delta = (sequence - self._last_sequence) & 0xFFFFFFFF
                if 1 < delta < 0x80000000:
                    self._lost += delta - 1

            self._received += 1
            self._last_sequence = sequence
            self._last_device_us = device_time_us
            self._last_host_ms = host_time_ms

    def _mark_invalid_line(self):
        with self._stats_lock:
            self._invalid += 1

    def _set_state(self, state):
        with self._stats_lock:
            if self._state == state:
                return
            self._state = state
        if self.on_state is not None:
            self.on_state(state)
