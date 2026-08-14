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
from collections import deque


# ============================================================
# CONFIGURACION DE DETECCION DE FUEGO
# ============================================================
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
def detect_fire_candidate(frame):
    """
    Detecta un candidato de fuego en UN frame.

    Combina:
      - HSV para rojo/naranja/amarillo.
      - BGR para exigir predominio de rojo y reducir rosa.
      - brillo/saturacion para reducir cafe y colores oscuros.

    La estabilidad temporal se maneja en VisionBehaviour.
    """
    small = cv2.resize(frame, constants.FIRE_RESOLUTION, interpolation=cv2.INTER_AREA,)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)

    # Colores calidos: rojo -> naranja -> amarillo.
    lower_warm = np.array([0, 100, 140])
    upper_warm = np.array([35, 255, 255])
    warm_mask = cv2.inRange(hsv, lower_warm, upper_warm)

    # OpenCV usa BGR.
    b, g, r = cv2.split(small)

    # Filtros para reducir rosa y cafe:
    # - rosa: normalmente tiene demasiado componente azul.
    # - cafe: suele tener menor brillo y menor dominancia roja.
    rgb_fire = ((r > 150) & (r >= g * 1.05) & (g >= b * 1.15) & (r >= b * 1.30))
    rgb_mask = rgb_fire.astype(np.uint8) * 255
    mask = cv2.bitwise_and(warm_mask, rgb_mask)

    # Limpieza de ruido.
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    fire_pixels = cv2.countNonZero(mask)

    if fire_pixels < constants.FIRE_MIN_PIXELS:
        return False

    # Exigir una region conectada suficiente.
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    max_area = 0.0

    for contour in contours:
        max_area = max(max_area, cv2.contourArea(contour))

    return max_area >= 20


# ============================================================
# PUNTAJE CORPORAL
# ============================================================
def calcula_puntaje(umbral_deteccion, nariz, ojo_i, ojo_d, oreja_i, oreja_d,
                    confianza_hombro, confianza_cadera, confianza_rodilla):
    valores = (nariz, ojo_i, ojo_d, oreja_i, oreja_d,
               confianza_hombro, confianza_cadera, confianza_rodilla,)
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
        results_skeleton = model(frame,
                                 verbose=False,
                                 imgsz=constants.YOLO_IMGSZ,
                                 conf=constants.YOLO_CONF,
                                 device=YOLO_DEVICE,
                                 half=YOLO_HALF)

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

                score = calcula_puntaje(0.5,
                                        nariz,
                                        ojo_i,
                                        ojo_d,
                                        oreja_i,
                                        oreja_d,
                                        confianza_hombro,
                                        confianza_cadera,
                                        confianza_rodilla,)

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

            last_box.append((int(x1), int(y1), int(x2), int(y2), estado, color,))

    if not last_box:
        score = 0

    return last_box, str(score)


def draw_detections(frame, detections):
    for x1, y1, x2, y2, estado, color in detections:
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, estado, (x1, max(y1 - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2,)

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
                    print(f"[{self.agent.jid}] REQUEST -> "
                          f"bridge_request(get_state)")
                    self.agent.bdi.set_belief("bridge_request", "get_state",)
                elif content == "detecta_fuego":
                    self.agent.bdi.set_belief("bridge_request", "detecta_fuego",)
                elif content == "detecta_persona":
                    self.agent.bdi.set_belief("bridge_request", "detecta_persona",)
                elif content == "set_task_none":
                    self.agent.bdi.set_belief("bridge_request", "set_task_none",)
                elif content == "deactivate_alarm":
                    self.agent.bdi.set_belief("bridge_request", "deactivate_alarm",)
                else:
                    print(f"[{self.agent.jid}] "
                          f"Comando desconocido: {content}")
            elif performative == "inform":
                self.agent.bdi.set_belief("bridge_notification", content,)

        await asyncio.sleep(0)


# ============================================================
# AGENTE MONITOR
# ============================================================
class BDI_agent_monitor(BDIAgent):
    def __init__(self, jid, passw, behaviour, cam_id, url, model):
        super().__init__(jid, passw, behaviour, verify_security=False,)

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

        # Estado temporal de fuego.
        self.fire_positive_streak = 0
        self.fire_negative_streak = 0
        self.confirmed_fire = False

        # Una sola inferencia pendiente por monitor.
        self.inference_task = None

    # ========================================================
    # ACCION PERSONALIZADA AGENTSPEAK -> PUENTE
    # ========================================================
    def add_custom_actions(self, actions):
        @actions.add(".enviar_mensaje_puente", 6)
        def _enviar_mensaje_puente(agent, term, intention):
            try:
                receiver = agentspeak.grounded(term.args[0], intention.scope,)
                content = agentspeak.grounded(term.args[1], intention.scope,)
                performative = agentspeak.grounded(term.args[2], intention.scope,)
                protocol = agentspeak.grounded(term.args[3], intention.scope,)
                language = agentspeak.grounded(term.args[4], intention.scope,)
                ontology = agentspeak.grounded(term.args[5], intention.scope,)

                receiver_str = str(receiver).strip('"').strip("'")
                content_str = str(content)
                performative_str = (str(performative).strip('"').strip("'"))
                protocol_str = (str(protocol).strip('"').strip("'"))
                language_str = (str(language).strip('"').strip("'"))
                ontology_str = (str(ontology).strip('"').strip("'"))

                msg = Message(to=receiver_str)
                msg.body = content_str

                msg.set_metadata("performative", performative_str,)
                msg.set_metadata("protocol", protocol_str,)
                msg.set_metadata("language", language_str,)
                msg.set_metadata("ontology", ontology_str,)

                # "agent" es el runtime interno de AgentSpeak.
                # Para evitar el AttributeError de agent.jid/client,
                # usamos directamente "self", que es el BDI_agent_monitor
                # real de SPADE que contiene esta accion.
                print(f"[{self.jid}] ENVIANDO AL PUENTE -> to={receiver_str} | performative={performative_str} | "
                      f"body={content_str}")

                async def send_message():
                    try:
                        await self.bdi.send(msg)
                        print(f"[{self.jid}] MENSAJE ENVIADO CORRECTAMENTE AL PUENTE")
                    except Exception as e:
                        print(f"[{self.jid}] ERROR ENVIANDO AL PUENTE: {e}")

                asyncio.create_task(send_message())

            except Exception as e:
                print(f"[{self.jid}] "
                      f"ERROR EN .enviar_mensaje_puente: {e}")

            # Obligatorio para acciones personalizadas AgentSpeak.
            yield

    async def setup(self):
        print(f"Starting {self.jid} agent. Opening camera window...")
        self.add_behaviour(VisionBehaviour())
        self.add_behaviour(FipaReceiver())


# ============================================================
# VISION
# ============================================================
class VisionBehaviour(CyclicBehaviour):
    async def run(self):
        success, frame = await asyncio.to_thread(self.agent.cap.read)
        # ----------------------------------------------------
        # CAMARA DESCONECTADA
        # ----------------------------------------------------
        if not success:
            if self.agent.current_camara_ok is not False:
                print(f"[{self.agent.jid}] PYTHON -> BDI: actualizar_camara(false)")
                self.agent.bdi.set_belief("actualizar_camara", False,)
                self.agent.current_camara_ok = False

            self.agent.cap.release()
            await asyncio.sleep(constants.RECONNECT_DELAY)
            self.agent.cap = open_camera(self.agent.url)

            return

        # ----------------------------------------------------
        # CAMARA ENCENDIDA
        # ----------------------------------------------------
        if self.agent.current_camara_ok is not True:
            print(f"[{self.agent.jid}] PYTHON -> BDI: actualizar_camara(true)")
            self.agent.bdi.set_belief("actualizar_camara", True,)
            self.agent.current_camara_ok = True

        self.agent.frame_count += 1

        # ----------------------------------------------------
        # FUEGO
        # ----------------------------------------------------
        fire_candidate = detect_fire_candidate(frame)

        if fire_candidate:
            self.agent.fire_positive_streak += 1
            self.agent.fire_negative_streak = 0
        else:
            self.agent.fire_negative_streak += 1
            self.agent.fire_positive_streak = 0

        # Activar solo despues de varios frames consecutivos.
        if (not self.agent.confirmed_fire and self.agent.fire_positive_streak >= constants.FIRE_CONFIRM_FRAMES):
            self.agent.confirmed_fire = True

        # Desactivar con histeresis: exigimos mas frames sin fuego.
        elif (self.agent.confirmed_fire and self.agent.fire_negative_streak >= constants.FIRE_CLEAR_FRAMES):
            self.agent.confirmed_fire = False

        fire = self.agent.confirmed_fire

        if fire != self.agent.current_fire:
            print(f"[{self.agent.jid}] "
                  f"FUEGO: candidato={fire_candidate} | "
                  f"confirmado={fire} | "
                  f"positivos={self.agent.fire_positive_streak} | "
                  f"negativos={self.agent.fire_negative_streak}")

            print(f"[{self.agent.jid}] PYTHON -> BDI: actualizar_fuego({fire})")

            self.agent.bdi.set_belief("actualizar_fuego", fire)
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
                    print(f"[{self.agent.jid}] PYTHON -> BDI: actualizar_persona({score})")
                    self.agent.bdi.set_belief("actualizar_persona", score)
                    self.agent.current_person_score = score

            except Exception as e:
                print(f"[{self.agent.jid}] Error en YOLO: {e}")
            finally:
                self.agent.inference_task = None

        # ----------------------------------------------------
        # LANZAR NUEVA INFERENCIA
        # ----------------------------------------------------
        if (self.agent.frame_count % constants.INFERENCE_EVERY_N_FRAMES == 0 and self.agent.inference_task is None):
            frame_for_inference = frame.copy()
            self.agent.inference_task = asyncio.create_task(asyncio.to_thread(procesar_frame,
                                                                              frame_for_inference,
                                                                              self.agent.model,))

        # ----------------------------------------------------
        # VISUALIZACION
        # ----------------------------------------------------
        display_frame = draw_detections(frame, self.agent.cache,)
        display_frame = cv2.resize(display_frame,
                                   (constants.DISPLAY_WIDTH, constants.DISPLAY_HEIGHT),
                                   interpolation=cv2.INTER_LINEAR,)

        cv2.imshow(f"Monitoreo - {self.agent.jid}", display_frame,)
        cv2.waitKey(1)

        await asyncio.sleep(0)


# ============================================================
# MAIN
# ============================================================
async def main():
    # Compartimos el modelo para evitar duplicar VRAM/RAM.
    model = MODEL

    url1 = (f"rtsp://{constants.USUARIOS[0]}:{constants.CONTRASENIA}@{constants.IPS[0]}/stream2")
    url2 = (f"rtsp://{constants.USUARIOS[1]}:{constants.CONTRASENIA}@{constants.IPS[1]}/stream2")

    monitor1 = BDI_agent_monitor(f"monitor1@{constants.IP_SERVER}", constants.PASS_XMPP, "cam_agent.asl",
                                 "camera_1", url1, model,)
    monitor2 = BDI_agent_monitor(f"monitor2@{constants.IP_SERVER}", constants.PASS_XMPP, "cam_agent.asl",
                                 "camera_2", url2, model)

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
