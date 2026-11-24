"""Every type name and field name of TOA that Gazettoa reads, in one place: the manifests, and the
keys of the index of `toa` that are named after them.

The names follow the type specifications of TOA (`toa/spec/types/` in the toa repository), as
decisions B32 and B33 renamed them (2026-11-24). A rename is made here and nowhere else. The
builder turns manifests into views with Gazettoa's own keys, so the pages never read a manifest
field by name.
"""

# The types of TOA. Gazettoa keys its pages, its data and its addresses by the kinds on the left;
# on the right is each type's name in TOA, the prefix of its object names. They are the same since
# B32; a later rename of a type changes the right side, and the page takes the table from the
# site's data (`site.json`, `types`).
TYPES = {"ifc": "ifc", "ckt": "ckt", "tb": "tb", "evd": "evd", "doc": "doc", "lib": "lib"}
_KIND_OF = {name: kind for kind, name in TYPES.items()}


def kind_of(name: str) -> str:
    """The kind of an object, from the prefix of its name through TYPES."""
    p = str(name).split("_", 1)[0]
    return _KIND_OF.get(p, p)


# Common fields (TOA 0.1, 3.2.1).
TYPE = "type"
LICENSE = "license"
AUTHOR = "author"
BASE = "base"
TITLE = "title"
DESCRIPTION = "description"
TAGS = "tags"

README = "README.md"


class HISTORY:
    """`history.json` (TOA 0.1, 3.4), as the index gives it under `history`."""
    FILE = "history.json"
    LISTED = "listed"           # the names of history.json, nearest ancestor first
    GENERATION = "generation"   # the generation history.json gives


class INDEX:
    """Keys of the index of `toa` that are named after fields of TOA (index-format.md, format 2,
    section 5)."""
    BASE = "base"               # the object's `base`, as written
    BASE_BY = "base_by"         # who names this object first in `base`, verified (8.3)
    HISTORY = "history"
    LATEST = "latest"           # on a place (`locations`): the library list marks it latest (5.2)
    NEWER = "newer"             # the newer versions of 7.5, from the latest marks
    MARKED_BY = "marked_by"     # in an item of `newer`: the libraries that mark it latest
    TOGETHER = "together"       # in an item of `newer`: the libraries that hold both
    IFC_CHANGED = "ifc_changed"  # in an item of `newer`: it has another interface
    # on a place: the format of the signature of its first commit (ssh, openpgp, x509, other), null
    # when not signed, unverified (6.3, 8.3); in `first` the same of the earliest commit is `signature`
    FIRST_SIGNATURE = "first_signature"
    SIGNATURE = "signature"
    # on a place: the timestamp proofs in <object name>.stamps/ beside it (4.3), each with `file`,
    # `kind` (opentimestamps, rfc3161, other), `size` and the `commit` and `date` that first added it;
    # not checked by the index
    STAMPS = "stamps"
    STAMPS_DIR = ".stamps"      # the suffix of the stamps directory beside an object (4.3)
    # on an object: the same files without a declared lineage (8.3), computed by the index:
    # `earlier`, `later` (with `basis` library or dates), `common`; in index.json, the numbers it used
    SAME_FILES = "same_files"


class IFC:
    NAME = "name"
    PINS = "pins"
    SYMBOL_FILE = "symbol.rnl"


class PIN:
    NAME = "name"
    KIND = "kind"
    DIRECTION = "direction"
    WIDTH = "width"
    DESCRIPTION = "description"


class ROLE:
    """The roles of `files`, for circuits and testbenches alike."""
    NETLIST = "netlist"
    VA = "va"
    RTL = "rtl"
    PACKAGES = "packages"
    EXTRAS = "extras"


class CKT:
    IFC = "ifc"
    NAME = "name"
    FORM = "form"
    FILES = "files"
    EXTERNAL = "external"
    USES = "uses"
    PARAMETERS = "parameters"
    SPECIFICATIONS = "specifications"
    ORIGIN = "origin"


class SPEC:
    """Keys of `specifications` that Gazettoa reads; the others are shown as they are."""
    PROCESS = "process"


class USE:
    IFC = "ifc"
    CKT = "ckt"
    REQUIREMENTS = "requirements"


class ORIGIN:
    """`origin` of a circuit taken from outside TOA."""
    REPO = "repo"
    COMMIT = "commit"
    PATH = "path"
    TAG = "tag"
    LICENSE = "license"         # {spdx, file}
    LICENSE_SPDX = "spdx"
    LICENSE_FILE = "file"
    AUTHORS = "authors"
    FILES = "files"


class TB:
    IFC = "ifc"
    NAME = "name"
    FILES = "files"
    EXTERNAL = "external"
    RUN = "run"
    ANALYZE = "analyze"
    METRICS = "metrics"
    SIMULATORS = "simulators"
    PARAMETERS = "parameters"
    PRESETS = "presets"


class METRIC:
    ID = "id"
    UNIT = "unit"
    BETTER = "better"
    TOLERANCE = "tolerance"
    TOLERANCE_ABS = "abs"
    TOLERANCE_REL = "rel"
    DESCRIPTION = "description"


def metric_full_name(tb_name: str, metric_id: str) -> str:
    """The full name of a metric, `<name>.<id>`, as evidence records key their metrics."""
    return f"{tb_name}.{metric_id}"


class EVD:
    KIND = "kind"
    SIM = "sim"                 # the one kind of 0.1: a simulation
    DUT = "dut"
    TBS = "tbs"
    CONDITIONS = "conditions"
    ENVIRONMENT = "environment"
    METRICS = "metrics"
    EVIDENCE = "evidence"
    LOCK_FILE = "lock.json"


class LOCK:
    """Keys of `lock.json` (format lock/1) that the index names in `references`."""
    TREE = "tree"
    OBJECT = "object"
    IFC = "ifc"


class COND:
    """The three slots of `conditions` (and of a testbench's `presets`)."""
    PARAMETERS = "parameters"
    OPTIONS = "options"
    MODELS = "models"
    SLOTS = (PARAMETERS, OPTIONS, MODELS)
    MODEL_FILE = "file"         # the file name of an item of `models`
    MODEL_SECTION = "section"


class ENV:
    SIMULATOR = "simulator"
    COMMAND = "command"         # of `simulator`: the whole command line


class DOC:
    REFS = "refs"
    DATE = "date"


class LIB:
    NAME = "name"
    MEMBERS_FILE = "members.source.jsonl"


class SOURCE:
    """The fields of an object line of a source list (TOA 0.1, 5.1), for a frozen library's members."""
    OBJECT = "object"
    LABEL = "label"
    GROUP = "group"
    LICENSE = "license"
    REFS = "refs"
    SOURCES = "sources"
    HEADER = "toa"
