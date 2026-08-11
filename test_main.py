import cv2
import numpy as np
from ultralytics import YOLO
import requests
import time
import constants
import asyncio
from spade_bdi.bdi import BDIAgent
from spade.behaviour import CyclicBehaviour

#[cite: 7]
def enviar_a_api(estado, camara_id):
    try:
        datos_camara = {"actividad": estado,
                        "camara": camara_id}
        # Asegurate de tener tu API corriendo o comenta esta funcion si no quieres errores de conexion en la prueba
        response = requests.post(constants.API_URL, json=datos_camara, timeout=2)
        print(f"API: [Cámara {camara_id}] Enviado -> {estado}")
        print(f"Estado: ", response.status_code)
        print(f"Respuesta de java: ", response.json())

    except Exception as e:
        print(f"Error API [Cámara {camara_id}]: {e}")

#[cite: 7]
def detectar_fire_rojo(frame):
    """
    Esta funcion es una abstraccion de una deteccion de fire por medio del color rojo,
    si hay suficientes pixeles rojos, se considera que hay fire en el lugar
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    lower_red1 = np.array([0, 120, 70])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, 120, 70])
    upper_red2 = np.array([180, 255, 255])

    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask = mask1 + mask2

    pixeles_rojos = cv2.countNonZero(mask)
    return pixeles_rojos > 500  

#[cite: 7]
def procesar_frame(frame, model, last_box_cache, cam_state, last_sent, camara_id, COOLDOWN_API):
    fire = detectar_fire_rojo(frame)
    if fire:
        print("PELIGRO, HAY fire EN EL LUGAR")

    results_skeleton = model(frame, verbose=False, imgsz=320)
    last_box = []

    for r in results_skeleton:
        if r.keypoints is None or r.boxes is None:
            continue

        for i, box in enumerate(r.boxes):
            if int(box.cls[0]) == 0:  
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
                    confianza_rodilla = kpts[13][2]  

                    dif_y_torso = abs(y_hombro - y_cadera)  
                    dif_x_torso = abs(x_hombro - x_cadera)

                    if w > (h * 1.1):
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

                last_box.append((int(x1), int(y1), int(x2), int(y2), estado, color))

                tiempo_actual = time.time()
                if estado != cam_state or (tiempo_actual - last_sent > COOLDOWN_API):
                    cam_state = estado
                    last_sent = tiempo_actual

    datos_a_dibujar = last_box if last_box else last_box_cache

    for x1, y1, x2, y2, estado, color in datos_a_dibujar:
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, estado, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    return frame, datos_a_dibujar, cam_state, last_sent, fire

#[cite: 7]
class BDI_agent_monitor(BDIAgent):
    def __init__(self, jid, passw, asl_file, cam_id, url, model):
        super().__init__(jid, passw, asl_file)  

        self.cam_id = cam_id
        # url ahora puede ser un numero entero (0, 1, 2) para webcams
        self.cap = cv2.VideoCapture(url) 
        self.model = model

        self.frame_count = 0
        self.cam_state = None
        self.cache = []
        self.last_sent = 0

    async def setup(self):
        print(f"Starting {self.jid} agent. Opening camera window...")
        self.add_behaviour(VisionBehaviour())

#[cite: 7]
class VisionBehaviour(CyclicBehaviour):
    async def run(self):
        success, frame = self.agent.cap.read()

        if not success:
            print(f"Error al leer la cámara en {self.agent.jid}. Reintentando...")
            await asyncio.sleep(3)
            return

        self.agent.frame_count += 1

        if self.agent.frame_count % 5 == 0:
            frame, self.agent.cache, self.agent.cam_state, self.agent.last_sent, fire = procesar_frame(
                frame,
                self.agent.model,
                self.agent.cache,
                self.agent.cam_state,
                self.agent.last_sent,
                self.agent.cam_id,
                5.0)

            # Implementación optimizada de creencias para evitar "Belief Stacking"
            if fire:
                self.agent.bdi.set_belief("fire")
            else:
                self.agent.bdi.remove_belief("fire")
                if self.agent.cam_state:
                    if not hasattr(self.agent, 'current_belief'):
                        self.agent.current_belief = None
                    
                    if self.agent.current_belief != self.agent.cam_state:
                        if self.agent.current_belief:
                            self.agent.bdi.remove_belief(f"person(\"{self.agent.current_belief}\")")
                        
                        self.agent.bdi.set_belief(f"person(\"{self.agent.cam_state}\")")
                        self.agent.current_belief = self.agent.cam_state

        else:
            for x1, y1, x2, y2, estado, color in self.agent.cache:
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, estado, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Volteo horizontal tipo espejo (opcional, suele ser útil para cámaras web)
        frame_espejo = cv2.flip(frame, 1) 
        
        frame_resized = cv2.resize(frame_espejo, (700, 420))
        cv2.imshow(f"Monitoreo - {self.agent.jid}", frame_resized)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            pass  

        await asyncio.sleep(0.01)


async def main():
    model = YOLO('yolov8n-pose.pt')

    # Para pruebas locales, usamos el índice 0 en lugar de las URLs de constants
    url_camara_laptop = 0 
    
    # Si conectas una segunda cámara USB, usarías este:
    # url_camara_usb = 1 

    monitor1 = BDI_agent_monitor("monitor1@localhost", "p@tr0ll", "cam_agent.asl", "camera_1", url_camara_laptop, model)
    await monitor1.start()
    
    # Comentado para evitar errores de hardware al leer la misma cámara dos veces:
    # monitor2 = BDI_agent_monitor("monitor2@localhost", "p@tr0ll", "cam_agent.asl", "camera_2", url_camara_usb, model)
    # await monitor2.start()

    try:
        print("Presiona Ctrl+C en la terminal para detener la prueba.")
        while True:
            await asyncio.sleep(2)
    except KeyboardInterrupt:
        print("\nDeteniendo sistema de monitoreo de prueba...")
        await monitor1.stop()
        # await monitor2.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    asyncio.run(main())