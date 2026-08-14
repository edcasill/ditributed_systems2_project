// ============================================================
//                        CREENCIAS
// ============================================================
tarea_actual("ninguna").
camara(false).
fuego(false).
person(0).


// ============================================================
//                          DESEOS
// ============================================================
// ============================================================
// RESPUESTA DE ESTADO COMPLETO
//
// Siempre envia los tres valores:
//   fuego
//   persona
//   camara
//
// get_state usa esta respuesta directamente.
// detecta_fuego y detecta_persona tambien la utilizan,
// pero solamente modifican previamente el dato asociado
// a su tarea.
// ============================================================
+!responder_estado : fuego(Fuego) & person(Score) & camara(CamaraOk) <-
    .print("========================================");
    .print("[BDI] RESPONDER_ESTADO EJECUTADO");
    .print("[BDI] Fuego=", Fuego);
    .print("[BDI] Persona=", Score);
    .print("[BDI] Camara=", CamaraOk);
    .print("[BDI] Preparando envio al puente");
    .enviar_mensaje_puente("puente@192.168.0.202", estado(Fuego, Score, CamaraOk), "inform", "fipa-inform", "es", "sensores").


// ============================================================
//                        INTENCIONES
// ============================================================
// ============================================================
// REQUEST: GET_STATE
// Consulta el estado completo sin modificarlo.
//
// Respuesta:
// estado(Fuego, Score, CamaraOk)
// ============================================================
+bridge_request(get_state) <-
    .print("========================================");
    .print("[BDI] GET_STATE recibido");
    .print("[BDI] Consultando estado completo");
    .print("========================================");
    -bridge_request(get_state);
    !responder_estado.


// ============================================================
// REQUEST: DETECTA_FUEGO
//
// Cambia la tarea activa a detecta_fuego.
// Python solo inyectara cambios de fuego al BDI mientras
// esta sea la tarea activa.
//
// Los valores de persona y camara permanecen con su ultimo
// valor conocido.
// ============================================================
+bridge_request(detecta_fuego) <-
    .print("========================================");
    .print("[BDI] Tarea recibida: detecta_fuego");
    .print("========================================");
    -bridge_request(detecta_fuego);
    -tarea_actual(_);
    +tarea_actual("detecta_fuego");
    .print("[BDI] TAREA ACTUAL = detecta_fuego").


// ============================================================
// REQUEST: DETECTA_PERSONA
//
// Cambia la tarea activa a detecta_persona.
// Python solo inyectara cambios de persona al BDI mientras
// esta sea la tarea activa.
//
// Los valores de fuego y camara permanecen con su ultimo
// valor conocido.
// ============================================================
+bridge_request(detecta_persona) <-
    .print("========================================");
    .print("[BDI] Tarea recibida: detecta_persona");
    .print("========================================");
    -bridge_request(detecta_persona);
    -tarea_actual(_);
    +tarea_actual("detecta_persona");
    .print("[BDI] TAREA ACTUAL = detecta_persona").


// ============================================================
// REQUEST: NINGUNA
//
// Desactiva las tareas de deteccion.
// El estado almacenado no se borra.
// ============================================================
+bridge_request(set_task_none) <-
    .print("[BDI] REQUEST: ninguna tarea");
    -bridge_request(set_task_none);
    -tarea_actual(_);
    +tarea_actual("ninguna");
    .print("[BDI] TAREA ACTUAL = ninguna").


// ============================================================
// REQUEST: DEACTIVATE_ALARM
//
// Limpia fuego y mantiene los demas estados.
// ============================================================
+bridge_request(deactivate_alarm) <-
    .print("[BDI] REQUEST: deactivate_alarm");
    -bridge_request(deactivate_alarm);
    -fuego(_);
    +fuego(false);
    !responder_estado.


// ============================================================
// INFORM DEL PUENTE
// ============================================================
+bridge_notification(Content) <-
    .print("[BDI] INFORM recibido del puente: ", Content).


// ============================================================
// ACTUALIZACION DE CAMARA
//
// La camara se actualiza siempre, independientemente de la
// tarea activa, porque representa el estado del sensor.
// ============================================================
+actualizar_camara(Estado) <-
    .print("[BDI] PLAN actualizar_camara EJECUTADO. Estado=", Estado);
    -camara(_);
    +camara(Estado);
    -actualizar_camara(Estado);
    .print("[BDI] camara actualizada").


// ============================================================
// ACTUALIZACION DE FUEGO
//
// Python solo genera actualizar_fuego cuando la tarea activa
// es detecta_fuego.
// ============================================================
+actualizar_fuego(Estado) <-
    .print("[BDI] PLAN actualizar_fuego EJECUTADO. Estado=", Estado);
    -fuego(_);
    +fuego(Estado);
    -actualizar_fuego(Estado);
    .print("[BDI] fuego actualizado").


// ============================================================
// ACTUALIZACION DE PERSONA
//
// Python solo genera actualizar_persona cuando la tarea activa
// es detecta_persona.
// ============================================================
+actualizar_persona(Score) <-
    .print("[BDI] PLAN actualizar_persona EJECUTADO. Score=", Score);
    -person(_);
    +person(Score);
    -actualizar_persona(Score);
    .print("[BDI] persona actualizada").


// ============================================================
// CAMBIO DE FUEGO
//
// Solo reaccionara cuando la tarea activa sea detecta_fuego.
// ============================================================
+fuego(Fuego) : tarea_actual("detecta_fuego") <-
    .print("[BDI] Cambio de fuego detectado: ", Fuego);
    !responder_estado.


// ============================================================
// CAMBIO DE PERSONA
//
// Solo reaccionara cuando la tarea activa sea detecta_persona.
// ============================================================
+person(Score) : tarea_actual("detecta_persona") <-
    .print("[BDI] Cambio de persona detectado: ", Score);
    !responder_estado.
