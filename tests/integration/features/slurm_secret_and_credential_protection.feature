Feature: Slurm secret and credential protection
  Slurm secret files are owner-only with the correct per-charm service
owner and are unreadable by unprivileged users. The accounting database
password stays confined to its 0600 file and must not leak into
slurm.conf, which is world-readable by design. Complements the key
rotation feature, which proves rotation works but never checks the
resulting files' modes or owners.

  Background:
    Given 'login' is deployed
    And 'controller' is deployed
    And 'compute' is deployed
    And 'database' is deployed
    And 'rest-api' is deployed

  @security @edge
  Scenario: Auth key file is owner-only with the correct owner on every slurm unit
    Then the file '/etc/slurm/slurm.jwks' on unit 'login/0' has mode '600' and owner 'slurm'
    And the file '/etc/slurm/slurm.jwks' on unit 'controller/0' has mode '600' and owner 'slurm'
    And the file '/etc/slurm/slurm.jwks' on unit 'database/0' has mode '600' and owner 'slurm'
    And the file '/etc/slurm/slurm.jwks' on unit 'compute/0' has mode '600' and owner 'root'
    And the file '/etc/slurm/slurm.jwks' on unit 'rest-api/0' has mode '600' and owner 'slurmrestd'
  Scenario: JWT signing key file is owner-only where it exists
    Then the file '/etc/slurm/jwt_hs256.key' on unit 'controller/0' has mode '600' and owner 'slurm'
    And the file '/etc/slurm/jwt_hs256.key' on unit 'database/0' has mode '600' and owner 'slurm'
  Scenario: Unprivileged user cannot read slurm key material
    Then the command 'cat /etc/slurm/slurm.jwks' on unit 'controller/0' as user 'nobody' is denied
    And the command 'cat /etc/slurm/jwt_hs256.key' on unit 'controller/0' as user 'nobody' is denied
  Scenario: Database password file is owner-only and unreadable by unprivileged users
    Then the file '/etc/slurm/slurmdbd.conf' on unit 'database/0' has mode '600' and owner 'slurm'
    And the command 'cat /etc/slurm/slurmdbd.conf' on unit 'database/0' as user 'nobody' is denied
  Scenario: World-readable slurm config contains no credentials
    Then the output of 'cat /etc/slurm/slurm.conf' on unit 'controller/0' as user 'nobody' does not contain 'StoragePass'
    And the output of 'cat /etc/slurm/slurm.conf' on unit 'controller/0' as user 'nobody' does not contain 'StorageUser'
