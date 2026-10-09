Feature: Slurm mail notifications
  SMTP integrator deployment and Slurm job notification emails for job end, failure, and begin with a custom signature.

  Background:
    Given 'controller' is deployed

  @functional @edge
  Scenario: Deploy and integrate SMTP integrator
    Given I deploy 'smtp-integrator' with auto-resolved local host and port '8025'
    And I integrate 'controller' with 'smtp-integrator:smtp'
    Then the workload status for app 'controller' is 'active'
    And the workload status for app 'smtp-integrator' is 'active'
  Scenario: Notification email when a job ends
    When I execute 'srun --time=1 --partition compute --mail-user=user@localhost --mail-type=END sleep 1' on unit 'login/0'
    Then a notification email is received by 'user@localhost' with subject matching '^Job charmed-hpc-[\w-]{4}\.\d+: Ended$' and content matching 'Your job \d+ has ended on charmed-hpc-[\w-]{4}\.'
  Scenario: Notification email when a job fails
    When I run a failing slurm srun job on unit 'login/0' with mail user 'anotheruser@localhost' and mail type 'FAIL,END'
    Then a notification email is received by 'anotheruser@localhost' with subject matching '^Job charmed-hpc-[\w-]{4}\.\d+: Failed$' and content matching 'Your job \d+ has failed on charmed-hpc-[\w-]{4}\.'
  Scenario: Notification email with custom signature when a job begins
    Given I set 'email-from-name' for app 'controller' to 'Integration Test Suite'
    When I execute 'srun --time=1 --partition compute --mail-user=furtheruser@localhost --mail-type=BEGIN sleep 1' on unit 'login/0'
    Then a notification email is received by 'furtheruser@localhost' with subject matching '^Job charmed-hpc-[\w-]{4}\.\d+: Began$' and content matching 'Your job \d+ has started on charmed-hpc-[\w-]{4}\..*?Regards,.*?Integration Test Suite'
  Scenario: Remove SMTP integrator
    When I remove app 'smtp-integrator'
    Then the workload status for app 'controller' is 'active'
