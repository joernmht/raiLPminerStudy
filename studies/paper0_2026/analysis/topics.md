# Types of model elements (NMF topics over names)

## constraints: 13286 names, k = 16, unassigned 1549

| topic | names | top terms | examples | in references |
|---|---|---|---|---|
| 12 | 1285 | capacity, track, station, station capacity, track capacity, assignment | station capacity; track assignment; capacity; acceleration limit | P1, P2, P3, P4, P5 |
| 13 | 1176 | departure, arrival, arrival departure, link, arrival time, origin | flow conservation; origin departure; continuity; occupancy link | P1, P2, P3, P4 |
| 4 | 1073 | selection, profile, profile selection, speed, speed profile, route | speed profile selection; profile selection; route selection; speed limits | P2, P4, P5 |
| 3 | 988 | running, running time, time, time consistency, consistency, time linkage | running time bounds; running time consistency; running time; time propagation | P1, P2, P4, P5 |
| 2 | 902 | headway, direction, direction headway, headway constraint, constraint, station headway | headway; same direction headway; headway constraint; station headway | P1, P3, P4 |
| 7 | 855 | ordering, consistency, ordering consistency, headway ordering, time consistency, conflict ordering | ordering consistency; ordering; timetable consistency; headway ordering | P3 |
| 5 | 712 | disruption, window, disruption window, entry, avoidance, disruption avoidance | disruption window; disruption; disruption avoidance; disruption arrival | P1, P2, P3, P5 |
| 0 | 691 | dwell, dwell time, time, min, max, min dwell | dwell time; dwell time bounds; minimum dwell time; min dwell time | P1, P2, P4 |
| 10 | 597 | cancellation, cancellation logic, logic, cancellation consistency, consistency, propagation | cancellation logic; cancellation consistency; cancellation propagation; cancellation arrival | P1, P2, P3 |
| 11 | 584 | bound, lower, lower bound, delay lower, delay, time lower | delay lower bound; energy lower bound; dwell time lower bound; dwell time upper bound | P1, P3, P4, P5 |
| 15 | 572 | linearization, delay, delay linearization, non, negativity, non negativity | delay linearization; delay non negativity; delay calculation; delay propagation | P1, P2, P5 |
| 8 | 563 | rerouting, logic, rerouting logic, restriction, rerouting restriction, rerouting window | rerouting logic; rerouting restriction; rerouting window; rerouting feasibility | P1 |
| 6 | 516 | conflict, bidirectional, bidirectional conflict, avoidance, conflict avoidance, resolution | bidirectional conflict; conflict avoidance; conflict resolution; blockage avoidance | P5 |
| 1 | 430 | definition, delay definition, delay, time definition, arrival delay, departure delay | delay definition; travel time definition; arrival delay definition; departure delay definition | P3 |
| 14 | 427 | energy, consumption, energy consumption, calculation, energy calculation, energy definition | energy consumption; energy calculation; energy definition; energy model | P1 |
| 9 | 366 | bounds, time bounds, speed bounds, speed, dwell bounds, horizon | speed bounds; dwell bounds; mccormick; horizon bounds | P1, P4 |

## variables: 8409 names, k = 12, unassigned 701

| topic | names | top terms | examples | in references |
|---|---|---|---|---|
| 11 | 1210 | occupancy, track, disruption, track occupancy, assignment, track assignment | occupancy; track assignment; reroute indicator; reroute | P1, P2, P3, P5 |
| 8 | 956 | running, running time, time, entry, entry time, exit | running time; entry time; dwell time; exit time | P1, P2, P3, P4 |
| 2 | 955 | delay, arrival delay, departure delay, arrival, total delay, total | delay; arrival delay; departure delay; total delay | P1, P2, P5 |
| 1 | 782 | departure, departure time, time, departure delay, entry time, entry | departure time; actual departure time; departure deviation; alighting passengers | P1, P3, P4 |
| 0 | 746 | arrival time, arrival, time, arrival delay, entry time, entry | arrival time; actual arrival time; arrival deviation; rescheduled arrival time | P1, P4 |
| 4 | 676 | ordering, station ordering, station, direction, direction ordering, segment ordering | ordering; ordering variable; station ordering; segment ordering | P4, P5 |
| 10 | 556 | speed, level, speed level, level selection, speed profile, speed plan | speed; speed level selection; speed plan selection; speed level | P1, P2, P3, P4 |
| 5 | 473 | profile, selection, profile selection, speed profile, route, route selection | speed profile selection; route selection; profile selection; route choice | P3, P5 |
| 7 | 442 | energy, consumption, energy consumption, total energy, total, total delay | energy consumption; energy; acceleration; total energy | P1 |
| 3 | 393 | cancellation, trip cancellation, trip, train cancellation, train, shunting cancellation | cancellation; cancellation indicator; trip cancellation; cancellation decision | P3 |
| 6 | 304 | rerouting, rerouting flag, flag, usage, total, track | rerouting; rerouting indicator; rerouting decision; rerouting variable | P1 |
| 9 | 215 | precedence, direction, track, opposite, reroute, direction precedence | precedence; precedence indicator; reordering; precedence variable | P5 |

## objectives: 845 names, k = 6, unassigned 264

| topic | names | top terms | examples | in references |
|---|---|---|---|---|
| 0 | 264 | cost, cancellation cost, delay route, route, deviation, operational cost | total cost; minimize total cost; total weighted cost; min cost | P3 |
| 1 | 153 | energy, delay energy, cancellations, energy cancellations, trade, penalty | min delay and energy; minimize weighted delay and energy; total delay and energy; minimize delay and energy | P1 |
| 2 | 78 | delay, train delay, train, penalty, trade, delay route | total weighted delay; minimize total weighted delay; minimize total delay; total delay | P5 |
| 4 | 35 | cancellation, energy cancellation, cancellation cost, penalty, rerouting, delays | minimize weighted delay, energy, and cancellation; min delay, energy, and cancellation; min delay, energy and cancellation; minimize total weighted delay, energy, and cancellation | P3 |
| 3 | 32 | operational, operational cost, costs, cost, delay, cancellation cost | total operational cost; minimize weighted costs; minimize total operational cost; total weighted operational cost | P4 |
| 5 | 19 | secondary delay, secondary, penalty, energy penalty, route, delay route | minimize total secondary delay; minimize weighted delay, penalty, and energy; minimize total weighted secondary delay; total weighted delay, energy, and penalty | P2 |
