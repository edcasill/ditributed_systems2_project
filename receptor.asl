// ==========================================
// CREENCIAS INICIALES Y ACTUALIZADORES SEGUROS
// ==========================================
person(0).
fuego(false).
camara(true).

+actualizar_persona(Score) <-
    -person(_);
    +person(Score);
    -actualizar_persona(Score).

// ==========================================
// METAS Y REACCIÓN A LA RED
// ==========================================
!iniciar.

+!iniciar <- 
    .print(">>> RECEPTOR (Monitor 2) INICIADO. Escuchando a la red... <<<").

// Reacción de RED: Usamos la variable 'Emisor' para atrapar cualquier JID completo
+persona_monitor1(Score_M1)[source(Emisor)] <-
    .print("=========================================================");
    .print(" [RED] ¡RECIBI DATOS EXTERNOS! ");
    .print(" -> El agente ", Emisor, " ve a una persona con puntaje: ", Score_M1);
    
    // Consulto mi propia memoria para ver qué está viendo mi cámara
    ?person(MiScore);
    .print(" -> Mi propia camara ve a una persona con puntaje: ", MiScore);
    .print("=========================================================").