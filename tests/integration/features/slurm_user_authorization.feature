@security @edge @planned
Feature: Slurm user authorization
  Unprivileged users may query the scheduler and mint JWT tokens for themselves but cannot administer the cluster, control its services, modify accounting, mint tokens for other users, or tamper with configuration and logs. Slurm CLI probes run on the login node, where sackd brokers credentials for unprivileged users; each denial is paired with a check that the protected resource is genuinely unchanged.

  Background:
    Given 'login' is deployed
    And 'controller' is deployed
    And 'compute' is deployed
    And 'database' is deployed

  Scenario: Unprivileged user can query the scheduler
    Then the command 'sinfo' on unit 'login/0' as user 'nobody' succeeds
  Scenario: Unprivileged user cannot reconfigure slurm
    Then the command 'scontrol reconfigure' on unit 'login/0' as user 'nobody' is denied
    And the command 'scontrol create partitionname=authz-test nodes=compute-0' on unit 'login/0' as user 'nobody' is denied
    And the output of 'sinfo -h -o %P' on unit 'login/0' as user 'nobody' does not contain 'authz-test'
  Scenario: Unprivileged user cannot change node state
    Then the command 'scontrol update nodename=compute-0 state=drain reason=authz-test' on unit 'login/0' as user 'nobody' is denied
    And the output of 'sinfo -h -o %T -n compute-0' on unit 'login/0' as user 'nobody' contains 'idle'
  Scenario: Unprivileged user cannot control slurm services
    Then the command 'systemctl restart slurmctld' on unit 'controller/0' as user 'nobody' is denied
    And the output of 'systemctl is-active slurmctld' on unit 'controller/0' as user 'nobody' contains 'active'
    And the command 'systemctl stop slurmd' on unit 'compute/0' as user 'nobody' is denied
    And the output of 'systemctl is-active slurmd' on unit 'compute/0' as user 'nobody' contains 'active'
  Scenario: Unprivileged user cannot tamper with slurm configuration or logs
    Then the command 'echo tampered >> /etc/slurm/slurm.conf' on unit 'controller/0' as user 'nobody' is denied
    And the output of 'grep -c tampered /etc/slurm/slurm.conf' on unit 'controller/0' as user 'nobody' contains '0'
    And the command 'echo tampered >> /var/log/slurm/slurmctld.log' on unit 'controller/0' as user 'nobody' is denied
  Scenario: Unprivileged user cannot modify accounting
    Then the command 'sacctmgr -i delete account nonexistent-authz-test' on unit 'login/0' as user 'nobody' is denied
    And the command 'sacctmgr -i add qos authz-test' on unit 'login/0' as user 'nobody' is denied
  Scenario: Unprivileged user can mint a jwt token for themselves
    Then the command 'scontrol token' on unit 'login/0' as user 'nobody' succeeds
  Scenario: Unprivileged user cannot mint jwt tokens for other users
    Then the command 'scontrol token username=root' on unit 'login/0' as user 'nobody' is denied
