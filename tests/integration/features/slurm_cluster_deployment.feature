Feature: Slurm cluster deployment
  Deploy the full Slurm cluster (sackd, slurmctld, slurmd, slurmdbd, slurmrestd, mysql) and integrate all applications. Shared session state relied on by every subsequent feature.

  @functional @edge
  Scenario: Deploy the slurm cluster
    Given I add model 'slurm'
    And I switch to model 'slurm'
    And I deploy the slurm reference cluster
    And I integrate 'login' with 'controller'
    And I integrate 'compute' with 'controller'
    And I integrate 'database' with 'controller'
    And I integrate 'rest-api' with 'controller'
    And I integrate 'mysql' with 'database'
    Then the workload status for app 'login' is 'active'
    And the workload status for app 'controller' is 'active'
    And the workload status for app 'compute' is 'active'
    And the workload status for app 'database' is 'active'
    And the workload status for app 'rest-api' is 'active'
