#include <WiFi.h>
#include <WebServer.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ESP32Servo.h>
#include config.h

// 1. Credenciais de Rede
const char* ssid_principal = ARTHUR_SSID;
const char* password_principal = ARTHUR_SENHA;

const char* ssid_fallback = VICTOR_SSID;
const char* password_fallback = VICTOR_SENHA;

WebServer server(80);

// 2. Configuração dos OLEDs (128x64)
#define LARGURA_OLED 128
#define ALTURA_OLED 64
#define SDA_2 32
#define SCL_2 33

TwoWire I2C_2 = TwoWire(1);
Adafruit_SSD1306 olhoEsq(LARGURA_OLED, ALTURA_OLED, &Wire, -1);
Adafruit_SSD1306 olhoDir(LARGURA_OLED, ALTURA_OLED, &I2C_2, -1);

// 3. Configuração do Servo
Servo braco;

void setup() {
  Serial.begin(115200);

  // Inicialização do Servomotor no ESP32
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);
  braco.setPeriodHertz(50);
  braco.attach(13, 500, 2400); // Pino digital 13
  braco.write(0);

  // Inicialização do Barramento I2C Duplo
  Wire.begin(21, 22);        // I2C Padrão (Olho Esquerdo)
  I2C_2.begin(SDA_2, SCL_2); // I2C Secundário (Olho Direito)

  // Inicializa ambos os ecrãs no endereço 0x3C
  olhoEsq.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  olhoDir.begin(SSD1306_SWITCHCAPVCC, 0x3C);

  // Começa de olhos fechados (ecrã preto)
  desenharOlhoFechado(olhoEsq);
  desenharOlhoFechado(olhoDir);

  // 4. Lógica de Ligação Wi-Fi
  Serial.println("\nA tentar ligar à rede principal...");
  WiFi.begin(ssid_principal, password_principal);

  int tentativas = 0;
  while (WiFi.status() != WL_CONNECTED && tentativas < 20) {
    delay(500);
    Serial.print(".");
    tentativas++;
  }

  // Fallback para o telemóvel se a faculdade bloquear
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\nFalha na rede principal. A ligar ao Hotspot de emergência...");
    WiFi.begin(ssid_fallback, password_fallback);
    while (WiFi.status() != WL_CONNECTED) {
      delay(500);
      Serial.print(".");
    }
  }

  Serial.println("\nLigação estabelecida com sucesso!");
  Serial.print("Endereço IP para configurar no Python: ");
  Serial.println(WiFi.localIP());

  // 5. Configuração das Rotas HTTP
  server.on("/acordar", executarAcordar);
  server.on("/acenar", executarAcenar);
  server.on("/sorrir", executarSorrir);
  server.on("/dormir", executarDormir);
  server.on("/pensar", executarPensar);
  server.on("/sorrir", executarSorrir);

  server.begin();
}

void loop() {
  server.handleClient();
}

// FUNÇÕES DE EXECUÇÃO DAS ROTAS (AÇÕES)

void executarAcordar() {
  server.send(200, "text/plain", "Acordou");
  desenharOlhoAberto(olhoEsq, true);
  desenharOlhoAberto(olhoDir, false);
}

void executarAcenar() {
  server.send(200, "text/plain", "Acenando");

  braco.write(90);
  delay(300);
  braco.write(45);
  delay(300);
  braco.write(90);
  delay(300);
  braco.write(0);
}


void executarSorrir() {
  server.send(200, "text/plain", "Sorrindo");
  desenharOlhoFeliz(olhoEsq, true);
  desenharOlhoFeliz(olhoDir, false);
}

void executarDormir() {
  server.send(200, "text/plain", "Dormindo");
  desenharOlhoFechado(olhoEsq);
  desenharOlhoFechado(olhoDir);
}

void executarPensar() {
  server.send(200, "text/plain", "Pensando");
  desenharOlhoPensativo(olhoEsq, true);
  desenharOlhoPensativo(olhoDir, false);
}




// FUNÇÕES MATEMÁTICAS DE DESENHO DOS OLHOS

void desenharOlhoFechado(Adafruit_SSD1306 &tela) {
  tela.clearDisplay(); // Deixa o ecrã totalmente preto
  tela.display();
}

void desenharOlhoAberto(Adafruit_SSD1306 &tela, bool esquerdo) {
  tela.clearDisplay();
  int centroX = 64;
  int centroY = 32;
  float raioX = 40.0;
  float raioY = 22.0;

  float angulo = 20.0 * PI / 180.0;
  if (esquerdo) angulo = -angulo;

  float cosA = cos(angulo);
  float sinA = sin(angulo);

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
  int centroX = 64;
  int centroY = 32;

  // 1. Elipse principal
  float raioX = 40.0;
  float raioY = 25.0;

  // 2. Elipse de recorte
  float raioX_recorte = 42.0;
  float raioY_recorte = 25.0;
  float deslocamentoY = -12.0;

  // O ângulo zero remove totalmente a inclinação
  float angulo = 0.0;

  float cosA = cos(angulo);
  float sinA = sin(angulo);

  for (int x = 0; x < 128; x++) {
    for (int y = 0; y < 64; y++) {
      float dx = x - centroX;
      float dy = y - centroY;

      // Coordenadas
      float rotX = dx * cosA + dy * sinA;
      float rotY = -dx * sinA + dy * cosA;

      float rotY_recorte = rotY - deslocamentoY;

      bool dentroPrincipal = ((rotX * rotX) / (raioX * raioX) + (rotY * rotY) / (raioY * raioY)) <= 1.0;
      bool dentroRecorte = ((rotX * rotX) / (raioX_recorte * raioX_recorte) + (rotY_recorte * rotY_recorte) / (raioY_recorte * raioY_recorte)) <= 1.0;

      if (dentroPrincipal && !dentroRecorte) {
        tela.drawPixel(x, y, WHITE);
      }
    }
  }

  tela.display();
}

void desenharOlhoPensativo(Adafruit_SSD1306 &tela, bool esquerdo) {
  tela.clearDisplay();
  int centroX = 64;
  int centroY = 32;
  float raioX = 40.0;
  float raioY = 8.0; // Achata bastante a altura no eixo Y

  float angulo = 20.0 * PI / 180.0;
  if (esquerdo) angulo = -angulo;

  float cosA = cos(angulo);
  float sinA = sin(angulo);

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