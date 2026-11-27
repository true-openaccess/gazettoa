"""The settings of an instance: `gaze.yaml` beside the workspace list.

`gaze.yaml` holds what TOA does not: the title, the site's own address, how the files of a library
are reached on its host. It is read without a YAML library, so it keeps to a small part of YAML:
block mappings nested by spaces, `key: value` with plain or quoted scalars, flow mappings of
scalars on one line (`{raw: copy}`), and `#` comments. Anything else is an error that names the
line. Nothing here names an organisation or an address of its own: what a fork does not set is
taken from the environment of GitHub Actions or left out.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

CONFIG_FILE = "gaze.yaml"
WORKSPACE_FILE = "workspace.source.jsonl"

# How the files of a library are reached on well-known hosts. {repo} is the path of the
# repository on the host (owner/name), {commit} the commit read, {path} a path in the library.
DEFAULT_HOSTS: dict[str, dict[str, str]] = {
    "github.com": {
        "raw": "https://raw.githubusercontent.com/{repo}/{commit}/{path}",
        "web": "https://github.com/{repo}/tree/{commit}/{path}",
    },
    "gitlab.com": {
        "raw": "https://gitlab.com/{repo}/-/raw/{commit}/{path}",
        "web": "https://gitlab.com/{repo}/-/tree/{commit}/{path}",
    },
    "codeberg.org": {
        "raw": "https://codeberg.org/{repo}/raw/commit/{commit}/{path}",
        "web": "https://codeberg.org/{repo}/src/commit/{commit}/{path}",
    },
}


class ConfigError(ValueError):
    pass


# ---------------------------------------------------------------- a small part of YAML

_KEY = re.compile(r"^[A-Za-z0-9_.\-/]+$")
_INT = re.compile(r"^[-+]?[0-9]+$")
_FLOAT = re.compile(r"^[-+]?([0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)([eE][-+]?[0-9]+)?$")


def _strip_comment(line: str) -> str:
    quote = ""
    for i, c in enumerate(line):
        if quote:
            if c == quote:
                quote = ""
        elif c in "\"'":
            quote = c
        elif c == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line.rstrip()


def _scalar(text: str, where: str):
    s = text.strip()
    if len(s) >= 2 and s[0] == s[-1] == '"':
        body = s[1:-1]
        out, i = [], 0
        while i < len(body):
            c = body[i]
            if c == "\\" and i + 1 < len(body):
                n = body[i + 1]
                out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(n, "\\" + n))
                i += 2
                continue
            out.append(c)
            i += 1
        return "".join(out)
    if len(s) >= 2 and s[0] == s[-1] == "'":
        return s[1:-1].replace("''", "'")
    if s[:1] in ("[", "{", "&", "*", "!", "|", ">"):
        raise ConfigError(f"{where}: this part of YAML is not read here: {s!r}")
    if s in ("true", "True", "TRUE"):
        return True
    if s in ("false", "False", "FALSE"):
        return False
    if s in ("null", "~", ""):
        return None
    if _INT.match(s):
        return int(s)
    if _FLOAT.match(s):
        return float(s)
    return s


def _flow_mapping(text: str, where: str) -> dict:
    inner = text.strip()[1:-1].strip()
    out: dict = {}
    if not inner:
        return out
    for part in inner.split(","):
        k, sep, v = part.partition(":")
        k = k.strip()
        if not sep or not _KEY.match(k):
            raise ConfigError(f"{where}: a flow mapping holds `key: value` pairs of scalars only")
        if k in out:
            raise ConfigError(f"{where}: the key {k!r} is written twice")
        out[k] = _scalar(v, where)
    return out


def parse_yaml_subset(text: str, source: str = CONFIG_FILE) -> dict:
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for no, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        where = f"{source}:{no}"
        line = _strip_comment(raw)
        if not line.strip():
            continue
        lead = line[: len(line) - len(line.lstrip())]
        if "\t" in lead:
            raise ConfigError(f"{where}: indent with spaces, not tabs")
        indent = len(lead)
        body = line.strip()
        if body.startswith("- ") or body == "-":
            raise ConfigError(f"{where}: lists are not read here; write a mapping")
        if body.startswith("---"):
            continue
        key, sep, rest = body.partition(":")
        key = key.strip()
        quoted = len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'"
        if quoted:
            key = key[1:-1]
        if not sep or not key or (not quoted and not _KEY.match(key)):
            raise ConfigError(f"{where}: expected `key: value`")
        if rest and not rest.startswith((" ", "\t")):
            raise ConfigError(f"{where}: put a space after the colon")
        while stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        if key in parent:
            raise ConfigError(f"{where}: the key {key!r} is written twice")
        rest = rest.strip()
        if rest == "":
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
        elif rest.startswith("{") and rest.endswith("}"):
            parent[key] = _flow_mapping(rest, where)
        else:
            parent[key] = _scalar(rest, where)
    return root


# ---------------------------------------------------------------- the settings

@dataclass
class Config:
    title: str = "Gazettoa"
    description: str = ""
    site_url: str = ""
    viewer_url: str = "https://rich-netlist.github.io/rnl/viewer/"
    toa_site: str = ""            # the site of TOA, linked from the home page; no link when empty
    hosts: dict[str, dict[str, str]] = field(default_factory=lambda: {k: dict(v) for k, v in DEFAULT_HOSTS.items()})
    libraries: dict[str, dict] = field(default_factory=dict)
    repository: str = ""          # where this instance's own code lives, for the footer; from Actions
    # ask GitHub whether the signed commits of libraries on github.com verified, and by whom (B35);
    # only with a token in GITHUB_TOKEN, as an Actions job has, and not offline
    github_signature_check: bool = True
    # the token of a site in Cloudflare Web Analytics: the page then carries Cloudflare's tag
    # (build.write_shell); empty, no tag and nothing sent anywhere
    cloudflare_web_analytics: str = ""
    source: Path | None = None    # the file read, if any

    def library_raw_mode(self, key: str) -> str:
        """`url` (the page fetches from the host) or `copy` (the build copies the files)."""
        mode = (self.libraries.get(key) or {}).get("raw", "url")
        if mode not in ("url", "copy"):
            raise ConfigError(f"{CONFIG_FILE}: libraries.{key}.raw is `url` or `copy`, not {mode!r}")
        return mode


def _actions_site_url() -> str:
    """The address GitHub Pages gives a repository, from the variables every Actions job has."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    server = os.environ.get("GITHUB_SERVER_URL", "")
    if not repo or "/" not in repo or server.rstrip("/") != "https://github.com":
        return ""
    owner, name = repo.split("/", 1)
    if name.lower() == f"{owner.lower()}.github.io":
        return f"https://{owner.lower()}.github.io/"
    return f"https://{owner.lower()}.github.io/{name}/"


def load(instance: Path, site_url: str | None = None) -> Config:
    cfg = Config()
    path = instance / CONFIG_FILE
    if path.is_file():
        data = parse_yaml_subset(path.read_text(encoding="utf-8"), str(path.name))
        cfg.source = path
        known = {"schema", "title", "description", "site_url", "viewer_url", "toa_site", "hosts", "libraries",
                 "github_signature_check", "cloudflare_web_analytics"}
        for k in data:
            if k not in known:
                raise ConfigError(f"{CONFIG_FILE}: unknown key {k!r}; known: {', '.join(sorted(known))}")
        if data.get("schema") not in (None, "gaze/instance/1"):
            raise ConfigError(f"{CONFIG_FILE}: schema is gaze/instance/1, not {data.get('schema')!r}")
        for k in ("title", "description", "site_url", "viewer_url", "toa_site"):
            if data.get(k) is not None:
                if not isinstance(data[k], str):
                    raise ConfigError(f"{CONFIG_FILE}: {k} is a string")
                setattr(cfg, k, data[k])
        # a link on the home page: an address on the web, never a script
        if cfg.toa_site and not re.match(r"^https?://[^\s\"'<>]+$", cfg.toa_site):
            raise ConfigError(f"{CONFIG_FILE}: toa_site is an address that starts with https://, not {cfg.toa_site!r}")
        # written into the page as it is: letters and digits only, as Cloudflare gives it
        cf = data.get("cloudflare_web_analytics")
        if cf is not None:
            if not isinstance(cf, str) or not re.match(r"^[0-9A-Za-z]{16,64}$", cf):
                raise ConfigError(f"{CONFIG_FILE}: cloudflare_web_analytics is the token Cloudflare gives a site, "
                                  f"letters and digits, not {cf!r}")
            cfg.cloudflare_web_analytics = cf
        if data.get("github_signature_check") is not None:
            if not isinstance(data["github_signature_check"], bool):
                raise ConfigError(f"{CONFIG_FILE}: github_signature_check is true or false")
            cfg.github_signature_check = data["github_signature_check"]
        for host, spec in (data.get("hosts") or {}).items():
            if not isinstance(spec, dict) or not all(isinstance(v, str) for v in spec.values()):
                raise ConfigError(f"{CONFIG_FILE}: hosts.{host} maps raw and web to address templates")
            cfg.hosts[host] = {**cfg.hosts.get(host, {}), **spec}
        for key, spec in (data.get("libraries") or {}).items():
            if not isinstance(spec, dict):
                raise ConfigError(f"{CONFIG_FILE}: libraries.{key} is a mapping")
            cfg.libraries[key] = spec
            cfg.library_raw_mode(key)
    if site_url is not None:
        cfg.site_url = site_url
    if not cfg.site_url:
        cfg.site_url = _actions_site_url()
    if cfg.site_url and not cfg.site_url.endswith("/"):
        cfg.site_url += "/"
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    server = os.environ.get("GITHUB_SERVER_URL", "").rstrip("/")
    if repo and server:
        cfg.repository = f"{server}/{repo}"
    return cfg


# ---------------------------------------------------------------- addresses of libraries

def split_address(address: str | None) -> tuple[str, str] | None:
    """(host, repo) of a git address, or None: https://host/owner/name(.git), ssh://…, git@host:owner/name."""
    if not address:
        return None
    a = address.strip()
    m = re.match(r"^[A-Za-z0-9_.\-]+@([A-Za-z0-9.\-]+):(.+)$", a)
    if m:
        host, path = m.group(1), m.group(2)
    else:
        u = urlsplit(a)
        if u.scheme not in ("https", "http", "ssh", "git") or not u.hostname:
            return None
        host, path = u.hostname, u.path
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if not path:
        return None
    return host.lower(), path


def fill(template: str, repo: str, commit: str, path: str) -> str:
    return template.replace("{repo}", repo).replace("{commit}", commit).replace("{path}", path.strip("/"))


def library_templates(cfg: Config, address: str | None) -> tuple[str, str] | None:
    """(raw, web) templates with {path} left open, or None when the host is not known."""
    hr = split_address(address)
    if not hr:
        return None
    host, repo = hr
    spec = cfg.hosts.get(host)
    if not spec or "raw" not in spec:
        return None
    return spec["raw"].replace("{repo}", repo), spec.get("web", "").replace("{repo}", repo)
