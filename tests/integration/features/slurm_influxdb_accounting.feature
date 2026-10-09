Feature: Slurm InfluxDB accounting
  InfluxDB task accounting. Currently skipped because the influxdb charm deployment is broken.

  Background:
    Given 'controller' is deployed
    And 'login' is deployed

  @functional @edge
  Scenario: Task accounting works
    Given I deploy 'influxdb'
    And I integrate 'influxdb' with 'controller'
    Then the workload status for app 'influxdb' is 'active'
    And a slurm sstat task accounting job on unit 'login/0' reports '1' task
