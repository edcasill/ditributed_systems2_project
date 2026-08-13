import cv2
import numpy as np
from ultralytics import YOLO
import constants
import asyncio
import agentspeak
from spade_bdi.bdi import BDIAgent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
import threading
import torch

# ============================================================
# CONFIGURACION DE RENDIMIENTO
# ============================================================
DISPLAY_WIDTH = 700
DISPLAY_HEIGHT = 420
INFERENCE_EVERY_N_FRAMES = 5
YOLO_IMGSZ = 320
YOLO_CONF = 0.25
RECONNECT_DELAY = 3.0

# Un solo modelo compartido evita duplicar memoria.
# El lock evita ejecutar el mismo modelo desde dos hilos simultaneamente.
MODEL = YOLO("yolov8n-pose.pt")
MODEL_LOCK = threading.Lock()

USE_CUDA = torch.cuda.is_available()
YOLO_DEVICE = 0 if USE_CUDA else "cpu"
YOLO_HALF = USE_CUDA

if USE_CUDA:
    print("[YOLO] CUDA disponible. Se usara GPU + FP16.")
else:
    print("[YOLO] CUDA no disponible. Se usara CPU.")


# ============================================================
# CAMARA
# ============================================================
def open_camera(url):
    """Abre una camara RTSP con un buffer pequeno para reducir latencia."""
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)

    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass

    return cap


# ============================================================
# DETECCION DE FUEGO
# ============================================================
def detect_fire_red(frame):
    """Deteccion sencilla de fuego basada en pixeles rojos."""
    small = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)

    # Rangos para el color rojo (tiene dos rangos en HSV)
    # lower_red1 = np.array([0, 120, 70])  # estos se supone son los ideales para el fuego
    # upper_red1 = np.array([10, 255, 255])
    # lower_red2 = np.array([170, 120, 70])  # estos se supone son los ideales para el fuego
    # upper_red2 = np.array([180, 255, 255])

    # funcionan pero muy cerca o grande
    """
    lower_red1 = np.array([0, 150, 150])
    upper_red1 = np.array([8, 255, 255])
    lower_red2 = np.array([175, 150, 150])
    upper_red2 = np.array([180, 255, 255])
    """

    
    lower_red1 = np.array([0, 135, 110])
    upper_red1 = np.array([9, 255, 255])
    lower_red2 = np.array([173, 135, 110])
    upper_red2 = np.array([180, 255, 255])
    

    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask = mask1 | mask2

    # Umbral proporcional a la imagen reducida 320x180.
    return cv2.countNonZero(mask) > 80


# ============================================================
# PUNTAJE CORPORAL
# ============================================================
def calcula_puntaje(
    umbral_deteccion,
    nariz,
    ojo_i,
    ojo_d,
    oreja_i,
    oreja_d,
    confianza_hombro,
    confianza_cadera,
    confianza_rodilla,
):
    valores = (
        nariz,
        ojo_i,
        ojo_d,
        oreja_i,
        oreja_d,
        confianza_hombro,
        confianza_cadera,
        confianza_rodilla,
    )

    return sum(v > umbral_deteccion for v in valores)


# ============================================================
# YOLO
# ============================================================
def procesar_frame(frame, model):
    """
    Ejecuta YOLO y devuelve:
        - detecciones para dibujar
        - puntaje corporal

    No dibuja ni realiza comunicacion.
    """
    last_box = []
    score = 0

    with MODEL_LOCK:
        results_skeleton = model(
            frame,
            verbose=False,
            imgsz=YOLO_IMGSZ,
            conf=YOLO_CONF,
            device=YOLO_DEVICE,
            half=YOLO_HALF,
        )

    for r in results_skeleton:
        if r.keypoints is None or r.boxes is None:
            continue

        for i, box in enumerate(r.boxes):
            if int(box.cls[0]) != 0:
                continue

            x1, y1, x2, y2 = box.xyxy[0].tolist()

            w = x2 - x1
            h = y2 - y1
            kpts = r.keypoints.data[i]

            try:
                y_hombro = kpts[5][1]
                x_hombro = kpts[5][0]
                y_cadera = kpts[11][1]
                x_cadera = kpts[11][0]
                y_rodilla = kpts[13][1]

                confianza_rodilla = float(kpts[13][2])
                nariz = float(kpts[0][2])
                ojo_i = float(kpts[1][2])
                ojo_d = float(kpts[2][2])
                oreja_i = float(kpts[3][2])
                oreja_d = float(kpts[4][2])
                confianza_hombro = float(kpts[5][2])
                confianza_cadera = float(kpts[11][2])

                score = calcula_puntaje(
                    0.5,
                    nariz,
                    ojo_i,
                    ojo_d,
                    oreja_i,
                    oreja_d,
                    confianza_hombro,
                    confianza_cadera,
                    confianza_rodilla,
                )

                dif_y_torso = abs(y_hombro - y_cadera)
                dif_x_torso = abs(x_hombro - x_cadera)

                if w > h * 1.1:
                    estado = "Acostado"
                    color = (255, 0, 0)

                elif dif_x_torso > dif_y_torso:
                    estado = "Acostado"
                    color = (255, 0, 0)

                elif confianza_rodilla > 0.4:
                    dif_y_pierna = abs(y_cadera - y_rodilla)

                    if dif_y_pierna < 45 or (h > w and dif_y_pierna < 80):
                        estado = "Sentado"
                        color = (0, 0, 255)
                    else:
                        estado = "De pie"
                        color = (0, 255, 0)

                else:
                    estado = "Sentado"
                    color = (0, 0, 255)

            except IndexError:
                estado = "Analizando..."
                color = (255, 255, 255)

            last_box.append(
                (
                    int(x1),
                    int(y1),
                    int(x2),
                    int(y2),
                    estado,
                    color,
                )
            )

    if not last_box:
        score = 0

    return last_box, str(score)


def draw_detections(frame, detections):
    for x1, y1, x2, y2, estado, color in detections:
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            frame,
            estado,
            (x1, max(y1 - 10, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            2,
        )

    return frame


# ============================================================
# RECEPCION FIPA
# ============================================================
class FipaReceiver(CyclicBehaviour):
    async def run(self):
        msg = await self.receive(timeout=0.1)

        if msg:
            print(f"[{self.agent.jid}] FIPA: mensaje recibido")

            performative = msg.metadata.get("performative")
            content = msg.body.replace('"', "").replace("'", "").strip().lower()

            print(f"[{self.agent.jid}] Performative: {performative}")
            print(f"[{self.agent.jid}] Content: {content}")

            if performative == "request":
                if content == "get_state":
                    print(
                        f"[{self.agent.jid}] REQUEST -> "
                        f"bridge_request(get_state)"
                    )
                    self.agent.bdi.set_belief(
                        "bridge_request",
                        "get_state",
                    )

                elif content == "set_task_fire":
                    self.agent.bdi.set_belief(
                        "bridge_request",
                        "set_task_fire",
                    )

                elif content == "set_task_person":
                    self.agent.bdi.set_belief(
                        "bridge_request",
                        "set_task_person",
                    )

                elif content == "set_task_none":
                    self.agent.bdi.set_belief(
                        "bridge_request",
                        "set_task_none",
                    )

                elif content == "deactivate_alarm":
                    self.agent.bdi.set_belief(
                        "bridge_request",
                        "deactivate_alarm",
                    )

                else:
                    print(
                        f"[{self.agent.jid}] "
                        f"Comando desconocido: {content}"
                    )

            elif performative == "inform":
                self.agent.bdi.set_belief(
                    "bridge_notification",
                    content,
                )

        await asyncio.sleep(0)


# ============================================================
# AGENTE MONITOR
# ============================================================
class BDI_agent_monitor(BDIAgent):

    def __init__(self, jid, passw, behaviour, cam_id, url, model):
        super().__init__(
            jid,
            passw,
            behaviour,
            verify_security=False,
        )

        self.cam_id = cam_id
        self.url = url
        self.cap = open_camera(self.url)
        self.model = model

        self.frame_count = 0
        self.cache = []

        # Estados visuales actuales
        self.cam_state = "0"
        self.current_camara_ok = None
        self.current_fire = None
        self.current_person_score = None

        # Una sola inferencia pendiente por monitor.
        self.inference_task = None

    # ========================================================
    # ACCION PERSONALIZADA AGENTSPEAK -> PUENTE
    # ========================================================
    def add_custom_actions(self, actions):

        @actions.add(".enviar_mensaje_puente", 6)
        def _enviar_mensaje_puente(agent, term, intention):
            try:
                receiver = agentspeak.grounded(
                    term.args[0],
                    intention.scope,
                )

                content = agentspeak.grounded(
                    term.args[1],
                    intention.scope,
                )

                performative = agentspeak.grounded(
                    term.args[2],
                    intention.scope,
                )

                protocol = agentspeak.grounded(
                    term.args[3],
                    intention.scope,
                )

                language = agentspeak.grounded(
                    term.args[4],
                    intention.scope,
                )

                ontology = agentspeak.grounded(
                    term.args[5],
                    intention.scope,
                )

                receiver_str = str(receiver).strip('"').strip("'")
                content_str = str(content)
                performative_str = (
                    str(performative).strip('"').strip("'")
                )
                protocol_str = (
                    str(protocol).strip('"').strip("'")
                )
                language_str = (
                    str(language).strip('"').strip("'")
                )
                ontology_str = (
                    str(ontology).strip('"').strip("'")
                )

                msg = Message(to=receiver_str)
                msg.body = content_str

                msg.set_metadata(
                    "performative",
                    performative_str,
                )

                msg.set_metadata(
                    "protocol",
                    protocol_str,
                )

                msg.set_metadata(
                    "language",
                    language_str,
                )

                msg.set_metadata(
                    "ontology",
                    ontology_str,
                )

                # IMPORTANTE:
                # "agent" es el runtime interno de AgentSpeak.
                # Para evitar el AttributeError de agent.jid/client,
                # usamos directamente "self", que es el BDI_agent_monitor
                # real de SPADE que contiene esta accion.
                print(
                    f"[{self.jid}] ENVIANDO AL PUENTE -> "
                    f"to={receiver_str} | "
                    f"performative={performative_str} | "
                    f"body={content_str}"
                )

                async def send_message():
                    try:
                        await self.bdi.send(msg)

                        print(
                            f"[{self.jid}] "
                            f"MENSAJE ENVIADO CORRECTAMENTE AL PUENTE"
                        )

                    except Exception as e:
                        print(
                            f"[{self.jid}] "
                            f"ERROR ENVIANDO AL PUENTE: {e}"
                        )

                asyncio.create_task(send_message())

            except Exception as e:
                print(
                    f"[{self.jid}] "
                    f"ERROR EN .enviar_mensaje_puente: {e}"
                )

            # Obligatorio para acciones personalizadas AgentSpeak.
            yield

    async def setup(self):
        print(
            f"Starting {self.jid} agent. "
            f"Opening camera window..."
        )

        self.add_behaviour(VisionBehaviour())
        self.add_behaviour(FipaReceiver())


# ============================================================
# VISION
# ============================================================
class VisionBehaviour(CyclicBehaviour):

    async def run(self):
        success, frame = await asyncio.to_thread(
            self.agent.cap.read
        )

        # ----------------------------------------------------
        # CAMARA DESCONECTADA
        # ----------------------------------------------------
        if not success:

            if self.agent.current_camara_ok is not False:
                print(
                    f"[{self.agent.jid}] "
                    f"PYTHON -> BDI: actualizar_camara(false)"
                )

                self.agent.bdi.set_belief(
                    "actualizar_camara",
                    False,
                )

                self.agent.current_camara_ok = False

            self.agent.cap.release()

            await asyncio.sleep(RECONNECT_DELAY)

            self.agent.cap = open_camera(
                self.agent.url
            )

            return

        # ----------------------------------------------------
        # CAMARA ENCENDIDA
        # ----------------------------------------------------
        if self.agent.current_camara_ok is not True:
            print(
                f"[{self.agent.jid}] "
                f"PYTHON -> BDI: actualizar_camara(true)"
            )

            self.agent.bdi.set_belief(
                "actualizar_camara",
                True,
            )

            self.agent.current_camara_ok = True

        self.agent.frame_count += 1

        # ----------------------------------------------------
        # FUEGO
        # ----------------------------------------------------
        fire = detect_fire_red(frame)

        if fire != self.agent.current_fire:
            print(
                f"[{self.agent.jid}] "
                f"PYTHON -> BDI: actualizar_fuego({fire})"
            )

            self.agent.bdi.set_belief(
                "actualizar_fuego",
                fire,
            )

            self.agent.current_fire = fire

        # ----------------------------------------------------
        # RESULTADO DE YOLO ANTERIOR
        # ----------------------------------------------------
        task = self.agent.inference_task

        if task is not None and task.done():

            try:
                detections, score = task.result()

                self.agent.cache = detections
                self.agent.cam_state = score

                if score != self.agent.current_person_score:
                    print(
                        f"[{self.agent.jid}] "
                        f"PYTHON -> BDI: "
                        f"actualizar_persona({score})"
                    )

                    self.agent.bdi.set_belief(
                        "actualizar_persona",
                        score,
                    )

                    self.agent.current_person_score = score

            except Exception as e:
                print(
                    f"[{self.agent.jid}] "
                    f"Error en YOLO: {e}"
                )

            finally:
                self.agent.inference_task = None

        # ----------------------------------------------------
        # LANZAR NUEVA INFERENCIA
        # ----------------------------------------------------
        if (
            self.agent.frame_count % INFERENCE_EVERY_N_FRAMES == 0
            and self.agent.inference_task is None
        ):

            frame_for_inference = frame.copy()

            self.agent.inference_task = asyncio.create_task(
                asyncio.to_thread(
                    procesar_frame,
                    frame_for_inference,
                    self.agent.model,
                )
            )

        # ----------------------------------------------------
        # VISUALIZACION
        # ----------------------------------------------------
        display_frame = draw_detections(
            frame,
            self.agent.cache,
        )

        display_frame = cv2.resize(
            display_frame,
            (
                DISPLAY_WIDTH,
                DISPLAY_HEIGHT,
            ),
            interpolation=cv2.INTER_LINEAR,
        )

        cv2.imshow(
            f"Monitoreo - {self.agent.jid}",
            display_frame,
        )

        cv2.waitKey(1)

        await asyncio.sleep(0)


# ============================================================
# MAIN
# ============================================================
async def main():

    # Compartimos el modelo para evitar duplicar VRAM/RAM.
    model = MODEL

    url1 = (
        f"rtsp://{constants.USUARIOS[0]}:"
        f"{constants.CONTRASENIA}@"
        f"{constants.IPS[0]}/stream2"
    )

    url2 = (
        f"rtsp://{constants.USUARIOS[1]}:"
        f"{constants.CONTRASENIA}@"
        f"{constants.IPS[1]}/stream2"
    )

    monitor1 = BDI_agent_monitor(
        f"monitor1@{constants.IP_SERVER}",
        constants.PASS_XMPP,
        "cam_agent.asl",
        "camera_1",
        url1,
        model,
    )

    monitor2 = BDI_agent_monitor(
        f"monitor2@{constants.IP_SERVER}",
        constants.PASS_XMPP,
        "cam_agent.asl",
        "camera_2",
        url2,
        model,
    )

    await monitor1.start()
    await monitor2.start()

    try:
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("Stopping agents...")

        await monitor1.stop()
        await monitor2.stop()

        cv2.destroyAllWindows()


if __name__ == "__main__":
    asyncio.run(main())