USUARIOS = ["Camara_1", "Camara_2"]
IPS = ["192.168.0.87", "192.168.0.158", "192.168.68.128", "192.168.68.130"]
CONTRASENIA = "Cinvestav.101"
IP_SERVER = "192.168.0.202"
PASS_XMPP = "p@tr0ll"
frame_count = 5  # procesa cada 5 frames
UMBRAL_SENTADO = 0.4
API_URL = "http://18.222.227.108:8000/api/camera"

# ============================================================
# CONFIGURACION DE RENDIMIENTO
# ============================================================
DISPLAY_WIDTH = 700
DISPLAY_HEIGHT = 420
INFERENCE_EVERY_N_FRAMES = 5
YOLO_IMGSZ = 320
YOLO_CONF = 0.25
RECONNECT_DELAY = 3.0

# ============================================================
# CONFIGURACION DE DETECCION DE FUEGO
# ============================================================
FIRE_RESOLUTION = (320, 180)

# Confirmacion temporal: evita activar fuego por un solo frame.
FIRE_CONFIRM_FRAMES = 3

# Histeresis: se requieren mas frames sin fuego para apagarlo.
FIRE_CLEAR_FRAMES = 5

# Umbral bajo para permitir deteccion a mayor distancia.
FIRE_MIN_PIXELS = 45