import json
from pathlib import Path
import subprocess

config = json.loads(Path("/etc/vm-lab/server.json").read_text())
print("MCP: Authentication = No authentication; ключ уже включён в URL:")
print("https://" + config["public_ip"] + "/" + config["token"] + "/mcp")
print("Ссылку не публикуй и не присылай в чат.")
print("API для других агентов: https://" + config["public_ip"] + "/api/tools/<имя инструмента>")
print("Authorization: Bearer <ключ из ссылки между IP и /mcp>")
resources=config.get("resources",{})
print("Для расчёта: %s потоков, %.1f ГБ RAM; рабочая папка /var/lib/vm-lab/work" % (resources.get("threads","?"),resources.get("memory_limit_mib",0)/1024))
if not config.get("ip_reservation", {}).get("reserved"):
    print("Закрепление IP не подтверждено. В Яндекс Cloud: VPC → IP-адреса → " + config["public_ip"] + " → Сделать статическим.")
else:
    print("Публичный IP закреплён в Яндексе.")
subprocess.run(["systemctl", "is-active", "vm-lab-api.service", "vm-lab-worker.service", "vm-lab-cert-renew.timer"])

