// ============================================
// CREENCIAS INICIALES
// ============================================
msg_performative("request").
msg_protocol("fipa-request").
msg_language("es").
msg_ontology("sensores").

tarea_actual("ninguna").

// Estado actual de la cámara y del entorno
camara(false).
fuego(false).
person(0).

// ============================================
// INICIO
// ============================================
!iniciar_agente.

+!iniciar_agente <-
    .print("Agente iniciado. Esperando datos de monitoreo y ordenes del puente...").

// ============================================
// ACTUALIZACION DE CREENCIAS DESDE PYTHON
// ============================================
// Python mantiene una sola creencia por estado y elimina el valor anterior.

+actualizar_persona(Score) <-
    -person(_);
    +person(Score);
    -actualizar_persona(Score);
    !reportar_estado.

+actualizar_fuego(Estado) <-
    -fuego(_);
    +fuego(Estado);
    -actualizar_fuego(Estado);
    !reportar_estado.

+actualizar_camara(Estado) <-
    -camara(_);
    +camara(Estado);
    -actualizar_camara(Estado);
    !reportar_estado.

// ============================================
// REPORTE AL AGENTE PUENTE
// ============================================
// La informacion enviada es siempre la misma estructura:
// estado(fuego, puntaje_persona, camara_ok)

+!reportar_estado : fuego(Fuego) & person(Score) & camara(CamaraOk) <-
    .print("[PUENTE] Estado -> fuego: ", Fuego,
           " | persona: ", Score,
           " | camara: ", CamaraOk);
    .send("puente@192.168.0.202", achieve, estado(Fuego, Score, CamaraOk)).

// ============================================
// ORDENES RECIBIDAS DEL AGENTE PUENTE
// ============================================

+cmd_get_state <-
    -cmd_get_state;
    .print(">>> El puente solicita el estado actual <<<");
    !reportar_estado.

+cmd_task_fire <-
    -cmd_task_fire;
    -+tarea_actual("fire");
    .print(">>> Cambiando tarea a: FIRE <<<").

+cmd_task_person <-
    -cmd_task_person;
    -+tarea_actual("person");
    .print(">>> Cambiando tarea a: PERSON <<<").

+cmd_task_none <-
    -cmd_task_none;
    -+tarea_actual("ninguna");
    .print(">>> Cambiando tarea a: NINGUNA <<<").

+cmd_deactivate_alarm <-
    -cmd_deactivate_alarm;
    .print(">>> Orden del puente: desactivar alarma <<<");
    -fuego(true);
    +fuego(false);
    !reportar_estado.

// El puente puede avisar informacion adicional sin alterar el estado local.
+bridge_notification(Content) <-
    .print(">>> Notificacion del puente: ", Content, " <<<").

// ============================================
// COMPATIBILIDAD CON MENSAJES ANTIGUOS
// ============================================
+person_state(State) <-
    .print(">>> Ignorando mensaje atrasado: person_state(", State, ") <<<").
