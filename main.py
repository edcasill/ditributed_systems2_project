import cv2
import numpy as np
from ultralytics import YOLO
import requests
import time
import constants
import asyncio
from spade_bdi.bdi import BDIAgent
from spade.behaviour import CyclicBehaviour
import agentspeak
from spade.message import Message


def detect_fire_red(frame):
    """
    Esta funcion es una abstraccion de una deteccion de fire por medio del color rojo,
    si hay suficientes pixeles rojos, se considera que hay fire en el lugar
    """
    # Convertir a HSV para detectar color
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Rangos para el color rojo (tiene dos rangos en HSV)
    # lower_red1 = np.array([0, 120, 70])  # estos se supone son los ideales para el fuego
    # upper_red1 = np.array([10, 255, 255])
    # lower_red2 = np.array([170, 120, 70])  # estos se supone son los ideales para el fuego
    # upper_red2 = np.array([180, 255, 255])

    # funcionan pero muy cerca o grande
    lower_red1 = np.array([0, 150, 150])
    upper_red1 = np.array([8, 255, 255])
    lower_red2 = np.array([175, 150, 150])
    upper_red2 = np.array([180, 255, 255])

    """
    lower_red1 = np.array([0, 135, 110])
    upper_red1 = np.array([9, 255, 255])
    lower_red2 = np.array([173, 135, 110])
    upper_red2 = np.array([180, 255, 255])
    """

    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask = mask1 + mask2

    # Si hay suficientes pixeles rojos, consideramos que hay "fire"
    pixeles_rojos = cv2.countNonZero(mask)
    return pixeles_rojos > 500  # Ajustar este umbral según tus pruebas


def enviar_mensaje_java(agente, receiver, content, performative, protocol, language, ontology):
    """
    Agrega los metadatos a los mensajes que se envian a java
    Returns:
        _type_: _description_
    """
    # Se usa .strip('"') por si AgentSpeak manda los textos con comillas literales
    receiver_str = str(receiver).strip('"')

    msg = Message(to=receiver_str)
    msg.body = str(content)
    # Metadatos para que el agente en Java los pueda interpretar
    msg.set_metadata("performative", str(performative).strip('"'))
    msg.set_metadata("protocol", str(protocol).strip('"'))
    msg.set_metadata("language", str(language).strip('"'))
    msg.set_metadata("ontology", str(ontology).strip('"'))

    # Enviar usando el cliente del agente en segundo plano
    asyncio.create_task(agente.client.send(msg))
    return True


def calcula_puntaje(umbral_deteccion, puntaje_cuerpo, nariz, ojo_i, ojo_d, oreja_i, oreja_d, confianza_hombro, confianza_cadera, confianza_rodilla):
    if nariz > umbral_deteccion: puntaje_cuerpo += 1
    if ojo_i > umbral_deteccion: puntaje_cuerpo += 1
    if ojo_d > umbral_deteccion: puntaje_cuerpo += 1
    if oreja_i > umbral_deteccion: puntaje_cuerpo += 1
    if oreja_d > umbral_deteccion: puntaje_cuerpo += 1
    if confianza_hombro > umbral_deteccion: puntaje_cuerpo += 1
    if confianza_cadera > umbral_deteccion: puntaje_cuerpo += 1
    if confianza_rodilla > umbral_deteccion: puntaje_cuerpo += 1
    return puntaje_cuerpo


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
                    nariz = kpts[0][2]  # el valor de confianza nos dice que esta ahi
                    ojo_i = kpts[1][2]
                    ojo_d = kpts[2][2]
                    oreja_i = kpts[3][2]
                    oreja_d = kpts[4][2]
                    confianza_hombro = kpts[5][2]
                    confianza_cadera = kpts[11][2]

                    umbral_deteccion = 0.5
                    puntaje_cuerpo = 0
                    puntaje_cuerpo = calcula_puntaje(umbral_deteccion,
                                                     puntaje_cuerpo,
                                                     nariz,
                                                     ojo_i,
                                                     ojo_d,
                                                     oreja_i,
                                                     oreja_d,
                                                     confianza_hombro,
                                                     confianza_cadera,
                                                     confianza_rodilla)

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
                puntaje_str = str(puntaje_cuerpo)
                # if estado != cam_state or (tiempo_actual - last_sent > COOLDOWN_API):
                if tiempo_actual - last_sent > COOLDOWN_API:
                    cam_state = puntaje_str
                    last_sent = tiempo_actual
                """
                if puntaje_str != cam_state or (tiempo_actual - last_sent > COOLDOWN_API):
                    # enviar_a_api(estado, camara_id)
                    # cam_state = estado
                    cam_state = puntaje_str
                    last_sent = tiempo_actual
                """

    # dibujar usando los datos nuevos (o el cache si no hay detecciones nuevas este frame)
    datos_a_dibujar = last_box if last_box else last_box_cache

    for x1, y1, x2, y2, estado, color in datos_a_dibujar:
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, estado, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    return frame, datos_a_dibujar, cam_state, last_sent, fire


class FipaReceiver(CyclicBehaviour):
    async def run(self):
        # Espera recibir mensajes wait to receive messages
        msg = await self.receive(timeout=1.0)
        if msg:
            # SPADE extrae los metadatos FIPA automaticamente y los pone en un diccionario
            performative = msg.metadata.get("performative")
            Content = msg.body

            print(f"[{self.agent.jid}] FIPA message received:")
            print(f" - Performative: {performative}")
            print(f" - Content: {Content}")
            
            # Razonamiento basado en el estándar FIPA
            if performative == "request":
                # Si Java hace una petición (REQUEST), inyectamos una orden al motor BDI
                self.agent.bdi.set_belief(f'java_command("{Content}")')
                
            elif performative == "inform":
                # Si Java solo te informa de un estado (INFORM)
                self.agent.bdi.set_belief(f'java_notification("{Content}")')
                
            elif performative == "query-ref":
                # Si Java te pregunta algo
                pass


class VisionBehaviour(CyclicBehaviour):
    """
    Permite que el agente 'vea' con opencv y ademas nos pueda generar las ventanas para nosotros
    ver lo que ve el agente por su camara asignada
    Args:
        CyclicBehaviour (_type_): _description_
    """
    async def run(self):
        # the agent read the frames from his own camera
        success, frame = self.agent.cap.read()

        if not success:
            self.agent.bdi.remove_belief("camara(encendida)")
            self.agent.bdi.set_belief("camara(apagada)")
            print(f"Reconecting {self.agent.jid}...")
            await asyncio.sleep(3)
            return

        # detecta la camara encendida y lo hace saber al agente
        self.agent.bdi.remove_belief("camara(apagada)")
        self.agent.bdi.set_belief("camara(encendida)")
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
                        print(f"[{self.agent.jid} PYTHON DEBUG] Enviando creencia person({self.agent.cam_state}) a AgentSpeak")
                        if self.agent.current_belief:  # delete if there was a previous state
                            self.agent.bdi.remove_belief(f"person({self.agent.current_belief})")

                        self.agent.bdi.set_belief(f"person({self.agent.cam_state})")
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
        await asyncio.sleep(0.15)


class BDI_agent_monitor(BDIAgent):
    """
    Initialize agents with the model to monitor on the cameras
    """
    def __init__(self, jid, passw, behaviour, cam_id, url, model):
        super().__init__(jid, passw, behaviour, verify_security=False)

        self.cam_id = cam_id
        self.cap = cv2.VideoCapture(url)
        self.model = model
        self.frame_count = 0
        self.cam_state = None
        self.cache = []
        self.last_sent = 0

    # --- DEBE ESTAR AL MISMO NIVEL QUE __init__ ---
    def add_custom_actions(self, actions):
        @actions.add(".enviar_mensaje_java", 6)
        def _enviar_mensaje_java(agent, term, intention):
            try:
                # Extraer y "aterrizar" (grounded) los 6 parámetros desde AgentSpeak
                receiver = agentspeak.grounded(term.args[0], intention.scope)
                content = agentspeak.grounded(term.args[1], intention.scope)
                performative = agentspeak.grounded(term.args[2], intention.scope)
                protocol = agentspeak.grounded(term.args[3], intention.scope)
                language = agentspeak.grounded(term.args[4], intention.scope)
                ontology = agentspeak.grounded(term.args[5], intention.scope)
                
                # Limpiar comillas extras y armar el mensaje
                receiver_str = str(receiver).strip('"').strip("'")
                msg = Message(to=receiver_str)

                content_str = str(content)
                
                if content_str.startswith("estado("):
                    # Interceptamos "estado(true, 8, true)" y extraemos los 3 valores puros
                    valores = content_str.replace("estado(", "").replace(")", "").split(",")
                    fuego_val = valores[0].strip().lower()
                    persona_val = valores[1].strip()
                    camara_val = valores[2].strip().lower()
                    
                    # Armamos el string en formato JSON con comillas dobles estrictas para Java
                    msg.body = f'{{"fuego": {fuego_val}, "persona": {persona_val}, "camara_ok": {camara_val}}}'
                else:
                    # Comportamiento normal (envía el puntaje o "emergency" de los reportes del foco)
                    msg.body = content_str
                
                # msg.body = str(content)
                msg.set_metadata("performative", str(performative).strip('"').strip("'"))
                msg.set_metadata("protocol", str(protocol).strip('"').strip("'"))
                msg.set_metadata("language", str(language).strip('"').strip("'"))
                msg.set_metadata("ontology", str(ontology).strip('"').strip("'"))
                
                # Enviar usando el motor BDI del agente (self.bdi)
                asyncio.create_task(self.bdi.send(msg))
                
            except Exception as e:
                # Si algo falla en Python, esto lo imprimirá en consola en lugar de crashear AgentSpeak
                print(f"[{self.jid}] Error interno al enviar mensaje a Java: {e}")
            
            # Obligatorio para las acciones personalizadas en AgentSpeak
            yield

    async def setup(self):
        print(f"Starting {self.jid} agent. Opening camera window...")
        self.add_behaviour(VisionBehaviour())
        self.add_behaviour(FipaReceiver())


async def main():
    model = YOLO('yolov8n-pose.pt')

    # Instanciar las camaras a usar
    url1 = f"rtsp://{constants.USUARIOS[0]}:{constants.CONTRASENIA}@{constants.IPS[0]}/stream2"
    url2 = f"rtsp://{constants.USUARIOS[1]}:{constants.CONTRASENIA}@{constants.IPS[1]}/stream2"

    monitor1 = BDI_agent_monitor(f"monitor1@{constants.IP_SERVER}", constants.PASS_XMPP, "cam_agent.asl",
                                 "Camara_1", url1, model)
    monitor2 = BDI_agent_monitor(f"monitor2@{constants.IP_SERVER}", constants.PASS_XMPP, "cam_agent.asl",
                                 "Camara_2", url2, model)
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
