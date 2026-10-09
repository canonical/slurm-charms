Feature: Slurmctld high availability
  High availability for slurmctld: shared storage deploy, scale up/down, service and unit failover and recovery, degraded scale-up, and removal of a failed controller. Gated by the high_availability marker (--run-high-availability).

  Background:
    Given 'controller' is deployed

  @reliability @edge
  Scenario: Deploy shared storage for high availability
    Given I deploy 'microceph' with constraints 'mem=4G root-disk=20G virt-type=virtual-machine' with storage 'osd-standalone=loop,2G,3'
    And I deploy 'filesystem-client' from channel 'latest/edge' on base 'ubuntu@26.04'
    Then the workload status for app 'microceph' is 'active'
    Given I set up the cephfs pools and client on unit 'microceph/0'
    And I deploy 'cephfs-server-proxy' from channel 'latest/edge' with cephfs config gathered from unit 'microceph/0'
    And I integrate 'filesystem-client' with 'cephfs-server-proxy'
    And I integrate 'filesystem-client:mount' with 'controller:mount'
    Then the workload status for app 'controller' is 'active'
    And the slurmctld controller that is primary reports ping status 'UP'
  Scenario: Scale up slurmctld by two units
    Given the slurmctld controller that is primary reports ping status 'UP'
    And I record the current slurmctld controller mode assignments
    And I add '2' units to app 'controller'
    Then the workload status for app 'controller' is 'active'
    And the slurmctld controller that is primary reports ping status 'UP'
    And the slurmctld controller that is primary has the hostname recorded for primary
    And there are '3' slurmctld controllers registered
    And the slurmctld controller that is backup1 reports ping status 'UP'
    And the slurmctld controller that is backup2 reports ping status 'UP'
  Scenario: Scale down slurmctld by one unit
    Given there are '3' slurmctld controllers registered
    And the slurmctld controller that is primary reports ping status 'UP'
    And the slurmctld controller that is backup1 reports ping status 'UP'
    And the slurmctld controller that is backup2 reports ping status 'UP'
    And I record the current slurmctld controller mode assignments
    When I remove the slurmctld controller that is backup1
    Then the workload status for app 'controller' is 'active'
    And there are '2' slurmctld controllers registered
    And the slurmctld controller that is primary reports ping status 'UP'
    And the slurmctld controller that is primary has the hostname recorded for primary
    And the slurmctld controller that is backup reports ping status 'UP'
    And the slurmctld controller that is backup has the hostname recorded for backup2
  Scenario: Service failover to backup controller
    Given I record the current slurmctld controller mode assignments
    And the slurmctld controller that is primary reports ping status 'UP'
    And the slurmctld controller that is backup reports ping status 'UP'
    When I stop the slurmctld service on the controller that is primary
    Then the slurm sinfo command succeeds on unit 'login/0'
    And the slurmctld service on the controller that is backup is running as primary
  Scenario: Service recovery after restarting primary
    Given I record the current slurmctld controller mode assignments
    And the slurmctld controller that is primary reports ping status 'DOWN'
    And the slurmctld controller that is backup reports ping status 'UP'
    When I restart the slurmctld service on the controller that is primary
    Then the slurm sinfo command succeeds on unit 'login/0'
    And the slurmctld service on the controller that is primary is running as primary
    And the slurmctld service on the controller that is backup is running in background mode
  Scenario: Unit failover after powering off primary machine
    Given I record the current slurmctld controller mode assignments
    And the slurmctld controller that is primary reports ping status 'UP'
    And the slurmctld controller that is backup reports ping status 'UP'
    And the slurmd node for unit 'compute/0' is schedulable according to scontrol from unit 'login/0'
    When I power off the primary slurmctld machine
    Then the primary slurmctld machine is powered off
    And the slurmctld service on the controller that is backup is running as primary
    And the slurm sinfo command succeeds on unit 'login/0'
    And a slurm srun job submitted from unit 'login/0' runs on unit 'compute/0'
  Scenario: Unit recovery after rebooting primary machine
    Given I record the current slurmctld controller mode assignments
    And the slurmctld controller that is primary reports ping status 'DOWN'
    And the slurmctld controller that is backup reports ping status 'UP'
    And the primary slurmctld machine is powered off
    When I reboot the primary slurmctld machine
    Then the workload status for app 'controller' is 'active'
    And the slurm sinfo command succeeds on unit 'login/0'
    And the slurmctld service on the controller that is primary is running as primary
    And the slurmctld service on the controller that is backup is running in background mode
  Scenario: Scale up slurmctld while primary is failed
    Given I record the current slurmctld controller mode assignments
    And the slurmctld controller that is primary reports ping status 'UP'
    When I power off the primary slurmctld machine
    Then the primary slurmctld machine is powered off
    And the slurmctld controller that is primary reports ping status 'DOWN'
    And the slurmctld controller that is backup reports ping status 'UP'
    Given I add '1' units to app 'controller'
    Then there are '3' slurmctld controllers registered
    And the slurmctld controller that is primary reports ping status 'DOWN'
    And the slurmctld controller that is primary has the hostname recorded for primary
    And the slurmctld controller that is backup1 reports ping status 'UP'
    And the slurmctld controller that is backup1 has the hostname recorded for backup
    And the slurmctld controller that is backup2 reports ping status 'UP'
  Scenario: Remove failed controller unit
    Given there are '1' down and '2' up slurmctld controller machines
    When I remove the slurmctld controller that is down
    Then the workload status for app 'controller' is 'active'
    And there are '2' slurmctld controllers registered
    And the slurmctld controller that is primary reports ping status 'UP'
    And the slurmctld controller that is backup reports ping status 'UP'
