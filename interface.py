import serial
import threading
import time
import csv
import math
import random
import dearpygui.dearpygui as dpg

# Configurações
SERIAL_PORT = "COM5"
BAUD_RATE = 115200
WINDOW_MS_DEFAULT = 2000
window_ms = WINDOW_MS_DEFAULT

# Buffers
time_buffer_emg = []
emg1_buffer = []
emg2_buffer = []
fsr1_buffer = []
fsr2_buffer = []
time_buffer_opt = []
opt_wavelengths_buffer = []

# Dados para salvar
save_data = []
save_opt_data = []

# Controle
running = True
t0 = None  # Referência de tempo
lock = threading.Lock()

def update_led(tag, active):
    color = (0, 255, 0, 255) if active else (255, 0, 0, 255)
    dpg.configure_item(tag + "_circle", fill=color)

# Thread: Leitura EMG
def serial_reader():
    global running, t0
    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE) as ser:
            time.sleep(2)
            t0 = time.perf_counter()

            while running:
                try:
                    line = ser.readline().decode(errors="ignore").strip()
                    parts = line.split(',')
                    if len(parts) == 4 and all(p.strip().isdigit() for p in parts):
                        emg1, emg2, fsr1, fsr2 = map(int, parts)
                        t_now = (time.perf_counter() - t0) * 1000  # ms

                        with lock:
                            time_buffer_emg.append(t_now)
                            emg1_buffer.append(emg1)
                            emg2_buffer.append(emg2)
                            fsr1_buffer.append(fsr1)
                            fsr2_buffer.append(fsr2)

                            save_data.append([t_now, emg1, emg2, fsr1, fsr2])

                            # Remover dados fora da janela
                            while time_buffer_emg and (t_now - time_buffer_emg[0]) > window_ms:
                                time_buffer_emg.pop(0)
                                emg1_buffer.pop(0)
                                emg2_buffer.pop(0)
                                fsr1_buffer.pop(0)
                                fsr2_buffer.pop(0)

                            # Atualizar gráficos
                            dpg.set_value("emg1_series", [time_buffer_emg, emg1_buffer])
                            dpg.set_value("emg2_series", [time_buffer_emg, emg2_buffer])
                            dpg.set_value("fsr1_series", [time_buffer_emg, fsr1_buffer])
                            dpg.set_value("fsr2_series", [time_buffer_emg, fsr2_buffer])

                            # Atualizar eixos
                            if len(time_buffer_emg) > 2:
                                xmin = time_buffer_emg[-1] - window_ms
                                xmax = time_buffer_emg[-1]
                                dpg.set_axis_limits("x_axis_emg1", xmin, xmax)
                                dpg.set_axis_limits("x_axis_emg2", xmin, xmax)
                                dpg.set_axis_limits("x_axis_fsr1", xmin, xmax)
                                dpg.set_axis_limits("x_axis_fsr2", xmin, xmax)

                            # Atualizar LED EMG
                            update_led("led_emg", True)
                            # Atualizar LED FSR
                            update_led("led_fsr", True)

                except Exception as e:
                    print(f"[Erro ao processar dados do ESP32] {e}")
                    update_led("led_emg", False)
                    update_led("led_fsr", False)
    except Exception as e:
        print(f"[Erro serial] {e}")

# Thread: Interrogador Óptico (simulado)
def simulated_interrogator_reader():
    global running
    while running:
        try:
            t_now = (time.perf_counter() - t0) * 1000 if t0 else 0

            simulated_values = [
                1550 + 0.5 * math.sin(time.time() * 2 * math.pi * 0.1 + i) + random.uniform(-0.05, 0.05)
                for i in range(3)
            ]

            with lock:
                time_buffer_opt.append(t_now)
                opt_wavelengths_buffer.append(simulated_values)
                save_opt_data.append([t_now] + simulated_values)

                # Remover dados fora da janela
                while time_buffer_opt and (t_now - time_buffer_opt[0]) > window_ms:
                    time_buffer_opt.pop(0)
                    opt_wavelengths_buffer.pop(0)

                # Atualizar gráfico óptico
                for i in range(3):
                    ys = [row[i] for row in opt_wavelengths_buffer]
                    dpg.set_value(f"opt_line_{i}", [time_buffer_opt, ys])

                if len(time_buffer_opt) > 2:
                    xmin = time_buffer_opt[-1] - window_ms
                    xmax = time_buffer_opt[-1]
                    dpg.set_axis_limits("x_axis_opt", xmin, xmax)

                # Ajustar eixo Y auto
                all_vals = [val for row in opt_wavelengths_buffer for val in row]
                ymin = min(all_vals)
                ymax = max(all_vals)
                margin = 0.1 * (ymax - ymin)
                dpg.set_axis_limits("y_axis_opt", ymin - margin, ymax + margin)

                # Atualizar LED óptico
                update_led("led_opt", True)

            time.sleep(0.01)
        except Exception as e:
            print(f"[Erro interrogador] {e}")
            update_led("led_opt", False)

# Slider janela
def set_window_ms(sender, app_data):
    global window_ms
    window_ms = int(app_data)

# Salvar CSV
def save_and_exit_callback():
    global running
    running = False
    time.sleep(1)

    filename = time.strftime("dados_emg_interrogador_%Y%m%d_%H%M%S.csv")
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        header = ['timestamp_ms', 'emg1_raw', 'emg2_raw', 'fsr1', 'fsr2', 'wavelength1', 'wavelength2', 'wavelength3']
        writer.writerow(header)

        with lock:
            for row_emg in save_data:
                t_emg = row_emg[0]
                # Busca dado óptico mais próximo
                closest_opt = None
                closest_diff = 1e9
                for row_opt in save_opt_data:
                    diff = abs(row_opt[0] - t_emg)
                    if diff < closest_diff:
                        closest_diff = diff
                        closest_opt = row_opt
                if closest_diff < 50:
                    waves = closest_opt[1:]
                else:
                    waves = [None, None, None]

                writer.writerow([t_emg, row_emg[1], row_emg[2], row_emg[3], row_emg[4]] + waves)

    print(f"[Dados salvos] Arquivo: {filename}")
    dpg.stop_dearpygui()

def create_led(tag):
    with dpg.drawlist(width=20, height=20, tag=tag):
        dpg.draw_circle((10,10), 8, fill=(255,0,0,255), tag=tag+"_circle")

# Interface DPG
dpg.create_context()
dpg.create_viewport(title='Monitor EMG + Interrogador', width=1920, height=1280)

with dpg.window(label="Aquisição", width=1920, height=1280):

    # Seção de controle (topo)
    with dpg.group(horizontal=True):
        dpg.add_button(label="Salvar e Sair", callback=save_and_exit_callback)
        dpg.add_slider_int(label="Janela (ms)", default_value=WINDOW_MS_DEFAULT, min_value=100, max_value=10000,
                           callback=set_window_ms, width=300)

        with dpg.group(horizontal=True):
            dpg.add_text("Status EMG:")
            create_led("led_emg")
            dpg.add_text("Status FSR:")
            create_led("led_fsr")  # <- NOVO LED PARA FSR
            dpg.add_text("Status Interrogador Óptico:")
            create_led("led_opt")

    dpg.add_separator()

    # Área principal com 3 colunas verticais
    with dpg.group(horizontal=True):

        # Coluna 1: EMG1 e EMG2
        with dpg.group():
            with dpg.plot(label="EMG1", height=360, width=600):
                dpg.add_plot_axis(dpg.mvXAxis, label="Tempo (ms)", tag="x_axis_emg1")
                with dpg.plot_axis(dpg.mvYAxis, label="EMG1 (ADC)", tag="y_axis_emg1"):
                    dpg.set_axis_limits("y_axis_emg1", 0.0, 4095.0)
                    dpg.add_line_series([], [], label="EMG1", tag="emg1_series")

            with dpg.plot(label="EMG2", height=360, width=600):
                dpg.add_plot_axis(dpg.mvXAxis, label="Tempo (ms)", tag="x_axis_emg2")
                with dpg.plot_axis(dpg.mvYAxis, label="EMG2 (ADC)", tag="y_axis_emg2"):
                    dpg.set_axis_limits("y_axis_emg2", 0.0, 4095.0)
                    dpg.add_line_series([], [], label="EMG2", tag="emg2_series")

        # Coluna 2: FSR1 e FSR2
        with dpg.group():
            with dpg.plot(label="FSR1", height=360, width=450):
                dpg.add_plot_axis(dpg.mvXAxis, label="Tempo (ms)", tag="x_axis_fsr1")
                with dpg.plot_axis(dpg.mvYAxis, label="FSR1 (ADC)", tag="y_axis_fsr1"):
                    dpg.set_axis_limits("y_axis_fsr1", -10.0, 2500.0)
                    dpg.add_line_series([], [], label="FSR1", tag="fsr1_series")

            with dpg.plot(label="FSR2", height=360, width=450):
                dpg.add_plot_axis(dpg.mvXAxis, label="Tempo (ms)", tag="x_axis_fsr2")
                with dpg.plot_axis(dpg.mvYAxis, label="FSR2 (ADC)", tag="y_axis_fsr2"):
                    dpg.set_axis_limits("y_axis_fsr2", -10.0, 2500.0)
                    dpg.add_line_series([], [], label="FSR2", tag="fsr2_series")

        # Coluna 3: Interrogador Óptico
        with dpg.group():
            with dpg.plot(label="Interrogador Óptico", height=720, width=450):
                dpg.add_plot_axis(dpg.mvXAxis, label="Tempo (ms)", tag="x_axis_opt")
                with dpg.plot_axis(dpg.mvYAxis, label="Wavelength (nm)", tag="y_axis_opt"):
                    for i in range(3):
                        dpg.add_line_series([], [], label=f"Wavelength {i+1}", tag=f"opt_line_{i}")

dpg.setup_dearpygui()

# Inicia threads
thread_emg = threading.Thread(target=serial_reader, daemon=True)
thread_opt = threading.Thread(target=simulated_interrogator_reader, daemon=True)
thread_emg.start()
thread_opt.start()

dpg.show_viewport()
dpg.start_dearpygui()
dpg.destroy_context()
