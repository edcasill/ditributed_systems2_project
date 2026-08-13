// ============================================
// Creencias iniciales (Beliefs)
// ============================================
msg_performative("request").
msg_protocol("fipa-request").
msg_language("es").
msg_ontology("sensores").

tarea_actual("ninguna").
// Valores iniciales seguros para que nunca colapse
camara(true). 
fuego(false).
person(0).

// ============================================
// Metas e Inicio
// ============================================
!iniciar_agente.

+!iniciar_agente <- 
    .print("Agente iniciado. Tarea actual: ninguna. Esperando ordenes de Java...").

// ============================================
// TAREAS AUTOMÁTICAS (Monitoreo enfocado)
// ============================================

+person(Score) : tarea_actual("person") <-
    ?msg_performative(Perf); ?msg_protocol(Prot); ?msg_language(Lang); ?msg_ontology(Ont);
    .enviar_mensaje_java("mente@192.168.0.202", Score, Perf, Prot, Lang, Ont).

+fuego(true) : tarea_actual("fire") <-
    ?msg_performative(Perf); ?msg_protocol(Prot); ?msg_language(Lang); ?msg_ontology(Ont);
    .print("[TAREA FUEGO] ¡Emergencia detectada! Avisando a Java.");
    .enviar_mensaje_java("mente@192.168.0.202", "emergency", Perf, Prot, Lang, Ont).

// Silenciadores Estrictos
+person(_) : not tarea_actual("person") <- true.
+fuego(true) : not tarea_actual("fire") <- true.

// ============================================
// REACCIÓN A ORDENES DE JAVA (Mente)
// ============================================

+cmd_get_state <-
    -cmd_get_state; 
    .print(">>> Java solicita reporte de estado (GET_STATE) <<<");
    !responder_estado.

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
    .print(">>> Cambiando tarea a: NINGUNA (Silencio total) <<<").

// ============================================
// META: !responder_estado (Evalúa y Envía el JSON)
// ============================================

+!responder_estado : fuego(Fuego) & person(Score) & camara(EstatusCam) <-
    // IMPRESIÓN DE DEPURACIÓN AÑADIDA: Muestra la memoria real de AgentSpeak
    .print(">>> [MEMORIA INTERNA ASL] Preparando envio -> Fuego: ", Fuego, " | Persona: ", Score, " | Camara: ", EstatusCam, " <<<");
    ?msg_performative(Perf); ?msg_protocol(Prot); ?msg_language(Lang); ?msg_ontology(Ont);
    .enviar_mensaje_java("mente@192.168.0.202", estado(Fuego, Score, EstatusCam), Perf, Prot, Lang, Ont).

// ============================================
// ATRAPA-ERRORES PARA MENSAJES BDI DE LA RED
// ============================================
+!person_state(State) <-
    .print(">>> Ignorando mensaje atrasado de la red: ", State, " <<<").

// ============================================
// ACTUALIZADORES SEGUROS DE CREENCIAS
// ============================================
// Usamos el comodín (_) para forzar el borrado de cualquier valor viejo antes de guardar el nuevo

+actualizar_persona(Score) <-
    -person(_);
    +person(Score);
    -actualizar_persona(Score).
    
+actualizar_fuego(Estado) <-
    -fuego(_);
    +fuego(Estado);
    -actualizar_fuego(Estado).
    
+actualizar_camara(Estado) <-
    -camara(_);
    +camara(Estado);
    -actualizar_camara(Estado).