#!/usr/bin/env python3
"""Publish the complete X26 v0.3 main scientific output to private GitHub.

Run on the VM HOST (not inside the isolated scientific worker), from a checkout
containing this file, with root access to /etc/vm-lab-sync/config.json.

Reads only the pinned X26 main output; validates every file against the final
artifact manifest pinned in GitHub; publishes original bytes (including NPZ)
with git; never modifies VM data, recomputes science, or force-pushes.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile

REPOSITORY = "IgorSabirov/vm-lab"
RUN = "x26_v3_main_54f8e7d_20261109"
SOURCE_COMMIT = "54f8e7d6974b2059b150214021dc74a5ce6e2583"
SOURCE_REF = "cb8780fc8857fa036e456b63718030dbb37a4130"
SOURCE_RECEIPT = (
    "analysis/X26_R040_ANALYTIC_BATH_20261109/PHYSICAL_V3_20261109/"
    "INTEGRITY_REVIEW/MAIN_FINAL_ARTIFACT_MANIFEST.json"
)
WORK = Path("/var/lib/vm-compute/work")
SOURCE_ROOT = Path("results") / RUN / "output"
DEST = "results/X26_V3_MAIN_54f8e7d6_20261109_RAW"
CONFIG = Path("/etc/vm-lab-sync/config.json")
LOCK = Path("/run/lock/x26-v3-raw-publication.lock")

EXPECTED_JSON_ROWS = 249
EXPECTED_NPZ_ROWS = 156
EXPECTED_ROW_BYTES = 50_328_986
MAX_FILES = 500
MAX_SINGLE_FILE = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 70 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_REMOTES = {
    "ssh://git@ssh.github.com:443/IgorSabirov/vm-lab.git",
    "git@github.com:IgorSabirov/vm-lab.git",
}

README = """# X26 v0.3 — полный сырой результат основного прогона

Каталог содержит байт-в-байт экспорт output с ВМ. Ничего не пересчитывалось,
NPZ не распаковывались и не пересжимались.

## Состав

- 249 подробных JSON строк опыта;
- 156 NPZ: cycle-матрицы и ramp-векторы;
- 12 файлов output-корня: подготовка, среда, checkpoint, runtime gate,
  preflight, process/launcher receipts, output manifest, результаты,
  индекс строк, тайминги и workload;
- PUBLICATION_MANIFEST.json с SHA-256, размерами и Git blob SHA каждого файла.

## Содержимое NPZ

Cycle: rho_load, rho_after, rho_final, H_before, H_after, T, P_before, P_after.
Ramp: times, ket. Это сохранённая сетка вывода, не все внутренние шаги решателя.

В cycle NPZ нет полной временной серии матриц плотности во время загрузки.
JSON содержит сохранённые ряды населения, энергии и норм. Отсутствующие
промежуточные фазы по одним населённостям восстановить нельзя.

## Назначение

- D01: отличить сохранение защищённого состояния от простого заселения сектора;
- D02: разобрать спад тёмного населения и отдельно проверить ресурсный учёт;
- D03: сопоставить движущийся проектор, leakage и bath population.

Население сектора само по себе не доказывает сохранение исходной матрицы.
Условия модели и границы описаны в соседнем X26 RESULT.md.

Квитанция закреплена на commit cb8780fc8857fa036e456b63718030dbb37a4130.
Исходный прогон: 54f8e7d6974b2059b150214021dc74a5ce6e2583.
"""

def sha256(data):
    return hashlib.sha256(data).hexdigest()


def safe_relative(name):
    p = PurePosixPath(name)
    if (
        not name or p.is_absolute() or str(p) != name
        or any(
            part in ("", ".", "..") or part.startswith(".") or len(part) > 200
            or any(ord(ch) < 32 for ch in part)
            for part in p.parts
        )
    ):
        raise ValueError("Unsafe relative path: " + repr(name))
    return p


def read_regular(path, limit=MAX_SINGLE_FILE):
    path = Path(path)
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError("Symlink refused: " + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > limit
        ):
            raise ValueError("Expected bounded regular non-hardlinked file: " + str(path))
        data = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
    if len(data) > limit or (
        before.st_size, before.st_mtime_ns, before.st_ctime_ns
    ) != (
        after.st_size, after.st_mtime_ns, after.st_ctime_ns
    ) or len(data) != before.st_size:
        raise ValueError("File changed or exceeds limit: " + str(path))
    return data


def walk_regular_files(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Expected real output directory: " + str(root))
    found = {}

    def walk(directory, prefix):
        for entry in sorted(directory.iterdir(), key=lambda p: p.name):
            if entry.name.startswith(".") or any(ord(c) < 32 for c in entry.name):
                raise ValueError("Unexpected hidden/unsafe path: " + str(entry))
            if entry.is_symlink():
                raise ValueError("Symlink refused: " + str(entry))
            rel = (prefix / entry.name) if prefix else PurePosixPath(entry.name)
            rel_s = rel.as_posix()
            safe_relative(rel_s)
            if entry.is_dir():
                walk(entry, rel)
            elif entry.is_file():
                found[rel_s] = entry
            else:
                raise ValueError("Non-regular output entry: " + str(entry))

    walk(root, PurePosixPath())
    return found


class Git:
    def __init__(self, git_dir, config):
        self.git_dir = str(git_dir)
        self.env = {
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_SSH_COMMAND": config["ssh_command"],
            "GIT_AUTHOR_NAME": "VM Compute",
            "GIT_AUTHOR_EMAIL": "vm-compute@users.noreply.github.com",
            "GIT_COMMITTER_NAME": "VM Compute",
            "GIT_COMMITTER_EMAIL": "vm-compute@users.noreply.github.com",
        }
        self("init", "--bare", self.git_dir)
        self("remote", "add", "origin", config["remote"])

    def __call__(self, *args, data=None, extra_env=None, check=True):
        command = [
            "/usr/bin/git",
            "-c", "core.hooksPath=/dev/null",
            "-c", "gc.auto=0",
            "-c", "protocol.ext.allow=never",
            "-c", "protocol.file.allow=never",
            "--git-dir=" + self.git_dir,
            *args,
        ]
        result = subprocess.run(
            command, input=data, env={**self.env, **(extra_env or {})},
            capture_output=True, timeout=900
        )
        if check and result.returncode:
            raise RuntimeError(
                "git " + (args[0] if args else "command")
                + " failed (code " + str(result.returncode) + ")"
            )
        return result.stdout if check else result

    def tree(self, commit):
        result = {}
        raw = self("ls-tree", "-rz", "--full-tree", commit, "--", DEST)
        for item in raw.split(b"\0"):
            if item:
                meta, name = item.split(b"\t", 1)
                mode, kind, oid = meta.decode("ascii").split()
                result[name.decode("utf-8")] = (mode, kind, oid)
        return result


def fetch_pinned_receipt(git):
    git("fetch", "--no-tags", "--depth=1", "origin", SOURCE_REF)
    actual = git("rev-parse", "FETCH_HEAD").decode().strip()
    if actual != SOURCE_REF:
        raise ValueError("Pinned X26 source ref mismatch")
    raw = git("show", "FETCH_HEAD:" + SOURCE_RECEIPT)
    receipt = json.loads(raw)
    if receipt.get("root") != SOURCE_ROOT.as_posix():
        raise ValueError("Pinned artifact manifest points to another output root")
    if receipt.get("original_files_modified") is not False:
        raise ValueError("Pinned artifact receipt does not attest original files")
    expected = receipt.get("sha256")
    if not isinstance(expected, dict) or len(expected) != 417:
        raise ValueError("Unexpected pinned X26 artifact count")
    for name, digest in expected.items():
        safe_relative(name)
        if not SHA256_RE.fullmatch(digest):
            raise ValueError("Malformed SHA-256 in pinned artifact receipt: " + name)
    return expected, sha256(raw)


def collect(work, expected):
    root = work / SOURCE_ROOT
    actual = walk_regular_files(root)
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))[:5]
        extra = sorted(set(actual) - set(expected))[:5]
        raise ValueError(
            "X26 inventory differs from pinned receipt; missing="
            + repr(missing) + "; extra=" + repr(extra)
        )
    if len(actual) > MAX_FILES:
        raise ValueError("X26 file count exceeds export cap")

    row_names = [name for name in actual if name.startswith("rows/")]
    json_rows = [name for name in row_names if name.endswith(".json")]
    npz_rows = [name for name in row_names if name.endswith("_states.npz")]
    if (
        len(row_names) != EXPECTED_JSON_ROWS + EXPECTED_NPZ_ROWS
        or len(json_rows) != EXPECTED_JSON_ROWS
        or len(npz_rows) != EXPECTED_NPZ_ROWS
    ):
        raise ValueError("X26 row JSON/NPZ counts differ from inventory snapshot")

    items, manifest = {}, {}
    total = row_total = 0
    for number, name in enumerate(sorted(actual), 1):
        data = read_regular(actual[name])
        digest = sha256(data)
        if digest != expected[name]:
            raise ValueError("SHA-256 mismatch against pinned receipt: " + name)
        total += len(data)
        if name.startswith("rows/"):
            row_total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("X26 package exceeds the 70 MiB export safety cap")
        oid = hashlib.sha1(
            b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        ).hexdigest()
        manifest[name] = {
            "bytes": len(data), "sha256": digest, "git_blob_sha1": oid
        }
        items[name] = data
        if number % 100 == 0:
            print("Verified", number, "/", len(actual), flush=True)

    if row_total != EXPECTED_ROW_BYTES:
        raise ValueError("X26 row byte count differs from recorded inventory")

    required = {
        "CASE_PREPARATION.json", "ENVIRONMENT.json", "PROCESS.json",
        "LAUNCH_PROCESS.json", "FROZEN_RUNTIME_GATE.json",
        "OUTPUT_MANIFEST.json", "RESULTS.json", "ROW_INDEX.json",
        "TASK_TIMINGS.json", "WORKLOAD.json", "CHECKPOINT.json",
        "PREFLIGHT.json",
    }
    if not required <= set(items):
        raise ValueError("Required X26 scientific receipts are missing")

    internal = json.loads(items["OUTPUT_MANIFEST.json"])
    if not isinstance(internal, dict):
        raise ValueError("OUTPUT_MANIFEST.json is not a mapping")
    for name, digest in internal.items():
        if name not in expected or expected[name] != digest:
            raise ValueError("Internal OUTPUT_MANIFEST disagrees with pinned receipt: " + name)

    launch = json.loads(items["LAUNCH_PROCESS.json"])
    if not (
        launch.get("mode") == "main"
        and launch.get("completed") == EXPECTED_JSON_ROWS
        and launch.get("planned") == EXPECTED_JSON_ROWS
        and launch.get("technical_pass") is True
        and launch.get("runtime_gate") == "PASS"
        and launch.get("exit_code") == 0
    ):
        raise ValueError("X26 launcher receipt does not describe the completed main run")

    results = json.loads(items["RESULTS.json"])
    if not (
        results.get("task_count") == EXPECTED_JSON_ROWS
        and results.get("planned") == EXPECTED_JSON_ROWS
        and results.get("technical_pass") is True
    ):
        raise ValueError("X26 RESULTS.json does not match the completed main run")

    return items, manifest, total, row_total, len(json_rows), len(npz_rows)


def publish(work=WORK, config_path=CONFIG):
    if os.geteuid() != 0:
        raise PermissionError("Run on VM host as root (sudo); not in the worker")
    config = json.loads(read_regular(config_path, 256 * 1024))
    if config.get("repository") != REPOSITORY:
        raise ValueError("Transport config points to another repository")
    if config.get("remote") not in ALLOWED_REMOTES:
        raise ValueError("Unexpected Git remote in transport config")

    with tempfile.TemporaryDirectory(prefix="x26-raw-publish-") as temp:
        git = Git(Path(temp) / "repo.git", config)
        expected, receipt_sha256 = fetch_pinned_receipt(git)
        items, file_manifest, total, row_total, json_count, npz_count = collect(work, expected)

        files = {DEST + "/output/" + name: data for name, data in items.items()}
        files[DEST + "/README.md"] = README.encode("utf-8")
        publication = {
            "schema": 1,
            "run_id": RUN,
            "source_commit": SOURCE_COMMIT,
            "artifact_receipt_ref": SOURCE_REF,
            "artifact_receipt_path": SOURCE_RECEIPT,
            "artifact_receipt_sha256": receipt_sha256,
            "source_output_root": SOURCE_ROOT.as_posix(),
            "destination": DEST,
            "files": file_manifest,
            "file_count": len(file_manifest),
            "row_counts": {"json": json_count, "npz": npz_count},
            "row_bytes": row_total,
            "total_source_bytes": total,
            "publication": (
                "Original bytes at output-relative paths; no recompression, "
                "encoding conversion, scientific computation or VM mutation."
            ),
            "scope": "Complete X26 v0.3 main output; excludes calibration raw, worker logs and secrets.",
        }
        files[DEST + "/PUBLICATION_MANIFEST.json"] = (
            json.dumps(publication, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")

        expected_tree = {}
        for number, (name, data) in enumerate(sorted(files.items()), 1):
            oid = git("hash-object", "-w", "--stdin", data=data).decode().strip()
            expected_tree[name] = ("100644", "blob", oid)
            if number % 100 == 0:
                print("Prepared Git blobs", number, "/", len(files), flush=True)

        # Re-read and re-hash the whole source before any remote write.
        check_items, _, check_total, _, _, _ = collect(work, expected)
        if check_total != total or set(check_items) != set(items):
            raise ValueError("X26 source inventory changed before publication")

        commit = None
        for attempt in range(3):
            git("fetch", "--no-tags", "--depth=1", "origin", "refs/heads/main")
            base = git("rev-parse", "FETCH_HEAD").decode().strip()
            existing = git.tree(base)
            if existing:
                if existing != expected_tree:
                    raise ValueError(
                        "Destination exists but differs; refusing to overwrite"
                    )
                commit = base
                break

            index = str(Path(temp) / ("index-" + str(attempt)))
            env = {"GIT_INDEX_FILE": index}
            try:
                git("read-tree", base, extra_env=env)
                for name, value in sorted(expected_tree.items()):
                    git(
                        "update-index", "--add", "--cacheinfo",
                        value[0], value[2], name, extra_env=env
                    )
                tree = git("write-tree", extra_env=env).decode().strip()
                if git.tree(tree) != expected_tree:
                    raise ValueError("Staged X26 tree verification failed")
                commit = git(
                    "commit-tree", tree, "-p", base,
                    data=b"Publish complete X26 v0.3 main raw output\n"
                ).decode().strip()
            finally:
                try:
                    os.unlink(index)
                except FileNotFoundError:
                    pass

            pushed = git(
                "push", "origin", commit + ":refs/heads/main", check=False
            )
            if pushed.returncode == 0:
                break
            # A race or lost acknowledgement is resolved from fresh main.

        if commit is None:
            raise RuntimeError("Push not confirmed after three safe attempts")

        git("fetch", "--no-tags", "--depth=1", "origin", "refs/heads/main")
        head = git("rev-parse", "FETCH_HEAD").decode().strip()
        if git.tree(head) != expected_tree:
            raise ValueError("Remote X26 tree differs from verified source snapshot")

        print("PUBLISHED_AND_VERIFIED", json.dumps({
            "commit": commit,
            "verified_main": head,
            "file_count": len(file_manifest),
            "published_paths": len(files),
            "source_bytes": total,
            "row_counts": {"json": json_count, "npz": npz_count},
            "row_bytes": row_total,
            "source_commit": SOURCE_COMMIT,
            "url": "https://github.com/" + REPOSITORY + "/tree/" + head + "/" + DEST,
        }, ensure_ascii=False), flush=True)


def main():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        publish()


if __name__ == "__main__":
    main()
