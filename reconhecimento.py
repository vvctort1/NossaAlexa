import cv2
import numpy as np
import os
import json

# Inicializa o classificador de detecção e o reconhecedor de faces
classificador = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
reconhecedor = cv2.face.LBPHFaceRecognizer_create()
camera = cv2.VideoCapture(0)


# CLAHE: equalização de histograma adaptativa, ajuda MUITO com iluminação ruim/desigual
clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

altura, largura = 220, 220
pasta_fotos = 'fotos/'

# Cria a pasta 'fotos' caso ela não exista
if not os.path.exists(pasta_fotos):
    os.makedirs(pasta_fotos)
dicionario_nomes = {}
modo_reconhecimento = False
id_atual_global = 1


def treinar_modelo():
    """Lê as imagens salvas na pasta, treina o modelo de reconhecimento e exporta os arquivos."""
    faces = []
    ids = []

    for nome_arquivo in os.listdir(pasta_fotos):
        if nome_arquivo.endswith('.jpg'):
            caminho_imagem = os.path.join(pasta_fotos, nome_arquivo)
            imagem_cinza = cv2.imread(caminho_imagem, cv2.IMREAD_GRAYSCALE)

            # Os arquivos são salvos no formato: "ID_NOME_AMOSTRA.jpg" (Ex: 1_Maria_1.jpg)
            partes_nome = nome_arquivo.split('_')
            id_pessoa = int(partes_nome[0])
            nome_pessoa = partes_nome[1]

            dicionario_nomes[id_pessoa] = nome_pessoa
            faces.append(imagem_cinza)
            ids.append(id_pessoa)

    if len(faces) > 0:
        reconhecedor.train(faces, np.array(ids))

        # --- SALVA OS ARQUIVOS PARA A TRIA USAR ---
        reconhecedor.save('modelo_lbph.yml')
        with open('nomes_lbph.json', 'w', encoding='utf-8') as f:
            json.dump(dicionario_nomes, f)

        print("\n[INFO] Modelo treinado e salvo com sucesso (.yml e .json)!")
        return True
    else:
        print("\n[AVISO] Nenhuma foto encontrada na pasta para treinar.")
        return False


def detectar_faces(imagemCinza):
    """
    Detecta rostos aplicando equalização de contraste (CLAHE) primeiro,
    e retorna apenas o MAIOR rosto encontrado (assume-se que é o mais
    próximo da câmera, filtrando pessoas/objetos ao fundo).
    """
    imagem_equalizada = clahe.apply(imagemCinza)

    faces = classificador.detectMultiScale(
        imagem_equalizada,
        scaleFactor=1.1,
        minNeighbors=6,
        minSize=(100, 100)
    )

    if len(faces) == 0:
        return [], imagem_equalizada

    # Ordena por área (largura * altura) e mantém só a maior
    maior_face = max(faces, key=lambda f: f[2] * f[3])
    return [maior_face], imagem_equalizada


print("=" * 40)
print(" COMANDOS DA CÂMERA:")
print(" [ s ] - Salvar a face atual")
print(" [ r ] - Ativar/Desativar modo de reconhecimento (e treinar)")
print(" [ q ] - Sair do programa")
print("=" * 40)

while True:
    status, imagem = camera.read()
    if not status:
        break

    imagemCinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)

    # --- Detecção robusta: CLAHE + apenas o maior rosto ---
    facesDetectadas, imagemCinzaEqualizada = detectar_faces(imagemCinza)

    for (x, y, l, a) in facesDetectadas:
        # Recorta e redimensiona a face detectada (usa a versão equalizada,
        # assim o reconhecimento treina/prediz com o mesmo contraste)
        imagemFace = cv2.resize(imagemCinzaEqualizada[y: y + a, x:x + l], (largura, altura))

        # Se o modo de reconhecimento estiver ativo
        if modo_reconhecimento and len(dicionario_nomes) > 0:
            id_previsto, confianca = reconhecedor.predict(imagemFace)

            # Quanto menor a confiança no LBPH, mais precisa é a detecção (geralmente < 75 é bom)
            if confianca < 75:
                nome = dicionario_nomes.get(id_previsto, "Desconhecido")
                texto = f"{nome} - {int(confianca)}"
                cor = (0, 255, 0)  # Verde para reconhecido
            else:
                texto = "Desconhecido"
                cor = (0, 0, 255)  # Vermelho para não reconhecido

            cv2.putText(imagem, texto, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, cor, 2)
            cv2.rectangle(imagem, (x, y), (x + l, y + a), cor, 2)
        else:
            # Modo normal (Apenas detecção da caixa azul)
            cv2.rectangle(imagem, (x, y), (x + l, y + a), (255, 0, 0), 2)

    cv2.imshow("Camera", imagem)

    # Captura a tecla pressionada
    tecla = cv2.waitKey(1) & 0xFF

    if tecla == ord('q'):
        print("Encerrando...")
        break

    elif tecla == ord('s'):
        if len(facesDetectadas) == 0:
            print("\n[AVISO] Nenhuma face detectada na câmera. Tente novamente.")
            continue

        nome_digitado = input("\nDigite o nome da pessoa: ")

        # Pega a face detectada (já é a maior/única, filtrada em detectar_faces)
        (x, y, l, a) = facesDetectadas[0]
        imagemFace = cv2.resize(imagemCinzaEqualizada[y: y + a, x:x + l], (largura, altura))

        # Verifica se essa pessoa já tem um ID registrado, se não, cria um novo
        id_pessoa = id_atual_global
        for key, val in dicionario_nomes.items():
            if val.lower() == nome_digitado.lower():
                id_pessoa = key
                break

        # Conta quantas fotos dessa pessoa já existem para ter um ponto de partida...
        amostras_existentes = len([f for f in os.listdir(pasta_fotos) if f.startswith(f"{id_pessoa}_{nome_digitado}")])
        nova_amostra = amostras_existentes + 1

        # ...mas GARANTE um nome livre mesmo se a contagem acima estiver desatualizada
        # (ex: dois 's' em sequência rápida). Isso evita sobrescrever fotos existentes.
        localFoto = f"{pasta_fotos}{id_pessoa}_{nome_digitado}_{nova_amostra}.jpg"
        while os.path.exists(localFoto):
            nova_amostra += 1
            localFoto = f"{pasta_fotos}{id_pessoa}_{nome_digitado}_{nova_amostra}.jpg"

        sucesso = cv2.imwrite(localFoto, imagemFace)
        if not sucesso:
            print(f"\n[ERRO] Falha ao salvar a imagem em {localFoto}. Verifique permissões/espaço em disco.")
            continue

        print(f"[SUCESSO] Face salva como: {localFoto}")

        dicionario_nomes[id_pessoa] = nome_digitado
        if id_pessoa == id_atual_global:
            id_atual_global += 1

    elif tecla == ord('r'):
        if not modo_reconhecimento:
            print("\nTreinando o modelo com as imagens salvas...")
            if treinar_modelo():
                modo_reconhecimento = True
                print(">> MODO RECONHECIMENTO LIGADO <<")
        else:
            modo_reconhecimento = False
            print(">> MODO RECONHECIMENTO DESLIGADO <<")

camera.release()
cv2.destroyAllWindows()