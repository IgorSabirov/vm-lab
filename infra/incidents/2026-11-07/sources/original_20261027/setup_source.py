try:
    """Runs once as root after the user launches the installer over SSH."""
    import grp
    import hashlib
    import json
    import os
    from pathlib import Path
    import platform
    import pwd
    import re
    import secrets
    import shutil
    import socket
    import stat
    import subprocess
    import sys
    import time
    import urllib.request
    import http.client
    import ssl

    payload = json.load(sys.stdin)
    owner = pwd.getpwuid(payload["uid"])
    if os.geteuid() != 0 or owner.pw_name != "yc-user" or owner.pw_dir != "/home/yc-user":
        raise SystemExit("Этот установщик предназначен для yc-user на указанной ВМ.")
    home = Path(owner.pw_dir)
    if home.is_symlink() or home.resolve() != home or home.stat().st_uid != owner.pw_uid:
        raise SystemExit("Неожиданный домашний каталог; очистка не выполнялась.")
    if not Path("/run/systemd/system").is_dir():
        raise SystemExit("Нужна ВМ с systemd; очистка не выполнялась.")
    exec(payload["cleanup_source"])
    exec(payload["units_source"])
    exec(payload["network_source"])
    actual_id = metadata("instance/id")
    if actual_id != "fv4i5mtgkh5k870680fi":
        raise SystemExit("Это другая ВМ; установку и очистку не выполнял.")
    ip = public_ip()

    install = Path("/opt/vm-lab")
    control = Path("/etc/vm-lab")
    state = Path("/var/lib/vm-lab")
    work = state / "work"
    marker = control / "installed.json"
    staged = control / "staged.json"
    units = ["vm-lab-worker.service", "vm-lab-api.service", "vm-lab-cert-renew.timer"]

    def command(argv, **kw):
        return subprocess.run(argv, check=True, **kw)

    def atomic(path, data, mode=0o644, uid=0, gid=0):
        temp = path.with_name("."+path.name+"-"+secrets.token_hex(6))
        fd = os.open(temp, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, mode)
        with os.fdopen(fd, "wb") as f:
            f.write(data.encode() if isinstance(data,str) else data)
            f.flush()
            os.fsync(f.fileno())
            os.fchmod(f.fileno(),mode)
            os.fchown(f.fileno(),uid,gid)
        os.replace(temp,path)

    def rpc(url, method, params=None):
        req = urllib.request.Request(url, json.dumps({"jsonrpc":"2.0", "id":1, "method":method,
                "params":params or {}}).encode(), headers={"Content-Type":"application/json", "Accept":"application/json, text/event-stream"})
        if url.startswith("https://"):
            # Yandex NAT need not support connecting to our own public IP. Connect
            # locally while still verifying the public IP's real certificate/SAN.
            connection = http.client.HTTPSConnection(ip, 443, timeout=12)
            context = ssl.create_default_context()
            connection.sock = context.wrap_socket(socket.create_connection(("127.0.0.1",443),12), server_hostname=ip)
            try:
                connection.request("POST", urllib.parse.urlsplit(url).path, req.data, dict(req.header_items()))
                response = connection.getresponse()
                if response.status != 200:
                    raise RuntimeError("HTTPS API: HTTP " + str(response.status))
                result = json.loads(response.read())["result"]
            finally:
                connection.close()
        else:
            with urllib.request.urlopen(req, timeout=12) as response:
                result = json.load(response)["result"]
        if result.get("isError"):
            raise RuntimeError(result["content"][0]["text"])
        return result

    def call(url, name, **args):
        return json.loads(rpc(url, "tools/call", {"name":name, "arguments":args})["content"][0]["text"])

    def show(url, resources, cleaned):
        print("\nУСТАНОВЛЕНО: HTTPS, запись кода, Python и фоновые задания проверены на ВМ.", flush=True)
        print("CPU для расчёта: %s; память для расчёта: %.1f ГБ." % (resources["threads"], resources["memory_limit_mib"]/1024), flush=True)
        if cleaned:
            print("Старые файлы yc-user и прежний мост удалены. SSH и система сохранены.", flush=True)
        print("Рабочая папка: /var/lib/vm-lab/work", flush=True)
        print("\nПлагины → + → Add custom MCP server", flush=True)
        print("Название: VM Compute | Authentication: No authentication", flush=True)
        print("Server URL — копируй следующую строку только в поле плагина:", flush=True)
        print(url, flush=True)
        print("Создай и установи плагин; затем выбери @VM Compute в чате.", flush=True)
        print("Ссылка содержит ключ доступа. Не присылай её в чат.", flush=True)
        print("\nПроцессы не зависят от открытого чата или SSH. Службы включены на автозапуск.", flush=True)
        if config.get("ip_reservation", {}).get("reserved"):
            print("Публичный IP закреплён в Яндексе. Туннеля нет.", flush=True)
        else:
            print("Закрепление IP не подтверждено: Яндекс Cloud → VPC → IP-адреса → "+ip+" → Сделать статическим.",flush=True)
        print("Открой в браузере https://"+ip+"/healthz — должен появиться VM Compute.",flush=True)
        print("Если браузер не подключается: во входящих правилах группы безопасности ВМ разреши TCP 80 и 443 из 0.0.0.0/0.",flush=True)
        print("Показать действующий адрес: sudo /usr/bin/python3 /opt/vm-lab/status.py", flush=True)

    previous_install = json.loads(marker.read_text()) if marker.is_file() else (json.loads(staged.read_text()) if staged.is_file() else {})
    if previous_install.get("version") == "4.0.0":
        installed=previous_install
        if installed.get("owner_uid")!=owner.pw_uid:
            raise SystemExit("Другая установленная среда; ничего не менял.")
        command(["systemctl","start",*units])
        config=json.loads((control/"server.json").read_text())
        if config["public_ip"] != ip:
            raise SystemExit("Публичный IP ВМ изменился. Нужен перевыпуск сертификата; данные расчётов сохранены.")
        url="https://"+ip+"/"+config["token"]+"/mcp"
        rpc(url,"ping")
        show(url,config["resources"],False)
        raise SystemExit(0)

    print("1/4. Готовлю прямой API на "+ip+" и зависимости…",flush=True)
    for reserved_port in (80, 443):
        with socket.socket() as port_check:
            port_check.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            try:
                port_check.bind(("0.0.0.0",reserved_port))
            except OSError:
                raise RuntimeError("Порт "+str(reserved_port)+" уже занят. Нужен вывод: sudo ss -lntp '( sport = :80 or sport = :443 )'")
    for directory in (install,control,state):
        if directory.is_symlink():
            raise SystemExit("Недопустимая ссылка в каталоге установки; очистка не выполнялась.")
        directory.mkdir(mode=0o755,parents=True,exist_ok=True)
        if directory.stat().st_uid!=0:
            raise SystemExit("Каталог установки принадлежит не root; очистка не выполнялась.")

    env=dict(os.environ,DEBIAN_FRONTEND="noninteractive",NEEDRESTART_MODE="a")
    command(["apt-get","update","-qq"],env=env)
    command(["apt-get","install","-y","--no-install-recommends","python3-venv","ca-certificates",
             "python3-numpy","python3-scipy","python3-sympy","python3-matplotlib"],env=env)

    for username in ("vm-lab-api","vm-lab-runner"):
        try:
            user=pwd.getpwnam(username)
            if user.pw_uid>=1000 or user.pw_dir!="/nonexistent":
                raise RuntimeError("Имя служебного пользователя уже занято: "+username)
        except KeyError:
            command(["useradd","--system","--user-group","--home-dir","/nonexistent","--shell","/usr/sbin/nologin",username])
    try:
        lab_group=grp.getgrnam("vm-lab")
    except KeyError:
        command(["groupadd","--system","vm-lab"])
        lab_group=grp.getgrnam("vm-lab")
    api=pwd.getpwnam("vm-lab-api")
    runner=pwd.getpwnam("vm-lab-runner")
    for name in ("", "code", "data", "jobs", "results"):
        directory=work/name
        if directory.is_symlink():
            raise RuntimeError("Symlink in working directories")
        directory.mkdir(parents=True,exist_ok=True)
        os.chown(directory,runner.pw_uid,lab_group.gr_gid)
        directory.chmod(0o770)

    certbot = install/"certbot/bin/certbot"
    if not certbot.is_file():
        command(["/usr/bin/python3","-m","venv",str(install/"certbot")])
    command([str(install/"certbot/bin/python"),"-m","pip","install","--disable-pip-version-check","--no-cache-dir","certbot==5.8.0","acme==5.8.0"])
    atomic(install/"server.py",payload["server_source"])
    atomic(install/"worker.py",payload["worker_source"])
    atomic(install/"status.py",payload["status_source"])
    atomic(install/"deploy_cert.py",payload["deploy_cert_source"])
    atomic(install/"finalize.py",payload["finalize_source"])

    cpus=os.cpu_count() or 1
    threads=max(1,cpus-1)
    memory_mib=int(next(x.split()[1] for x in Path("/proc/meminfo").read_text().splitlines() if x.startswith("MemTotal:")))/1024
    limit_mib=max(256,int(min(memory_mib*.80,memory_mib-1024)))
    resources={"cpu_count":cpus,"threads":threads,"memory_total_mib":int(memory_mib),"memory_limit_mib":limit_mib}
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        port=sock.getsockname()[1]
    config={"root":str(work),"work":str(work),"ready_path":str(work/"api-ready.json"),
            "token":secrets.token_hex(32),"port":port,"resources":resources}
    config["public_ip"] = ip
    config["ip_reservation"] = reserve_ip(ip)
    atomic(control/"server.json",json.dumps(config),mode=0o600,uid=api.pw_uid,gid=lab_group.gr_gid)
    for name,content in make_units(threads,limit_mib,port=port).items():
        atomic(Path("/etc/systemd/system")/name,content)
    command(["systemd-analyze","verify",*["/etc/systemd/system/"+u for u in make_units(threads,limit_mib)]])
    command(["systemctl","daemon-reload"])
    subprocess.run(["systemctl","reset-failed",*units],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    command(["systemctl","restart","vm-lab-worker.service","vm-lab-api.service"])
    local="http://127.0.0.1:"+str(port)+"/"+config["token"]+"/mcp"
    for _ in range(60):
        try:
            if call(local,"work_status")["worker"]["responsive"]:
                break
        except Exception:
            pass
        time.sleep(.5)
    else:
        raise RuntimeError("Новая служба не запустилась; старые файлы не удалялись.")

    print("2/4. Проверяю запись, Python, результат и ограничения доступа…",flush=True)
    probe = "import json, os, pathlib, socket\nimport numpy as np, scipy, sympy, matplotlib\nassert os.getuid() not in (0, OWNER_UID)\ntry:\n    ssh_visible = pathlib.Path('/home/yc-user/.ssh').exists()\nexcept PermissionError:\n    ssh_visible = False\nassert not ssh_visible\ntry:\n    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)\nexcept OSError:\n    pass\nelse:\n    sock.close()\n    raise AssertionError('Network access unexpectedly allowed')\nfor p in ['/etc/vm-lab-test-denied','/opt/vm-lab/test-denied']:\n    try:\n        fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)\n    except OSError:\n        pass\n    else:\n        os.close(fd)\n        pathlib.Path(p).unlink()\n        raise AssertionError('OS unexpectedly writable')\nassert abs(np.linalg.det(np.array([[2.,1.],[1.,2.]]))-3.)<1e-10\npathlib.Path('selftest.json').write_text(json.dumps({'status':'PASS','numpy':np.__version__,'scipy':scipy.__version__,'uid':os.getuid()}))\nprint('SELFTEST PASS',flush=True)\n".replace('OWNER_UID', str(owner.pw_uid))
    jid="install_"+secrets.token_hex(8)
    wrote=call(local,"write_work_file",path="code/"+jid+".py",text=probe)
    call(local,"start_python_job",path=wrote["path"],sha256=wrote["sha256"],request_id=jid)
    for _ in range(120):
        result=call(local,"job_status",job_id=jid)
        if result["state"] not in ("queued","running"):
            break
        time.sleep(.5)
    if result["state"]!="completed":
        print("Статус задания: "+json.dumps(result,ensure_ascii=False),flush=True)
        try:
            print(call(local,"read_work_file",path=result["log_path"])["text"],flush=True)
        except Exception:
            pass
        raise RuntimeError("Самопроверка не прошла; старые файлы не удалялись.")
    assert json.loads(call(local,"read_work_file",path=result["results_path"]+"/selftest.json")["text"])["status"]=="PASS"

    print("3/4. Получаю HTTPS-сертификат для IP и включаю прямой доступ…",flush=True)
    if shutil.which("ufw"):
        firewall = subprocess.run(["ufw","status"],capture_output=True,text=True,env=dict(os.environ,LC_ALL="C"))
        if "Status: active" in firewall.stdout:
            command(["ufw","allow","80/tcp"])
            command(["ufw","allow","443/tcp"])
    certificate_command = [str(certbot),"certonly","--non-interactive","--agree-tos",
        "--register-unsafely-without-email","--no-eff-email","--standalone","--http-01-address","0.0.0.0",
        "--preferred-challenges","http","--preferred-profile","shortlived","--ip-address",ip,
        "--cert-name","vm-lab","--keep-until-expiring",
        "--config-dir","/etc/vm-lab/acme","--work-dir","/var/lib/vm-lab/acme","--logs-dir","/var/log/vm-lab-acme",
        "--deploy-hook","/usr/bin/python3 /opt/vm-lab/deploy_cert.py"]
    try:
        command(certificate_command,timeout=240)
    except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as error:
        raise RuntimeError("Сертификат не получен. Проверь ошибку выше. При timeout/connection refused: в группе безопасности ВМ разреши входящие TCP 80 и 443 из 0.0.0.0/0 и повтори эту же команду установки.") from error
    # Explicit deployment also covers an already valid certificate on a retry.
    command(["/usr/bin/python3",str(install/"deploy_cert.py")])
    config.update(bind="0.0.0.0",port=443,tls_cert="/etc/vm-lab/fullchain.pem",tls_key="/etc/vm-lab/privkey.pem")
    atomic(control/"server.json",json.dumps(config),mode=0o600,uid=api.pw_uid,gid=lab_group.gr_gid)
    command(["systemctl","restart","vm-lab-api.service"])
    public="https://"+ip+"/"+config["token"]+"/mcp"
    for _ in range(30):
        try:
            if rpc(public,"initialize")["serverInfo"]["version"]=="4.0.0":
                break
        except Exception:
            pass
        time.sleep(.5)
    else:
        raise RuntimeError("HTTPS-служба не прошла проверку сертификата и MCP.")
    names={t["name"] for t in rpc(public,"tools/list")["tools"]}
    if not {"write_work_file","start_python_job","job_status","read_work_file"}<=names:
        raise RuntimeError("Через HTTPS доступны не все инструменты; очистка не выполнялась.")
    assert call(public,"job_status",job_id=jid)["state"]=="completed"
    command(["systemctl","enable","--now",*units])
    command(["systemctl","is-active",*units])


    atomic(staged,json.dumps({"owner_uid":owner.pw_uid,"version":"4.0.0","staged":time.time()}),mode=0o600)
    print("Проверка на ВМ пройдена. Теперь установщик проверит порт 443 с Мака и выполнит очистку.",flush=True)

except Exception as exc:
    import subprocess
    print("Ошибка установки: "+str(exc),flush=True)
    subprocess.run(["journalctl","-u","vm-lab-worker.service","-u","vm-lab-api.service","-n","14","--no-pager"])
    subprocess.run(["systemctl","stop","vm-lab-api.service","vm-lab-worker.service"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    print("Очистка старых файлов не начиналась.",flush=True)
    raise SystemExit(1)
