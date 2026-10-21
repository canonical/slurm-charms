Feature: Slurm key rotation
  rotate-auth-key and rotate-jwt-key action verification, including
cross-unit key propagation and REST API token invalidation.

  Background:
    Given 'login' is deployed
    And 'controller' is deployed
    And 'compute' is deployed
    And 'database' is deployed
    And 'rest-api' is deployed

  @functional @edge
  Scenario: Rotate auth key across the cluster
    Given I capture the Slurm auth JWKS key from unit 'controller/0'
    When I run action 'rotate-auth-key' on unit 'controller/0' with an extended timeout
    Then the workload status for app 'login' is 'active'
    And the workload status for app 'controller' is 'active'
    And the workload status for app 'compute' is 'active'
    And the workload status for app 'database' is 'active'
    And the workload status for app 'rest-api' is 'active'
    And the Slurm auth JWKS key on unit 'controller/0' is rotated and propagated to all units
  Scenario: Rotate JWT key across the cluster
    Given I capture the Slurm JWT signing key from unit 'controller/0'
    And I capture the Slurm JWT signing key from unit 'database/0'
    And the initial Slurm JWT signing keys match between 'controller/0' and 'database/0'
    And I capture an initial Slurm JWT token from unit 'controller/0'
    And the slurmrestd diagnostic endpoints are reachable from 'controller/0'
    When I run action 'rotate-jwt-key' on unit 'controller/0' with an extended timeout
    Then the workload status for app 'login' is 'active'
    And the workload status for app 'controller' is 'active'
    And the workload status for app 'compute' is 'active'
    And the workload status for app 'database' is 'active'
    And the workload status for app 'rest-api' is 'active'
    And the Slurm JWT signing key on unit 'controller/0' is rotated and matches unit 'database/0'
    And the initial Slurm JWT token from unit 'controller/0' is no longer valid
    And a new Slurm JWT token from unit 'controller/0' is valid for all slurmrestd diagnostic endpoints
