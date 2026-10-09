Feature: Slurm key rotation
  rotate-auth-key and rotate-jwt-key action verification, including cross-unit key propagation and REST API token invalidation.

  @functional @edge
  Scenario: Rotate auth key across the cluster
    Given I capture the slurm auth JWKS key from unit 'controller/0'
    When I run action 'rotate-auth-key' on unit 'controller/0' with an extended timeout
    Then the workload status for app 'login' is 'active'
    And the workload status for app 'controller' is 'active'
    And the workload status for app 'compute' is 'active'
    And the workload status for app 'database' is 'active'
    And the workload status for app 'rest-api' is 'active'
    And the slurm auth JWKS key on unit 'controller/0' is rotated and propagated to all units
  Scenario: Rotate JWT key across the cluster
    Given I capture the slurm JWT signing key from unit 'controller/0'
    And I capture the slurm JWT signing key from unit 'database/0'
    And the initial slurm JWT signing keys match between 'controller/0' and 'database/0'
    And I capture an initial slurm JWT token from unit 'controller/0'
    And the slurmrestd diagnostic endpoints are reachable from 'controller/0'
    When I run action 'rotate-jwt-key' on unit 'controller/0' with an extended timeout
    Then the workload status for app 'login' is 'active'
    And the workload status for app 'controller' is 'active'
    And the workload status for app 'compute' is 'active'
    And the workload status for app 'database' is 'active'
    And the workload status for app 'rest-api' is 'active'
    And the slurm JWT signing key on unit 'controller/0' is rotated and matches unit 'database/0'
    And the initial slurm JWT token from unit 'controller/0' is no longer valid
    And a new slurm JWT token from unit 'controller/0' is valid for all slurmrestd diagnostic endpoints
