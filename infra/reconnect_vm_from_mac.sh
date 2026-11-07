#!/bin/bash
# Run on the MAC, from a checked-out copy of IgorSabirov/vm-lab.
set -euo pipefail
if [ "$(uname -s)" != Darwin ]; then
    echo 'Эта команда для Мака. Внутри ВМ: sudo python3 -I infra/reconnect_vm.py НОВЫЙ_IP' >&2
    exit 1
fi
vm_ip="${1:?Передайте новый публичный IPv4 ВМ единственным параметром}"
if [[ ! "$vm_ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo 'Нужен IPv4, например 158.160.159.114' >&2
    exit 2
fi
vm_source_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
test -f "$HOME/.ssh/yc_key"
test -f "$vm_source_dir/reconnect_vm.py"
ssh -i "$HOME/.ssh/yc_key" -o IdentitiesOnly=yes \
    -o ServerAliveInterval=15 -o ServerAliveCountMax=8 \
    "yc-user@$vm_ip" "sudo -n /usr/bin/python3 -I - $vm_ip" \
    < "$vm_source_dir/reconnect_vm.py"
vm_host="vm-${vm_ip//./-}.sslip.io"
curl --fail --show-error --connect-timeout 5 --max-time 15 "https://$vm_host/healthz"
printf '\nHTTPS с Мака проверен. Теперь используйте напечатанный URL в подключении ChatGPT.\n'
