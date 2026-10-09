Feature: Slurm job submission
  Basic job submission and GPU job submission with a mock GPU device.

  Background:
    Given 'login' is deployed
    And 'controller' is deployed
    And 'compute' is deployed

  @functional @edge
  Scenario: Simple job submission
    Then a slurm srun job submitted from unit 'login/0' runs on unit 'compute/0'
  Scenario: GPU job submission with mock GPU
    Given I set up a mock NVIDIA GPU device on unit 'compute/0'
    And I set 'cgroup-parameters' for app 'controller' to 'constraindevices=no'
    When I run action 'set-node-config' on unit 'compute/0' with parameters 'parameters=gres=gpu:mock_gpu:1'
    And I re-register the slurmd node 'compute-0' with the slurm controller on unit 'login/0'
    Then a slurm srun GPU job requesting 1 GPU submitted from unit 'login/0' runs on unit 'compute/0'
