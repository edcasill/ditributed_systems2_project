import cv2
import numpy as np
from ultralytics import YOLO
import requests
import time
import constants
import asyncio
from spade_bdi.bdi import BDIAgent
from spade.behaviour import CyclicBehaviour
import json
from spade.message import Message


def enviar_a_api(estado, camara_id):
    try:
        datos_camara = {"actividad": estado,
                        "camara": camara_id}
        response = requests.post(constants.API_URL, json=datos_camara, timeout=2)
        print(f"API: [Cámara {camara_id}] Enviado -> {estado}")
        print(f"Estado: ", response.status_code)
        print(f"Respuesta de java: ", response.json())

    except Exception as e:
        print(f"Error API [Cámara {camara_id}]: {e}")


def detect_fire_red(frame):
    """
    Esta funcion es una abstraccion de una deteccion de fire por medio del color rojo,
    si hay suficientes pixeles rojos, se considera que hay fire en el lugar
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

    # Si hay suficientes pixeles rojos, consideramos que hay "fire"
    pixeles_rojos = cv2.countNonZero(mask)
    return pixeles_rojos > 500  # Ajustar este umbral según tus pruebas


def procesar_frame(frame, model, last_box_cache, cam_state, last_sent, camara_id, COOLDOWN_API):
    """
    Esta función aisla la lógica para pasar cualquier frame de cualquier camara
    y que devuelva el frame dibujado y las variables de control actualizadas.
    """
    fire = detect_fire_red(frame)
    if fire:
        print("WARNING, FIRE DETECTED")

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

                # logica de la API. En desuso por los agentes
                tiempo_actual = time.time()
                if estado != cam_state or (tiempo_actual - last_sent > COOLDOWN_API):
                    # enviar_a_api(estado, camara_id)
                    cam_state = estado
                    last_sent = tiempo_actual

    # dibujar usando los datos nuevos (o el cache si no hay detecciones nuevas este frame)
    datos_a_dibujar = last_box if last_box else last_box_cache

    for x1, y1, x2, y2, estado, color in datos_a_dibujar:
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, estado, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    return frame, datos_a_dibujar, cam_state, last_sent, fire


class ReceiverFromJava(CyclicBehaviour):
    """
    Recive los mensajes de java
    Args:
        CyclicBehaviour (_type_): _description_
    """
    async def run(self):
        # Espera recibir mensajes
        msg = await self.receive(timeout=1.0)
        if msg:
            try:
                # Se asume que Java enviará un string JSON en el body
                contenido = json.loads(msg.body)

                # Ejemplo: Java  {"performativa": "request", "accion": "apagar_alarma"}
                if contenido.get("performativa") == "request":
                    accion = contenido.get("accion")
                    print(f"[{self.agent.jid}] Mensaje de Java recibido: {accion}")

                    # Inyectar la orden como una nueva creencia en el entorno BDI
                    self.agent.bdi.set_belief(f'comando_java("{accion}")')

            except json.JSONDecodeError:
                print("El mensaje recibido de Java no tiene un formato JSON válido.")


class BDI_agent_monitor(BDIAgent):
    """
    Initialize agents with the model to monitor on the cameras
    Args:
        BDIAgent (_type_): let us use BDI agents
    """
    def __init__(self, jid, passw, behaviour, cam_id, url, model):
        super().__init__(jid, passw, behaviour)  # this is the agent

        self.cam_id = cam_id
        self.cap = cv2.VideoCapture(url)
        self.model = model

        self.frame_count = 0
        self.cam_state = None
        self.cache = []
        self.last_sent = 0

    async def setup(self):
        print(f"Starting {self.jid} agent. Opening camera window...")
        self.add_behaviour(VisionBehaviour())
        self.add_behaviour(ReceiverFromJava())


class VisionBehaviour(CyclicBehaviour):
    async def run(self):
        # the agent read the frames from his own camera
        success, frame = self.agent.cap.read()

        if not success:
            print(f"Reconecting {self.agent.jid}...")
            await asyncio.sleep(3)
            return

        self.agent.frame_count += 1

        # every 5 frames the agent checks if the camera detects a person or fire
        if self.agent.frame_count % 5 == 0:
            # detects and draw bounding boxes for the person or fire
            frame, self.agent.cache, self.agent.cam_state, self.agent.last_sent, fire = procesar_frame(
                frame,
                self.agent.model,
                self.agent.cache,
                self.agent.cam_state,
                self.agent.last_sent,
                self.agent.cam_id,
                5.0)

            # update beliefs of the agent, depending on what he detects
            if fire:
                self.agent.bdi.set_belief("fire")
            else:
                self.agent.bdi.remove_belief("fire")
                if self.agent.cam_state:
                    # temp atribute to search the active believe
                    if not hasattr(self.agent, 'current_belief'):
                        self.agent.current_belief = None

                    # update only if it change it
                    if self.agent.current_belief != self.agent.cam_state:
                        if self.agent.current_belief:  # delete if there was a previous state
                            self.agent.bdi.remove_belief(f"person(\"{self.agent.current_belief}\")")

                        self.agent.bdi.set_belief(f"person(\"{self.agent.cam_state}\")")
                        self.agent.current_belief = self.agent.cam_state

        # redraw frames from cache
        else:
            for x1, y1, x2, y2, estado, color in self.agent.cache:
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, estado, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # resize window and show
        frame_resized = cv2.resize(frame, (700, 420))
        cv2.imshow(f"Monitoreo - {self.agent.jid}", frame_resized)

        # refresh window
        if cv2.waitKey(1) & 0xFF == ord('q'):
            pass  # close window with Ctrl+C on terminal

        # lend the control to asyncio, so the BDI can read messages
        await asyncio.sleep(0.01)


async def main():
    model = YOLO('yolov8n-pose.pt')

    # Instanciar las camaras a usar
    url1 = f"rtsp://{constants.USUARIOS[0]}:{constants.CONTRASENIA}@{constants.IPS[0]}/stream2"
    url2 = f"rtsp://{constants.USUARIOS[1]}:{constants.CONTRASENIA}@{constants.IPS[1]}/stream2"

    monitor1 = BDI_agent_monitor(f"monitor1@{constants.IP_SERVER}", constants.PASS_XMPP, "cam_agent.asl",
                                 "camera_1", url1, model)
    monitor2 = BDI_agent_monitor(f"monitor2@{constants.IP_SERVER}", constants.PASS_XMPP, "cam_agent.asl",
                                 "camera_2", url2, model)
    await monitor1.start()
    await monitor2.start()

    try:
        while True:
            await asyncio.sleep(2)
    except KeyboardInterrupt:
        print("WARNING. Couldn't connect to cameras")
        await monitor1.stop()
        await monitor2.stop()


if __name__ == "__main__":
    asyncio.run(main())
