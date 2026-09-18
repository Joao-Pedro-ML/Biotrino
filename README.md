# BioTrino — aquisição de EMG e FSR

Sistema para aquisição, visualização e armazenamento de dois canais de
eletromiografia de superfície (sEMG) e dois sensores resistivos de força (FSR).
Um ESP32 realiza a conversão A/D e transmite as amostras pela porta serial para
uma interface desenvolvida em Python com Dear PyGui.

## Funcionalidades

- Aquisição simultânea de EMG1, EMG2, FSR1 e FSR2 a 1 kHz.
- Gráficos em tempo real com janela temporal configurável.
- Interface responsiva ao tamanho da janela e do monitor, sem barras de rolagem.
- Conexão e desconexão segura da porta serial.
- Gravação incremental em CSV para reduzir o risco de perda de dados.
- Identificação do participante ou ensaio no nome e nos metadados do arquivo.
- Medição da frequência real de amostragem.
- Detecção de amostras perdidas, linhas inválidas e saturação do ADC.
- Pausa dos gráficos sem interromper a aquisição ou a gravação.
- Compatibilidade de leitura com o protocolo legado de quatro colunas.

## Estrutura principal

```text
FSR_EMG/
  platformio.ini       Configuração do projeto ESP32
  src/main.cpp         Firmware da placa de aquisição
interface.py           Interface gráfica e gravação dos dados
serial_manager.py      Comunicação serial e validação dos pacotes
main.py                Ponto de entrada da aplicação
out_data/              Arquivos CSV produzidos nas coletas
test/                   Testes automatizados do protocolo serial
requirements.txt       Dependências Python
```

## Requisitos

- Windows 10 ou 11.
- Python 3.11 recomendado.
- ESP32 Dev Module ou placa compatível.
- VS Code com a extensão PlatformIO, ou PlatformIO Core instalado.
- Cabo USB capaz de transmitir dados.

## Preparação da interface

Abra o PowerShell na pasta do projeto e crie um ambiente virtual:

```powershell
py -3.11 -m venv dpg_env
.\dpg_env\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Se o ambiente `dpg_env` já estiver configurado, basta ativá-lo:

```powershell
.\dpg_env\Scripts\Activate.ps1
```

Para executar a aplicação:

```powershell
python main.py
```

Também é possível executar sem ativar o ambiente:

```powershell
.\dpg_env\Scripts\python.exe main.py
```

## Firmware do ESP32

O projeto PlatformIO está na pasta `FSR_EMG`. A configuração padrão utiliza:

- Placa: `esp32dev`.
- Framework: Arduino.
- Comunicação serial: `921600` baud.
- Resolução do ADC: 12 bits, com valores de 0 a 4095.
- Frequência nominal: 1000 amostras por segundo.

### Canais de entrada

| Canal | GPIO |
| --- | ---: |
| EMG1 | 34 |
| EMG2 | 35 |
| FSR1 | 32 |
| FSR2 | 33 |

### Upload pelo VS Code

1. Abra a pasta `FSR_EMG` no VS Code.
2. Aguarde o PlatformIO carregar o ambiente `esp32dev`.
3. Conecte o ESP32 por USB.
4. Clique em **PlatformIO: Upload**.
5. Aguarde a mensagem de upload concluído.

### Upload pelo terminal

Com o PlatformIO disponível no `PATH`:

```powershell
cd FSR_EMG
pio run
pio run --target upload
```

Para abrir o monitor serial:

```powershell
pio device monitor
```

Não deixe o monitor serial aberto ao mesmo tempo que a interface, pois apenas um
programa pode utilizar a mesma porta COM por vez.

## Procedimento de coleta

1. Faça o upload do firmware atualizado no ESP32.
2. Execute `python main.py`.
3. Clique em **Atualizar portas** se a placa ainda não aparecer.
4. Selecione a porta identificada como ESP32, CP210x, CH340 ou dispositivo
   serial equivalente.
5. Mantenha o baud rate em `921600`.
6. Clique em **Conectar**.
7. Aguarde o estado **Recebendo dados** e a indicação **Fluxo válido**.
8. Preencha **Identificação** com o participante, ensaio ou condição experimental.
9. Clique em **Iniciar coleta**.
10. Acompanhe frequência, amostras perdidas, pacotes inválidos e saturação dos
    canais durante o experimento.
11. Clique em **Parar e salvar** ao terminar.
12. Use **Nova coleta** para limpar os gráficos e preparar outro ensaio.
13. Clique em **Desconectar** antes de retirar o cabo USB.

Os dados são salvos automaticamente em `out_data`. O arquivo é aberto no início
da coleta e sincronizado periodicamente, portanto um arquivo parcial tende a ser
preservado mesmo se a aplicação for interrompida.

## Controles da interface

- **Conectar/Desconectar:** controla a comunicação com a placa.
- **Atualizar portas:** refaz a busca por dispositivos seriais.
- **Identificação:** adiciona um nome seguro ao arquivo da sessão.
- **Iniciar coleta:** inicia a gravação incremental.
- **Parar e salvar:** encerra e fecha corretamente o CSV.
- **Nova coleta:** limpa os dados exibidos e prepara uma nova sessão.
- **Janela temporal:** define, em segundos, o intervalo mostrado nos gráficos.
  Arraste a barra, use `Ctrl + clique` para digitar um valor ou use os botões
  laterais para ajustar em passos de `0,5 s`.
- **Pausar gráficos:** interrompe somente o redesenho; a aquisição continua.
- **Autoescala Y:** ajusta os limites verticais aos dados visíveis.

A interface recalcula automaticamente as dimensões quando a janela é
redimensionada ou movida para outro monitor. O tamanho mínimo é `960 × 640`.

## Indicadores de qualidade

- **Fluxo:** informa se pacotes válidos estão chegando.
- **Frequência:** taxa calculada a partir do contador e timestamp do ESP32.
- **Recebidas:** quantidade de amostras válidas recebidas desde a conexão.
- **Perdidas:** lacunas detectadas no contador de amostras.
- **Inválidas:** linhas corrompidas ou fora do formato esperado.
- **Fila descartada:** amostras descartadas se a interface ficar excessivamente
  atrasada.
- **Gravadas:** quantidade registrada no arquivo da coleta atual.
- **Duração:** tempo decorrido da gravação.

Os valores instantâneos ficam vermelhos quando se aproximam de 0 ou 4095,
indicando possível saturação do conversor A/D.

## Protocolo serial

Ao iniciar, o firmware anuncia:

```text
#BIOTRINO,1,1000,4
```

Cada amostra utiliza seis campos:

```text
numero_amostra,timestamp_us,emg1,emg2,fsr1,fsr2
```

Exemplo:

```text
1523,4872150,2040,1987,812,745
```

O número da amostra permite detectar ciclos perdidos. O timestamp é produzido no
ESP32, evitando que atrasos do computador sejam confundidos com o tempo real de
aquisição.

O formato legado abaixo ainda pode ser lido selecionando o baud rate utilizado
pelo firmware antigo, normalmente `115200`:

```text
emg1,emg2,fsr1,fsr2
```

Nesse modo, frequência da placa e amostras perdidas não podem ser determinadas
com precisão e aparecem como indisponíveis.

## Formato do arquivo CSV

O arquivo começa com metadados prefixados por `#`, seguidos pelas colunas:

| Coluna | Descrição |
| --- | --- |
| `sample_number` | Contador produzido pelo ESP32 |
| `device_timestamp_us` | Tempo do ESP32 em microssegundos |
| `host_timestamp_ms` | Momento de recepção no computador |
| `missing_before` | Amostras ausentes antes da linha atual |
| `emg1_raw` | Leitura ADC do canal EMG1 |
| `emg2_raw` | Leitura ADC do canal EMG2 |
| `fsr1_raw` | Leitura ADC do canal FSR1 |
| `fsr2_raw` | Leitura ADC do canal FSR2 |

Para carregar o arquivo com pandas ignorando os metadados:

```python
import pandas as pd

dados = pd.read_csv("out_data/arquivo.csv", comment="#")
```

## Testes

Os testes do protocolo não precisam de uma placa conectada:

```powershell
python -m unittest discover -s test -p "test_*.py" -v
```

## Solução de problemas

### A porta não aparece

- Confirme que o cabo USB transmite dados.
- Clique em **Atualizar portas**.
- Verifique o Gerenciador de Dispositivos do Windows.
- Instale o driver do conversor USB da placa, normalmente CP210x ou CH340.

### A porta abre, mas não chegam dados

- Confirme que o firmware atualizado foi enviado ao ESP32.
- Verifique se firmware e interface usam o mesmo baud rate.
- Feche o monitor serial do Arduino IDE ou PlatformIO.
- Pressione o botão `EN/RESET` do ESP32 e reconecte.

### Há muitas amostras perdidas ou inválidas

- Utilize `921600` baud com o firmware atual.
- Evite hubs USB e cabos longos ou de baixa qualidade.
- Feche aplicações que estejam consumindo muita CPU.
- Confira se os quatro sinais permanecem entre 0 e 4095.

### O PowerShell bloqueia a ativação do ambiente

Execute a aplicação diretamente, sem ativação:

```powershell
.\dpg_env\Scripts\python.exe main.py
```
