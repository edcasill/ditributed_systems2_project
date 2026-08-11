// This is an example of how to do BDI programming

// =================
//     BELIEFS
// =================
// The agent is at the base and his battery is fully charged

location(base).
battery_state(high).

// =================
//     DESIRES
// =================
// When the agent born, it has the desire (!goal) to be informing about the cameras

!start_monitor.

// =================
//     INTENTIONS
// =================
// The plan (+!) he's going to implement to achieve his goal

// Plan A: patrolling with high battery
+!start_monitor : battery_state(high) <-
    .print("Ranger: Battery fully charged. Leaving the base and start patrolling...");
    -location(base);        // the agent is no more at the base
    +location(north_zone);  // the agent is at a new location
    !check_enviroment.      // a new goal arise

// if the agent gets the belief that the baterry is low
+battery_state(low) <-
    .print("Ranger: Warning: Low battery. I need to recharge");
    .print("Ranger: Requesting help to the base");
    // send message to the commander telling he needs help
    .send("commander@localhost", tell, need_asistance).

// Plan B: patrolling with low battery
+!start_monitor : battery_state(low) <-
    .print("Ranger: Low battery. Can not be patrolling").

// Secondary desire plan
+!check_enviroment <-