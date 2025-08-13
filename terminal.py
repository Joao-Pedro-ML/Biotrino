import dearpygui.dearpygui as dpg
import sys
import time
from threading import Thread

class MainInterface:
    def __init__(self):
        self.logs = []  # armazena mensagens do terminal

        # Redireciona prints para o terminal
        sys.stdout = self
        sys.stderr = self

        dpg.create_context()
        self.build_gui()

    # Função para receber mensagens de print()
    def write(self, message):
        if message.strip():
            self.add_log(message.strip(), level="info")

    def flush(self):
        pass

    # Adiciona mensagem ao terminal
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

    # Atualiza o terminal
    def refresh_terminal(self):
        dpg.delete_item("terminal_child", children_only=True)
        for msg, color in self.logs[-200:]:  # mantém últimas 200 mensagens
            dpg.add_text(msg, color=color, parent="terminal_child")
        dpg.set_y_scroll("terminal_child", dpg.get_y_scroll_max("terminal_child"))

    # Simulação de processo que gera mensagens
    def run_process(self):
        def task():
            print("Iniciando processo...")
            time.sleep(0.5)
            self.add_log("Processo em execução...", "info")
            time.sleep(0.5)
            self.add_log("Aviso: execução lenta detectada.", "warning")
            time.sleep(0.5)
            self.add_log("Erro: conexão perdida!", "error")
            print("Processo finalizado.")
        Thread(target=task, daemon=True).start()

    # Criação da GUI
    def build_gui(self):
        viewport_width = 900
        viewport_height = 600
        with dpg.window(label="Meu App com Terminal", tag="main_window", width=viewport_width, height=viewport_height):
            dpg.add_button(label="Rodar Processo", callback=self.run_process)
            dpg.add_separator()
            dpg.add_text("Terminal de Mensagens", color=(150, 255, 150))
            with dpg.child_window(tag="terminal_child", autosize_x=True, height=200, border=True):
                pass

        dpg.create_viewport(title='App Responsivo com Terminal', width=viewport_width, height=viewport_height)
        dpg.set_primary_window("main_window", True)
        dpg.setup_dearpygui()

    # Roda a GUI
    def run(self):
        dpg.show_viewport()
        dpg.start_dearpygui()
        dpg.destroy_context()


if __name__ == "__main__":
    app = MainInterface()
    app.run()
