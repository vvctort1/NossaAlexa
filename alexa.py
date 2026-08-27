import requests
import speech_recognition as sr
from datetime import datetime
import re
import asyncio
import edge_tts
import pygame
import os
import io
import json
import cv2
from dotenv import load_dotenv



PESSOAS_AUTORIZADAS = {"victor"}

CAMINHO_MODELO = 'modelo_lbph.yml'
CAMINHO_NOMES = 'nomes_lbph.json'
CAMINHO_XML = 'haarcascade_frontalface_default.xml'

CONFIANCA_MAXIMA = 75  # mesmo limiar usado no script de treino

_classificador = None
_reconhecedor = None
_nomes = {}
_pronto = False


def _carregar_modelo():
    """Carrega o modelo treinado uma única vez (lazy loading)."""
    global _classificador, _reconhecedor, _nomes, _pronto
    if _pronto:
        return True

    if not (os.path.exists(CAMINHO_MODELO) and os.path.exists(CAMINHO_NOMES) and os.path.exists(CAMINHO_XML)):
        print("[reconhecimento] Modelo ainda não foi treinado (rode o reconhecimento_facial.py e aperte 'r').")
        return False

    _classificador = cv2.CascadeClassifier(CAMINHO_XML)
    _reconhecedor = cv2.face.LBPHFaceRecognizer_create()
    _reconhecedor.read(CAMINHO_MODELO)

    with open(CAMINHO_NOMES, 'r', encoding='utf-8') as f:
        nomes_json = json.load(f)
    _nomes = {int(k): v for k, v in nomes_json.items()}

    _pronto = True
    return True


def identificar_pessoa_atual(tentativas=15):
    """
    Abre a câmera, tenta reconhecer um rosto por algumas tentativas,
    fecha a câmera e retorna o nome reconhecido (str) ou None.
    """
    if not _carregar_modelo():
        return None

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    camera = cv2.VideoCapture(0)

    nome_encontrado = None
    try:
        for _ in range(tentativas):
            status, imagem = camera.read()
            if not status:
                continue

            cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
            equalizada = clahe.apply(cinza)

            faces = _classificador.detectMultiScale(
                equalizada, scaleFactor=1.1, minNeighbors=6, minSize=(100, 100)
            )
            if len(faces) == 0:
                continue

            # Pega só o maior rosto (mais próximo da câmera)
            x, y, l, a = max(faces, key=lambda f: f[2] * f[3])
            rosto = cv2.resize(equalizada[y:y + a, x:x + l], (220, 220))

            id_previsto, confianca = _reconhecedor.predict(rosto)
            if confianca < CONFIANCA_MAXIMA:
                nome_encontrado = _nomes.get(id_previsto)
                break
    finally:
        camera.release()

    return nome_encontrado


# ==========================================
# 1. Configurações Iniciais (Voz e Microfone)
# ==========================================
pygame.mixer.init()
reconhecedor = sr.Recognizer()

VOZ_TRIA = "pt-BR-FranciscaNeural"
load_dotenv()

API_KEY_OPENWEATHER = os.getenv("API_KEY_OPENWEATHER")

ARQUIVO_AGENDA = "minha_agenda.json"

def adicionar_tarefa(texto):
    """Extrai a tarefa da frase e salva no arquivo JSON."""
    # Descobre o que a pessoa falou depois do comando
    if "adicionar tarefa" in texto:
        tarefa = texto.split("adicionar tarefa")[1].strip()
    elif "anotar na agenda" in texto:
        tarefa = texto.split("anotar na agenda")[1].strip()
    else:
        return "O que você quer que eu anote?"

    if not tarefa:
        return "Você não me disse qual é a tarefa."

    # Carrega as tarefas existentes (se o arquivo já existir)
    tarefas = []
    if os.path.exists(ARQUIVO_AGENDA):
        with open(ARQUIVO_AGENDA, "r", encoding="utf-8") as arquivo:
            try:
                tarefas = json.load(arquivo)
            except json.JSONDecodeError:
                tarefas = []

    # Cria a nova tarefa com a data em que foi registrada
    nova_tarefa = {
        "tarefa": tarefa,
        "data_registro": datetime.now().strftime("%d/%m/%Y %H:%M")
    }
    tarefas.append(nova_tarefa)

    # Salva de volta no arquivo
    with open(ARQUIVO_AGENDA, "w", encoding="utf-8") as arquivo:
        json.dump(tarefas, arquivo, ensure_ascii=False, indent=4)

    return f"Pronto, anotei na sua agenda: {tarefa}."

def ler_agenda():
    """Lê as tarefas salvas e transforma em texto para a assistente falar."""
    if not os.path.exists(ARQUIVO_AGENDA):
        return "Sua agenda está vazia. Você ainda não anotou nada."

    with open(ARQUIVO_AGENDA, "r", encoding="utf-8") as arquivo:
        try:
            tarefas = json.load(arquivo)
        except json.JSONDecodeError:
            return "Houve um erro ao ler a sua agenda."

    if not tarefas:
        return "Você não tem nenhuma tarefa pendente."

    # Monta a frase que a TRIA vai falar
    frase = f"Você tem {len(tarefas)} tarefas na agenda. "
    for i, item in enumerate(tarefas, 1):
        frase += f"Tarefa {i}: {item['tarefa']}. "

    return frase

def limpar_texto_para_voz(texto):
    """Remove caracteres especiais e marcações de Markdown."""
    return re.sub(r'[*#_`\n]', ' ', texto)


def obter_data():
    agora = datetime.now()
    dia = agora.day
    ano = agora.year
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
             "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    mes = meses[agora.month - 1]
    return f"Hoje é dia {dia} de {mes} de {ano}."


def obter_hora():
    agora = datetime.now()
    hora = agora.hour
    minuto = agora.minute
    str_minuto = f"e {minuto} minutos" if minuto > 0 else "em ponto"
    return f"Agora são {hora} horas {str_minuto}."


async def _gerar_audio(texto):
    """Função assíncrona interna que baixa o áudio da Microsoft."""
    comunicador = edge_tts.Communicate(texto, VOZ_TRIA)
    await comunicador.save(ARQUIVO_AUDIO)


async def _gerar_audio_memoria(texto):
    """Baixa o áudio da Microsoft e guarda direto na memória, sem criar arquivo."""
    comunicador = edge_tts.Communicate(texto, VOZ_TRIA)
    audio_data = bytearray()

    # Faz o download em pedaços (stream) e junta tudo
    async for chunk in comunicador.stream():
        if chunk["type"] == "audio":
            audio_data.extend(chunk["data"])

    # Converte os bytes em um "falso arquivo" para o pygame conseguir ler
    return io.BytesIO(audio_data)


def falar(texto):
    """Reproduz o áudio diretamente da memória."""
    print(f"TRIA: {texto}")

    try:
        # 1. Gera o áudio na memória
        audio_buffer = asyncio.run(_gerar_audio_memoria(texto))

        # 2. Carrega e reproduz o buffer
        pygame.mixer.music.load(audio_buffer)
        pygame.mixer.music.play()

        # 3. Trava o código enquanto o áudio estiver tocando
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)

        pygame.mixer.music.unload()

    except Exception as e:
        print(f"[Erro no motor de voz]: {e}")



# ==========================================
# 2. Funções de Habilidades (Skills / LLM)
# ==========================================
def consulta_llm(texto):
    prompt = "Responda de forma breve com no máximo 50 palavras isto: " + texto
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "gemma4:26b",
                "prompt": prompt,
                "stream": False
            })
        return response.json()['response']
    except Exception:
        return "Desculpe, estou com problemas para acessar a inteligência artificial agora."


def executar_calculo(texto):
    lista = texto.lower().split()
    try:
        if lista[2] == "+":
            return f"O resultado é: {float(lista[1]) + float(lista[-1])}"
        elif lista[2] == "-":
            return f"O resultado é: {float(lista[1]) - float(lista[-1])}"
        elif lista[2] == "x":
            return f"O resultado é: {float(lista[1]) * float(lista[-1])}"
        elif lista[2] == "/" or (lista[2] == "dividido" and lista[3] == "por"):
            if lista[-1] == "0":
                return "Não é possível dividir por 0!"
            total = float(lista[1]) / float(lista[-1])
            return f"O resultado é {total:.2f}"
    except IndexError:
        return "Ops, não ouvi os números para o cálculo por completo."
    except Exception:
        return "Não consegui realizar este cálculo."


def consultar_clima(cidade, api_key):
    """Busca o clima atual de uma cidade via OpenWeather API."""
    url = f"http://api.openweathermap.org/data/2.5/weather?q={cidade}&appid={api_key}&units=metric&lang=pt_br"

    try:
        resposta = requests.get(url)
        dados = resposta.json()

        # Converte o 'cod' para string para evitar erros de comparação (200 vs "200")
        if str(dados.get("cod")) != "200":
            return f"Desculpe, não consegui encontrar a previsão do tempo para a cidade de {cidade}."

        temperatura = round(dados["main"]["temp"])
        descricao = dados["weather"][0]["description"]
        nome_cidade = dados["name"]

        return f"A temperatura atual em {nome_cidade} é de {temperatura} graus, com {descricao}."
    except Exception as e:
        print(f"Erro na API de clima: {e}")
        return "Ocorreu um erro de conexão ao tentar consultar o clima."

# ==========================================
# 3. Loop Principal e Roteamento
# ==========================================
def iniciar_assistente():
    print("Tentando reconhecer quem está na frente da câmera...")
    usuario_atual = identificar_pessoa_atual()

    if usuario_atual:
        falar(f"Oi, {usuario_atual}! Sistema iniciado, estou ouvindo.")
    else:
        usuario_atual = None
        falar("Sistema iniciado. Não consegui te reconhecer, mas estou ouvindo.")

    with sr.Microphone() as mic:
        reconhecedor.adjust_for_ambient_noise(mic, duration=2)

        while True:
            print("\nFale algo...")
            try:
                audio = reconhecedor.listen(mic, timeout=5, phrase_time_limit=10)
                texto = reconhecedor.recognize_google(audio, language='pt-BR')

                if "oi" in texto.lower():
                    print(f"Você falou: {texto}")
                    texto_lower = texto.lower()

                    if "sair" in texto_lower or "desligar" in texto_lower:
                        falar("Desligando. Até mais!")
                        break
                    elif "calcular" in texto_lower:
                        resposta = executar_calculo(texto_lower)
                        falar(resposta)
                    elif "que dia é hoje" in texto_lower or "qual é o dia de hoje" in texto_lower:
                        data = obter_data()
                        falar(data)
                    elif "que horas são" in texto_lower:
                        hora = obter_hora()
                        falar(hora)
                    # --- NOVO: Comando de Clima ---
                    # --- NOVO: Comando de Clima ---
                    elif "clima" in texto_lower or "tempo" in texto_lower or "graus" in texto_lower or "temperatura" in texto_lower:
                        cidade = "São Paulo"  # Cidade padrão
                        # Extrai a cidade com segurança, garantindo que a mesma string do 'if' seja usada no 'split'
                        if "clima em " in texto_lower or "clima no" in texto_lower:
                            cidade = texto_lower.split("clima em ")[1].strip()
                        elif "tempo em " in texto_lower or "tempo no" in texto_lower:
                            cidade = texto_lower.split("tempo em ")[1].strip()
                        elif "graus em " in texto_lower or "graus no" in texto_lower:
                            cidade = texto_lower.split("graus em ")[1].strip()
                        elif "temperatura em " in texto_lower or "temperatura no" in texto_lower:
                            cidade = texto_lower.split("temperatura em ")[1].strip()
                        resposta_clima = consultar_clima(cidade, API_KEY_OPENWEATHER)
                        falar(resposta_clima)
                    elif "adicionar tarefa" in texto_lower or "anotar na agenda" in texto_lower:
                        # Comando restrito: exige rosto reconhecido e autorizado
                        if usuario_atual is None or usuario_atual.lower() not in PESSOAS_AUTORIZADAS:
                            print("Acesso negado: pessoa não reconhecida/autorizada.")
                            falar("Desculpe, não consigo adicionar tarefas para você.")
                        else:
                            print("Adicionando tarefa...")
                            resposta_agenda = adicionar_tarefa(texto_lower)
                            falar(resposta_agenda)

                    elif "quem sou eu" in texto_lower or "quem esta ai" in texto_lower or "quem está aí" in texto_lower:
                        # Refaz o reconhecimento na hora, sem esperar reiniciar a TRIA
                        usuario_atual = identificar_pessoa_atual()
                        if usuario_atual:
                            falar(f"Você é o {usuario_atual}.")
                        else:
                            falar("Não consegui reconhecer você.")

                    elif "ler agenda" in texto_lower or "minhas tarefas" in texto_lower or "o que tem na agenda" in texto_lower:
                        print("Lendo tarefas...")
                        resposta_leitura = ler_agenda()
                        falar(resposta_leitura)
                    else:
                        print("Consultando LLM...")
                        resposta_llm = consulta_llm(texto)
                        resposta_falada = limpar_texto_para_voz(resposta_llm)
                        falar(resposta_falada)

            except sr.WaitTimeoutError:
                pass
            except sr.UnknownValueError:
                pass
            except Exception as e:
                print(f"Erro na captação: {e}")


# Executa o programa
iniciar_assistente()