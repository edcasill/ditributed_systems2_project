// ============================================================
// CREENCIAS INICIALES
// ============================================================

tarea_actual("ninguna").

camara(false).
fuego(false).
person(0).


// ============================================================
// RECEPCION DE REQUEST DEL PUENTE
// ============================================================

+bridge_request(get_state) <-
    .print("========================================");
    .print("[BDI] PLAN get_state EJECUTADO");
    .print("[BDI] Obteniendo estado actual");
    .print("================================");
    -bridge_request(get_state);
    !responder_estado.

+bridge_request(detecta_fuego) <-
    .print("[BDI] PLAN detecta_fuego EJECUTADO");
    .print("[BDI] >>> REQUEST detecta_fuego <<<");
    -bridge_request(detecta_fuego);
    -tarea_actual(_);
    +tarea_actual("detecta_fuego");
    .print("[BDI] TAREA ACTUAL = detecta_fuego").

+bridge_request(detecta_persona) <-
    .print("[BDI] PLAN detecta_persona EJECUTADO");
    .print("[BDI] >>> REQUEST detecta_persona <<<");
    -bridge_request(detecta_persona);
    -tarea_actual(_);
    +tarea_actual("detecta_persona");
    .print("[BDI] TAREA ACTUAL = detecta_persona").

+bridge_request(set_task_none) <-
    .print("[BDI] PLAN set_task_none EJECUTADO");
    -bridge_request(set_task_none);
    -tarea_actual(_);
    +tarea_actual("ninguna").

+bridge_request(deactivate_alarm) <-
    .print("[BDI] PLAN deactivate_alarm EJECUTADO");
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
// ACTUALIZACION DEL ESTADO DE CAMARA
// ============================================================

+actualizar_camara(Estado) <-
    .print(
        "[BDI] PLAN actualizar_camara EJECUTADO. Estado=",
        Estado
    );
    -camara(_);
    +camara(Estado);
    -actualizar_camara(Estado);
    .print("[BDI] camara actualizada").

// ============================================================
// ACTUALIZACION DEL ESTADO DE FUEGO
// ============================================================

+actualizar_fuego(Estado) <-
    .print(
        "[BDI] PLAN actualizar_fuego EJECUTADO. Estado=",
        Estado
    );
    -fuego(_);
    +fuego(Estado);
    -actualizar_fuego(Estado);
    .print("[BDI] fuego actualizado").

// ============================================================
// ACTUALIZACION DEL PUNTAJE DE PERSONA
// ============================================================

+actualizar_persona(Score) <-
    .print(
        "[BDI] PLAN actualizar_persona EJECUTADO. Score=",
        Score
    );
    -person(_);
    +person(Score);
    -actualizar_persona(Score);
    .print("[BDI] persona actualizada").

// ============================================================
// RESPONDER ESTADO AL PUENTE
// ============================================================

+!responder_estado : fuego(Fuego) & person(Score) & camara(CamaraOk) <-
    .print("========================================");
    .print("[BDI] RESPONDER_ESTADO EJECUTADO");
    .print("[BDI] Fuego=", Fuego);
    .print("[BDI] Persona=", Score);
    .print("[BDI] Camara=", CamaraOk);
    .print("[BDI] Preparando envio al puente");

    .enviar_mensaje_puente(
        "puente@192.168.0.202",
        estado(Fuego, Score, CamaraOk),
        "inform",
        "fipa-inform",
        "es",
        "sensores"
    ).


// ============================================================
// REPORTES ESPONTANEOS DE CAMBIOS
// ============================================================

+fuego(true) : tarea_actual("detecta_fuego") <-
    .print("[BDI] Reportando fuego detectado");
    !responder_estado.

+person(Score) : tarea_actual("detecta_persona") <-
    .print("[BDI] Reportando cambio de puntaje: ", Score);
    !responder_estado.


// ============================================================
// CONSULTA QUERY-REF DEL PUENTE
// ============================================================

+bridge_query(get_state) <-
    .print("[BDI] QUERY-REF get_state recibido");
    -bridge_query(get_state);
    !responder_estado.
