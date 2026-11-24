"""Evidence of authorship and time (TOA decision B35; docs/toa-authorship.md in toa-dev).

TOA does not judge who may sign a work, and nothing here is a verdict. Beside each object the
build gives three kinds of evidence:

- **When this site first saw it** (data/seen.json): the library, the commit this site read and
  the time of the build. The record is kept from build to build and only ever added to. It is the
  record of whoever runs this site, not a proof by a third party; the dates of commits are written
  by the committers and prove less still.
- **Its identifier in Software Heritage:** the hash of an object name is the hash of a directory
  there, `swh:1:dir:<hash>` (TOA chapter 11). Optionally, the build asks Software Heritage which
  objects it has archived (`software_heritage_check: true` in gaze.yaml).
- **Who signed the commit that put it into each library** (data/signatures.json): the index says
  whether that commit is signed and in which format, unverified (TOA 6.3, 8.3). For a library on
  github.com, the build asks GitHub whether the signature verified and for which account, once
  per commit (`github_signature_check`, with the token of the Actions job). A commit GitHub signed
  itself when merging on the web (`web-flow`) names GitHub, not a person: the pull request it
  merged and its author are kept beside it. A signature shows who put an object into a library,
  never who wrote it.
- **Same files, lineage not declared** (TOA 8.3) are not computed here: the index of toa gives
  them for each object (`same_files`, index-format.md), so that this site and `toa check` show
  the same. The view takes them as they are (views.Model.same).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from .config import split_address
from .fields import INDEX
from .views import swhid

SEEN_FORMAT = "gaze-seen/1"
SWH_FORMAT = "gaze-swh/1"
SWH_ARCHIVE = "https://archive.softwareheritage.org/"
SWH_KNOWN = SWH_ARCHIVE + "api/1/known/"
SWH_BATCH = 1000          # SWHIDs per request to the known endpoint
SIG_FORMAT = "gaze-signatures/1"
GITHUB_API = "https://api.github.com/"
SIG_MAX = 400             # commits asked of GitHub per build; the rest wait for the next one


# ------------------------------------------------------------------ when this site first saw it

def update_seen(model, prev: dict | None, built: str) -> dict:
    """The record of when this site first saw each object, from the previous one and this build.

    An object present now and not in the record is added with this build's time, the library it
    is first in (by the index's `first`) and the commit this build read of that library. A record
    started now marks everything already there `before`: it was there when the record began, not
    first seen that day."""
    ok = isinstance(prev, dict) and prev.get("format") == SEEN_FORMAT and isinstance(prev.get("objects"), dict)
    objs = {n: e for n, e in (prev["objects"].items() if ok else []) if isinstance(e, dict) and isinstance(e.get("seen"), str)}
    since = prev.get("since") if ok and isinstance(prev.get("since"), str) else built
    for n, o in sorted(model.index.objects.items()):
        if n in objs or not o.get("present"):
            continue
        locs = model.sorted_locations(o)
        libs = [loc["library"] for loc in locs]
        lib = (o.get("first") or {}).get("library")
        if lib not in libs:
            lib = libs[0] if libs else None
        rec = (model.index.library(lib) or {}) if lib else {}
        e = {"seen": built, "library": lib, "commit": rec.get("commit")}
        if not ok:
            e["before"] = True
        objs[n] = e
    return {"format": SEEN_FORMAT, "since": since, "objects": objs}


# ------------------------------------------------------------------ archived by Software Heritage

def swh_known(names, prev: dict | None, built: str, log) -> dict:
    """Which objects Software Heritage has archived: {"format", "checked", "known": {swhid: date}}.

    The date is the first build that found it archived. Only names not yet found are asked, in
    batches; a request that fails leaves what was known before."""
    ok = isinstance(prev, dict) and prev.get("format") == SWH_FORMAT and isinstance(prev.get("known"), dict)
    known = dict(prev["known"]) if ok else {}
    ask = sorted({s for s in (swhid(n) for n in names) if s and s not in known})
    asked = 0
    for i in range(0, len(ask), SWH_BATCH):
        part = ask[i:i + SWH_BATCH]
        req = urllib.request.Request(SWH_KNOWN, data=json.dumps(part).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "gazettoa"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                got = json.loads(r.read().decode("utf-8"))
        except (OSError, ValueError, urllib.error.URLError) as e:
            log(f"Software Heritage: the known endpoint failed ({e}); {len(ask) - i} names not asked")
            return {"format": SWH_FORMAT, "checked": prev.get("checked") if ok else None, "known": known}
        for s in part:
            if isinstance(got, dict) and isinstance(got.get(s), dict) and got[s].get("known") is True:
                known[s] = built
        asked += len(part)
    if asked:
        log(f"Software Heritage: asked {asked}, {len(known)} archived in all")
    return {"format": SWH_FORMAT, "checked": built, "known": known}


# ------------------------------------------------------------------ who signed, as GitHub verified it

_SHA = re.compile(r"^[0-9a-f]{40}$")
_REPO = re.compile(r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+$")


def github_repo(address: str | None) -> str | None:
    """`owner/name` of a library on github.com, or None."""
    hr = split_address(address)
    return hr[1] if hr and hr[0] == "github.com" and _REPO.match(hr[1]) else None


def signed_commits(index) -> dict[str, str]:
    """The signed commits that put a present object into a library on github.com: commit -> owner/name."""
    out: dict[str, str] = {}
    for _, o in sorted(index.objects.items()):
        if not o.get("present"):
            continue
        for loc in o.get("locations") or []:
            sha = loc.get("first_commit")
            if not loc.get(INDEX.FIRST_SIGNATURE) or not isinstance(sha, str) or not _SHA.match(sha) or sha in out:
                continue
            repo = github_repo((index.library(loc.get("library")) or {}).get("address"))
            if repo:
                out[sha] = repo
    return out


def _github_get(token: str):
    def get(path: str):
        req = urllib.request.Request(GITHUB_API + path, headers={
            "Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "gazettoa"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    return get


def _login(user) -> str | None:
    return user.get("login") if isinstance(user, dict) and isinstance(user.get("login"), str) else None


def check_signatures(commits: dict[str, str], prev: dict | None, built: str, log, *, token: str | None = None,
                     get=None) -> dict:
    """What GitHub says of each signed commit: {"format", "checked", "commits": {sha: entry}}.

    An entry: `repo`, `verified`, GitHub's `reason`, the `signer` (the account the key belongs to,
    when verified), and for a commit GitHub signed itself (`web_flow`) the `pulls` it merged, each
    with its number, author and address. A commit does not change, so an entry is kept for good;
    only commits not asked before are asked, at most SIG_MAX a build. A request that fails ends the
    asking for this build and keeps what was known."""
    ok = isinstance(prev, dict) and prev.get("format") == SIG_FORMAT and isinstance(prev.get("commits"), dict)
    known = {k: e for k, e in (prev["commits"].items() if ok else []) if _SHA.match(k) and isinstance(e, dict)}
    ask = [sha for sha in sorted(commits) if sha not in known]
    if not ask:
        return {"format": SIG_FORMAT, "checked": prev.get("checked") if ok else None, "commits": known}
    get = get or _github_get(token or "")
    asked = 0
    for sha in ask[:SIG_MAX]:
        repo = commits[sha]
        try:
            c = get(f"repos/{repo}/commits/{sha}")
            ver = ((c.get("commit") or {}).get("verification") or {}) if isinstance(c, dict) else {}
            verified = ver.get("verified") is True
            e = {"repo": repo, "verified": verified, "reason": str(ver.get("reason") or ""),
                 "signer": _login(c.get("committer")) if verified else None, "checked": built}
            if verified and e["signer"] == "web-flow":
                e["web_flow"] = True
                e["signer"] = None
                pulls = get(f"repos/{repo}/commits/{sha}/pulls")
                e["pulls"] = [{"number": p.get("number"), "author": _login(p.get("user")), "url": p.get("html_url")}
                              for p in (pulls if isinstance(pulls, list) else [])[:5] if isinstance(p, dict)]
        except urllib.error.HTTPError as err:
            if err.code in (404, 422):
                # GitHub does not have this commit in this repository (moved, private): asked again next time
                log(f"GitHub: commit {sha[:10]} not found in {repo} ({err.code})")
                continue
            log(f"GitHub: asking about signatures failed ({err}); {len(ask) - asked} commits not asked")
            break
        except (OSError, ValueError, AttributeError, urllib.error.URLError) as err:
            log(f"GitHub: asking about signatures failed ({err}); {len(ask) - asked} commits not asked")
            break
        known[sha] = e
        asked += 1
    if asked:
        log(f"GitHub: asked about {asked} signed commits, {len(known)} known in all"
            + (f"; {len(ask) - SIG_MAX} left for the next build" if len(ask) > SIG_MAX else ""))
    return {"format": SIG_FORMAT, "checked": built if asked else (prev.get("checked") if ok else None), "commits": known}
