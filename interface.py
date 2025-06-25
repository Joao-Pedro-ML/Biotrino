# interface.py
import dearpygui.dearpygui as dpg
import serial.tools.list_ports
import time
import csv
from threading import Lock

from serial_manager import SerialManager
from optical_interrogator import OpticalInterrogator

class MainInterface:
    def __init__(self):
        self.serial_manager = SerialManager(
            on_data_callback=self.process_serial_data,
            on_error_callback=self.serial_error
        )
        self.optical_simulator = OpticalInterrogator(callback=self.process_optical_data)

        self.window_ms = 2000
        self.lock = Lock()

        self.time_buffer_emg = []
        self.emg1_buffer = []
        self.emg2_buffer = []
        self.fsr1_buffer = []
        self.fsr2_buffer = []
        self.time_buffer_opt = []
        self.opt_wavelengths_buffer = []

        self.save_data = []
        self.save_opt_data = []

        dpg.create_context()
        dpg.create_viewport(title='BioTrino', width=1920, height=1280)

    def list_serial_ports(self):
        return [p.device for p in serial.tools.list_ports.comports()]

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

    def process_optical_data(self, t, wavelengths):
        with self.lock:
            self.time_buffer_opt.append(t)
            self.opt_wavelengths_buffer.append(wavelengths)
            self.save_opt_data.append([t] + wavelengths)

            while self.time_buffer_opt and (t - self.time_buffer_opt[0]) > self.window_ms:
                self.time_buffer_opt.pop(0)
                self.opt_wavelengths_buffer.pop(0)

            for i in range(3):
                ys = [row[i] for row in self.opt_wavelengths_buffer]
                dpg.set_value(f"opt_line_{i}", [self.time_buffer_opt, ys])

            if len(self.time_buffer_opt) > 2:
                xmin = self.time_buffer_opt[-1] - self.window_ms
                xmax = self.time_buffer_opt[-1]
                dpg.set_axis_limits("x_axis_opt", xmin, xmax)

                all_vals = [val for row in self.opt_wavelengths_buffer for val in row]
                ymin = min(all_vals)
                ymax = max(all_vals)
                margin = 0.1 * (ymax - ymin)
                dpg.set_axis_limits("y_axis_opt", ymin - margin, ymax + margin)

            self.update_led("led_opt", True)

    def serial_error(self, msg):
        print(msg)
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
            self.serial_manager.set_port(port)
            self.serial_manager.start()
        else:
            print("[Aviso] Nenhuma porta selecionada.")

    def save_and_exit(self):
        self.serial_manager.stop()
        self.optical_simulator.stop()
        time.sleep(1)

        filename = time.strftime("dados_emg_interrogador_%Y%m%d_%H%M%S.csv")
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp_ms', 'emg1_raw', 'emg2_raw', 'fsr1', 'fsr2', 'wavelength1', 'wavelength2', 'wavelength3'])
            with self.lock:
                for row_emg in self.save_data:
                    t_emg = row_emg[0]
                    closest_opt = min(self.save_opt_data, key=lambda r: abs(r[0] - t_emg), default=None)
                    waves = closest_opt[1:] if closest_opt and abs(closest_opt[0] - t_emg) < 50 else [None, None, None]
                    writer.writerow([t_emg, row_emg[1], row_emg[2], row_emg[3], row_emg[4]] + waves)

        print(f"[Dados salvos] Arquivo: {filename}")
        dpg.stop_dearpygui()

    def create_led(self, tag):
        with dpg.drawlist(width=20, height=20, tag=tag):
            dpg.draw_circle((10, 10), 8, fill=(255, 0, 0, 255), tag=tag + "_circle")

    def build_gui(self):
        with dpg.window(label="Aquisição", width=1920, height=1280):
            with dpg.group(horizontal=True):  # Linha 1
                dpg.add_button(label="Salvar e Sair", callback=self.save_and_exit)
                dpg.add_slider_int(label="Janela (ms)", default_value=self.window_ms, min_value=100, max_value=10000,
                                callback=self.set_window_ms, width=250)

            with dpg.group(horizontal=True):
                dpg.add_text("Porta Serial:")
                dpg.add_combo(self.list_serial_ports(), width=120, tag="porta_serial_combo",
                            callback=lambda s, a: dpg.set_value("porta_selecionada_valor", a))
                dpg.add_text("", tag="porta_selecionada_valor", show=False)

                dpg.add_button(label="Iniciar Coleta", callback=self.start_serial_acquisition)

            with dpg.group(horizontal=True):  # Linha 3
                dpg.add_text("Status EMG:")
                self.create_led("led_emg")
                dpg.add_text("Status FSR:")
                self.create_led("led_fsr")
                dpg.add_text("Status Interrogador Óptico:")
                self.create_led("led_opt")

            dpg.add_separator()

            with dpg.group(horizontal=True):
                with dpg.group():
                    with dpg.plot(label="EMG1", height=350, width=600):
                        dpg.add_plot_axis(dpg.mvXAxis, label="Tempo (ms)", tag="x_axis_emg1")
                        with dpg.plot_axis(dpg.mvYAxis, label="EMG1 (ADC)", tag="y_axis_emg1"):
                            dpg.set_axis_limits("y_axis_emg1", 0.0, 4095.0)
                            dpg.add_line_series([], [], label="EMG1", tag="emg1_series", parent="y_axis_emg1")

                    with dpg.plot(label="EMG2", height=350, width=600):
                        dpg.add_plot_axis(dpg.mvXAxis, label="Tempo (ms)", tag="x_axis_emg2")
                        with dpg.plot_axis(dpg.mvYAxis, label="EMG2 (ADC)", tag="y_axis_emg2"):
                            dpg.set_axis_limits("y_axis_emg2", 0.0, 4095.0)
                            dpg.add_line_series([], [], label="EMG2", tag="emg2_series", parent="y_axis_emg2")

                with dpg.group():
                    with dpg.plot(label="FSR1", height=350, width=450):
                        dpg.add_plot_axis(dpg.mvXAxis, label="Tempo (ms)", tag="x_axis_fsr1")
                        with dpg.plot_axis(dpg.mvYAxis, label="FSR1 (ADC)", tag="y_axis_fsr1"):
                            dpg.set_axis_limits("y_axis_fsr1", -10.0, 2500.0)
                            dpg.add_line_series([], [], label="FSR1", tag="fsr1_series", parent="y_axis_fsr1")

                    with dpg.plot(label="FSR2", height=350, width=450):
                        dpg.add_plot_axis(dpg.mvXAxis, label="Tempo (ms)", tag="x_axis_fsr2")
                        with dpg.plot_axis(dpg.mvYAxis, label="FSR2 (ADC)", tag="y_axis_fsr2"):
                            dpg.set_axis_limits("y_axis_fsr2", -10.0, 2500.0)
                            dpg.add_line_series([], [], label="FSR2", tag="fsr2_series", parent="y_axis_fsr2")

                with dpg.group():
                    with dpg.plot(label="Interrogador Óptico", height=700, width=450):
                        dpg.add_plot_axis(dpg.mvXAxis, label="Tempo (ms)", tag="x_axis_opt")
                        with dpg.plot_axis(dpg.mvYAxis, label="Wavelength (nm)", tag="y_axis_opt"):
                            for i in range(3):
                                dpg.add_line_series([], [], label=f"Wavelength {i + 1}", tag=f"opt_line_{i}")

        # Criar temas
        with dpg.theme() as green_theme:
            with dpg.theme_component(dpg.mvLineSeries):
                dpg.add_theme_color(dpg.mvThemeCol_PlotLines, (0, 255, 0, 255))  # Verde

        with dpg.theme() as pink_theme:
            with dpg.theme_component(dpg.mvLineSeries):
                dpg.add_theme_color(dpg.mvThemeCol_PlotLines, (255, 105, 180, 255))  # Rosa

        with dpg.theme() as blue_theme:
            with dpg.theme_component(dpg.mvLineSeries):
                dpg.add_theme_color(dpg.mvThemeCol_PlotLines, (0, 0, 255, 255))  # azul

        # Aplicar temas
        dpg.bind_item_theme("emg1_series", green_theme)
        dpg.bind_item_theme("emg2_series", green_theme)
        dpg.bind_item_theme("fsr1_series", pink_theme)
        dpg.bind_item_theme("fsr2_series", pink_theme)
        for i in range(3):
            dpg.bind_item_theme(f"opt_line_{i}", blue_theme)

        dpg.setup_dearpygui()

    def run(self):
        self.build_gui()
        self.optical_simulator.start()
        dpg.show_viewport()
        # dpg.bind_item_theme("emg1_series", self.green_theme)
        # dpg.bind_item_theme("emg2_series", self.green_theme)
        # dpg.bind_item_theme("fsr1_series", self.pink_theme)
        # dpg.bind_item_theme("fsr2_series", self.pink_theme)
        # for i in range(3):
        #     dpg.bind_item_theme(f"opt_line_{i}", self.blue_theme)
        dpg.start_dearpygui()
        dpg.destroy_context()
