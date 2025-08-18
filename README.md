# Biotrino

This project acquires sEMG (2 channels) and FSR signals in real time, displaying the graphs in a modern graphical interface using [Dear PyGui](https://github.com/hoffstadt/DearPyGui).

---

## 🖥️ Features

- Serial reading of EMG and FSR signals (via proprietary board).
- Interface divided into three sections:
  - EMG (2 channels)
  - FSR (2 channels)
  - Terminal for logs
- Controls for:
  - Adjusting the display window (slider).
  - Button to save data to `.csv`.
  - Visual indicators (LEDs) for communication status.
  - Export of synchronized data in `.csv` format.

---

## 📷 Interface

![Interface](img/screenshot.png)

---

## 📦 Requirements

- Python 3.8 or higher

---

## 🚀 Step-by-step guide to running the project

### 1. Clone the repository (if you haven't already)

```bash
git clone <repository-url>
cd <folder-name>
```

### 2. Create a virtual environment (recommended)

- On Windows (PowerShell):

```bash
python -m venv venv
.\venv\Scripts\Activate.ps1
```

- On Windows (Command Prompt):

```bash
python -m venv venv
venv\Scripts\activate.bat
```

- On Linux/MacOS:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Execute
```bash
python main.py
```
