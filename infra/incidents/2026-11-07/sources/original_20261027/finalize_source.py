import json, os, pwd, re, shutil, subprocess, sys, time
from pathlib import Path
if os.geteuid()!=0:
    raise SystemExit("Запускать через sudo")
owner=pwd.getpwnam("yc-user")
home=Path(owner.pw_dir)
if str(home)!="/home/yc-user" or home.is_symlink() or home.stat().st_uid!=owner.pw_uid:
    raise SystemExit("Неожиданный домашний каталог")
control=Path("/etc/vm-lab")
state=Path("/var/lib/vm-lab")
marker=control/"installed.json"
stage=json.loads((control/"staged.json").read_text()) if (control/"staged.json").exists() else {}
if marker.exists() and json.loads(marker.read_text()).get("version")=="4.0.0":
    subprocess.run(["/usr/bin/python3","/opt/vm-lab/status.py"],check=True)
    raise SystemExit(0)
if stage.get("owner_uid")!=owner.pw_uid or stage.get("version")!="4.0.0":
    raise SystemExit("Нет успешно проверенной установки; очистку не выполнял")
subprocess.run(["systemctl","is-active","--quiet","vm-lab-api.service","vm-lab-worker.service","vm-lab-cert-renew.timer"],check=True)
def command(argv,**kw):
    return subprocess.run(argv,check=True,**kw)
def atomic(path,data,mode=0o600):
    import secrets
    tmp=path.with_name("."+path.name+"-"+secrets.token_hex(6))
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,"w") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp,path)
"""Cleanup authorized by the owner; never follows links outside their home."""
KEEP_HOME = frozenset({".ssh", ".bashrc", ".bash_profile", ".bash_logout", ".profile",
                      ".zshrc", ".zprofile", ".zlogout", ".inputrc", ".pam_environment",
                      ".sudo_as_admin_successful", ".Xauthority", ".ICEauthority"})

def cleanup_home(home, mountpoints=()):
    from pathlib import Path
    import shutil
    home = Path(home)
    if home.is_symlink() or not home.is_absolute() or home.name != "yc-user" or home == Path("/"):
        raise ValueError("Refusing unexpected home path")
    mounts = [Path(p) for p in mountpoints]
    removed, skipped, errors = [], [], []
    for entry in sorted(home.iterdir()):
        if entry.name in KEEP_HOME:
            continue
        if not entry.is_symlink() and any(p == entry or p.is_relative_to(entry) for p in mounts):
            skipped.append(str(entry))
            continue
        try:
            if entry.is_symlink() or not entry.is_dir():
                entry.unlink()
            else:
                shutil.rmtree(entry)
            removed.append(str(entry))
        except OSError as exc:
            errors.append({"path":str(entry), "error":str(exc)})
    return {"removed":removed, "mounted_paths_skipped":skipped, "errors":errors}

def ancestor_pids():
    from pathlib import Path
    import os
    ids = set()
    pid = os.getpid()
    while pid > 0 and pid not in ids:
        ids.add(pid)
        try:
            text = Path(f"/proc/{pid}/stat").read_text()
            pid = int(text.rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return ids

def stop_old_work(owner):
    from pathlib import Path
    import json
    import os
    import re
    import signal
    import subprocess
    import time
    protected = ancestor_pids()
    # Stop only locally installed system services explicitly running as yc-user
    # and referencing that user's old files. Vendor/SSH services are excluded.
    listed = subprocess.run(["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--plain"],
                            capture_output=True, text=True)
    stopped = []
    for line in listed.stdout.splitlines():
        unit = line.split()[0] if line.split() else ""
        if not re.fullmatch(r"[A-Za-z0-9_.@:-]+\.service", unit) or unit.startswith("vm-lab-"):
            continue
        props = subprocess.run(["systemctl", "show", unit, "-p", "User", "-p", "FragmentPath", "-p", "ExecStart"],
                               capture_output=True, text=True)
        values = dict(x.split("=",1) for x in props.stdout.splitlines() if "=" in x)
        if (values.get("User") == owner.pw_name and
            values.get("FragmentPath", "").startswith("/etc/systemd/system/") and
            owner.pw_dir + "/" in values.get("ExecStart", "")):
            subprocess.run(["systemctl", "disable", "--now", unit], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            stopped.append(unit)
    subprocess.run(["systemctl", "disable", "--now", "chatgpt-research.service"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Stop old user computations, but preserve the current SSH/installer ancestry,
    # the user session manager and authentication agents.
    victims = []
    for directory in Path("/proc").iterdir():
        if not directory.name.isdigit() or int(directory.name) in protected:
            continue
        try:
            if directory.stat().st_uid != owner.pw_uid:
                continue
            command = (directory / "cmdline").read_bytes().split(b"\0")
            executable = Path(os.fsdecode(command[0])).name if command[0] else ""
            if executable in {"sshd", "systemd", "(sd-pam)", "dbus-daemon", "dbus-broker",
                              "ssh-agent", "gpg-agent", "gnome-keyring-daemon"}:
                continue
            pid = int(directory.name)
            start = (directory / "stat").read_text().rsplit(")",1)[1].split()[19]
            os.kill(pid, signal.SIGTERM)
            victims.append((pid,start))
        except (OSError, ValueError, IndexError):
            continue
    time.sleep(1)
    for pid,start in victims:
        try:
            now = Path(f"/proc/{pid}/stat").read_text().rsplit(")",1)[1].split()[19]
            if now == start:
                os.kill(pid, signal.SIGKILL)
        except (OSError, ValueError, IndexError):
            pass
    if Path("/usr/bin/crontab").exists():
        subprocess.run(["crontab", "-u", owner.pw_name, "-r"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"services_stopped":stopped, "old_user_processes_stopped":len(victims), "user_crontab_removed":True}

print("4/4. Проверки прошли. Удаляю старые пользовательские файлы и прежний мост…",flush=True)
stopped=stop_old_work(owner)
subprocess.run(["systemctl","disable","--now","vm-lab-tunnel.service"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
mounts=[]
for line in Path("/proc/self/mountinfo").read_text().splitlines():
    fields=line.split()
    if len(fields)>4:
        path=re.sub(r"\\([0-7]{3})",lambda m:chr(int(m.group(1),8)),fields[4])
        mounts.append(path)
cleaned=cleanup_home(home,mounts)
for old in (Path("/var/lib/chatgpt-vm-work"),Path("/opt/chatgpt-vm-runner"),
            Path("/etc/systemd/system/chatgpt-research.service.d"),Path("/etc/systemd/system/chatgpt-research.service")):
    try:
        if old.is_symlink() or old.is_file():
            old.unlink()
        elif old.is_dir():
            shutil.rmtree(old)
    except OSError as exc:
        cleaned["errors"].append({"path":str(old),"error":str(exc)})
command(["systemctl","daemon-reload"])
report={**cleaned,**stopped,"time":time.time(),"owner_uid":owner.pw_uid}
atomic(state/"cleanup-report.json",json.dumps(report,ensure_ascii=False,indent=2),mode=0o600)
atomic(marker,json.dumps({"owner_uid":owner.pw_uid,"version":"4.0.0","installed":time.time()}),mode=0o600)

if cleaned["errors"] or cleaned["mounted_paths_skipped"]:
    print("Часть очистки пропущена. Отчёт: sudo cat /var/lib/vm-lab/cleanup-report.json",flush=True)
else:
    print("ГОТОВО. Старые файлы yc-user удалены. SSH и Ubuntu сохранены.",flush=True)
print("Название нового плагина: VM Compute. После добавления выбери его в чате.",flush=True)
subprocess.run(["/usr/bin/python3","/opt/vm-lab/status.py"],check=True)
