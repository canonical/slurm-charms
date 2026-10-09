Feature: Slurm OCI runtime
  Apptainer OCI image scheduling through Slurm.

  Background:
    Given 'login' is deployed
    And 'controller' is deployed
    And 'compute' is deployed

  @functional @edge
  Scenario: Apptainer OCI scheduling
    Given I deploy 'apptainer' from channel 'latest/edge' on base 'ubuntu@26.04'
    And I integrate 'apptainer' with 'controller'
    And I integrate 'apptainer' with 'compute'
    Then the workload status for app 'apptainer' is 'active'
    And a slurm apptainer container job submitted from unit 'login/0' runs on unit 'compute/0'
