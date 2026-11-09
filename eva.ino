#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ESP32Servo.h>
#include <driver/i2s.h>
#include <HTTPClient.h>
#include <palmasEVA_inferencing.h>
#include <config.h>

// 1. Credenciais de Rede e IP do computador
const char* ssid_principal = SSID;
const char* password_principal = PASSWORD;

const char* ssid_fallback = SSID2;
const char* password_fallback = PASSWORD2;

String ip_do_computador = MY_IP;

WebServer server(80);

// 2. Configuração dos OLEDs (128x64)
#define LARGURA_OLED 128
#define ALTURA_OLED 64
#define SDA_2 32
#define SCL_2 33

TwoWire I2C_2 = TwoWire(1);
Adafruit_SSD1306 olhoEsq(LARGURA_OLED, ALTURA_OLED, &Wire, -1);
Adafruit_SSD1306 olhoDir(LARGURA_OLED, ALTURA_OLED, &I2C_2, -1);

// 3. Configuração do Servo e PIR
unsigned long tempoUltimoPrintPIR = 0;
Servo braco;
#define PINO_PIR 14
unsigned long tempoUltimoMovimento = 0;
const unsigned long TEMPO_PARA_DORMIR = 10000;
bool evaDormindo = false;
bool scriptRodando = true;

// 4. Variáveis de Controle da Palma
unsigned long tempoUltimaPalma = 0;
const unsigned long COOLDOWN_PALMA = 2000; // Ignora sons durante 2 segundos após uma palma

// 5. Configurações do Microfone I2S (INMP441)
#define I2S_WS 15
#define I2S_SCK 2
#define I2S_SD 4
#define I2S_PORT I2S_NUM_0
#define SAMPLE_RATE 16000

// Buffer de Áudio para o TinyML
#define AUDIO_BUFFER_SIZE EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE
int16_t audio_buffer[AUDIO_BUFFER_SIZE];
size_t amostras_lidas = 0;

// Função Callback para alimentar o Edge Impulse
int get_audio_data(size_t offset, size_t length, float *out_ptr) {
    for (size_t i = 0; i < length; i++) {
        out_ptr[i] = (float)audio_buffer[offset + i];
    }
    return 0;
}

// Configuração do Barramento de Áudio
void setup_i2s() {
  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,
    .dma_buf_len = 512,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0
  };
  i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_SCK,
    .ws_io_num = I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_SD
  };
  i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_PORT, &pin_config);
  i2s_zero_dma_buffer(I2S_PORT);
}

void setup() {
  Serial.begin(115200);
  pinMode(PINO_PIR, INPUT);

  ESP32PWM::allocateTimer(0);
  braco.setPeriodHertz(50);
  braco.attach(13, 500, 2400);
  braco.write(0);

  Wire.begin(21, 22);
  I2C_2.begin(SDA_2, SCL_2);
  olhoEsq.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  olhoDir.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  desenharOlhoFechado(olhoEsq);
  desenharOlhoFechado(olhoDir);

  setup_i2s();
  Serial.println("Microfone I2S Inicializado!");

  Serial.println("\nA tentar ligar à rede principal...");
  WiFi.begin(ssid_principal, password_principal);

  int tentativas = 0;
  while (WiFi.status() != WL_CONNECTED && tentativas < 20) {
    delay(500);
    Serial.print(".");
    tentativas++;
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\nFalha na rede. A ligar ao Hotspot de emergência...");
    WiFi.begin(ssid_fallback, password_fallback);
    while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  }

  Serial.print("\nLigação estabelecida! IP: ");
  Serial.println(WiFi.localIP());

  server.on("/acordar", executarAcordar);
  server.on("/acenar", executarAcenar);
  server.on("/sorrir", executarSorrir);
  server.on("/dormir", executarDormir);
  server.on("/pensar", executarPensar);
  server.begin();
}

void loop() {
 // Debug PIR
  if (millis() - tempoUltimoPrintPIR > 1000) {
    int leituraBruta = digitalRead(PINO_PIR);
    Serial.print("Valor_PIR:");
    Serial.println(leituraBruta);
    tempoUltimoPrintPIR = millis();
  }
  server.handleClient();

  // 1. LÓGICA DO SENSOR PIR
  int estadoPIR = digitalRead(PINO_PIR);

  if (estadoPIR == HIGH && scriptRodando) {

    // Faz as 10 leituras rápidas
    int leiturasPositivas = 0;
    for(int i = 0; i < 10; i++) {
      if(digitalRead(PINO_PIR) == HIGH) {
        leiturasPositivas++;
      }
      delay(10);
    }


    // Só aceita o movimento se o sinal for consistente (80% de certeza)
    if (leiturasPositivas >= 8) {
      tempoUltimoMovimento = millis();

      if (evaDormindo) {
        desenharOlhoAberto(olhoEsq, true);
        desenharOlhoAberto(olhoDir, false);
        evaDormindo = false;
        Serial.println("Movimento REAL confirmado! Eva acordou.");
      }
    }
  } else {
    if (!evaDormindo && (millis() - tempoUltimoMovimento > TEMPO_PARA_DORMIR)) {
      desenharOlhoFechado(olhoEsq);
      desenharOlhoFechado(olhoDir);
      evaDormindo = true;
      Serial.println("Sem movimento. Eva foi dormir.");
    }
  }

  // 2. LÓGICA DE ESCUTA E INFERÊNCIA TINYML
  size_t bytes_read = 0;
  int16_t chunk_audio[256];

  i2s_read(I2S_PORT, &chunk_audio, sizeof(chunk_audio), &bytes_read, 0);
  int samples_read = bytes_read / sizeof(int16_t);

  for(int i = 0; i < samples_read; i++) {
    audio_buffer[amostras_lidas++] = chunk_audio[i];

    if (amostras_lidas >= AUDIO_BUFFER_SIZE) {

      signal_t signal;
      signal.total_length = AUDIO_BUFFER_SIZE;
      signal.get_data = &get_audio_data;

      ei_impulse_result_t result = { 0 };

      EI_IMPULSE_ERROR res = run_classifier(&signal, &result, false);

      if (res == EI_IMPULSE_OK) {
        for (uint16_t j = 0; j < EI_CLASSIFIER_LABEL_COUNT; j++) {
          if (strcmp(result.classification[j].label, "palma") == 0) {

            if (result.classification[j].value > 0.95 && (millis() - tempoUltimaPalma > COOLDOWN_PALMA)) {

              Serial.print("==== PALMA DETETADA! Certeza: ");
              Serial.print(result.classification[j].value * 100);
              Serial.println("% ====");

              tempoUltimaPalma = millis();
              tempoUltimoMovimento = millis();
              evaDormindo = false;
              desenharOlhoFeliz(olhoEsq, true);
              desenharOlhoFeliz(olhoDir, false);

              // GATILHO PARA ACORDAR O COMPUTADOR
              Serial.println("A avisar o computador para iniciar a escuta...");
              HTTPClient http;
              String url = "http://" + ip_do_computador + ":5001/iniciar_escuta";
              http.begin(url);
              int httpCode = http.GET();

              if (httpCode > 0) {
                Serial.printf("Computador avisado com sucesso! Código HTTP: %d\n", httpCode);
              } else {
                Serial.printf("Falha ao comunicar com o computador: %s\n", http.errorToString(httpCode).c_str());
              }
              http.end();
            }
          }
        }
      }
      amostras_lidas = 0;
    }
  }
}


// FUNÇÕES DE EXECUÇÃO DAS ROTAS HTTP

void executarAcordar() {
  tempoUltimoMovimento = millis();
  evaDormindo = false;
  server.send(200, "text/plain", "Acordou");
  desenharOlhoAberto(olhoEsq, true);
  desenharOlhoAberto(olhoDir, false);
}

void executarAcenar() {
  tempoUltimoMovimento = millis();
  evaDormindo = false;
  server.send(200, "text/plain", "Acenando");
  braco.write(90); delay(300);
  braco.write(45); delay(300);
  braco.write(90); delay(300);
  braco.write(0);
}

void executarSorrir() {
  tempoUltimoMovimento = millis();
  evaDormindo = false;
  server.send(200, "text/plain", "Sorrindo");
  desenharOlhoFeliz(olhoEsq, true);
  desenharOlhoFeliz(olhoDir, false);
}

void executarDormir() {
  evaDormindo = true;
  scriptRodando = false;
  server.send(200, "text/plain", "Dormindo");
  desenharOlhoFechado(olhoEsq);
  desenharOlhoFechado(olhoDir);
}

void executarPensar() {
  tempoUltimoMovimento = millis();
  evaDormindo = false;
  server.send(200, "text/plain", "Pensando");
  desenharOlhoPensativo(olhoEsq, true);
  desenharOlhoPensativo(olhoDir, false);
}

// FUNÇÕES MATEMÁTICAS DE DESENHO DOS OLHOS

void desenharOlhoFechado(Adafruit_SSD1306 &tela) {
  tela.clearDisplay();
  tela.display();
}

void desenharOlhoAberto(Adafruit_SSD1306 &tela, bool esquerdo) {
  tela.clearDisplay();
  int centroX = 64, centroY = 32;
  float raioX = 40.0, raioY = 22.0;

  float angulo = 20.0 * PI / 180.0;
  if (esquerdo) angulo = -angulo;

  float cosA = cos(angulo), sinA = sin(angulo);

  for (int x = 0; x < 128; x++) {
    for (int y = 0; y < 64; y++) {
      float dx = x - centroX;
      float dy = y - centroY;
      float rotX = dx * cosA + dy * sinA;
      float rotY = -dx * sinA + dy * cosA;

      if ((rotX * rotX) / (raioX * raioX) + (rotY * rotY) / (raioY * raioY) <= 1.0) {
        tela.drawPixel(x, y, WHITE);
      }
    }
  }
  tela.display();
}

void desenharOlhoFeliz(Adafruit_SSD1306 &tela, bool esquerdo) {
  tela.clearDisplay();
  int centroX = 64, centroY = 32;
  float raioX = 40.0, raioY = 25.0;
  float raioX_recorte = 42.0, raioY_recorte = 25.0;
  float deslocamentoY = -12.0, angulo = 0.0;

  float cosA = cos(angulo), sinA = sin(angulo);

  for (int x = 0; x < 128; x++) {
    for (int y = 0; y < 64; y++) {
      float dx = x - centroX, dy = y - centroY;
      float rotX = dx * cosA + dy * sinA;
      float rotY = -dx * sinA + dy * cosA;
      float rotY_recorte = rotY - deslocamentoY;

      bool dentroPrincipal = ((rotX * rotX) / (raioX * raioX) + (rotY * rotY) / (raioY * raioY)) <= 1.0;
      bool dentroRecorte = ((rotX * rotX) / (raioX_recorte * raioX_recorte) + (rotY_recorte * rotY_recorte) / (raioY_recorte * raioY_recorte)) <= 1.0;

      if (dentroPrincipal && !dentroRecorte) tela.drawPixel(x, y, WHITE);
    }
  }
  tela.display();
}

void desenharOlhoPensativo(Adafruit_SSD1306 &tela, bool esquerdo) {
  tela.clearDisplay();
  int centroX = 64, centroY = 32;
  float raioX = 40.0, raioY = 8.0;

  float angulo = 20.0 * PI / 180.0;
  if (esquerdo) angulo = -angulo;

  float cosA = cos(angulo), sinA = sin(angulo);

  for (int x = 0; x < 128; x++) {
    for (int y = 0; y < 64; y++) {
      float dx = x - centroX, dy = y - centroY;
      float rotX = dx * cosA + dy * sinA;
      float rotY = -dx * sinA + dy * cosA;

      if ((rotX * rotX) / (raioX * raioX) + (rotY * rotY) / (raioY * raioY) <= 1.0) {
        tela.drawPixel(x, y, WHITE);
      }
    }
  }
  tela.display();
}