// This is an example of how to do BDI programming

// =================
//     BELIEFS
// =================
// The agent does not know what is watching
person(unknown).


// =================
//     DESIRES
// =================
// When the agent born, it has the desire (!goal) to be informing about the cameras

!start_monitor.

// =================
//     INTENTIONS
// =================
// The plan (+!) he's going to implement to achieve his goal

// start monitor
+!start_monitor : person(unknown)<-
    .print("Monitoring enviroment");
    .print("Person  (prueba_red) detected, informing to master");
    .send("mente@192.168.0.202", achieve, person_state("prueba_red")).

// Reaction to JAVA agent
+java_command("detectar_fuego") <-
    .print("Order received, deactivating alarm...").
    // we can remoce previous beliefs
    // -fire.