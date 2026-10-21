Feature: Slurm cluster deployment
  Deploy the full Slurm cluster (sackd, slurmctld, slurmd, slurmdbd,
slurmrestd, mysql) and integrate all applications. Shared session state
relied on by every subsequent feature.

  @functional @edge
  Scenario: Deploy the Slurm cluster
    Given I add model 'slurm'
    And I switch to model 'slurm'
    And I set 'update-status-hook-interval' for model 'slurm' to '10s'
    And I deploy 'sackd' from a local charm on base 'ubuntu@26.04' with name 'login'
    And I deploy 'slurmctld' from a local charm on base 'ubuntu@26.04' with name 'controller' with config 'slurm-conf-parameters=SlurmctldTimeout=10' with constraints 'virt-type=virtual-machine'
    And I deploy 'slurmd' from a local charm on base 'ubuntu@26.04' with name 'compute'
    And I deploy 'slurmdbd' from a local charm on base 'ubuntu@26.04' with name 'database'
    And I deploy 'slurmrestd' from a local charm on base 'ubuntu@26.04' with name 'rest-api'
    And I deploy 'mysql'
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
