Feature: Slurm node operations
  Compute node state, set-node-config, and set-node-state action verification.

  Background:
    Given 'controller' is deployed
    And 'compute' is deployed

  @functional @edge
  Scenario: Default slurmd node state and reason
    Then the slurmd node for unit 'compute/0' has state containing 'DOWN' and reason "'n/a'"
  Scenario: Set node config action updates node weight
    When I run action 'set-node-config' on unit 'compute/0' with parameters 'parameters=weight=100'
    Then the slurmd node for unit 'compute/0' has weight '100' and state containing 'DOWN' and reason "'n/a'"
    When I run action 'set-node-config' on unit 'compute/0' with parameters 'reset=true'
    Then the slurmd node for unit 'compute/0' has weight '1' and state containing 'DOWN' and reason "'n/a'"
  Scenario: Set node state action updates node state and reason
    When I run action 'set-node-state' on unit 'controller/0' with parameters 'nodes=compute-0 state=down reason=maintenance'
    Then the slurmd node for unit 'compute/0' has state containing 'DOWN' and reason "'maintenance'"
    When I run action 'set-node-state' on unit 'controller/0' with parameters 'nodes=compute-0 state=idle'
    Then the slurmd node for unit 'compute/0' has state containing 'IDLE' and reason ""
