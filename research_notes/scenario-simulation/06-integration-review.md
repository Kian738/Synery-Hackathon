# Integration review: constraints before a solver ships

This package is research and an API proposal. Capacity units and scenario inputs still require explicit values; no production simulation is integrated.

The proposed fractional-flow output plus per-group largest-remainder rounding is not sufficient to claim a feasible integer movement schedule. Rounding must preserve every shared door capacity, occupancy conservation and time constraint; a final deterministic feasibility check is mandatory. For integer people and integral capacities, a single-commodity network-flow formulation can yield integral flows directly. Capacity rates that create fractional service per time step require an explicit discretization/service-credit policy, with accumulated throughput verified across time; silently flooring each step can turn a usable low-rate door into a permanently blocked one.

Complexity claims for a time-expanded network refer to the size of that expanded network. Horizon and time resolution multiply its size and must be bounded in the API. The first prototype should verify conservation, capacity units, queue/service discretization and infeasibility on hand-checkable fixtures before adding responder counterflow or door interventions.

The source-verification limitations recorded by package D remain in force. This review does not certify the cited empirical studies or turn synthetic examples into predictions of human evacuation.
