# Biotrino

Este projeto realiza a aquisição de sinais de **EMG (2 canais)** e **FSR** em tempo real, exibindo os gráficos em uma interface gráfica moderna usando [Dear PyGui](https://github.com/hoffstadt/DearPyGui).

---
## 📥 Download
[![Baixar Executável](https://img.shields.io/badge/Download-EXE-blue?style=for-the-badge)]([https://github.com/Joao-Pedro-ML/Biotrino/releases/latest/download/main.exe](https://github.com/Joao-Pedro-ML/Biotrino/releases/latest/download/main.exe))

[![Baixar Executável](https://img.shields.io/badge/Download-EXE-blue?style=for-the-badge)](https://github.com/Joao-Pedro-ML/Biotrino/releases/latest/download/main.exe)
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

![Interface](img/screenshot.png)

---

## 📦 Requisitos

- Python 3.8 ou superior

---

## 🚀 Passo a passo para rodar o projeto

### 1. Clonar o repositório (se ainda não fez)

```bash
git clone <url-do-repositorio>
cd <nome-da-pasta>
```

### 2. Criar um ambiente virtual (recomendado)

- No Windows (PowerShell):

```bash
python -m venv venv
.\venv\Scripts\Activate.ps1
```

- No Windows (Prompt de Comando):

```bash
python -m venv venv
venv\Scripts\activate.bat
```

- No Linux/MacOS:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar dependências
```bash
pip install -r requirements.txt
```

### 4. Executar
```bash
python main.py
```
