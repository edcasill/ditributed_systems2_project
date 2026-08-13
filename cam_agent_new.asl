// ============================================
// Creencias iniciales (Beliefs)
// ============================================
msg_performative("request").
msg_protocol("fipa-request").
msg_language("es").
msg_ontology("sensores").

// Estado interno inicial (usando átomos en minúsculas)
tarea_actual(ninguna).

// ============================================
// Metas e Inicio
// ============================================
!iniciar_agente.

+!iniciar_agente <- 
    .print("Agente iniciado. Tarea actual: ninguna. Esperando ordenes de Java...").

// ============================================
// TAREAS AUTOMÁTICAS (Monitoreo enfocado)
// ============================================

+person(Score) : tarea_actual(person) <-
    ?msg_performative(Perf); ?msg_protocol(Prot); ?msg_language(Lang); ?msg_ontology(Ont);
    .enviar_mensaje_java("mente@192.168.0.202", Score, Perf, Prot, Lang, Ont).

+fire : tarea_actual(fire) <-
    ?msg_performative(Perf); ?msg_protocol(Prot); ?msg_language(Lang); ?msg_ontology(Ont);
    .print("[TAREA FUEGO] ¡Emergencia detectada! Avisando a Java.");
    .enviar_mensaje_java("mente@192.168.0.202", "emergency", Perf, Prot, Lang, Ont).

// Silenciadores Estrictos
+person(_) : not tarea_actual(person) <- true.
+fire : not tarea_actual(fire) <- true.

// ============================================
// REACCIÓN A ORDENES DE JAVA (Mente)
// ============================================

// 1. Solicitud explícita de estado (Envía el JSON) (con thread)
+java_request(get_state, Thread) <-
    -java_request(get_state, Thread); // Consume la orden
    .print(">>> Java solicita reporte de estado con thread: ", Thread, " <<<");
    !responder_estado(Thread).

// Órdenes SET_TASK con thread
+java_request(set_task_fire, Thread) <-
    -java_request(set_task_fire, Thread);
    -+tarea_actual(fire);
    .print(">>> Cambiando tarea a: FIRE (thread: ", Thread, ") <<<").

+java_request(set_task_person, Thread) <-
    -java_request(set_task_person, Thread);
    -+tarea_actual(person);
    .print(">>> Cambiando tarea a: PERSON (thread: ", Thread, ") <<<").

+java_request(set_task_none, Thread) <-
    -java_request(set_task_none, Thread);
    -+tarea_actual(ninguna);
    .print(">>> Cambiando tarea a: NINGUNA (thread: ", Thread, ") <<<").

// ============================================
// META: !responder_estado (Evalúa y Envía el JSON)
// ============================================

+!responder_estado(Thread) : fire & person(Score) & camara(EstatusCam) <-
    ?msg_performative(Perf); ?msg_protocol(Prot); ?msg_language(Lang); ?msg_ontology(Ont);
    .enviar_mensaje_java_thread("mente@192.168.0.202", estado(true, Score, EstatusCam), Perf, Prot, Lang, Ont, Thread).

+!responder_estado(Thread) : fire & not person(_) & camara(EstatusCam) <-
    ?msg_performative(Perf); ?msg_protocol(Prot); ?msg_language(Lang); ?msg_ontology(Ont);
    .enviar_mensaje_java_thread("mente@192.168.0.202", estado(true, 0, EstatusCam), Perf, Prot, Lang, Ont, Thread).

+!responder_estado(Thread) : not fire & person(Score) & camara(EstatusCam) <-
    ?msg_performative(Perf); ?msg_protocol(Prot); ?msg_language(Lang); ?msg_ontology(Ont);
    .enviar_mensaje_java_thread("mente@192.168.0.202", estado(false, Score, EstatusCam), Perf, Prot, Lang, Ont, Thread).

+!responder_estado(Thread) : not fire & not person(_) & camara(EstatusCam) <-
    ?msg_performative(Perf); ?msg_protocol(Prot); ?msg_language(Lang); ?msg_ontology(Ont);
    .enviar_mensaje_java_thread("mente@192.168.0.202", estado(false, 0, EstatusCam), Perf, Prot, Lang, Ont, Thread).