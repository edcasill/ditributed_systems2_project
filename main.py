import cv2
import numpy as np
from ultralytics import YOLO
import requests
import time
import constants
import asyncio
from spade_bdi.bdi import BDIAgent


def enviar_a_api(estado, camara_id):
    try:
        datos_camara = {"actividad": estado,
                        "camara": camara_id,}
        response = requests.post(constants.API_URL, json=datos_camara, timeout=2)
        print(f"API: [Cámara {camara_id}] Enviado -> {estado}")
        print(f"Estado: ", response.status_code)
        print(f"Respuesta de java: ", response.json())

    except Exception as e:
        print(f"Error API [Cámara {camara_id}]: {e}")


def detectar_fuego_rojo(frame):
    """
    Esta funcion es una abstraccion de una deteccion de fuego por medio del color rojo,
    si hay suficientes pixeles rojos, se considera que hay fuego en el lugar
    """
    # Convertir a HSV para detectar color
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Rangos para el color rojo (tiene dos rangos en HSV)
    lower_red1 = np.array([0, 120, 70])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, 120, 70])
    upper_red2 = np.array([180, 255, 255])

    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask = mask1 + mask2

    # Si hay suficientes pixeles rojos, consideramos que hay "fuego"
    pixeles_rojos = cv2.countNonZero(mask)
    return pixeles_rojos > 500 # Ajustar este umbral según tus pruebas


def procesar_frame(frame, model, last_box_cache, ultimo_estado, ultimo_envio, camara_id, COOLDOWN_API):
    """
    Esta función aisla la lógica para pasar cualquier frame de cualquier camara
    y que devuelva el frame dibujado y las variables de control actualizadas.
    """
    fuego = detectar_fuego_rojo(frame)
    if fuego:
        print("PELIGRO, HAY FUEGO EN EL LUGAR")

    results_skeleton = model(frame, verbose=False, imgsz=320)
    last_box = []

    for r in results_skeleton:
        if r.keypoints is None or r.boxes is None:
            continue

        for i, box in enumerate(r.boxes):
            if int(box.cls[0]) == 0:  # Es persona
                # Obtener coordenadas: x1, y1 (arriba izq), x2, y2 (abajo der)
                x1, y1, x2, y2 = box.xyxy[0].tolist()

                # calcula alto y ancho de la bounding box
                w = x2 - x1
                h = y2 - y1
                kpts = r.keypoints.data[i]  # keypoints del esqueleto

                try:
                    # localiza puntos del esqueleto
                    y_hombro = kpts[5][1]
                    x_hombro = kpts[5][0]
                    y_cadera = kpts[11][1]
                    x_cadera = kpts[11][0]
                    y_rodilla = kpts[13][1]

                    confianza_rodilla = kpts[13][2]  # se usa la rodilla de referencia para la pose

                    dif_y_torso = abs(y_hombro - y_cadera)  # tomamos en cuenta la posicion del torso
                    dif_x_torso = abs(x_hombro - x_cadera)

                    # Acostado normal: La caja es mucho mas ancha que alta
                    if w > (h * 1.1):
                        estado = "Acostado"
                        color = (255, 0, 0)

                    # Acostado Diagonal: El torso esta estirado horizontalmente
                    elif dif_x_torso > dif_y_torso:
                        estado = "Acostado"
                        color = (255, 0, 0)

                    # Sentado de Frente o Perfil
                    elif confianza_rodilla > 0.4:
                        dif_y_pierna = abs(y_cadera - y_rodilla)

                        # si la distancia vertical entre cadera y rodilla es corta (Perfil)
                        # o si la caja es mas alta que ancha y la distancia es media (De frente)
                        if dif_y_pierna < 45 or (h > w and dif_y_pierna < 80):
                            estado = "Sentado"
                            color = (0, 0, 255)
                        else:
                            estado = "De pie"
                            color = (0, 255, 0)

                    # Piernas Ocultas
                    else:
                        # estado = "Piernas Ocultas"
                        # color = (255, 165, 0)
                        estado = "Sentado"
                        color = (0, 0, 255)

                except IndexError:
                    estado = "Analizando..."
                    color = (255, 255, 255)

                last_box.append((int(x1), int(y1), int(x2), int(y2), estado, color))

                # logica de la API
                tiempo_actual = time.time()
                if estado != ultimo_estado or (tiempo_actual - ultimo_envio > COOLDOWN_API):
                    enviar_a_api(estado, camara_id)
                    ultimo_estado = estado
                    ultimo_envio = tiempo_actual

    # dibujar usando los datos nuevos (o el cache si no hay detecciones nuevas este frame)
    datos_a_dibujar = last_box if last_box else last_box_cache

    for x1, y1, x2, y2, estado, color in datos_a_dibujar:
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, estado, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    return frame, datos_a_dibujar, ultimo_estado, ultimo_envio, fuego


async def main():
    model = YOLO('yolov8n-pose.pt')
    monitor = BDIAgent("monitor@localhost", "p@tr0ll", "cam_agent.asl")
    await monitor.start()

    # Instanciar las camaras a usar
    url1 = f"rtsp://{constants.USUARIOS[0]}:{constants.CONTRASENIA}@{constants.IPS[0]}/stream2"
    url2 = f"rtsp://{constants.USUARIOS[1]}:{constants.CONTRASENIA}@{constants.IPS[1]}/stream2"
    cap1 = cv2.VideoCapture(url1)
    cap2 = cv2.VideoCapture(url2)

    frame_count = 0

    # Controles independientes por camara
    estado_cam1, envio_cam1, cache_cam1 = None, 0, []
    estado_cam2, envio_cam2, cache_cam2 = None, 0, []
    COOLDOWN_API = 5.0

    NOMBRE_VENTANA = "Monitoreo Dual - Uso de Silla/Cama"
    cv2.namedWindow(NOMBRE_VENTANA, cv2.WINDOW_NORMAL)

    while True:
        # Leer de ambas camaras al mismo tiempo
        success1, frame1 = cap1.read()
        success2, frame2 = cap2.read()

        # reconexion si alguna falla
        if not success1 or not success2:
            print('Reconectando camaras...')
            cap1.release()
            cap2.release()
            time.sleep(3)
            cap1 = cv2.VideoCapture(url1)
            cap2 = cv2.VideoCapture(url2)
            continue

        frame_count += 1

        # Procesamos cada 5 frames para no matar el CPU
        if frame_count % 5 == 0:
            # Procesar camara 1
            frame1, cache_cam1, estado_cam1, envio_cam1, fuego1 = procesar_frame(frame1, model, cache_cam1,
                                                                                 estado_cam1, envio_cam1, 1,
                                                                                 COOLDOWN_API)

            # Procesar camara 2
            frame2, cache_cam2, estado_cam2, envio_cam2, fuego2 = procesar_frame(frame2, model, cache_cam2,
                                                                                 estado_cam2, envio_cam2, 2,
                                                                                 COOLDOWN_API)
        else:
            # En frames sin IA, solo redibujar el cache para evitar parpadeos
            for x1, y1, x2, y2, estado, color in cache_cam1:
                cv2.rectangle(frame1, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame1, estado, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            for x1, y1, x2, y2, estado, color in cache_cam2:
                cv2.rectangle(frame2, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame2, estado, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Redimensionamos a un tamanio manejable
        frame1_resized = cv2.resize(frame1, (700, 420))
        frame2_resized = cv2.resize(frame2, (700, 420))

        # unir horizontalmente los frames
        frame_unido = np.hstack((frame1_resized, frame2_resized))
        cv2.imshow(NOMBRE_VENTANA, frame_unido)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap1.release()
    cap2.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    asyncio.run(main)
