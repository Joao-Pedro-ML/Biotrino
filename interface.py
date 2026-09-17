"""Interface principal de aquisicao EMG/FSR da placa BioTrino."""

import csv
import ctypes
import re
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from queue import Empty, Full, Queue

import dearpygui.dearpygui as dpg
import serial.tools.list_ports

from serial_manager import SerialManager


user32 = ctypes.windll.user32
SCREEN_WIDTH = user32.GetSystemMetrics(0)
SCREEN_HEIGHT = user32.GetSystemMetrics(1)
DESIGN_WIDTH = 1920
DESIGN_HEIGHT = 1080
MIN_WINDOW_WIDTH = 960
MIN_WINDOW_HEIGHT = 640
WINDOW_WIDTH = max(MIN_WINDOW_WIDTH, int(SCREEN_WIDTH * 0.95))
WINDOW_HEIGHT = max(MIN_WINDOW_HEIGHT, int(SCREEN_HEIGHT * 0.90))


class MainInterface:
    PLOT_REFRESH_INTERVAL_S = 1.0 / 30.0
    STATS_REFRESH_INTERVAL_S = 0.25
    FILE_FLUSH_INTERVAL_S = 1.0
    MAX_UI_QUEUE = 50000
    MAX_EVENTS_PER_FRAME = 5000

    STATE_LABELS = {
        "disconnected": "Desconectado",
        "connecting": "Conectando...",
        "connected": "Conectado; aguardando dados",
        "receiving": "Recebendo dados",
        "no_data": "Conectado; sem dados",
        "error": "Erro de conexao",
    }
    STATE_COLORS = {
        "disconnected": (125, 125, 125, 255),
        "connecting": (255, 190, 50, 255),
        "connected": (80, 160, 255, 255),
        "receiving": (55, 205, 90, 255),
        "no_data": (255, 150, 40, 255),
        "error": (235, 70, 70, 255),
    }

    def __init__(self):
        self.ui_queue = Queue(maxsize=self.MAX_UI_QUEUE)
        self.queue_dropped = 0
        self.serial_manager = SerialManager(
            on_data_callback=self.process_serial_data,
            on_error_callback=self.serial_error,
            on_state_callback=self.serial_state_changed,
            on_metadata_callback=self.serial_metadata_received,
        )

        self.window_ms = 2000
        self.time_buffer = deque()
        self.emg1_buffer = deque()
        self.emg2_buffer = deque()
        self.fsr1_buffer = deque()
        self.fsr2_buffer = deque()
        self.first_device_time_us = None
        self.plot_dirty = False
        self.last_plot_update = 0.0
        self.last_stats_update = 0.0
        self.last_layout_size = None

        self.port_map = {}
        self.metadata = {}
        self.current_state = "disconnected"
        self.current_values = (0, 0, 0, 0)

        self.recording = False
        self.record_file = None
        self.record_writer = None
        self.record_path = None
        self.record_started_at = None
        self.record_started_perf = None
        self.record_elapsed_s = 0.0
        self.recorded_samples = 0
        self.last_record_sequence = None
        self.record_start_host_ms = None
        self.record_stop_host_ms = None
        self.stop_recording_in_progress = False
        self.last_file_flush = 0.0

        self.log_items = deque()
        self.shutting_down = False

        dpg.create_context()
        dpg.create_viewport(
            title="BioTrino - Aquisicao EMG e FSR",
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            min_width=MIN_WINDOW_WIDTH,
            min_height=MIN_WINDOW_HEIGHT,
            resizable=True,
        )
        dpg.set_viewport_pos(
            (
                max(0, (SCREEN_WIDTH - WINDOW_WIDTH) // 2),
                max(0, (SCREEN_HEIGHT - WINDOW_HEIGHT) // 2),
            )
        )

    # ------------------------------------------------------------------
    # Entrada da thread serial: somente enfileira; nunca altera a GUI.
    # ------------------------------------------------------------------
    def _enqueue(self, event):
        try:
            self.ui_queue.put_nowait(event)
        except Full:
            self.queue_dropped += 1
            # Estados e erros sao mais importantes que uma amostra atrasada.
            if event[0] != "sample":
                try:
                    self.ui_queue.get_nowait()
                    self.ui_queue.put_nowait(event)
                except (Empty, Full):
                    pass

    def process_serial_data(
        self,
        host_time_ms,
        emg1,
        emg2,
        fsr1,
        fsr2,
        sample_number=None,
        device_time_us=None,
    ):
        self._enqueue(
            (
                "sample",
                host_time_ms,
                emg1,
                emg2,
                fsr1,
                fsr2,
                sample_number,
                device_time_us,
            )
        )

    def serial_error(self, message):
        self._enqueue(("error", message))

    def serial_state_changed(self, state):
        self._enqueue(("state", state))

    def serial_metadata_received(self, metadata):
        self._enqueue(("metadata", metadata))

    # ------------------------------------------------------------------
    # Portas e conexao
    # ------------------------------------------------------------------
    def _serial_port_items(self):
        self.port_map = {}
        ports = sorted(serial.tools.list_ports.comports(), key=lambda port: port.device)
        for port in ports:
            description = port.description or "Dispositivo serial"
            label = "{} - {}".format(port.device, description)
            self.port_map[label] = port.device
        return list(self.port_map.keys())

    def refresh_ports(self):
        previous_label = dpg.get_value("serial_port_combo")
        previous_device = self.port_map.get(previous_label)
        items = self._serial_port_items()
        dpg.configure_item("serial_port_combo", items=items)

        selected = ""
        if previous_device:
            selected = next(
                (label for label, device in self.port_map.items() if device == previous_device),
                "",
            )
        if not selected and len(items) == 1:
            selected = items[0]
        dpg.set_value("serial_port_combo", selected)

        if items:
            self.add_log("{} porta(s) serial(is) encontrada(s).".format(len(items)))
        else:
            self.add_log("Nenhuma porta serial encontrada.", "warning")

    def toggle_connection(self):
        if self.serial_manager.running:
            self.disconnect_serial()
            return

        selected_label = dpg.get_value("serial_port_combo")
        port = self.port_map.get(selected_label)
        if not port:
            self.add_log("Selecione uma porta serial antes de conectar.", "warning")
            return

        try:
            baud_rate = int(dpg.get_value("baud_combo"))
            self.serial_manager.set_port(port)
            self.serial_manager.set_baud_rate(baud_rate)
        except (TypeError, ValueError, RuntimeError) as exc:
            self.add_log(str(exc), "error")
            return

        self.metadata = {}
        self.queue_dropped = 0
        self.add_log("Abrindo {} a {} baud...".format(port, baud_rate))
        if self.serial_manager.start():
            dpg.configure_item("serial_port_combo", enabled=False)
            dpg.configure_item("baud_combo", enabled=False)
            dpg.set_item_label("connect_button", "Cancelar conexao")

    def disconnect_serial(self):
        if self.recording:
            self.stop_recording()
        self.add_log("Desconectando a placa...")
        self.serial_manager.stop()
        self._apply_connection_state("disconnected")

    # ------------------------------------------------------------------
    # Sessao e gravacao incremental
    # ------------------------------------------------------------------
    def start_recording(self):
        if self.recording:
            return
        if self.current_state != "receiving":
            self.add_log(
                "Aguarde a interface confirmar o recebimento de dados validos.",
                "warning",
            )
            return

        if getattr(sys, "frozen", False):
            application_dir = Path(sys.executable).resolve().parent
        else:
            application_dir = Path(__file__).resolve().parent
        output_dir = application_dir / "out_data"
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.add_log(
                "Nao foi possivel preparar a pasta de dados: {}".format(exc),
                "error",
            )
            return
        session_name = self._safe_session_name(dpg.get_value("session_name_input"))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        suffix = "_{}".format(session_name) if session_name else ""
        self.record_path = output_dir / "dados_biotrino_{}{}.csv".format(
            timestamp, suffix
        )

        try:
            self.record_file = self.record_path.open(
                "x", newline="", encoding="utf-8"
            )
            self.record_writer = csv.writer(self.record_file)
            self._write_file_header()
            self.record_file.flush()
        except OSError as exc:
            self._close_record_file()
            self.add_log("Nao foi possivel criar o arquivo: {}".format(exc), "error")
            return

        self.clear_plot_data()
        self.recording = True
        self.record_started_at = datetime.now()
        self.record_started_perf = time.perf_counter()
        self.record_elapsed_s = 0.0
        self.recorded_samples = 0
        self.last_record_sequence = None
        self.record_start_host_ms = self.serial_manager.connection_elapsed_ms()
        self.record_stop_host_ms = None
        self.last_file_flush = time.perf_counter()

        dpg.configure_item("start_record_button", enabled=False)
        dpg.configure_item("stop_record_button", enabled=True)
        dpg.configure_item("new_session_button", enabled=False)
        dpg.configure_item("session_name_input", enabled=False)
        dpg.set_value("recording_status_text", "GRAVANDO")
        dpg.configure_item("recording_status_text", color=(255, 80, 80, 255))
        self.add_log("Coleta iniciada: {}".format(self.record_path))

    def stop_recording(self):
        if not self.recording or self.stop_recording_in_progress:
            return

        self.stop_recording_in_progress = True
        try:
            self.record_stop_host_ms = self.serial_manager.connection_elapsed_ms()
            # Grava os pacotes que chegaram antes do clique em "Parar".
            while not self.ui_queue.empty():
                self._process_ui_events()
            if not self.recording:
                return
            self.record_elapsed_s = time.perf_counter() - self.record_started_perf
            self.recording = False
            saved_path = self.record_path
            saved_samples = self.recorded_samples
            self._close_record_file()

            dpg.configure_item(
                "start_record_button", enabled=self.serial_manager.running
            )
            dpg.configure_item("stop_record_button", enabled=False)
            dpg.configure_item("new_session_button", enabled=True)
            dpg.configure_item("session_name_input", enabled=True)
            dpg.set_value("recording_status_text", "Coleta finalizada")
            dpg.configure_item(
                "recording_status_text", color=(130, 210, 150, 255)
            )
            self.add_log(
                "Arquivo salvo com {} amostras: {}".format(
                    saved_samples, saved_path
                )
            )
        finally:
            self.stop_recording_in_progress = False

    def new_session(self):
        if self.recording:
            self.add_log("Finalize a coleta atual antes de iniciar outra.", "warning")
            return
        self.clear_plot_data()
        self.record_path = None
        self.recorded_samples = 0
        self.record_elapsed_s = 0.0
        self.last_record_sequence = None
        dpg.set_value("recording_status_text", "Pronto para nova coleta")
        dpg.configure_item("recording_status_text", color=(190, 190, 190, 255))
        self._update_stats_panel(force=True)
        self.add_log("Nova sessao preparada.")

    def _write_file_header(self):
        metadata = self.serial_manager.stats_snapshot().get("metadata", {})
        self.record_writer.writerow(["# BioTrino acquisition file"])
        self.record_writer.writerow(
            ["# started_at_iso", datetime.now().astimezone().isoformat()]
        )
        self.record_writer.writerow(["# serial_port", self.serial_manager.serial_port])
        self.record_writer.writerow(["# baud_rate", self.serial_manager.baud_rate])
        self.record_writer.writerow(
            ["# session_name", dpg.get_value("session_name_input").strip()]
        )
        self.record_writer.writerow(
            ["# protocol", metadata.get("protocol", "legacy")]
        )
        self.record_writer.writerow(
            ["# expected_sample_rate_hz", metadata.get("sample_rate_hz", "unknown")]
        )
        self.record_writer.writerow(
            [
                "sample_number",
                "device_timestamp_us",
                "host_timestamp_ms",
                "missing_before",
                "emg1_raw",
                "emg2_raw",
                "fsr1_raw",
                "fsr2_raw",
            ]
        )

    def _write_sample(
        self,
        host_time_ms,
        emg1,
        emg2,
        fsr1,
        fsr2,
        sample_number,
        device_time_us,
    ):
        missing_before = 0
        if sample_number is not None and self.last_record_sequence is not None:
            delta = (sample_number - self.last_record_sequence) & 0xFFFFFFFF
            if 1 < delta < 0x80000000:
                missing_before = delta - 1

        self.record_writer.writerow(
            [
                "" if sample_number is None else sample_number,
                "" if device_time_us is None else device_time_us,
                "{:.3f}".format(host_time_ms),
                missing_before,
                emg1,
                emg2,
                fsr1,
                fsr2,
            ]
        )
        self.recorded_samples += 1
        self.last_record_sequence = sample_number

    def _flush_record_file_if_needed(self, now):
        if (
            self.recording
            and self.record_file is not None
            and now - self.last_file_flush >= self.FILE_FLUSH_INTERVAL_S
        ):
            try:
                self.record_file.flush()
                self.last_file_flush = now
            except OSError as exc:
                self._abort_recording(
                    "Falha ao sincronizar o arquivo; o arquivo parcial foi preservado: {}".format(
                        exc
                    )
                )

    def _abort_recording(self, message):
        self.recording = False
        self._close_record_file()
        dpg.configure_item(
            "start_record_button", enabled=self.current_state == "receiving"
        )
        dpg.configure_item("stop_record_button", enabled=False)
        dpg.configure_item("new_session_button", enabled=True)
        dpg.configure_item("session_name_input", enabled=True)
        dpg.set_value("recording_status_text", "ERRO NA GRAVACAO")
        dpg.configure_item("recording_status_text", color=(255, 80, 80, 255))
        self.add_log(message, "error")

    def _close_record_file(self):
        if self.record_file is not None:
            try:
                self.record_file.flush()
                self.record_file.close()
            except OSError as exc:
                self.add_log("Erro ao fechar o arquivo: {}".format(exc), "error")
        self.record_file = None
        self.record_writer = None

    @staticmethod
    def _safe_session_name(value):
        value = (value or "").strip()
        value = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE)
        return value.strip("._")[:60]

    # ------------------------------------------------------------------
    # Processamento no thread principal e graficos
    # ------------------------------------------------------------------
    def _process_ui_events(self):
        for _ in range(self.MAX_EVENTS_PER_FRAME):
            try:
                event = self.ui_queue.get_nowait()
            except Empty:
                break

            event_type = event[0]
            if event_type == "sample":
                self._handle_sample(*event[1:])
            elif event_type == "state":
                self._apply_connection_state(event[1])
            elif event_type == "metadata":
                self.metadata = event[1]
                protocol = self.metadata.get("protocol")
                channels = self.metadata.get("channels")
                level = "info" if protocol == 1 and channels == 4 else "warning"
                self.add_log(
                    "Placa BioTrino detectada: protocolo {}, {} Hz, {} canais.".format(
                        protocol or "?",
                        self.metadata.get("sample_rate_hz", "?"),
                        channels or "?",
                    ),
                    level,
                )
            elif event_type == "error":
                self.add_log(event[1], "error")

    def _handle_sample(
        self,
        host_time_ms,
        emg1,
        emg2,
        fsr1,
        fsr2,
        sample_number,
        device_time_us,
    ):
        if device_time_us is not None:
            if self.first_device_time_us is None:
                self.first_device_time_us = device_time_us
            plot_time_ms = (device_time_us - self.first_device_time_us) / 1000.0
        else:
            plot_time_ms = host_time_ms

        self.time_buffer.append(plot_time_ms)
        self.emg1_buffer.append(emg1)
        self.emg2_buffer.append(emg2)
        self.fsr1_buffer.append(fsr1)
        self.fsr2_buffer.append(fsr2)
        self.current_values = (emg1, emg2, fsr1, fsr2)

        while self.time_buffer and plot_time_ms - self.time_buffer[0] > self.window_ms:
            self.time_buffer.popleft()
            self.emg1_buffer.popleft()
            self.emg2_buffer.popleft()
            self.fsr1_buffer.popleft()
            self.fsr2_buffer.popleft()

        inside_recording_interval = (
            self.record_start_host_ms is not None
            and host_time_ms >= self.record_start_host_ms
            and (
                self.record_stop_host_ms is None
                or host_time_ms <= self.record_stop_host_ms
            )
        )
        if (
            self.recording
            and self.record_writer is not None
            and inside_recording_interval
        ):
            try:
                self._write_sample(
                    host_time_ms,
                    emg1,
                    emg2,
                    fsr1,
                    fsr2,
                    sample_number,
                    device_time_us,
                )
            except (OSError, csv.Error) as exc:
                self._abort_recording(
                    "Falha ao gravar dados; o arquivo parcial foi preservado: {}".format(
                        exc
                    )
                )
        self.plot_dirty = True

    def _refresh_plots(self, now):
        if not self.plot_dirty or dpg.get_value("pause_plot_checkbox"):
            return
        if now - self.last_plot_update < self.PLOT_REFRESH_INTERVAL_S:
            return

        x_values = list(self.time_buffer)
        dpg.set_value("emg1_series", [x_values, list(self.emg1_buffer)])
        dpg.set_value("emg2_series", [x_values, list(self.emg2_buffer)])
        dpg.set_value("fsr1_series", [x_values, list(self.fsr1_buffer)])
        dpg.set_value("fsr2_series", [x_values, list(self.fsr2_buffer)])

        if len(x_values) > 1:
            xmin = max(0.0, x_values[-1] - self.window_ms)
            xmax = max(float(self.window_ms), x_values[-1])
            for axis in (
                "x_axis_emg1",
                "x_axis_emg2",
                "x_axis_fsr1",
                "x_axis_fsr2",
            ):
                dpg.set_axis_limits(axis, xmin, xmax)

        if dpg.get_value("autoscale_checkbox"):
            for axis in (
                "y_axis_emg1",
                "y_axis_emg2",
                "y_axis_fsr1",
                "y_axis_fsr2",
            ):
                dpg.fit_axis_data(axis)

        self.plot_dirty = False
        self.last_plot_update = now

    def clear_plot_data(self):
        self.time_buffer.clear()
        self.emg1_buffer.clear()
        self.emg2_buffer.clear()
        self.fsr1_buffer.clear()
        self.fsr2_buffer.clear()
        self.first_device_time_us = None
        self.current_values = (0, 0, 0, 0)
        self.plot_dirty = True

    def set_window_ms(self, sender, app_data):
        self.window_ms = int(app_data)
        self.plot_dirty = True

    # ------------------------------------------------------------------
    # Estado, indicadores e logs
    # ------------------------------------------------------------------
    def _apply_connection_state(self, state):
        self.current_state = state
        label = self.STATE_LABELS.get(state, state)
        color = self.STATE_COLORS.get(state, self.STATE_COLORS["disconnected"])
        dpg.set_value("connection_status_text", label)
        dpg.configure_item("connection_status_circle", fill=color)

        active = state in ("connecting", "connected", "receiving", "no_data")
        can_record = state == "receiving"
        dpg.set_item_label("connect_button", "Desconectar" if active else "Conectar")
        dpg.configure_item("serial_port_combo", enabled=not active)
        dpg.configure_item("baud_combo", enabled=not active)
        dpg.configure_item("refresh_ports_button", enabled=not active)
        dpg.configure_item(
            "start_record_button", enabled=can_record and not self.recording
        )

        if state == "receiving":
            dpg.set_value("stream_status_text", "Fluxo valido")
        elif state == "no_data":
            dpg.set_value("stream_status_text", "Sem pacotes ha mais de 1,5 s")
        else:
            dpg.set_value("stream_status_text", "-")

        if state == "error":
            dpg.set_item_label("connect_button", "Conectar novamente")
            dpg.configure_item("serial_port_combo", enabled=True)
            dpg.configure_item("baud_combo", enabled=True)
            dpg.configure_item("refresh_ports_button", enabled=True)

        if state in ("disconnected", "error") and self.recording:
            self.stop_recording()

    def _update_stats_panel(self, force=False):
        now = time.perf_counter()
        if not force and now - self.last_stats_update < self.STATS_REFRESH_INTERVAL_S:
            return
        self.last_stats_update = now

        stats = self.serial_manager.stats_snapshot()
        receive_rate = stats["receive_rate_hz"]
        device_rate = stats["device_rate_hz"]
        rate_text = "-"
        if device_rate is not None:
            rate_text = "{:.1f} Hz (placa)".format(device_rate)
        elif receive_rate is not None:
            rate_text = "{:.1f} Hz (recepcao)".format(receive_rate)

        expected_rate = stats["metadata"].get("sample_rate_hz")
        rate_out_of_tolerance = (
            device_rate is not None
            and expected_rate
            and abs(device_rate - expected_rate) / expected_rate > 0.02
        )

        if self.recording:
            self.record_elapsed_s = now - self.record_started_perf

        dpg.set_value("sample_rate_text", rate_text)
        dpg.configure_item(
            "sample_rate_text",
            color=(255, 190, 60, 255)
            if rate_out_of_tolerance
            else (130, 220, 150, 255),
        )
        dpg.set_value("received_text", str(stats["received"]))
        loss_detection = stats["loss_detection"]
        lost_text = str(stats["lost"])
        if stats["received"] and not loss_detection:
            lost_text = "N/D (firmware legado)"
        dpg.set_value("lost_text", lost_text)
        dpg.set_value("invalid_text", str(stats["invalid"]))
        dpg.set_value("queue_dropped_text", str(self.queue_dropped))
        dpg.configure_item(
            "lost_text",
            color=(255, 95, 95, 255)
            if stats["lost"]
            else (
                (130, 220, 150, 255)
                if loss_detection
                else (180, 180, 180, 255)
            ),
        )
        dpg.configure_item(
            "invalid_text",
            color=(255, 190, 60, 255)
            if stats["invalid"]
            else (130, 220, 150, 255),
        )
        dpg.configure_item(
            "queue_dropped_text",
            color=(255, 95, 95, 255)
            if self.queue_dropped
            else (130, 220, 150, 255),
        )
        dpg.set_value("recorded_text", str(self.recorded_samples))
        dpg.set_value("duration_text", "{:.1f} s".format(self.record_elapsed_s))
        dpg.set_value(
            "file_path_text", str(self.record_path) if self.record_path else "-"
        )
        dpg.set_value("emg1_value_text", str(self.current_values[0]))
        dpg.set_value("emg2_value_text", str(self.current_values[1]))
        dpg.set_value("fsr1_value_text", str(self.current_values[2]))
        dpg.set_value("fsr2_value_text", str(self.current_values[3]))
        for tag, value in zip(
            (
                "emg1_value_text",
                "emg2_value_text",
                "fsr1_value_text",
                "fsr2_value_text",
            ),
            self.current_values,
        ):
            saturated = stats["received"] > 0 and (value <= 10 or value >= 4085)
            dpg.configure_item(
                tag,
                color=(255, 90, 90, 255)
                if saturated
                else (120, 220, 160, 255),
            )

    def add_log(self, message, level="info"):
        colors = {
            "info": (205, 205, 205, 255),
            "warning": (255, 195, 60, 255),
            "error": (255, 95, 95, 255),
        }
        timestamp = datetime.now().strftime("%H:%M:%S")
        if not dpg.does_item_exist("terminal_child"):
            return
        item = dpg.add_text(
            "[{}] {}".format(timestamp, message),
            color=colors.get(level, colors["info"]),
            parent="terminal_child",
        )
        self.log_items.append(item)
        while len(self.log_items) > 200:
            dpg.delete_item(self.log_items.popleft())
        dpg.set_y_scroll("terminal_child", dpg.get_y_scroll_max("terminal_child"))

    def clear_terminal(self):
        self.log_items.clear()
        dpg.delete_item("terminal_child", children_only=True)

    @staticmethod
    def _create_status_circle():
        with dpg.drawlist(width=22, height=22):
            dpg.draw_circle(
                (11, 11),
                8,
                fill=MainInterface.STATE_COLORS["disconnected"],
                tag="connection_status_circle",
            )

    def _on_viewport_resize(self, sender=None, app_data=None):
        self._apply_responsive_layout()

    def _apply_responsive_layout(self, width=None, height=None, force=False):
        """Redimensiona a interface usando o tamanho util atual da janela."""
        if not dpg.does_item_exist("main_window"):
            return

        width = int(width or dpg.get_viewport_client_width())
        height = int(height or dpg.get_viewport_client_height())
        if width <= 0 or height <= 0:
            return
        if not force and self.last_layout_size == (width, height):
            return
        self.last_layout_size = (width, height)

        scale = min(width / DESIGN_WIDTH, height / DESIGN_HEIGHT)
        scale = max(0.65, min(1.50, scale))
        dpg.set_global_font_scale(scale)

        margin = max(6, int(12 * scale))
        gap = max(5, int(10 * scale))
        available_width = max(1, width - 2 * margin)

        # O painel de qualidade possui oito linhas; este minimo evita corte em
        # telas baixas, ainda reservando espaco suficiente para os graficos.
        top_height = max(170, int(190 * scale))
        terminal_height = max(62, int(105 * scale))
        footer_height = max(62, int(98 * scale))
        plot_area_height = height - top_height - terminal_height - footer_height
        plot_height = max(135, int((plot_area_height - 3 * gap) / 2))
        plot_width = max(300, int((available_width - gap) / 2))

        top_inner_width = max(1, available_width - 2 * margin)
        connection_width = int(top_inner_width * 0.31)
        session_width = int(top_inner_width * 0.38)
        quality_width = max(
            220, top_inner_width - connection_width - session_width - 2 * gap
        )
        panel_height = max(1, top_height - 2 * margin)

        dpg.configure_item("top_panel", height=top_height)
        dpg.configure_item(
            "connection_panel", width=connection_width, height=panel_height
        )
        dpg.configure_item("session_panel", width=session_width, height=panel_height)
        dpg.configure_item("quality_panel", width=quality_width, height=panel_height)

        connection_content = max(180, connection_width - int(72 * scale))
        dpg.configure_item("serial_port_combo", width=connection_content)
        dpg.configure_item("baud_combo", width=max(110, int(160 * scale)))
        connection_button_width = max(90, int((connection_width - gap) / 2))
        dpg.configure_item("connect_button", width=connection_button_width)
        dpg.configure_item("refresh_ports_button", width=connection_button_width)

        session_content = max(210, session_width - int(105 * scale))
        dpg.configure_item("session_name_input", width=session_content)
        dpg.configure_item("window_slider", width=session_content)
        session_buttons_width = max(225, session_width - 2 * gap)
        dpg.configure_item(
            "start_record_button", width=max(70, int(session_buttons_width * 0.34))
        )
        dpg.configure_item(
            "stop_record_button", width=max(80, int(session_buttons_width * 0.37))
        )
        dpg.configure_item(
            "new_session_button", width=max(70, int(session_buttons_width * 0.29))
        )

        for prefix in ("emg1", "emg2", "fsr1", "fsr2"):
            dpg.configure_item(
                "{}_plot".format(prefix), width=plot_width, height=plot_height
            )

        dpg.configure_item("file_path_text", wrap=max(200, width - int(130 * scale)))
        dpg.configure_item("terminal_child", height=terminal_height)

    # ------------------------------------------------------------------
    # Construcao e ciclo da GUI
    # ------------------------------------------------------------------
    def build_gui(self):
        port_items = self._serial_port_items()
        default_port = port_items[0] if len(port_items) == 1 else ""
        plot_width = max(300, (WINDOW_WIDTH - 32) // 2)
        plot_height = max(135, (WINDOW_HEIGHT - 390) // 2)

        with dpg.window(
            tag="main_window",
            label="BioTrino",
            no_scrollbar=True,
            no_scroll_with_mouse=True,
        ):
            with dpg.child_window(
                tag="top_panel",
                height=190,
                border=True,
                no_scrollbar=True,
                no_scroll_with_mouse=True,
            ):
                with dpg.group(horizontal=True):
                    with dpg.child_window(
                        tag="connection_panel",
                        width=480,
                        height=170,
                        border=False,
                        no_scrollbar=True,
                        no_scroll_with_mouse=True,
                    ):
                        dpg.add_text("CONEXAO COM A PLACA", color=(120, 190, 255, 255))
                        with dpg.group(horizontal=True):
                            self._create_status_circle()
                            dpg.add_text(
                                self.STATE_LABELS["disconnected"],
                                tag="connection_status_text",
                            )
                        dpg.add_combo(
                            port_items,
                            default_value=default_port,
                            tag="serial_port_combo",
                            label="Porta",
                            width=300,
                        )
                        dpg.add_combo(
                            ("115200", "230400", "460800", "921600"),
                            default_value=str(SerialManager.DEFAULT_BAUD_RATE),
                            tag="baud_combo",
                            label="Baud",
                            width=160,
                        )
                        with dpg.group(horizontal=True):
                            dpg.add_button(
                                label="Conectar",
                                tag="connect_button",
                                callback=self.toggle_connection,
                                width=150,
                            )
                            dpg.add_button(
                                label="Atualizar portas",
                                tag="refresh_ports_button",
                                callback=self.refresh_ports,
                                width=150,
                            )

                    dpg.add_spacer(width=20)
                    with dpg.child_window(
                        tag="session_panel",
                        width=590,
                        height=170,
                        border=False,
                        no_scrollbar=True,
                        no_scroll_with_mouse=True,
                    ):
                        dpg.add_text("SESSAO DE COLETA", color=(120, 190, 255, 255))
                        dpg.add_input_text(
                            label="Identificacao",
                            hint="participante_ensaio",
                            tag="session_name_input",
                            width=240,
                        )
                        dpg.add_text("Pronto para nova coleta", tag="recording_status_text")
                        with dpg.group(horizontal=True):
                            dpg.add_button(
                                label="Iniciar coleta",
                                tag="start_record_button",
                                callback=self.start_recording,
                                enabled=False,
                                width=125,
                            )
                            dpg.add_button(
                                label="Parar e salvar",
                                tag="stop_record_button",
                                callback=self.stop_recording,
                                enabled=False,
                                width=125,
                            )
                            dpg.add_button(
                                label="Nova coleta",
                                tag="new_session_button",
                                callback=self.new_session,
                                width=110,
                            )
                        dpg.add_slider_int(
                            label="Janela (ms)",
                            tag="window_slider",
                            default_value=self.window_ms,
                            min_value=100,
                            max_value=10000,
                            callback=self.set_window_ms,
                            width=250,
                        )
                        with dpg.group(horizontal=True):
                            dpg.add_checkbox(label="Pausar graficos", tag="pause_plot_checkbox")
                            dpg.add_checkbox(label="Autoescala Y", tag="autoscale_checkbox")

                    dpg.add_spacer(width=20)
                    with dpg.child_window(
                        tag="quality_panel",
                        width=500,
                        height=170,
                        border=False,
                        no_scrollbar=True,
                        no_scroll_with_mouse=True,
                    ):
                        dpg.add_text("QUALIDADE DA AQUISICAO", color=(120, 190, 255, 255))
                        self._add_stat_row("Fluxo", "stream_status_text", "-")
                        self._add_stat_row("Frequencia", "sample_rate_text", "-")
                        self._add_stat_row("Recebidas", "received_text", "0")
                        self._add_stat_row("Perdidas", "lost_text", "0")
                        self._add_stat_row("Invalidas", "invalid_text", "0")
                        self._add_stat_row("Fila descartada", "queue_dropped_text", "0")
                        self._add_stat_row("Gravadas", "recorded_text", "0")
                        self._add_stat_row("Duracao", "duration_text", "0.0 s")

            with dpg.group(horizontal=True):
                with dpg.group():
                    self._create_plot(
                        "EMG1", "emg1", plot_width, plot_height, (70, 210, 120, 255)
                    )
                    self._create_plot(
                        "FSR1", "fsr1", plot_width, plot_height, (255, 170, 70, 255)
                    )
                with dpg.group():
                    self._create_plot(
                        "EMG2", "emg2", plot_width, plot_height, (80, 160, 255, 255)
                    )
                    self._create_plot(
                        "FSR2", "fsr2", plot_width, plot_height, (220, 110, 230, 255)
                    )

            with dpg.group(horizontal=True):
                dpg.add_text("Valores ADC:")
                self._add_live_value("EMG1", "emg1_value_text")
                self._add_live_value("EMG2", "emg2_value_text")
                self._add_live_value("FSR1", "fsr1_value_text")
                self._add_live_value("FSR2", "fsr2_value_text")
            with dpg.group(horizontal=True):
                dpg.add_text("Arquivo:")
                dpg.add_text("-", tag="file_path_text", wrap=WINDOW_WIDTH - 130)

            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_text("LOG DA APLICACAO", color=(120, 190, 255, 255))
                dpg.add_button(label="Limpar", callback=self.clear_terminal, small=True)
            with dpg.child_window(
                tag="terminal_child",
                height=105,
                border=True,
                no_scrollbar=True,
                no_scroll_with_mouse=True,
            ):
                pass

        dpg.set_primary_window("main_window", True)
        self.add_log("Interface pronta. Selecione a porta da placa e conecte.")

    @staticmethod
    def _add_stat_row(label, tag, default):
        with dpg.group(horizontal=True):
            dpg.add_text("{}:".format(label), bullet=True)
            dpg.add_text(default, tag=tag)

    @staticmethod
    def _add_live_value(label, tag):
        dpg.add_text("{}:".format(label))
        dpg.add_text("0", tag=tag, color=(120, 220, 160, 255))
        dpg.add_spacer(width=12)

    @staticmethod
    def _create_plot(title, prefix, width, height, color):
        x_axis = "x_axis_{}".format(prefix)
        y_axis = "y_axis_{}".format(prefix)
        series = "{}_series".format(prefix)
        with dpg.plot(
            label=title,
            tag="{}_plot".format(prefix),
            width=width,
            height=height,
        ):
            dpg.add_plot_axis(dpg.mvXAxis, label="Tempo (ms)", tag=x_axis)
            with dpg.plot_axis(dpg.mvYAxis, label="{} (ADC)".format(title), tag=y_axis):
                dpg.set_axis_limits(y_axis, 0.0, 4095.0)
                dpg.add_line_series([], [], label=title, tag=series)
        with dpg.theme() as series_theme:
            with dpg.theme_component(dpg.mvLineSeries):
                dpg.add_theme_color(dpg.mvThemeCol_PlotLines, color)
        dpg.bind_item_theme(series, series_theme)

    def shutdown(self):
        if self.shutting_down:
            return
        self.shutting_down = True
        if self.recording:
            self.stop_recording()
        self.serial_manager.stop()
        self._close_record_file()

    def run(self):
        self.build_gui()
        dpg.setup_dearpygui()
        dpg.set_viewport_resize_callback(self._on_viewport_resize)
        dpg.show_viewport()
        self._apply_responsive_layout(force=True)
        try:
            while dpg.is_dearpygui_running():
                now = time.perf_counter()
                self._process_ui_events()
                self._refresh_plots(now)
                self._update_stats_panel()
                self._flush_record_file_if_needed(now)
                dpg.render_dearpygui_frame()
        finally:
            self.shutdown()
            dpg.destroy_context()
