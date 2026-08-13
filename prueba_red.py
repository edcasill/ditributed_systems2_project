import cv2
import numpy as np
from ultralytics import YOLO
import constants
import asyncio
import time
from spade_bdi.bdi import BDIAgent
from spade.behaviour import CyclicBehaviour
from spade.message import Message

# --- Funciones de Vision ---
def detect_fire_red(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower_red1 = np.array([0, 150, 150])
    upper_red1 = np.array([8, 255, 255])
    lower_red2 = np.array([175, 150, 150])
    upper_red2 = np.array([180, 255, 255])
    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    return cv2.countNonZero(mask1 + mask2) > 500  

def calcula_puntaje(umbral, puntaje, nariz, ojo_i, ojo_d, oreja_i, oreja_d, hombro, cadera, rodilla):
    if nariz > umbral: puntaje += 1
    if ojo_i > umbral: puntaje += 1
    if ojo_d > umbral: puntaje += 1
    if oreja_i > umbral: puntaje += 1
    if oreja_d > umbral: puntaje += 1
    if hombro > umbral: puntaje += 1
    if cadera > umbral: puntaje += 1
    if rodilla > umbral: puntaje += 1
    return puntaje

def procesar_frame(frame, model):
    fire = detect_fire_red(frame)
    results_skeleton = model(frame, verbose=False, imgsz=320)
    estado_persona = "0"
    
    for r in results_skeleton:
        if r.keypoints is None or r.boxes is None:
            continue
        for i, box in enumerate(r.boxes):
            if int(box.cls[0]) == 0:  
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                w, h = x2 - x1, y2 - y1
                kpts = r.keypoints.data[i]  
                try:
                    y_hombro, x_hombro = kpts[5][1], kpts[5][0]
                    y_cadera, x_cadera = kpts[11][1], kpts[11][0]
                    y_rodilla = kpts[13][1]
                    confianza_rodilla = kpts[13][2]  
                    nariz, ojo_i, ojo_d = kpts[0][2], kpts[1][2], kpts[2][2]
                    oreja_i, oreja_d = kpts[3][2], kpts[4][2]
                    confianza_hombro, confianza_cadera = kpts[5][2], kpts[11][2]

                    puntaje_cuerpo = calcula_puntaje(0.5, 0, nariz, ojo_i, ojo_d, oreja_i, oreja_d, confianza_hombro, confianza_cadera, confianza_rodilla)
                    estado_persona = str(puntaje_cuerpo)
                    
                    dif_y_torso, dif_x_torso = abs(y_hombro - y_cadera), abs(x_hombro - x_cadera)
                    if w > (h * 1.1) or dif_x_torso > dif_y_torso:
                        estado_txt, color = "Acostado", (255, 0, 0)
                    elif confianza_rodilla > 0.4:
                        dif_y_pierna = abs(y_cadera - y_rodilla)
                        if dif_y_pierna < 45 or (h > w and dif_y_pierna < 80):
                            estado_txt, color = "Sentado", (0, 0, 255)
                        else:
                            estado_txt, color = "De pie", (0, 255, 0)
                    else:
                        estado_txt, color = "Sentado", (0, 0, 255)
                except IndexError:
                    estado_txt, color = "Analizando...", (255, 255, 255)

                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                cv2.putText(frame, estado_txt, (int(x1), int(y1)-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    return frame, estado_persona, fire


# --- Receptor de Red en Python (Para Monitor 2) ---
class RedReceiver(CyclicBehaviour):
    async def run(self):
        msg = await self.receive(timeout=1.0)
        if msg:
            sender = str(msg.sender)
            content = msg.body
            print("=========================================================")
            print(f" [RED PYTHON] ¡RECIBI DATOS EXTERNOS DE {sender}!")
            print(f" -> Puntaje reportado por la otra cámara: {content}")
            print("=========================================================")
        await asyncio.sleep(0.05)


# --- Comportamiento de Visión y Envío (Para Monitor 1) ---
class VisionBehaviour(CyclicBehaviour):
    async def run(self):
        success, frame = await asyncio.to_thread(self.agent.cap.read)

        if not success:
            await asyncio.sleep(3)
            return

        self.agent.frame_count += 1

        if self.agent.frame_count % 5 == 0:
            frame, estado_persona, fire = await asyncio.to_thread(
                procesar_frame, frame, self.agent.model)

            if not hasattr(self.agent, 'current_belief'):
                self.agent.current_belief = "0"
            if not hasattr(self.agent, 'last_update_time'):
                self.agent.last_update_time = 0
            
            tiempo_actual = time.time()

            # Si YOLO detecta un cambio, Python mismo envía el mensaje FIPA por la red XMPP
            if self.agent.current_belief != estado_persona:
                if (tiempo_actual - self.agent.last_update_time) > 1.5:
                    print(f"\n[{self.agent.jid}] Cambio detectado: {self.agent.current_belief} -> {estado_persona}")
                    
                    # ENVIAR DIRECTAMENTE DESDE PYTHON A MONITOR 2
                    msg = Message(to=f"monitor2@{constants.IP_SERVER}")
                    msg.body = str(estado_persona)
                    msg.set_metadata("performative", "inform")
                    msg.set_metadata("ontology", "monitoreo_camaras")
                    # asyncio.create_task(self.agent.client.send(msg))
                    self.agent.client.send(msg)
                    print(f"[{self.agent.jid} ---> RED] Mensaje enviado a Monitor 2 con puntaje: {estado_persona}")

                    self.agent.current_belief = estado_persona
                    self.agent.last_update_time = tiempo_actual

        frame_resized = cv2.resize(frame, (700, 420))
        cv2.imshow(f"Prueba Red - {self.agent.jid}", frame_resized)
        cv2.waitKey(1)
        await asyncio.sleep(0.05)


class BDI_agent_monitor(BDIAgent):
    def __init__(self, jid, passw, behaviour_asl, is_emitter, url, model):
        super().__init__(jid, passw, behaviour_asl, verify_security=False)
        self.is_emitter = is_emitter
        self.cap = cv2.VideoCapture(url)
        self.model = model
        self.frame_count = 0

    async def setup(self):
        print(f"[{self.jid}] Encendiendo motores...")
        if self.is_emitter:
            self.add_behaviour(VisionBehaviour())
        else:
            self.add_behaviour(RedReceiver())


async def main():
    print("Iniciando prueba de red profunda con Python puro...\n")
    model1 = YOLO('yolov8n-pose.pt')
    model2 = YOLO('yolov8n-pose.pt')

    url1 = f"rtsp://{constants.USUARIOS[0]}:{constants.CONTRASENIA}@{constants.IPS[0]}/stream2"
    url2 = f"rtsp://{constants.USUARIOS[1]}:{constants.CONTRASENIA}@{constants.IPS[1]}/stream2"

    # Monitor 2 es RECEPTOR (is_emitter=False), escucha con RedReceiver
    monitor2 = BDI_agent_monitor(
        f"monitor2@{constants.IP_SERVER}", constants.PASS_XMPP, "receptor.asl", False, url2, model2
    )
    await monitor2.start()
    
    # Monitor 1 es EMISOR (is_emitter=True), procesa cámara y envía mensajes
    monitor1 = BDI_agent_monitor(
        f"monitor1@{constants.IP_SERVER}", constants.PASS_XMPP, "emisor.asl", True, url1, model1
    )
    await monitor1.start()

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nApagando cámaras de prueba...")
        await monitor1.stop()
        await monitor2.stop()

if __name__ == "__main__":
    asyncio.run(main())