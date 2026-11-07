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
    exec(payload["units_source"])
    exec(payload["network_source"])
    actual_id = metadata("instance/id")
    if actual_id != "fv4i5mtgkh5k870680fi":
        raise SystemExit("Это другая ВМ; установку и очистку не выполнял.")
    ip = public_ip()
    host = "vm-" + ip.replace(".", "-") + ".sslip.io"

    install = Path("/opt/vm-compute")
    control = Path("/etc/vm-compute")
    state = Path("/var/lib/vm-compute")
    work = state / "work"
    marker = control / "installed.json"
    staged = control / "staged.json"
    units = ["vm-compute-worker.service", "vm-compute-api.service", "vm-compute-cert-renew.timer"]

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
            connection = http.client.HTTPSConnection(host, 443, timeout=12)
            context = ssl.create_default_context()
            connection.sock = context.wrap_socket(socket.create_connection(("127.0.0.1",443),12), server_hostname=host)
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

    print("Новая установка VM Compute: " + host, flush=True)
    # Stop the previous bridge; SSH and the OS stay running.
    for unit in ("vm-lab-cert-renew.timer", "vm-lab-bridge-maintain.timer",
                 "vm-lab-api.service", "vm-lab-worker.service",
                 "vm-compute-cert-renew.timer", "vm-compute-api.service", "vm-compute-worker.service"):
        subprocess.run(["systemctl", "disable", "--now", unit],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40)
    for unit in ("vm-lab-cert-renew.service", "vm-lab-bridge-maintain.service", "vm-compute-cert-renew.service"):
        subprocess.run(["systemctl", "stop", unit],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40)
    # Each run gets empty installation/configuration/work directories.
    suffix = ".previous-" + str(time.time_ns())
    for directory in (install, control, state):
        if directory.is_symlink():
            raise RuntimeError("Unexpected symlink: " + str(directory))
        if directory.exists():
            directory.rename(directory.with_name(directory.name + suffix))

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
    command(["apt-get","update","-qq","-o","Acquire::Retries=0","-o","Acquire::http::Timeout=20","-o","Acquire::https::Timeout=20"],env=env,timeout=120)
    command(["apt-get","install","-y","--no-install-recommends","python3-venv","ca-certificates",
             "python3-numpy","python3-scipy","python3-sympy","python3-matplotlib"],env=env,timeout=300)

    for username in ("vm-compute-api","vm-compute-runner"):
        try:
            user=pwd.getpwnam(username)
            if user.pw_uid>=1000 or user.pw_dir!="/nonexistent":
                raise RuntimeError("Имя служебного пользователя уже занято: "+username)
        except KeyError:
            command(["useradd","--system","--user-group","--home-dir","/nonexistent","--shell","/usr/sbin/nologin",username])
    try:
        lab_group=grp.getgrnam("vm-compute")
    except KeyError:
        command(["groupadd","--system","vm-compute"])
        lab_group=grp.getgrnam("vm-compute")
    api=pwd.getpwnam("vm-compute-api")
    runner=pwd.getpwnam("vm-compute-runner")
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
    command([str(install/"certbot/bin/python"),"-m","pip","install","--disable-pip-version-check","--no-cache-dir","--retries","0","--timeout","20","certbot==5.8.0","acme==5.8.0"],timeout=180)
    atomic(install/"server.py",payload["server_source"])
    atomic(install/"worker.py",payload["worker_source"])
    atomic(install/"status.py",payload["status_source"])
    atomic(install/"deploy_cert.py",payload["deploy_cert_source"])

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
    config["ip_reservation"] = {"reserved": False, "reason": "Dynamic IP requested"}
    atomic(control/"server.json",json.dumps(config),mode=0o600,uid=api.pw_uid,gid=lab_group.gr_gid)
    for name,content in make_units(threads,limit_mib,port=port).items():
        atomic(Path("/etc/systemd/system")/name,content)
    command(["systemd-analyze","verify",*["/etc/systemd/system/"+u for u in make_units(threads,limit_mib)]])
    command(["systemctl","daemon-reload"])
    subprocess.run(["systemctl","reset-failed",*units],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    command(["systemctl","restart","vm-compute-worker.service","vm-compute-api.service"])
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
    probe = "import json, os, pathlib, socket\nimport numpy as np, scipy, sympy, matplotlib\nassert os.getuid() not in (0, OWNER_UID)\ntry:\n    ssh_visible = pathlib.Path('/home/yc-user/.ssh').exists()\nexcept PermissionError:\n    ssh_visible = False\nassert not ssh_visible\ntry:\n    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)\nexcept OSError:\n    pass\nelse:\n    sock.close()\n    raise AssertionError('Network access unexpectedly allowed')\nfor p in ['/etc/vm-compute-test-denied','/opt/vm-compute/test-denied']:\n    try:\n        fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)\n    except OSError:\n        pass\n    else:\n        os.close(fd)\n        pathlib.Path(p).unlink()\n        raise AssertionError('OS unexpectedly writable')\nassert abs(np.linalg.det(np.array([[2.,1.],[1.,2.]]))-3.)<1e-10\npathlib.Path('selftest.json').write_text(json.dumps({'status':'PASS','numpy':np.__version__,'scipy':scipy.__version__,'uid':os.getuid()}))\nprint('SELFTEST PASS',flush=True)\n".replace('OWNER_UID', str(owner.pw_uid))
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
        "--preferred-challenges","http","--preferred-profile","shortlived","--ip-address",ip,"-d",host,
        "--cert-name","vm-compute","--keep-until-expiring",
        "--config-dir","/etc/vm-compute/acme","--work-dir","/var/lib/vm-compute/acme","--logs-dir","/var/log/vm-compute-acme",
        "--deploy-hook","/usr/bin/python3 /opt/vm-compute/deploy_cert.py"]
    try:
        command(certificate_command,timeout=240)
    except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as error:
        raise RuntimeError("Новый API и расчётный worker установлены, но HTTPS-сертификат не выдан. Доступ из ChatGPT ещё не готов. Ошибка центра сертификации приведена выше.") from error
    # Explicit deployment also covers an already valid certificate on a retry.
    command(["/usr/bin/python3",str(install/"deploy_cert.py")])
    config.update(bind="0.0.0.0",port=443,tls_cert="/etc/vm-compute/fullchain.pem",tls_key="/etc/vm-compute/privkey.pem")
    atomic(control/"server.json",json.dumps(config),mode=0o600,uid=api.pw_uid,gid=lab_group.gr_gid)
    command(["systemctl","restart","vm-compute-api.service"])
    public="https://"+host+"/"+config["token"]+"/mcp"
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


    atomic(marker,json.dumps({"owner_uid":owner.pw_uid,"version":"4.0.0","installed":time.time()}),mode=0o600)
    print("ГОТОВО: новая установка, тест расчёта, HTTPS и MCP на ВМ прошли проверку.",flush=True)
    print("URL ДЛЯ ПЛАГИНА: " + public,flush=True)
    print("Название: VM Compute. Аутентификация: без аутентификации.",flush=True)

except Exception as exc:
    import subprocess
    print("Ошибка установки: "+str(exc),flush=True)
    subprocess.run(["journalctl","-u","vm-compute-worker.service","-u","vm-compute-api.service","-n","14","--no-pager"])
    subprocess.run(["systemctl","stop","vm-compute-api.service","vm-compute-worker.service"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    print("Новая установка НЕ завершена. SSH доступен.",flush=True)
    raise SystemExit(1)
