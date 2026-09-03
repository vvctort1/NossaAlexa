# Eva - Assistente de Voz Local

A **Eva** é uma assistente virtual desenvolvida em Python focada em automação, serviços de utilidade e processamento local. O grande diferencial da arquitetura é a integração de **visão computacional** (OpenCV + LBPH) para criar uma camada de autenticação biométrica em comandos sensíveis (como manipulação de agenda) e a utilização de um **modelo LLM local** (via Ollama) como fallback para conversas em linguagem natural.

## Principais Funcionalidades
* **Reconhecimento Facial:** Identifica o usuário via webcam antes de executar comandos restritos.
* **Automação de Mídia:** Controle total da reprodução do Spotify (requer conta Premium).
* **Processamento de Linguagem Natural:** Responde a perguntas abertas usando inteligência artificial offline.
* **Integração de APIs:** Consulta de clima em tempo real via OpenWeather.
* **Sistema de Tarefas:** Gerenciamento de uma agenda local persistente via JSON.

---

## Comandos Aceitos

Para que a assistente entenda o seu comando, a frase dita deve sempre conter a palavra de ativação **"Eva"**. Caso a frase dita não bata com nenhum dos comandos mapeados abaixo, ela será enviada para a Inteligência Artificial (Ollama) responder.

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

## Instalação Rápida

1. Clone o repositório:
   ```bash
   git clone [https://github.com/vvctort1/nossa-alexa.git](https://github.com/vvctort1/nossa-alexa.git)
   cd nossa-alexa
   

2. Instalar dependências
    ```bash
   pip install requirements.txt
   

3. Configure o .env com suas credenciais
    ```bash
   API_KEY_OPENWEATHER="sua_chave_aqui"
    SPOTIPY_CLIENT_ID="seu_client_id_aqui"
    SPOTIPY_CLIENT_SECRET="seu_client_secret_aqui"
    SPOTIPY_REDIRECT_URI="http://127.0.0.1:8080"
   

4. Treine o modelo facial e inicie a assistente
    ```bash
    python treinamento_facial.py
    python assistente_eva.py