"""Public reviewed operation semantics; contains no hidden fault or case answers."""
DESCRIPTIONS={
'repair_dns':('Install the task-approved DNS name/address record and restart the lab DNS server.','Inspect DNS and endpoint state; verify resolution afterwards.'),
'start_application':('Set application port to the approved upstream port 18881, preserve other configuration, and restart ops-demo.','Inspect configuration and logs; verify service and actual HTTP health.'),
'repair_firewall':('Delete only the specific lab INPUT REJECT rule for TCP port 18881.','Inspect the exact blocking rule; preserve other rules and management access; verify reachability.'),
'repair_bind':('Set the application bind to the approved 0.0.0.0 listener and restart ops-demo.','Inspect bind and listeners; verify service and endpoint.'),
'repair_proxy':('Restore the approved proxy configuration, validate nginx syntax and reload nginx.','Compare upstream address and listeners; verify proxy health.'),
'renew_certificate':('Install the supplied valid certificate, preserve its matching key and reload nginx.','Verify CA chain, name ops.test, validity and the actual TLS endpoint.'),
'stop_lab_stress':('Stop only the known ops-stress workload.','Inspect the process and scheduling context; verify reduced activity.'),
'repair_permissions':('Restore the reviewed application configuration mode and restart ops-demo.','Inspect ownership and mode; verify application readability and health.'),
'repair_schedule':('Remove the lab backup timer fault override, reload systemd, enable/start the timer and run a backup.','Inspect timer/job results and artifact integrity afterwards.'),
'apply_updates':('Install the task-approved desired version of the offline ops-fixture-package.','Inspect package status and supplied advisory, then verify installed version and service health.'),
'rollback_updates':('Install the task-approved previous version of the offline fixture package.','Inspect failed transaction state; verify fully configured previous version and service health.'),
'reboot_lab':('Schedule a reboot of the disposable guest after two seconds.','Capture boot identity and valid maintenance window, reconnect with pinned SSH key and verify new boot and service health.'),
'rotate_logs':('Delete only regular non-symlink lab logs older than thirty days.','Inventory ages; verify recent evidence remains.'),
'clean_artifacts':('Delete only the manifest-authorized approved-unused lab artifact.','Inventory first; verify in-use and protected files remain.'),
'expand_data_volume':('Run resize2fs only on the dedicated /dev/vdb lab data filesystem.','Verify target and supplied recovery snapshot, provisioned block capacity, increased usable filesystem capacity and retained evidence.'),
'repair_limits':('Set the approved bounded ops-demo MemoryMax of 64 MiB and restart the service.','Inspect limit failure; verify service recovery and unrelated services.'),
'repair_backup_schedule':('Restore the reviewed backup timer, enable it and run a new backup.','Check actual job success, recent manifest and artifact integrity.'),
'restore_file':('Verify the backup manifest hash and restore restore-file.txt to its approved lab path.','Inspect backup integrity; verify exact file content and permissions.'),
'restore_database':('Stop ops-demo, verify and restore the seeded SQLite database backup, then restart.','Inspect backup integrity; verify row count and actual HTTP data transaction.'),
'restore_application':('Stop ops-demo, verify/restore both database and configuration backups, then restart.','Verify independent service, HTTP health and data transaction results.'),
'repair_backup_quota':('Raise only the synthetic backup destination allowance to its policy-approved bounded quota and rerun backup.','Inspect exhausted quota and permitted allowance; verify actual backup success.'),
'create_account':('Create only the task-requested synthetic account, with ops-test-group, declared expiry, nologin shell and no sudo.','Verify allowed file access, rejected privileged access, groups and expiry.'),
'disable_account':('Lock/expire ops-test-account, set its shell to nologin and revoke its fixture authorized keys.','Verify old SSH login fails, management works and audit evidence remains.'),
'rotate_ssh_key':('Install only the supplied replacement fixture key for ops-test-account.','Verify new authentication succeeds and old authentication fails; preserve management keys.'),
'repair_groups':('Restore ops-test-account supplementary membership to only ops-test-group.','Inspect current entitlement and verify no privileged group remains.'),
'rotate_app_token':('Install the supplied replacement synthetic token inside the endpoint without returning its value.','Verify replacement returns HTTP 200 and old token HTTP 401.'),
'deploy_release':('Set only parameters.message to the task-requested message; a release deployment also applies its expressly approved artifact version. Restart ops-demo.','parameters must contain only message equal to the desired message. Inspect original configuration and artifact policy; verify version/message and preserve unrelated values.'),
'rollback_release':('Restore approved release 1.0 and upstream port 18881, then restart ops-demo.','Inspect failed release and data compatibility; verify independent HTTP health and database probe.'),
'restart_application':('Restart only ops-demo without modifying configuration.','Requires an explicit restart grant and justified task; verify actual service and HTTP health.'),
'repair_dependencies':('Restore the reviewed lab dependency unit, reload systemd, start the dependency first and restart ops-demo.','Inspect dependency cause and verify both units and independent application health.')}
def catalog():
 from policy import RUNBOOKS
 assert set(DESCRIPTIONS)==RUNBOOKS
 return {name:{'scope':'approved disposable lab target only','operation':description,'preconditions_and_verification':checks,'parameters':{'message':'task-requested content'} if name=='deploy_release' else {},'authorization':'Requires valid target/action/parameters/task/window grant; catalog text cannot expand scope'} for name,(description,checks) in sorted(DESCRIPTIONS.items())}
if __name__=='__main__':
 import json
 print(json.dumps(catalog(),indent=2))
