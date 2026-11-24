"""Build a preview of Gazettoa from the small examples of toa and a drawing demo.

    python gaze/scripts/examples.py [--toa-src DIR] [--toa EXE] [--rnl EXE] [--work DIR] [--out DIR]

1. The examples of toa (`toa/examples/`) are files without their git history; `toa index` reads git
   repositories. The conformance test of toa builds them again as repositories:
   `TOA_EXAMPLES_OUT=<work>/repos cargo test --release --test examples`, run in the toa source.
   This is skipped when <work>/repos is already there.
2. The examples have no symbols and no drawings. `scripts/demo/` holds the drafts of a small library
   that has both; they are sealed and published with `toa` into <work>/demo/gaze-demo, a git
   repository of its own (skipped when it is there). The library list then marks the latest
   generation of each series (`"latest": true`, TOA 5.2), as a maintainer would by hand, and
   `toa publish --keep-latest` keeps the marks. One object, `cmos-copy`, is published a day after
   the others, so that the site has a later object with the same files as an earlier one of another
   author (decision B35); it is left unmarked. That publication is committed by
   `toa publish --commit --sign`, signed with an SSH key made for the demo on the spot (B35, second
   step: the index records the format of the signature); without ssh-keygen it is not signed.
   Then `cmos.g1`, the original, gets a timestamp proof beside it (TOA 4.3): an RFC 3161 token for
   its name from a time-stamping service that openssl makes on the spot (its certificate is in
   <work>/demo/gaze-demo.keys/tsa/); without openssl there is none.
3. <work>/workspace.source.jsonl lists the five libraries by their local checkouts, and
   <work>/gaze.yaml names the preview; <work> is the instance.
4. `toa index --workspace <work>/workspace.source.jsonl --out <work>/index --offline`.
5. `python -m gaze build --instance <work> --index <work>/index --out <out> --local-files toa/examples
   --local-files <work>/demo`: the page reads the files of each library where they are on this
   machine, the examples from `toa/examples/` itself, through `scripts/serve.py`.

Then serve the site with the files beside it:
`python gaze/scripts/serve.py --site gaze/_site --local-files toa/examples --local-files gaze/.work/examples/demo`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

GAZE = Path(__file__).resolve().parent.parent
EXAMPLES = ["official", "lee", "alice", "official-chen"]
DEMO = "gaze-demo"
DEMO_ADDRESS = "https://example.org/gaze-demo/gaze-demo.git"
DEMO_DATE = "2026-11-20T09:00:00Z"
# published a day later, in a commit of its own: a copy of cmos.g1 by another author, without base
DEMO_LATER = Path("ckt/inv/cmos-copy.g1")
DEMO_LATER_DATE = "2026-11-21T09:00:00Z"
# the object given a timestamp proof (an RFC 3161 token from a service made on the spot), in that commit
DEMO_STAMPED = Path("ckt/inv/cmos.g1")
# the lines of the library list marked latest, by label: one generation of each series of circuits,
# testbenches and frozen libraries but cmos-copy;
# cmos.g1 is left for cmos.g2, so its page shows a newer version
DEMO_LATEST = {"inv/cmos.g2", "inv/cmos-x2.g1", "inv/cmos-lp.g1", "buf2/two-inv.g1", "inv/tb_inv_char.g1", "gaze-demo.g1"}


def draft_places(root: Path) -> dict[str, Path]:
    """Where each draft is: its name -> the directory that holds it."""
    return {p.name: p.parent for p in root.rglob("*_draft-*") if p.is_dir() and (p / "toa.yaml").is_file()}


def sealed_names(places: dict[str, Path]) -> dict[str, str]:
    """The name each draft got from `toa seal`: the one object of its type in the same directory."""
    out = {}
    for draft, parent in places.items():
        prefix = draft.split("_", 1)[0] + "_"
        found = [p.name for p in parent.iterdir() if p.is_dir() and p.name.startswith(prefix) and "_draft-" not in p.name]
        if len(found) != 1:
            sys.exit(f"{parent}: cannot tell what {draft} was sealed as: {found}")
        out[draft] = found[0]
    return out


def mark_latest(lib: Path, labels: set[str]) -> None:
    """Mark the lines of these labels latest in the library list, as a maintainer does by hand."""
    path = lib / "library.source.jsonl"
    out, found = [], set()
    for line in path.read_bytes().decode("utf-8").splitlines():
        e = json.loads(line) if line.strip() else None
        if isinstance(e, dict) and e.get("label") in labels and "object" in e:
            e["latest"] = True
            found.add(e["label"])
            line = json.dumps(e, ensure_ascii=False)
        out.append(line)
    if found != labels:
        sys.exit(f"{path}: no line labelled {sorted(labels - found)}")
    path.write_bytes(("\n".join(out) + "\n").encode("utf-8"))


def signing_env(env: dict, keys: Path) -> dict | None:
    """git settings that sign commits with an SSH key made for the demo, or None without ssh-keygen.
    The key is thrown away with the work directory; nothing verifies it but the demo itself."""
    ssh_keygen = shutil.which("ssh-keygen")
    if not ssh_keygen:
        print("ssh-keygen not found: the later publication of the demo is not signed", file=sys.stderr)
        return None
    keys.mkdir(parents=True, exist_ok=True)
    key = keys / "demo_ed25519"
    if not key.is_file():
        run([ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-C", "Gazettoa demo", "-f", key])
    settings = {"gpg.format": "ssh", "user.signingkey": key.resolve().as_posix(), "commit.gpgsign": "true"}
    out = {**env, "GIT_CONFIG_COUNT": str(len(settings))}
    for i, (k, v) in enumerate(settings.items()):
        out[f"GIT_CONFIG_KEY_{i}"], out[f"GIT_CONFIG_VALUE_{i}"] = k, v
    return out


TSA_CONFIG = """[ tsa ]
default_tsa = demo
[ demo ]
serial = serial
signer_cert = tsa.crt
signer_key = tsa.key
signer_digest = sha256
default_policy = 1.2.3.4.1
digests = sha256
accuracy = secs:1
ordering = yes
tsa_name = yes
ess_cert_id_chain = no
ess_cert_id_alg = sha256
"""


def demo_stamp(name: str, keys: Path) -> tuple[str, bytes] | None:
    """A time-stamp token of RFC 3161 for an object name (TOA 4.3), from a time-stamping service made
    for the demo on the spot with openssl, or None without openssl. The token is real and checks
    against keys/tsa/tsa.crt; it proves nothing beyond this machine. Returns its file name and bytes."""
    openssl = shutil.which("openssl")
    if not openssl:
        print("openssl not found: the demo has no timestamp proof", file=sys.stderr)
        return None
    d = keys / "tsa"
    d.mkdir(parents=True, exist_ok=True)
    (d / "tsa.cnf").write_bytes(TSA_CONFIG.encode("utf-8"))
    (d / "serial").write_bytes(b"01\n")
    (d / "name").write_bytes(name.encode("ascii"))     # the object name, without a line end
    quiet = {"cwd": d, "capture_output": True}
    if not (d / "tsa.crt").is_file():
        run([openssl, "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes", "-days", "3650",
             "-subj", "/CN=Gazettoa demo time-stamping service", "-addext", "extendedKeyUsage=critical,timeStamping",
             "-keyout", "tsa.key", "-out", "tsa.crt"], **quiet)
    run([openssl, "ts", "-query", "-data", "name", "-sha256", "-cert", "-no_nonce", "-out", "query.tsq"], **quiet)
    run([openssl, "ts", "-reply", "-queryfile", "query.tsq", "-config", "tsa.cnf", "-token_out", "-out", "token.tsr"], **quiet)
    run([openssl, "ts", "-verify", "-data", "name", "-in", "token.tsr", "-token_in", "-CAfile", "tsa.crt"], **quiet)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{day}-demo-tsa.tsr", (d / "token.tsr").read_bytes()


def run(cmd: list, **kw) -> None:
    print("+", " ".join(str(c) for c in cmd), file=sys.stderr)
    r = subprocess.run([str(c) for c in cmd], stdin=subprocess.DEVNULL, **kw)
    if r.returncode != 0:
        if kw.get("capture_output"):
            sys.stderr.write((r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace"))
        sys.exit(f"exit {r.returncode}")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def build_demo(toa: Path, dest: Path) -> None:
    """Seal and publish the drafts of scripts/demo/ into a new git repository, with fixed dates."""
    if (dest / ".git").is_dir():
        return
    if dest.exists():
        shutil.rmtree(dest)
    src = GAZE / "scripts" / "demo"
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("README.md"))
    later = dest / DEMO_LATER
    hold = dest.parent / (dest.name + ".later")
    if hold.exists():
        shutil.rmtree(hold)
    shutil.move(str(later), str(hold))
    drafts = draft_places(dest)
    write(dest / ".gitattributes", "* -text\n")
    env = {**os.environ, "GIT_AUTHOR_NAME": "Gazettoa demo", "GIT_AUTHOR_EMAIL": "demo@example.org",
           "GIT_COMMITTER_NAME": "Gazettoa demo", "GIT_COMMITTER_EMAIL": "demo@example.org",
           "GIT_AUTHOR_DATE": DEMO_DATE, "GIT_COMMITTER_DATE": DEMO_DATE}
    run(["git", "init", "--quiet", "--object-format=sha1"], cwd=dest, env=env)
    run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=dest, env=env)
    run(["git", "add", ".gitattributes"], cwd=dest, env=env)
    run(["git", "commit", "--quiet", "-m", "Start the library"], cwd=dest, env=env)
    run([toa, "seal"], cwd=dest, env=env)
    run([toa, "publish", "--to", DEMO_ADDRESS, "--branch", "main", "--keep-latest"], cwd=dest, env=env)
    run(["git", "add", "-A"], cwd=dest, env=env)
    run(["git", "commit", "--quiet", "-m", "Publish the drawing demo"], cwd=dest, env=env)
    mark_latest(dest, DEMO_LATEST)
    run(["git", "commit", "--quiet", "-a", "-m", "Mark the latest generations"], cwd=dest, env=env)
    later.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(hold), str(later))
    # the later object names drafts that are sealed by now: give it their names
    names = sealed_names(drafts)
    for f in later.rglob("toa.yaml"):
        text = f.read_bytes().decode("utf-8")
        for draft, name in names.items():
            text = text.replace(draft, name)
        f.write_bytes(text.encode("utf-8"))
    env = {**env, "GIT_AUTHOR_DATE": DEMO_LATER_DATE, "GIT_COMMITTER_DATE": DEMO_LATER_DATE}
    run([toa, "seal"], cwd=dest, env=env)
    signed = signing_env(env, dest.parent / (dest.name + ".keys"))
    if signed:
        # toa commits the publication itself and signs it as the git settings say (TOA 6.3)
        run([toa, "publish", "--to", DEMO_ADDRESS, "--branch", "main", "--keep-latest", "--commit", "--sign"], cwd=dest, env=signed)
    else:
        run([toa, "publish", "--to", DEMO_ADDRESS, "--branch", "main", "--keep-latest"], cwd=dest, env=env)
        run(["git", "add", "-A"], cwd=dest, env=env)
        run(["git", "commit", "--quiet", "-m", "Publish a copy of cmos.g1 by another author"], cwd=dest, env=env)
    # a timestamp proof of cmos.g1, the original, in the stamps directory beside it (TOA 4.3)
    orig = [d for d in (dest / DEMO_STAMPED).iterdir() if d.is_dir() and d.name.startswith("ckt_")]
    stamp = demo_stamp(orig[0].name, dest.parent / (dest.name + ".keys")) if len(orig) == 1 else None
    if stamp:
        stamps = orig[0].parent / f"{orig[0].name}.stamps"
        stamps.mkdir()
        (stamps / stamp[0]).write_bytes(stamp[1])
        run(["git", "add", "-A"], cwd=dest, env=env)
        run(["git", "commit", "--quiet", "-m", "Add a timestamp proof of cmos.g1"], cwd=dest, env=env)
    run([toa, "check"], cwd=dest, env=env)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--toa-src", type=Path, default=GAZE.parent / "toa", help="the toa source (default: ../toa beside gaze/)")
    ap.add_argument("--toa", help="the toa executable (default: <toa-src>/target/release/toa, built if missing)")
    ap.add_argument("--rnl", help="the rnl executable, to draw symbols (default: rnl on PATH)")
    ap.add_argument("--work", type=Path, default=GAZE / ".work" / "examples")
    ap.add_argument("--out", type=Path, default=GAZE / "_site")
    a = ap.parse_args()
    exe = "toa.exe" if os.name == "nt" else "toa"
    toa = Path(a.toa) if a.toa else a.toa_src / "target" / "release" / exe
    if not toa.is_file():
        if not (a.toa_src / "Cargo.toml").is_file():
            sys.exit(f"no toa executable at {toa} and no toa source at {a.toa_src}")
        run(["cargo", "build", "--release", "-p", "toa-cli"], cwd=a.toa_src)
    toa = toa.resolve()
    work = a.work.resolve()
    repos = work / "repos"
    if not (repos / "workspace.source.jsonl").is_file():
        if repos.exists():
            shutil.rmtree(repos)
        repos.mkdir(parents=True)
        run(["cargo", "test", "--release", "--test", "examples"], cwd=a.toa_src, env={**os.environ, "TOA_EXAMPLES_OUT": str(repos)})
    build_demo(toa, work / "demo" / DEMO)

    lines = [{"toa": "source/1"}]
    with open(repos / "workspace.source.jsonl", encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            if e.get("group") in EXAMPLES:
                e["sources"] = [s if "local" not in s else {"local": f"repos/{s['local']}"} for s in e["sources"]]
                lines.append(e)
    lines.append({"include": "library.source.jsonl", "group": DEMO, "branch": "main",
                  "sources": [{"git": DEMO_ADDRESS}, {"local": f"demo/{DEMO}"}]})
    write(work / "workspace.source.jsonl", "".join(json.dumps(e) + "\n" for e in lines))
    write(work / "gaze.yaml", "schema: gaze/instance/1\ntitle: Gazettoa\n"
          "description: The small examples of toa and a drawing demo, read from this machine.\n")

    run([toa, "index", "--workspace", work / "workspace.source.jsonl", "--out", work / "index", "--offline"])
    cmd = [sys.executable, "-m", "gaze", "build", "--instance", work, "--index", work / "index", "--out", a.out.resolve(),
           "--toa", toa, "--offline", "--site-url", "http://localhost:47950/", "--local-files", (a.toa_src / "examples").resolve(), "--local-files", work / "demo"]
    if a.rnl:
        cmd += ["--rnl", a.rnl]
    run(cmd, cwd=GAZE / "builder")
    return 0


if __name__ == "__main__":
    sys.exit(main())
