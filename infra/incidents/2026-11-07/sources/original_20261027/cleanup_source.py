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
