Feature: Slurm services health
  Verify Slurm services are active within units, the prometheus-slurm-exporter metrics endpoint is accessible, and slurmctld/slurmdbd are listening on their expected ports.

  Background:
    Given 'login' is deployed
    And 'controller' is deployed
    And 'compute' is deployed
    And 'database' is deployed
    And 'rest-api' is deployed

  @functional @edge
  Scenario: Slurm services are active within all units
    Then the slurm systemd service is active on all slurm units
  Scenario: Slurm metrics endpoint is accessible
    Then the slurmctld metrics endpoint on unit 'controller/0' returns http status '200'
  Scenario: Slurmctld is listening on port 6817
    Then unit 'controller/0' is listening on TCP port '6817'
  Scenario: Slurmdbd is listening on port 6819
    Then unit 'database/0' is listening on TCP port '6819'
