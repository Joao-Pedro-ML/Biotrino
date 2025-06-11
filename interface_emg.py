import serial
import threading
import time
import csv
import dearpygui.dearpygui as dpg

SERIAL_PORT = "COM5"
BAUD_RATE = 115200

# Variáveis globais
data = []
running = True
time_buffer = []
emg1_buffer = []
emg2_buffer = []
window_ms = 500

t0 = None  # Referência de tempo inicial

def serial_reader():
    global running, window_ms, t0
    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE) as ser:
            time.sleep(2)
            t0 = time.perf_counter()  # Marca início da aquisição no PC
            while running:
                try:
                    line = ser.readline().decode(errors="ignore").strip()
                    parts = line.split(',')
                    if len(parts) == 2 and all(p.strip().isdigit() for p in parts):
                        emg1, emg2 = map(int, parts)

                        # Calcula timestamp atual em ms
                        t_now = (time.perf_counter() - t0) * 1000  # em ms

                        time_buffer.append(t_now)
                        emg1_buffer.append(emg1)
                        emg2_buffer.append(emg2)

                        # Remove dados antigos fora da janela
                        while time_buffer and (t_now - time_buffer[0]) > window_ms:
                            time_buffer.pop(0)
                            emg1_buffer.pop(0)
                            emg2_buffer.pop(0)

                        # Atualiza gráfico EMG1
                        dpg.set_value("emg1_series", [time_buffer, emg1_buffer])
                        # Atualiza gráfico EMG2
                        dpg.set_value("emg2_series", [time_buffer, emg2_buffer])

                        # Atualiza eixo X (scroll automático)
                        if len(time_buffer) > 2:
                            xmin = time_buffer[-1] - window_ms
                            xmax = time_buffer[-1]
                            dpg.set_axis_limits("x_axis_emg1", xmin, xmax)
                            dpg.set_axis_limits("x_axis_emg2", xmin, xmax)

                        # Armazena para salvar depois
                        data.append([t_now, emg1, emg2])
                except Exception as e:
                    print(f"[Erro ao processar linha] {e}")
    except Exception as e:
        print(f"[Erro serial] {e}")

def set_window_ms(sender, app_data):
    global window_ms
    window_ms = int(app_data)

def save_and_exit_callback():
    global running
    running = False
    time.sleep(1)

    filename = time.strftime("dados_emg_dual_%Y%m%d_%H%M%S.csv")
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp_ms', 'emg1_raw', 'emg2_raw'])
        writer.writerows(data)
    print(f"Dados salvos em: {filename}")
    dpg.stop_dearpygui()

# Interface DPG
dpg.create_context()
dpg.create_viewport(title='Monitor EMG - 2 Canais', width=800, height=900)

with dpg.window(label="Aquisição EMG - 2 Canais", width=780, height=880):
    dpg.add_button(label="Salvar e Sair", callback=save_and_exit_callback)

    dpg.add_slider_int(label="Janela (ms)", default_value=2000, min_value=100, max_value=7000,
                       callback=set_window_ms, width=300)

    # Gráfico EMG1
    with dpg.plot(label="EMG1 (ADC 12 bits)", height=300, width=750):
        dpg.add_plot_axis(dpg.mvXAxis, label="Tempo (ms)", tag="x_axis_emg1")
        with dpg.plot_axis(dpg.mvYAxis, label="EMG1 (0–3.3V)", tag="y_axis_emg1"):
            dpg.set_axis_limits("y_axis_emg1", 0.0, 1800.0)
            dpg.add_line_series([], [], label="EMG1", tag="emg1_series")

    # Gráfico EMG2
    with dpg.plot(label="EMG2 (ADC 12 bits)", height=300, width=750):
        dpg.add_plot_axis(dpg.mvXAxis, label="Tempo (ms)", tag="x_axis_emg2")
        with dpg.plot_axis(dpg.mvYAxis, label="EMG2 (0–3.3V)", tag="y_axis_emg2"):
            dpg.set_axis_limits("y_axis_emg2", 0.0, 1800.0)
            dpg.add_line_series([], [], label="EMG2", tag="emg2_series")

# Inicia thread de leitura serial
threading.Thread(target=serial_reader, daemon=True).start()

# Executa interface
dpg.setup_dearpygui()
dpg.show_viewport()
dpg.start_dearpygui()
dpg.destroy_context()
