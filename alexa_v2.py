from __future__ import annotations
import asyncio
import io
import json
import os
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional
import cv2
import edge_tts
import pygame
import requests
import speech_recognition as sr
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth


# Configuração
CAMINHO_MODELO_FACIAL = "modelo_lbph.yml"
CAMINHO_NOMES_FACIAL = "nomes_lbph.json"
CAMINHO_XML_FACIAL = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
CONFIANCA_MAXIMA_FACIAL = 75

ARQUIVO_AGENDA = "minha_agenda.json"
PESSOAS_AUTORIZADAS = {"victor"}

VOZ_EVA = "pt-BR-FranciscaNeural"
WAKE_WORD = "eva"

URL_OLLAMA = "http://localhost:11434/api/generate"
MODELO_OLLAMA = "gemma4:26b"


# Reconhecimento facial
class ReconhecimentoFacial:
    """Identifica quem está na frente da câmera usando um modelo LBPH já treinado."""

    def __init__(
        self,
        caminho_modelo: str = CAMINHO_MODELO_FACIAL,
        caminho_nomes: str = CAMINHO_NOMES_FACIAL,
        caminho_xml: str = CAMINHO_XML_FACIAL,
        confianca_maxima: int = CONFIANCA_MAXIMA_FACIAL,
    ):
        self._caminho_modelo = caminho_modelo
        self._caminho_nomes = caminho_nomes
        self._caminho_xml = caminho_xml
        self._confianca_maxima = confianca_maxima

        self._classificador: Optional[cv2.CascadeClassifier] = None
        self._reconhecedor = None
        self._nomes: Dict[int, str] = {}
        self._pronto = False

    def _carregar(self) -> bool:
        """Carrega o modelo treinado uma única vez (lazy loading)."""
        if self._pronto:
            return True

        arquivos_necessarios = (self._caminho_modelo, self._caminho_nomes, self._caminho_xml)
        if not all(os.path.exists(caminho) for caminho in arquivos_necessarios):
            print("[reconhecimento] Modelo ainda não foi treinado (rode o script de treino e aperte 'r').")
            return False

        self._classificador = cv2.CascadeClassifier(self._caminho_xml)
        self._reconhecedor = cv2.face.LBPHFaceRecognizer_create()
        self._reconhecedor.read(self._caminho_modelo)

        with open(self._caminho_nomes, "r", encoding="utf-8") as arquivo:
            nomes_json = json.load(arquivo)
        self._nomes = {int(id_pessoa): nome for id_pessoa, nome in nomes_json.items()}

        self._pronto = True
        return True

    def identificar_pessoa_atual(self, tentativas: int = 35) -> Optional[str]:
        """Abre a câmera, tenta reconhecer um rosto por algumas tentativas e retorna o nome (ou None)."""
        if not self._carregar():
            return None

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        camera = cv2.VideoCapture(0)

        try:
            for _ in range(tentativas):
                nome = self._tentar_reconhecer_um_frame(camera, clahe)
                if nome is not None:
                    return nome
        finally:
            camera.release()

        return None

    def _tentar_reconhecer_um_frame(self, camera, clahe) -> Optional[str]:
        status, imagem = camera.read()
        if not status:
            return None

        cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
        equalizada = clahe.apply(cinza)

        faces = self._classificador.detectMultiScale(
            equalizada, scaleFactor=1.1, minNeighbors=6, minSize=(100, 100)
        )
        if len(faces) == 0:
            return None

        # Pega só o maior rosto (assume-se que é o mais próximo da câmera)
        x, y, largura, altura = max(faces, key=lambda f: f[2] * f[3])
        rosto = cv2.resize(equalizada[y : y + altura, x : x + largura], (220, 220))

        id_previsto, confianca = self._reconhecedor.predict(rosto)
        if confianca < self._confianca_maxima:
            return self._nomes.get(id_previsto)
        return None


# Voz (texto -> fala)
class SintetizadorDeVoz:
    """Converte texto em áudio (edge-tts) e reproduz direto da memória (pygame), sem criar arquivo."""

    def __init__(self, voz: str = VOZ_EVA, nome_exibido: str = "Eva"):
        self._voz = voz
        self._nome_exibido = nome_exibido
        pygame.mixer.init()

    def falar(self, texto: str) -> None:
        print(f"{self._nome_exibido}: {texto}")
        try:
            audio_buffer = asyncio.run(self._gerar_audio_memoria(texto))
            self._reproduzir(audio_buffer)
        except Exception as erro:
            print(f"[Erro no motor de voz]: {erro}")

    async def _gerar_audio_memoria(self, texto: str) -> io.BytesIO:
        comunicador = edge_tts.Communicate(texto, self._voz)
        audio_data = bytearray()
        async for pedaco in comunicador.stream():
            if pedaco["type"] == "audio":
                audio_data.extend(pedaco["data"])
        return io.BytesIO(audio_data)

    @staticmethod
    def _reproduzir(audio_buffer: io.BytesIO) -> None:
        pygame.mixer.music.load(audio_buffer)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()

    @staticmethod
    def limpar_texto_para_voz(texto: str) -> str:
        """Remove marcações de Markdown/caracteres especiais que soam estranho quando falados."""
        return re.sub(r"[*#_`\n]", " ", texto)


# LLM local (fallback de conversa livre)
class ClienteLLM:
    """Cliente simples para o modelo local rodando via Ollama."""

    def __init__(self, url: str = URL_OLLAMA, modelo: str = MODELO_OLLAMA):
        self._url = url
        self._modelo = modelo

    def perguntar(self, texto: str) -> str:
        prompt = f"Responda de forma breve com no máximo 50 palavras isto: {texto}"
        try:
            resposta = requests.post(
                self._url,
                json={"model": self._modelo, "prompt": prompt, "stream": False},
                timeout=30,
            )
            return resposta.json()["response"]
        except Exception:
            return "Desculpe, estou com problemas para acessar a inteligência artificial agora."


# Clima
class ServicoClima:
    """Consulta condições climáticas atuais via OpenWeather."""

    _URL_BASE = "http://api.openweathermap.org/data/2.5/weather"

    def __init__(self, api_key: Optional[str]):
        self._api_key = api_key

    def consultar(self, cidade: str) -> str:
        try:
            resposta = requests.get(
                self._URL_BASE,
                params={"q": cidade, "appid": self._api_key, "units": "metric", "lang": "pt_br"},
                timeout=10,
            )
            dados = resposta.json()

            if str(dados.get("cod")) != "200":
                return f"Desculpe, não consegui encontrar a previsão do tempo para a cidade de {cidade}."

            temperatura = round(dados["main"]["temp"])
            descricao = dados["weather"][0]["description"]
            nome_cidade = dados["name"]
            return f"A temperatura atual em {nome_cidade} é de {temperatura} graus, com {descricao}."
        except Exception as erro:
            print(f"Erro na API de clima: {erro}")
            return "Ocorreu um erro de conexão ao tentar consultar o clima."


# Agenda
class Agenda:
    """Persiste e lê tarefas simples num arquivo JSON."""

    def __init__(self, caminho_arquivo: str = ARQUIVO_AGENDA):
        self._caminho_arquivo = caminho_arquivo

    def adicionar(self, tarefa: str) -> str:
        tarefa = (tarefa or "").strip()
        if not tarefa:
            return "Você não me disse qual é a tarefa."

        tarefas = self._carregar_tarefas()
        tarefas.append({
            "tarefa": tarefa,
            "data_registro": datetime.now().strftime("%d/%m/%Y %H:%M"),
        })
        self._salvar_tarefas(tarefas)

        return f"Pronto, anotei na sua agenda: {tarefa}."

    def ler(self) -> str:
        if not os.path.exists(self._caminho_arquivo):
            return "Sua agenda está vazia. Você ainda não anotou nada."

        tarefas = self._carregar_tarefas()
        if not tarefas:
            return "Você não tem nenhuma tarefa pendente."

        partes = [f"Você tem {len(tarefas)} tarefas na agenda."]
        for indice, item in enumerate(tarefas, start=1):
            partes.append(f"Tarefa {indice}: {item['tarefa']}.")
        return " ".join(partes)

    def limpar(self) -> str:
        """Apaga todas as tarefas da agenda sobreescrevendo com uma lista vazia."""
        if not os.path.exists(self._caminho_arquivo):
            return "Sua agenda já está vazia."

        tarefas = self._carregar_tarefas()
        if not tarefas:
            return "Sua agenda já está vazia."

        # Salva uma lista vazia no arquivo JSON
        self._salvar_tarefas([])

        return "Pronto, apaguei todas as tarefas da sua agenda."

    def _carregar_tarefas(self) -> List[dict]:
        if not os.path.exists(self._caminho_arquivo):
            return []
        with open(self._caminho_arquivo, "r", encoding="utf-8") as arquivo:
            try:
                return json.load(arquivo)
            except json.JSONDecodeError:
                return []

    def _salvar_tarefas(self, tarefas: List[dict]) -> None:
        with open(self._caminho_arquivo, "w", encoding="utf-8") as arquivo:
            json.dump(tarefas, arquivo, ensure_ascii=False, indent=4)


# Calculadora
class Calculadora:
    """Interpreta uma frase com uma operação matemática simples e resolve."""

    @staticmethod
    def calcular_a_partir_da_frase(texto: str) -> str:
        palavras = texto.lower().split()
        try:

            if palavras[1] == "quanto":
                operador = palavras[4]
                numero1 = float(palavras[3])
                numero2 = float(palavras[-1])
            else:
                operador = palavras[3]
                numero1 = float(palavras[2])
                numero2 = float(palavras[-1])
        except IndexError:
            return "Ops, não ouvi os números para o cálculo por completo."
        except ValueError:
            return "Não consegui entender os números do cálculo."

        if operador == "+":
            return f"O resultado é: {numero1 + numero2}"
        if operador == "-":
            return f"O resultado é: {numero1 - numero2}"
        if operador == "x":
            return f"O resultado é: {numero1 * numero2}"
        if operador == "/" or (operador == "dividido" and "por" in palavras):
            if numero2 == 0:
                return "Não é possível dividir por 0!"
            return f"O resultado é {numero1 / numero2:.2f}"

        return "Não consegui realizar este cálculo."


# Spotify
class ServicoSpotify:
    """Controla a reprodução de músicas via API do Spotify."""

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._sp: Optional[spotipy.Spotify] = None
        self._autenticar()

    def _autenticar(self) -> None:
        if not (self._client_id and self._client_secret and self._redirect_uri):
            print("[spotify] Credenciais ausentes. Serviço inativo.")
            return

        # Escopos necessários para ler o estado e dar play
        escopo = "user-modify-playback-state user-read-playback-state"

        gerenciador_auth = SpotifyOAuth(
            client_id=self._client_id,
            client_secret=self._client_secret,
            redirect_uri=self._redirect_uri,
            scope=escopo
        )
        self._sp = spotipy.Spotify(auth_manager=gerenciador_auth)

    def tocar_playlist(self, nome_playlist: str) -> str:
        if not self._sp:
            return "As credenciais do Spotify não estão configuradas corretamente."

        try:
            # 1. Busca a playlist
            resultados = self._sp.search(q=nome_playlist, type="playlist", limit=1)
            items = resultados.get("playlists", {}).get("items", [])

            if not items:
                return f"Não encontrei nenhuma playlist chamada {nome_playlist}."

            playlist = items[0]
            uri_playlist = playlist["uri"]
            nome_encontrado = playlist["name"]

            # 2. Verifica se há algum dispositivo ativo
            dispositivos = self._sp.devices().get("devices", [])
            if not dispositivos:
                return "Abra o aplicativo do Spotify no seu computador ou celular primeiro."

            # 3. Dá o play no dispositivo ativo
            self._sp.start_playback(context_uri=uri_playlist)
            return f"Tocando a playlist {nome_encontrado}."

        except spotipy.SpotifyException as erro:
            if erro.http_status == 403:
                return "A conta do Spotify precisa ser Premium para tocar músicas por voz."
            return "Ocorreu um erro de permissão ao acessar o Spotify."
        except Exception as erro:
            print(f"Erro interno Spotify: {erro}")
            return "Tive um problema ao tentar conectar com o Spotify."

    def pausar_musica(self) -> str:
        if not self._sp: return "Spotify não configurado."
        try:
            self._sp.pause_playback()
            return "Música pausada."
        except spotipy.SpotifyException:
            return "Não consegui pausar. Talvez a música já esteja pausada ou não haja dispositivo ativo."

    def retomar_musica(self) -> str:
        if not self._sp: return "Spotify não configurado."
        try:
            self._sp.start_playback()
            return "Retomando a música."
        except spotipy.SpotifyException:
            return "Não consegui retomar. Verifique se o aplicativo está aberto."

    def proxima_musica(self) -> str:
        if not self._sp: return "Spotify não configurado."
        try:
            self._sp.next_track()
            return "Passando para a próxima."
        except spotipy.SpotifyException:
            return "Não consegui pular de música."

    def musica_anterior(self) -> str:
        if not self._sp: return "Spotify não configurado."
        try:
            self._sp.previous_track()
            return "Voltando a música."
        except spotipy.SpotifyException:
            return "Não consegui voltar a música."

# Comandos de voz (padrão Command)
class Comando(ABC):
    """Um comando de voz: sabe se uma frase é sua (`corresponde`) e como executá-la."""

    palavras_chave: List[str] = []

    def corresponde(self, texto_lower: str) -> bool:
        return any(palavra in texto_lower for palavra in self.palavras_chave)

    @abstractmethod
    def executar(self, texto_original: str, texto_lower: str, assistente: "AssistenteEva") -> Optional[str]:
        """Executa o comando. Pode retornar "ENCERRAR" para pedir o fim do laço principal."""


class ComandoSair(Comando):
    palavras_chave = ["sair", "desligar", "tchau"]

    def executar(self, texto_original, texto_lower, assistente):
        assistente.voz.falar("Desligando. Até mais!")
        return "ENCERRAR"


class ComandoCalcular(Comando):
    palavras_chave = ["calcular", "quanto é"]

    def executar(self, texto_original, texto_lower, assistente):
        assistente.voz.falar(Calculadora.calcular_a_partir_da_frase(texto_lower))


class ComandoData(Comando):
    palavras_chave = ["que dia é hoje", "qual é o dia de hoje", "que dia é", "data de hoje"]
    _MESES = [
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    ]

    def executar(self, texto_original, texto_lower, assistente):
        agora = datetime.now()
        mes = self._MESES[agora.month - 1]
        assistente.voz.falar(f"Hoje é dia {agora.day} de {mes} de {agora.year}.")


class ComandoHora(Comando):
    palavras_chave = ["que horas são", "que horas sao", "horas agora"]

    def executar(self, texto_original, texto_lower, assistente):
        agora = datetime.now()
        minutos = f"e {agora.minute} minutos" if agora.minute > 0 else "em ponto"
        assistente.voz.falar(f"Agora são {agora.hour} horas {minutos}.")


class ComandoClima(Comando):
    palavras_chave = ["clima", "tempo", "graus", "temperatura"]
    _PADRAO_CIDADE = re.compile(r"(?:clima|tempo|temperatura|graus)\s+(?:em|no|na)\s+(.+)")
    _CIDADE_PADRAO = "São Paulo"

    def executar(self, texto_original, texto_lower, assistente):
        match = self._PADRAO_CIDADE.search(texto_lower)
        cidade = match.group(1).strip() if match else self._CIDADE_PADRAO
        assistente.voz.falar(assistente.clima.consultar(cidade))


class ComandoAdicionarTarefa(Comando):
    palavras_chave = [
        "adicionar uma tarefa",
        "adicione uma tarefa",
        "adicionar tarefa",
        "anotar na agenda",
        "anota na agenda",
        "anote uma tarefa",
    ]

    def executar(self, texto_original, texto_lower, assistente):
        if not self._confirmar_pessoa_autorizada(assistente):
            return

        tarefa = self._extrair_tarefa(texto_lower)
        if not tarefa:
            tarefa = self._perguntar_tarefa(assistente)
            if not tarefa:
                return

        assistente.voz.falar(assistente.agenda.adicionar(tarefa))

    def _confirmar_pessoa_autorizada(self, assistente: "AssistenteEva") -> bool:
        # Segurança extra: reconfirma quem está na câmera AGORA, mesmo que a
        # pessoa já tenha sido reconhecida no início da sessão — evita que o
        # comando seja usado por outra pessoa depois da checagem inicial.
        assistente.voz.falar("Confirmando sua identidade.")
        pessoa = assistente.reconhecimento.identificar_pessoa_atual()
        assistente.usuario_atual = pessoa

        if pessoa is None or pessoa.lower() not in assistente.pessoas_autorizadas:
            print("Acesso negado: pessoa não reconhecida/autorizada na confirmação.")
            assistente.voz.falar("Não consegui confirmar sua identidade, então não vou adicionar essa tarefa.")
            return False
        return True

    def _extrair_tarefa(self, texto: str) -> str:
        """Corta a frase logo depois do gatilho que a disparou e retorna o que sobrou."""
        texto_lower = texto.lower()
        # Do gatilho mais longo pro mais curto, pra não cortar errado quando
        # um gatilho é prefixo de outro (ex: "tarefa" dentro de "uma tarefa").
        for gatilho in sorted(self.palavras_chave, key=len, reverse=True):
            indice = texto_lower.find(gatilho)
            if indice != -1:
                return texto[indice + len(gatilho):].strip(" ,.:")
        return ""

    @staticmethod
    def _perguntar_tarefa(assistente: "AssistenteEva") -> Optional[str]:
        assistente.voz.falar("O que você quer que eu anote?")
        tarefa = assistente.ouvir_resposta_simples()
        if not tarefa:
            assistente.voz.falar("Não consegui te ouvir, tenta de novo.")
        return tarefa


class ComandoQuemSouEu(Comando):
    palavras_chave = ["quem sou eu", "quem esta ai", "quem está aí"]

    def executar(self, texto_original, texto_lower, assistente):
        assistente.usuario_atual = assistente.reconhecimento.identificar_pessoa_atual()
        if assistente.usuario_atual:
            assistente.voz.falar(f"Você é o {assistente.usuario_atual}.")
        else:
            assistente.voz.falar("Não consegui reconhecer você.")


class ComandoLerAgenda(Comando):
    palavras_chave = ["ler agenda", "minhas tarefas", "o que tem na agenda"]

    def executar(self, texto_original, texto_lower, assistente):
        assistente.voz.falar(assistente.agenda.ler())


class ComandoLimparAgenda(Comando):
    palavras_chave = ["limpar agenda", "apagar agenda", "esvaziar agenda", "apagar tarefas", "limpar tarefas"]

    def executar(self, texto_original, texto_lower, assistente):
        if not self._confirmar_pessoa_autorizada(assistente):
            return

        assistente.voz.falar(assistente.agenda.limpar())

    def _confirmar_pessoa_autorizada(self, assistente: "AssistenteEva") -> bool:
        """Reaproveita a lógica de segurança para evitar que qualquer um apague a agenda."""
        assistente.voz.falar("Confirmando sua identidade para apagar a agenda.")
        pessoa = assistente.reconhecimento.identificar_pessoa_atual()
        assistente.usuario_atual = pessoa

        if pessoa is None or pessoa.lower() not in assistente.pessoas_autorizadas:
            print("Acesso negado: pessoa não reconhecida/autorizada na confirmação.")
            assistente.voz.falar("Não consegui confirmar sua identidade, então não vou apagar a agenda.")
            return False
        return True


class ComandoTocarPlaylist(Comando):
    palavras_chave = [
        "tocar a playlist",
        "tocar playlist",
        "toca a playlist",
        "reproduzir playlist",
        "toca playlist"
    ]

    def executar(self, texto_original, texto_lower, assistente):
        nome_playlist = self._extrair_playlist(texto_lower)

        # Se o usuário disser apenas "Eva, tocar playlist", a assistente pergunta qual.
        if not nome_playlist:
            assistente.voz.falar("Qual o nome da playlist que você quer tocar?")
            nome_playlist = assistente.ouvir_resposta_simples()
            if not nome_playlist:
                assistente.voz.falar("Não consegui ouvir o nome da playlist.")
                return

        assistente.voz.falar("Buscando no Spotify, aguarde.")
        resposta = assistente.spotify.tocar_playlist(nome_playlist)
        assistente.voz.falar(resposta)

    def _extrair_playlist(self, texto: str) -> str:
        for gatilho in sorted(self.palavras_chave, key=len, reverse=True):
            indice = texto.find(gatilho)
            if indice != -1:
                return texto[indice + len(gatilho):].strip(" ,.:")
        return ""


class ComandoProximaMusica(Comando):
    palavras_chave = ["próxima música", "proxima musica", "passar música", "pular música", "passar a música"]

    def executar(self, texto_original, texto_lower, assistente):
        assistente.voz.falar(assistente.spotify.proxima_musica())


class ComandoMusicaAnterior(Comando):
    palavras_chave = ["música anterior", "musica anterior", "voltar música", "voltar a música"]

    def executar(self, texto_original, texto_lower, assistente):
        assistente.voz.falar(assistente.spotify.musica_anterior())


class ComandoPausarMusica(Comando):
    palavras_chave = ["pausar música", "pausar a música", "pausar o spotify", "parar a música", "parar música"]

    def executar(self, texto_original, texto_lower, assistente):
        assistente.voz.falar(assistente.spotify.pausar_musica())


class ComandoRetomarMusica(Comando):
    palavras_chave = ["retomar música", "retomar a música", "despausar", "continuar a música", "continuar música"]

    def executar(self, texto_original, texto_lower, assistente):
        assistente.voz.falar(assistente.spotify.retomar_musica())

def comandos_padrao() -> List[Comando]:
    """Lista padrão de comandos que a Eva sabe executar."""
    return [
        ComandoSair(),
        ComandoCalcular(),
        ComandoData(),
        ComandoHora(),
        ComandoClima(),
        ComandoAdicionarTarefa(),
        ComandoQuemSouEu(),
        ComandoLerAgenda(),
        ComandoLimparAgenda(),
        ComandoTocarPlaylist(),
        ComandoProximaMusica(),
        ComandoMusicaAnterior(),
        ComandoPausarMusica(),
        ComandoRetomarMusica(),
    ]


# Roteamento
class RoteadorDeComandos:
    """Escolhe qual Comando atende a frase do usuário; se nenhum bater, cai no LLM."""

    def __init__(self, comandos: List[Comando], llm: ClienteLLM):
        self._comandos = comandos
        self._llm = llm

    def rotear(self, texto_original: str, texto_lower: str, assistente: "AssistenteEva") -> Optional[str]:
        for comando in self._comandos:
            if comando.corresponde(texto_lower):
                return comando.executar(texto_original, texto_lower, assistente)
        return self._conversar_com_llm(texto_original, assistente)

    def _conversar_com_llm(self, texto_original: str, assistente: "AssistenteEva") -> None:
        print("Consultando LLM...")
        resposta = self._llm.perguntar(texto_original)
        assistente.voz.falar(SintetizadorDeVoz.limpar_texto_para_voz(resposta))


# Assistente principal
class AssistenteEva:
    """Orquestra o laço de escuta, a wake word e o estado da sessão (quem está autorizado)."""

    def __init__(
        self,
        reconhecimento: ReconhecimentoFacial,
        voz: SintetizadorDeVoz,
        clima: ServicoClima,
        agenda: Agenda,
        spotify: ServicoSpotify,
        roteador: RoteadorDeComandos,
        pessoas_autorizadas: set,
        wake_word: str = WAKE_WORD,
    ):
        self.reconhecimento = reconhecimento
        self.voz = voz
        self.clima = clima
        self.agenda = agenda
        self.spotify = spotify
        self.roteador = roteador
        self.pessoas_autorizadas = pessoas_autorizadas
        self._wake_word = wake_word

        self.usuario_atual: Optional[str] = None
        self._reconhecedor_fala = sr.Recognizer()

    def iniciar(self) -> None:
        self._cumprimentar()
        with sr.Microphone() as microfone:
            self._reconhecedor_fala.adjust_for_ambient_noise(microfone, duration=2)
            # Só depois do ajuste de ruído o microfone está de fato pronto pra
            # capturar — por isso essa fala vem aqui, e só uma vez.
            self.voz.falar("Obrigado por esperar. Se precisar de alguma coisa, estou ouvindo.")
            self._laco_principal(microfone)

    def ouvir_resposta_simples(self, timeout: int = 6, phrase_time_limit: int = 10) -> Optional[str]:
        """Abre o microfone por uma frase só, para capturar a resposta a uma pergunta da Eva."""
        try:
            with sr.Microphone() as microfone:
                self._reconhecedor_fala.adjust_for_ambient_noise(microfone, duration=0.5)
                audio = self._reconhecedor_fala.listen(microfone, timeout=timeout, phrase_time_limit=phrase_time_limit)
            return self._reconhecedor_fala.recognize_google(audio, language="pt-BR")
        except (sr.WaitTimeoutError, sr.UnknownValueError):
            return None

    def _cumprimentar(self) -> None:
        print("Tentando reconhecer quem está na frente da câmera...")
        self.usuario_atual = self.reconhecimento.identificar_pessoa_atual()
        if self.usuario_atual:
            self.voz.falar(f"Oi, {self.usuario_atual}! Só um momento...")
        else:
            self.voz.falar("Sistema iniciado. Não consegui te reconhecer. Aguarde um momento...")

    def _laco_principal(self, microfone) -> None:
        while True:
            print("\nOuvindo...")
            try:
                audio = self._reconhecedor_fala.listen(microfone, timeout=5, phrase_time_limit=10)
                texto = self._reconhecedor_fala.recognize_google(audio, language="pt-BR")

                if self._wake_word in texto.lower():
                    print(f"Você falou: {texto}")
                    resultado = self.roteador.rotear(texto, texto.lower(), self)
                    if resultado == "ENCERRAR":
                        break

            except sr.WaitTimeoutError:
                pass
            except sr.UnknownValueError:
                pass
            except Exception as erro:
                print(f"Erro na captação: {erro}")


# Composição e execução
def montar_assistente() -> AssistenteEva:
    """Cria e conecta todas as dependências da Eva (composition root)."""
    load_dotenv()

    reconhecimento = ReconhecimentoFacial()
    voz = SintetizadorDeVoz()
    llm = ClienteLLM()
    clima = ServicoClima(api_key=os.getenv("API_KEY_OPENWEATHER"))
    agenda = Agenda()

    spotify = ServicoSpotify(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI")
    )


    roteador = RoteadorDeComandos(comandos_padrao(), llm)

    return AssistenteEva(
        reconhecimento=reconhecimento,
        voz=voz,
        clima=clima,
        agenda=agenda,
        spotify=spotify,
        roteador=roteador,
        pessoas_autorizadas=PESSOAS_AUTORIZADAS,
    )


if __name__ == "__main__":
    montar_assistente().iniciar()