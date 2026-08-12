# Copyright 2025-2026 Vantage Compute Corporation
# Copyright 2024 Omnivector, LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Constants used within the `slurmctld` charmed operator."""

OCI_RUNTIME_INTEGRATION_NAME = "oci-runtime"
PEER_INTEGRATION_NAME = "slurmctld-peer"
SACKD_INTEGRATION_NAME = "sackd"
SLURMD_INTEGRATION_NAME = "slurmd"
SLURMDBD_INTEGRATION_NAME = "slurmdbd"
SLURMRESTD_INTEGRATION_NAME = "slurmrestd"

HA_MOUNT_INTEGRATION_NAME = "mount"
HA_MOUNT_LOCATION = "/srv/slurmctld-statefs"

MAIL_INTEGRATION_NAME = "smtp"
MAILPROG_PATH = "/usr/bin/slurm-spool-mail"
SLURM_MAIL_CONFIG_PATH = "/etc/slurm-mail/slurm-mail.conf"

SLURMCTLD_PORT = 6817
PROMETHEUS_EXPORTER_PORT = 9092

CLUSTER_NAME_PREFIX = "charmed-hpc"

DEFAULT_SLURM_MAIL_CONFIG = {
    "common": {"spoolDir": "/var/spool/slurm-mail"},
    "slurm-spool-mail": {
        "logFile": "/var/log/slurm-mail/slurm-spool-mail.log",
        "verbose": "false",
    },
    "slurm-send-mail": {
        "logFile": "/var/log/slurm-mail/slurm-send-mail.log",
        "verbose": "false",
        "arrayMaxNotifications": "0",
        "emailFromUserAddress": "root",
        "emailFromName": "Slurm Admin",
        "emailRegEx": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "emailSubject": "Job $CLUSTER.$JOB_ID: $STATE",
        "gecosNameField": "0",
        "validateEmail": "false",
        "datetimeFormat": "%d/%m/%Y %H:%M:%S",
        "sacctExe": "/usr/bin/sacct",
        "scontrolExe": "/usr/bin/scontrol",
        "smtpServer": "localhost",
        "smtpPort": "25",
        "smtpUseTls": "no",
        "smtpUseSsl": "no",
        "smtpUserName": "",
        "smtpPassword": "",
        "retryOnFailure": "yes",
        "retryDelay": "0",
        "tailExe": "/usr/bin/tail",
        "includeOutputLines": "0",
    },
}

UBUNTU_HPC_PPA_KEY = """
-----BEGIN PGP PUBLIC KEY BLOCK-----
Comment: Hostname:
Version: Hockeypuck 2.2

xsFNBGTuZb8BEACtJ1CnZe6/hv84DceHv+a54y3Pqq0gqED0xhTKnbj/E2ByJpmT
NlDNkpeITwPAAN1e3824Me76Qn31RkogTMoPJ2o2XfG253RXd67MPxYhfKTJcnM3
CEkmeI4u2Lynh3O6RQ08nAFS2AGTeFVFH2GPNWrfOsGZW03Jas85TZ0k7LXVHiBs
W6qonbsFJhshvwC3SryG4XYT+z/+35x5fus4rPtMrrEOD65hij7EtQNaE8owuAju
Kcd0m2b+crMXNcllWFWmYMV0VjksQvYD7jwGrWeKs+EeHgU8ZuqaIP4pYHvoQjag
umqnH9Qsaq5NAXiuAIAGDIIV4RdAfQIR4opGaVgIFJdvoSwYe3oh2JlrLPBlyxyY
dayDifd3X8jxq6/oAuyH1h5K/QLs46jLSR8fUbG98SCHlRmvozTuWGk+e07ALtGe
sGv78ToHKwoM2buXaTTHMwYwu7Rx8LZ4bZPHdersN1VW/m9yn1n5hMzwbFKy2s6/
D4Q2ZBsqlN+5aW2q0IUmO+m0GhcdaDv8U7RVto1cWWPr50HhiCi7Yvei1qZiD9jq
57oYZVqTUNCTPxi6NeTOdEc+YqNynWNArx4PHh38LT0bqKtlZCGHNfoAJLPVYhbB
b2AHj9edYtHU9AAFSIy+HstET6P0UDxy02IeyE2yxoUBqdlXyv6FL44E+wARAQAB
zRxMYXVuY2hwYWQgUFBBIGZvciBVYnVudHUgSFBDwsGOBBMBCgA4FiEErocSHcPk
oLD4H/Aj9tDF1ca+s3sFAmTuZb8CGwMFCwkIBwIGFQoJCAsCBBYCAwECHgECF4AA
CgkQ9tDF1ca+s3sz3w//RNawsgydrutcbKf0yphDhzWS53wgfrs2KF1KgB0u/H+u
6Kn2C6jrVM0vuY4NKpbEPCduOj21pTCepL6PoCLv++tICOLVok5wY7Zn3WQFq0js
Iy1wO5t3kA1cTD/05v/qQVBGZ2j4DsJo33iMcQS5AjHvSr0nu7XSvDDEE3cQE55D
87vL7lgGjuTOikPh5FpCoS1gpemBfwm2Lbm4P8vGOA4/witRjGgfC1fv1idUnZLM
TbGrDlhVie8pX2kgB6yTYbJ3P3kpC1ZPpXSRWO/cQ8xoYpLBTXOOtqwZZUnxyzHh
gM+hv42vPTOnCo+apD97/VArsp59pDqEVoAtMTk72fdBqR+BB77g2hBkKESgQIEq
EiE1/TOISioMkE0AuUdaJ2ebyQXugSHHuBaqbEC47v8t5DVN5Qr9OriuzCuSDNFn
6SBHpahN9ZNi9w0A/Yh1+lFfpkVw2t04Q2LNuupqOpW+h3/62AeUqjUIAIrmfeML
IDRE2VdquYdIXKuhNvfpJYGdyvx/wAbiAeBWg0uPSepwTfTG59VPQmj0FtalkMnN
ya2212K5q68O5eXOfCnGeMvqIXxqzpdukxSZnLkgk40uFJnJVESd/CxHquqHPUDE
fy6i2AnB3kUI27D4HY2YSlXLSRbjiSxTfVwNCzDsIh7Czefsm6ITK2+cVWs0hNQ=
=cs1s
-----END PGP PUBLIC KEY BLOCK-----
"""
UBUNTU_HPC_SLURM_MAIL_PPA_URI = "https://ppa.launchpadcontent.net/ubuntu-hpc/slurm-mail/ubuntu"
