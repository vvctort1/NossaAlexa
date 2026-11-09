# EVA: Assistente Autônoma com ESP32 e TinyML

![Status](https://img.shields.io/badge/Status-Em_Desenvolvimento-brightgreen)
![Hardware](https://img.shields.io/badge/Hardware-ESP32-blue)
![Backend](https://img.shields.io/badge/Backend-Python%20%7C%20Flask-yellow)
![AI](https://img.shields.io/badge/AI-TinyML%20%7C%20Gemma_4-purple)

**Eva** é uma assistente virtual interativa (com design inspirado no universo WALL-E) que une robótica embarcada, computação de borda (*Edge Computing*) e Inteligência Artificial Generativa. 

O projeto divide o processamento entre um microcontrolador local (que atua como o sistema nervoso e sensorial autônomo) e um servidor local (o "cérebro"), permitindo interações por voz, reconhecimento facial, automação de tarefas e expressões visuais fluidas.

---

## Visão Geral e Contexto da Solução

O objetivo da Eva é materializar a IA, tirando-a da tela do computador e dando-lhe uma presença física no ambiente. A solução resolve o problema de alto consumo de recursos (CPU/Bateria) típico de assistentes de voz tradicionais, delegando a escuta contínua para um hardware de baixíssimo consumo (ESP32).

Quando a Eva está "dormindo", o servidor principal no computador fica ocioso. Apenas quando um gatilho sonoro (palma ou som agudo) é detectado localmente pela rede neural embarcada no ESP32, a assistente "acorda" fisicamente e solicita o processamento de linguagem natural ao servidor.

---

## Integração entre Sensores e IA (Arquitetura)

A arquitetura do sistema funciona sob um fluxo de reatividade orientada a eventos:

1. **Sistema Sensorial de Borda (TinyML + ESP32):** 
   - O microfone I2S (INMP441) capta áudio ambiente.
   - Um modelo de **Machine Learning Quantizado (Int8)** treinado via *Edge Impulse* roda nativamente no ESP32. Ele analisa o espectro sonoro em janelas de 1 segundo.
   - O sensor PIR monitoriza a presença humana, ativando ou desativando os olhos (Telas OLED) proativamente.
2. **O Gatilho (Handshake HTTP):** 
   - Ao reconhecer a assinatura acústica de ativação com >95% de confiança, o ESP32 muda a sua expressão facial para um sorriso e dispara uma requisição `HTTP GET` para o servidor Flask no computador local.
3. **Cérebro (Python + Ollama + Visão Computacional):**
   - O computador, ao receber o gatilho, ativa o seu microfone e a câmera.
   - **Visão:** Executa reconhecimento facial (OpenCV/LBPH) para saudar o utilizador pelo nome e aplicar permissões (ex: ler/apagar agenda).
   - **Voz e NLP:** Transcreve o áudio (SpeechRecognition), processa a intenção e, se for uma conversa aberta, consulta o modelo local via Ollama.
   - **Resposta:** A resposta em texto é convertida em fala (Edge-TTS) e reproduzida, enquanto comandos de retorno (ex: `/pensar`, `/acenar`) são enviados de volta ao ESP32 para sincronizar o corpo mecânico com o estado da IA.

---

## Componentes de Hardware e Peça imprimida em 3D

### Hardware Eletrônico
* **Microcontrolador:** ESP32 (Atua como hub IOT e motor TinyML).
* **Visão/Expressão:** 2x Telas OLED 0.96" SSD1306 (Comunicação via barramento duplo I2C - pinos padrão e pinos 32/33).
* **Audição (Local):** Microfone Omnidirecional INMP441 (Interface I2S).
* **Presença:** Sensor de Movimento HC-SR501 PIR (Ajustado via hardware para sensibilidade reduzida, mitigando ruído Wi-Fi).
* **Movimentação:** Servomotor (Controla o braço animatrônico para acenos).
* **Servidor (Backend):** Workstation rodando Python, Flask e Ollama.

### Estrutura Física e Modelagem 3D
A "carcaça" da Eva foi projetada para abrigar a eletrônica de forma compacta, inspirando-se na estética do WALL-E. O modelo tridimensional abriga os dois visores OLED frontais num ângulo ergonómico para simular contato visual. O interior possui montagens dedicadas para ocultar os jumpers, alocar o microfone I2S perto de frestas acústicas e fixar o servomotor que articula os braços laterais.

---

## Instruções de Instalação e Execução

### 1. Configuração do Hardware (ESP32)
1. Conecte os componentes ao ESP32 conforme o mapeamento I2C (OLEDs), I2S (Microfone: WS=15, SCK=2, SD=4), PIR (Pino 14) e Servo (Pino 13).
2. Instale o **Arduino IDE** e adicione a biblioteca `.zip` gerada pelo Edge Impulse (o cérebro acústico TinyML).
3. No arquivo `eva.ino` , edite as credenciais de Wi-Fi (`ssid` e `password`) e o **IP local do seu computador** (`ip_computador`).
4. Compile e faça o upload para o ESP32.

### 2. Configuração do Backend (Python)
1. Instale o Python 3.9+ e crie um ambiente virtual:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Mac/Linux
   venv\Scripts\activate     # Windows
   ```
2. Instale as dependências
   ```bash
   pip install -r requirements.txt
   ```
3. Instale o ollama e baixe o modelo LLM local
   ```bash
   ollama run gemma4:26b
   ```
4. Crie um arquivo .env na raíz do projeto com as chaves das APIs necessárias:
   ```bash
   SPOTIPY_CLIENT_ID=sua_chave
   SPOTIPY_CLIENT_SECRET=sua_chave
   SPOTIPY_REDIRECT_URI=http://localhost:8888/callback
   API_KEY_OPENWEATHER=sua_chave
   IP_ESP32=ip_do_esp32
   ```

---

### 3. Execução
1. Certifique-se de que o ESP32 e o computador estão na mesma rede WI-FI.
2. Ligue a energia da Eva (ESP32). 
3. No terminal do computador, inicie o servidor:
   ```bash
   python alexa_v2.py
   ```
4. O terminal exibirá: `Servidor aguardando o chamado da Eva (Porta 5001)...`
5. Chame atenção da Eva. O ESP32 irá detectar, as telas sorrirão e o terminal iniciará a captação de voz.

---

## Comandos Aceitos

Para chamar a atenção da Eva, é necessário apenas bater palma (graças ao nosso modelo TinyML de classificação de som treinado no EDGE IMPULSE). Caso a frase dita não bata com nenhum dos comandos mapeados abaixo, ela será enviada para a Inteligência Artificial (Ollama) responder.

### Organização Pessoal
| Ação | Exemplos de como falar | Restrição de Segurança |
| :--- | :--- | :--- |
| **Adicionar Tarefa** | *"Eva, adicionar uma tarefa"*, *"Eva, anotar na agenda"* | Requer Reconhecimento Facial |
| **Ler Tarefas** | *"Eva, ler agenda"*, *"Eva, o que tem na agenda?"* | Livre |
| **Limpar Agenda** | *"Eva, limpar agenda"*, *"Eva, apagar tarefas"* | Requer Reconhecimento Facial |

### Controle do Spotify
| Ação | Exemplos de como falar |
| :--- | :--- |
| **Tocar Playlist** | *"Eva, tocar a playlist [nome da playlist]"*, *"Eva, reproduzir playlist"* |
| **Pausar** | *"Eva, pausar música"*, *"Eva, parar o Spotify"* |
| **Retomar** | *"Eva, retomar música"*, *"Eva, despausar"* |
| **Próxima Música** | *"Eva, próxima música"*, *"Eva, pular música"* |
| **Música Anterior** | *"Eva, música anterior"*, *"Eva, voltar a música"* |

### Utilidades Diárias
| Ação | Exemplos de como falar |
| :--- | :--- |
| **Consultar Hora** | *"Eva, que horas são?"*, *"Eva, horas agora"* |
| **Consultar Data** | *"Eva, que dia é hoje?"*, *"Eva, data de hoje"* |
| **Previsão do Tempo** | *"Eva, como está o clima em São Paulo?"*, *"Eva, temperatura em [cidade]"* |
| **Calculadora** | *"Eva, calcular 5 x 10"*, *"Eva, quanto é 100 dividido por 4"* |

### Sistema e Identificação
| Ação | Exemplos de como falar |
| :--- | :--- |
| **Identificação Visual** | *"Eva, quem está aí?"*, *"Eva, quem sou eu?"* |
| **Encerrar Sistema** | *"Eva, desligar"*, *"Eva, sair"*, *"Eva, tchau"* |

---

## Vídeo Demonstrativo

Confira a Eva em ação, demonstrando o processamento local via TinyML e a resposta fluída conectada ao modelo LLM local:

<a href="https://www.youtube.com/watch?v=_4GzPeJns0g">Demonstração no Youtube</a>

## Integrantes

| RM     |                 Nome                  |
|:-------|:-------------------------------------:|
| 550219 |   Arthur Baldissera Marcos Claumann   |
| 97937  | Pedro Henrique Fernandes Lô de Barros |
| 550166 |         Ricardo Ramos Vergani         |
| 551649 |           Victor Kenzo Toma           |
