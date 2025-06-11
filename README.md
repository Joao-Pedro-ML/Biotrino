# Biotrino

Este projeto realiza a aquisição de sinais de **EMG (2 canais)**, **FSR** e de um **interrogador óptico** em tempo real, exibindo os gráficos em uma interface gráfica moderna usando [Dear PyGui](https://github.com/hoffstadt/DearPyGui).

---

## 🖥️ Funcionalidades

- Leitura serial dos sinais EMG e FSR (via ESP32 ou Arduino).
- Simulação do interrogador óptico.
- Interface dividida em três seções:
  - EMG (2 canais)
  - FSR
  - Interrogador óptico
- Controles para:
  - Ajuste da janela de exibição (slider).
  - Botão para salvar os dados em `.csv`.
  - Indicadores visuais (LEDs) para status de comunicação.
- Exportação de dados sincronizados em formato `.csv`.

---

## 📷 Interface

![screenshot opcional aqui, se desejar adicionar](#)

---

## 📦 Requisitos

- Python 3.8 ou superior

### Instalar dependências

```bash
pip install -r requirements.txt
