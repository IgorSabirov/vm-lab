"""Build a deterministic combined archive using one working tree per research branch."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


A = Path("analysis")
R136 = A / "R136_SHIROGANE_CALIBRATION"
R140 = A / "R140_HAAR_SORKIN"
PUB = R140 / "publication"
REG = A / "NOW_RESULTS_SYNTHESIS_20261106"
PACK_FILES = ("README.md", "PRIMARY_SOURCES.json", "DONOR_SOURCES.json", "replay.py", "requirements.txt", "build.py")

def json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode()


def build(roots, destination):
    content, inventory = {}, {}

    def add(name, data, source, path=None):
        key = str(name)
        if key in content:
            raise ValueError(f"Duplicate archive path {key}")
        content[key] = data
        inventory[key] = {"source": source, "path": str(path or name), "bytes": len(data),
                          "sha256": sha256(data).hexdigest()}

    def copy(source, name, dest=None):
        add(dest or name, (roots[source] / name).read_bytes(), source, name)

    for source, branch_dir in (("R136", R136), ("R140", R140)):
        root = roots[source]
        for path in sorted((root / branch_dir).rglob("*")):
            name = path.relative_to(root)
            if not path.is_file() or "__pycache__" in name.parts or PUB in name.parents:
                continue
            if name == R140 / "R140_reproduction.zip":
                continue
            copy(source, name)
        for ext in (".md", ".json"):
            copy(source, REG / (source + ext))
    for name in PACK_FILES:
        copy("R140", PUB / name)
    question = next(x for x in json.loads((roots["R136"] / REG / "OPEN_QUESTIONS.json").read_bytes())["questions"]
                    if x["id"] == "U013")
    add("registries/U013.json", json_bytes(question), "R136", REG / "OPEN_QUESTIONS.json#U013")
    add("README.md", (roots["R140"] / PUB / "README.md").read_bytes(), "publication", PUB / "README.md")
    content["INVENTORY.json"] = json_bytes(inventory)
    content["MANIFEST.sha256"] = "".join(f"{sha256(data).hexdigest()}  {name}\n"
        for name, data in sorted(content.items())).encode()
    with ZipFile(destination, "w") as out:
        for name, data in sorted(content.items()):
            info = ZipInfo(name, (2026, 11, 22, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            out.writestr(info, data, compress_type=ZIP_DEFLATED, compresslevel=9)
    print(len(content), destination.stat().st_size, sha256(destination.read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("r136_checkout", type=Path)
    parser.add_argument("r140_checkout", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    build({"R136": args.r136_checkout, "R140": args.r140_checkout}, args.destination)
