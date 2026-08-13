// ==========================================
// METAS Y COMUNICACIÓN EN RED
// ==========================================
!iniciar.

+!iniciar <- 
    .print(">>> EMISOR (Monitor 1) INICIADO. Procesando camara... <<<").

// Usamos un comando directo para evitar problemas de sincronización de memoria
+enviar_datos(Score) <-
    -enviar_datos(Score); // Se auto-elimina igual que java_command
    .print(">>> [MONITOR 1 - YOLO] Cambio detectado: persona(", Score, "). Avisando a Monitor 2... <<<");
    .send("monitor2@192.168.0.202", tell, persona_monitor1(Score)).