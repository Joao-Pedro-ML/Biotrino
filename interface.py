import dearpygui.dearpygui as dpg
import serial.tools.list_ports
import time
import csv
from threading import Lock
from serial_manager import SerialManager
import ctypes
import sys


user32 = ctypes.windll.user32
screen_width, screen_height = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
print(screen_width, screen_height)
win_width = int(screen_width)
win_height = int(screen_height)


class MainInterface:
    def __init__(self):
        self.serial_manager = SerialManager(
            on_data_callback=self.process_serial_data,
            on_error_callback=self.serial_error
        )

        self.window_ms = 2000
        self.lock = Lock()

        self.time_buffer_emg = []
        self.emg1_buffer = []
        self.emg2_buffer = []
        self.fsr1_buffer = []
        self.fsr2_buffer = []

        self.save_data = []

        self.logs = []
        sys.stdout = self
        sys.stderr = self

        dpg.create_context()
        
        dpg.create_viewport(title='BioTrino', width=win_width, height=win_height)
        dpg.set_viewport_pos([(screen_width - win_width)//2, (screen_height - win_height)//2])
        

    def list_serial_ports(self):
        return [p.device for p in serial.tools.list_ports.comports()]
    
    def refresh_ports(self):
        ports = self.list_serial_ports()
        dpg.configure_item("porta_serial_combo", items=ports)
        if ports:
            dpg.set_value("porta_serial_combo", ports[0])
            dpg.set_value("porta_selecionada_valor", ports[0])
        else:
            dpg.set_value("porta_serial_combo", "")
            dpg.set_value("porta_selecionada_valor", "")

    def process_serial_data(self, t, emg1, emg2, fsr1, fsr2):
        with self.lock:
            self.time_buffer_emg.append(t)
            self.emg1_buffer.append(emg1)
            self.emg2_buffer.append(emg2)
            self.fsr1_buffer.append(fsr1)
            self.fsr2_buffer.append(fsr2)
            self.save_data.append([t, emg1, emg2, fsr1, fsr2])

            while self.time_buffer_emg and (t - self.time_buffer_emg[0]) > self.window_ms:
                self.time_buffer_emg.pop(0)
                self.emg1_buffer.pop(0)
                self.emg2_buffer.pop(0)
                self.fsr1_buffer.pop(0)
                self.fsr2_buffer.pop(0)

            dpg.set_value("emg1_series", [self.time_buffer_emg, self.emg1_buffer])
            dpg.set_value("emg2_series", [self.time_buffer_emg, self.emg2_buffer])
            dpg.set_value("fsr1_series", [self.time_buffer_emg, self.fsr1_buffer])
            dpg.set_value("fsr2_series", [self.time_buffer_emg, self.fsr2_buffer])

            if len(self.time_buffer_emg) > 2:
                xmin = self.time_buffer_emg[-1] - self.window_ms
                xmax = self.time_buffer_emg[-1]
                for tag in ["x_axis_emg1", "x_axis_emg2", "x_axis_fsr1", "x_axis_fsr2"]:
                    dpg.set_axis_limits(tag, xmin, xmax)

            self.update_led("led_emg", True)
            self.update_led("led_fsr", True)

    def serial_error(self, msg):
        print(f"[ERRO] {msg}")
        self.update_led("led_emg", False)
        self.update_led("led_fsr", False)

    def update_led(self, tag, active):
        color = (0, 255, 0, 255) if active else (255, 0, 0, 255)
        dpg.configure_item(tag + "_circle", fill=color)

    def set_window_ms(self, sender, app_data):
        self.window_ms = int(app_data)

    def start_serial_acquisition(self):
        port = dpg.get_value("porta_selecionada_valor")
        if port:
            print(f"[INFO] Iniciando aquisição na porta {port}...")
            self.serial_manager.set_port(port)
            self.serial_manager.start()
        else:
            print("[AVISO] Nenhuma porta selecionada.")

    def save_and_exit(self):
        print("[INFO] Encerrando e salvando dados...")
        self.serial_manager.stop()
        time.sleep(1)

        filename = time.strftime("dados_emg_%Y%m%d_%H%M%S.csv")
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp_ms', 'emg1_raw', 'emg2_raw', 'fsr1', 'fsr2'])
            with self.lock:
                for row_emg in self.save_data:
                    writer.writerow(row_emg)

        print(f"[DADOS SALVOS] Arquivo: {filename}")
        dpg.stop_dearpygui()

    def create_led(self, tag):
        with dpg.drawlist(width=20, height=20, tag=tag):
            dpg.draw_circle((10, 10), 8, fill=(255, 0, 0, 255), tag=tag + "_circle")

    def write(self, message):
        if message.strip():
            self.add_log(message.strip(), level="info")

    def flush(self):
        pass

    def add_log(self, message, level="info"):
        timestamp = time.strftime("%H:%M:%S")
        colors = {
            "info": (200, 200, 200, 255),
            "warning": (255, 200, 0, 255),
            "error": (255, 100, 100, 255)
        }
        color = colors.get(level, (200, 200, 200, 255))
        self.logs.append((f"[{timestamp}] {message}", color))
        self.refresh_terminal()

    def refresh_terminal(self):
        dpg.delete_item("terminal_child", children_only=True)
        for msg, color in self.logs[-200:]:  # mantém últimas 200 mensagens
            dpg.add_text(msg, color=color, parent="terminal_child")
        dpg.set_y_scroll("terminal_child", dpg.get_y_scroll_max("terminal_child"))

    def clear_terminal(self):
        self.logs.clear()
        dpg.delete_item("terminal_child", children_only=True)

    def build_gui(self):
        with dpg.window(label="Aquisição", width=win_width, height=win_height):
            with dpg.group(horizontal=True):
                # Coluna 1
                with dpg.group():
                    with dpg.group(horizontal=True):
                        self.create_led("led_emg")
                        dpg.add_text("Status EMG")

                    with dpg.group(horizontal=True):
                        self.create_led("led_fsr")
                        dpg.add_text("Status FSR")

                dpg.add_spacer(width=10)
                # Coluna 2
                with dpg.group():
                    dpg.add_slider_int(label="Janela (ms)", default_value=self.window_ms, min_value=100, max_value=10000,
                                       callback=self.set_window_ms, width=250)
                    dpg.add_button(label="Iniciar Coleta", callback=self.start_serial_acquisition)
                    dpg.add_button(label="Salvar e Sair", callback=self.save_and_exit)

                dpg.add_spacer(width=10)
                # Coluna 3
                with dpg.group():
                    dpg.add_text("Porta Serial:")
                    dpg.add_combo(self.list_serial_ports(), width=120, tag="porta_serial_combo",
                                  callback=lambda s, a: dpg.set_value("porta_selecionada_valor", a))
                    dpg.add_text("", tag="porta_selecionada_valor", show=False)
                    dpg.add_button(label="Atualizar Portas", callback=lambda: self.refresh_ports())
                    # dpg.add_button(label="Iniciar Coleta", callback=self.start_serial_acquisition)
                    # dpg.add_button(label="Salvar e Sair", callback=self.save_and_exit)

            dpg.add_separator()

            with dpg.group(horizontal=True):
                with dpg.group():
                    with dpg.plot(label="EMG1", height=int(win_height * 0.25), width=int(win_width * 0.45)):
                        dpg.add_plot_axis(dpg.mvXAxis, label="Tempo (ms)", tag="x_axis_emg1")
                        with dpg.plot_axis(dpg.mvYAxis, label="EMG1 (ADC)", tag="y_axis_emg1"):
                            dpg.set_axis_limits("y_axis_emg1", 0.0, 4095.0)
                            dpg.add_line_series([], [], label="EMG1", tag="emg1_series", parent="y_axis_emg1")

                    with dpg.plot(label="EMG2", height=int(win_height * 0.25), width=int(win_width * 0.45)):
                        dpg.add_plot_axis(dpg.mvXAxis, label="Tempo (ms)", tag="x_axis_emg2")
                        with dpg.plot_axis(dpg.mvYAxis, label="EMG2 (ADC)", tag="y_axis_emg2"):
                            dpg.set_axis_limits("y_axis_emg2", 0.0, 4095.0)
                            dpg.add_line_series([], [], label="EMG2", tag="emg2_series", parent="y_axis_emg2")

                with dpg.group():
                    with dpg.plot(label="FSR1", height=int(win_height * 0.25), width=int(win_width * 0.30)):
                        dpg.add_plot_axis(dpg.mvXAxis, label="Tempo (ms)", tag="x_axis_fsr1")
                        with dpg.plot_axis(dpg.mvYAxis, label="FSR1 (ADC)", tag="y_axis_fsr1"):
                            dpg.set_axis_limits("y_axis_fsr1", -10.0, 2500.0)
                            dpg.add_line_series([], [], label="FSR1", tag="fsr1_series", parent="y_axis_fsr1")

                    with dpg.plot(label="FSR2", height=int(win_height * 0.25), width=int(win_width * 0.30)):
                        dpg.add_plot_axis(dpg.mvXAxis, label="Tempo (ms)", tag="x_axis_fsr2")
                        with dpg.plot_axis(dpg.mvYAxis, label="FSR2 (ADC)", tag="y_axis_fsr2"):
                            dpg.set_axis_limits("y_axis_fsr2", -10.0, 2500.0)
                            dpg.add_line_series([], [], label="FSR2", tag="fsr2_series", parent="y_axis_fsr2")

            dpg.add_separator()
            dpg.add_text("Terminal de Logs:")
            dpg.add_button(label="Limpar Terminal", callback=self.clear_terminal)

            with dpg.child_window(tag="terminal_child", autosize_x=True, height=win_height * 0.1, border=True):
                pass

        # Temas
        with dpg.theme() as green_theme:
            with dpg.theme_component(dpg.mvLineSeries):
                dpg.add_theme_color(dpg.mvThemeCol_PlotLines, (0, 255, 0, 255))  # Verde

        with dpg.theme() as pink_theme:
            with dpg.theme_component(dpg.mvLineSeries):
                dpg.add_theme_color(dpg.mvThemeCol_PlotLines, (255, 105, 180, 255))  # Rosa

        # Aplicar temas
        dpg.bind_item_theme("emg1_series", green_theme)
        dpg.bind_item_theme("emg2_series", green_theme)
        dpg.bind_item_theme("fsr1_series", pink_theme)
        dpg.bind_item_theme("fsr2_series", pink_theme)

        dpg.setup_dearpygui()

    def run(self):
        self.build_gui()
        dpg.show_viewport()
        dpg.start_dearpygui()
        dpg.destroy_context()
