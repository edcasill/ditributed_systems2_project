// This is an example of how to do BDI programming

// =================
//     BELIEFS
// =================
// The agent does not know what is watching
// person(unknown).


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
+!start_monitor <-
    .print("Monitoring enviroment").

// if the agent gets the belief to monitor people
+person(State) : not fire <-
    .print("Person  (", State, ") detected, informing to master");
    // .send("master@localhost", tell, person_state(State)).
    .send("puente@192.168.0.202", achieve, person_state(State)).

// Plan B: fire detected
+fire : true <-
    .print("ALERT! Fire dected");
    // .send("master@localhost", tell, emergency).
    .send("puente@192.168.0.202", achieve, emergency).

// Reaction to JAVA agent
+java_command("deactivate_alarm") <-
    .print("Order received, deactivating alarm...");
    // we can remoce previous beliefs
    -fire.