def make_units(threads, memory_mib, install="/opt/vm-compute", work="/var/lib/vm-compute/work", port=8765):
    common = '''NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=
ProtectSystem=strict
ProtectHome=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
RestrictNamespaces=yes
RestrictSUIDSGID=yes
LockPersonality=yes
UMask=0007
KillMode=control-group
TimeoutStopSec=10
Restart=on-failure
RestartSec=5
'''
    worker = f'''[Unit]
Description=VM Lab background Python computations
After=local-fs.target
StartLimitIntervalSec=60
StartLimitBurst=4

[Service]
Type=simple
User=vm-compute-runner
Group=vm-compute
ExecStart=/usr/bin/python3 -u {install}/worker.py {work}
WorkingDirectory={work}
Environment=VM_LAB_THREADS={threads}
ReadWritePaths={work}
PrivateTmp=yes
PrivateNetwork=yes
ProtectProc=invisible
RestrictAddressFamilies=AF_UNIX
MemoryMax={memory_mib}M
MemorySwapMax=0
CPUQuota={threads*100}%
TasksMax=1024
LimitFSIZE=2147483648
{common}
[Install]
WantedBy=multi-user.target
'''
    api = f'''[Unit]
Description=VM Lab MCP file and job API
After=network.target vm-compute-worker.service
Wants=vm-compute-worker.service
StartLimitIntervalSec=60
StartLimitBurst=4

[Service]
Type=simple
User=vm-compute-api
Group=vm-compute
ExecStart=/usr/bin/python3 -u {install}/server.py /etc/vm-compute/server.json
WorkingDirectory={install}
ReadWritePaths={work}
PrivateTmp=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
MemoryMax=384M
TasksMax=64
{common}
[Install]
WantedBy=multi-user.target
'''
    # The API can bind HTTPS port 443, but has no filesystem administration rights.
    api = api.replace("CapabilityBoundingSet=\n", "CapabilityBoundingSet=CAP_NET_BIND_SERVICE\n")
    api = api.replace("AmbientCapabilities=\n", "AmbientCapabilities=CAP_NET_BIND_SERVICE\n")
    api = api.replace("StartLimitIntervalSec=60\nStartLimitBurst=4", "StartLimitIntervalSec=0")
    worker = worker.replace("StartLimitIntervalSec=60\nStartLimitBurst=4", "StartLimitIntervalSec=0")
    renewal = f'''[Unit]
Description=Renew VM Lab HTTPS IP certificate
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart={install}/certbot/bin/certbot renew --quiet --no-random-sleep-on-renew --config-dir /etc/vm-compute/acme --work-dir /var/lib/vm-compute/acme --logs-dir /var/log/vm-compute-acme
TimeoutStartSec=300
UMask=0077
'''
    timer = '''[Unit]
Description=Check VM Lab certificate renewal every 8 hours

[Timer]
OnCalendar=*-*-* 00,08,16:00:00
RandomizedDelaySec=300
Persistent=true
Unit=vm-compute-cert-renew.service

[Install]
WantedBy=timers.target
'''
    return {"vm-compute-worker.service":worker, "vm-compute-api.service":api,
            "vm-compute-cert-renew.service":renewal, "vm-compute-cert-renew.timer":timer}
