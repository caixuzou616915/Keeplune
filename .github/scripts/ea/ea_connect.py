"""Shared helper for connecting to a Sparx Enterprise Architect project via COM.

Requires 32-bit Python + pywin32 (see .venv32). Loads configuration from a
`.env` file located alongside this script (EA_PROJECT, EA_PROJECT_PASSWORD).
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))


def load_env():
    """Load .env (if present) into os.environ without overwriting existing vars."""
    try:
        from dotenv import load_dotenv
        env_path = os.path.join(SCRIPT_DIR, ".env")
        if os.path.isfile(env_path):
            load_dotenv(env_path)
    except ImportError:
        pass


def resolve_project_path():
    load_env()
    project = os.environ.get("EA_PROJECT", "").strip()
    if not project:
        raise RuntimeError(
            "EA_PROJECT is not set. Create .github/scripts/ea/.env from .env.template "
            "and set EA_PROJECT to the .eap/.qea file path."
        )
    if not os.path.isabs(project):
        project = os.path.join(REPO_ROOT, project)
    project = os.path.normpath(project)
    if not os.path.isfile(project):
        raise RuntimeError(f"EA project file not found: {project}")
    return project


def connect(project_path=None):
    """Open the EA repository via COM automation and return the Repository object.

    Uses the EA.Repository automation object directly (does not require EA.exe
    to already be running - it will host a hidden EA engine instance).
    """
    try:
        import win32com.client
    except ImportError as exc:
        raise RuntimeError(
            "pywin32 is not installed in this interpreter. Run this script with "
            ".github/scripts/ea/.venv32/Scripts/python.exe"
        ) from exc

    if project_path is None:
        project_path = resolve_project_path()

    repo = win32com.client.Dispatch("EA.Repository")
    password = os.environ.get("EA_PROJECT_PASSWORD", "")
    try:
        ok = repo.OpenFile2(project_path, "", password) if password else repo.OpenFile(project_path)
    except Exception:
        ok = repo.OpenFile(project_path)
    if not ok:
        raise RuntimeError(f"EA.Repository.OpenFile failed for: {project_path}")
    return repo


def disconnect(repo):
    try:
        repo.CloseFile()
    except Exception:
        pass
    try:
        repo.Exit()
    except Exception:
        pass


def iter_root_packages(repo):
    """Yield top-level Package objects (one per Model root in the repository)."""
    models = repo.Models
    for i in range(models.Count):
        yield models.GetAt(i)


def iter_subpackages(package):
    packages = package.Packages
    for i in range(packages.Count):
        yield packages.GetAt(i)


def iter_elements(package):
    elements = package.Elements
    for i in range(elements.Count):
        yield elements.GetAt(i)


def iter_diagrams(package):
    diagrams = package.Diagrams
    for i in range(diagrams.Count):
        yield diagrams.GetAt(i)


def iter_child_elements(element):
    """Yield nested/composite child Elements owned directly by an Element
    (Element.Elements) - distinct from Package.Elements. Composite elements
    such as UseCase/Class can own child elements (e.g. scenario UseCases
    nested under a 'Dyn_<SwSubSys>' UseCase), each of which may in turn own
    its own Diagrams (Element.Diagrams) that are NOT reachable via any
    Package.Diagrams collection."""
    try:
        children = element.Elements
    except Exception:
        return
    for i in range(children.Count):
        yield children.GetAt(i)


def iter_element_diagrams(element):
    """Yield Diagrams owned directly by an Element (Element.Diagrams)."""
    try:
        diagrams = element.Diagrams
    except Exception:
        return
    for i in range(diagrams.Count):
        yield diagrams.GetAt(i)


def walk_element_diagrams(element, seen_ids=None):
    """Recursively yield every Diagram owned by `element` or any of its
    nested composite child elements (depth-unbounded, cycle-safe)."""
    if seen_ids is None:
        seen_ids = set()
    eid = getattr(element, "ElementID", None)
    if eid is not None:
        if eid in seen_ids:
            return
        seen_ids.add(eid)
    for d in iter_element_diagrams(element):
        yield d
    for child in iter_child_elements(element):
        yield from walk_element_diagrams(child, seen_ids)


def walk_packages(package, depth=0):
    """Recursively yield (package, depth) for a package and all its descendants."""
    yield package, depth
    for child in iter_subpackages(package):
        yield from walk_packages(child, depth + 1)


DESIGN_PREFIXES = ("SwSys_", "SwSubSys_", "SwMod_")


def matches_design_prefix(name):
    return any(name.startswith(p) for p in DESIGN_PREFIXES)


def safe_get(obj, attr, default=None):
    try:
        return getattr(obj, attr)
    except Exception:
        return default


def resolve_package_breadcrumb(repo, package_id, cache=None):
    """Resolve the full ancestor-name breadcrumb (root-first list of package
    Names) for a PackageID, memoized in `cache` (dict) across calls."""
    if cache is None:
        cache = {}
    if package_id in cache:
        return cache[package_id]
    names = []
    seen_ids = set()
    pid = package_id
    while pid:
        if pid in seen_ids:
            break
        seen_ids.add(pid)
        try:
            pkg = repo.GetPackageByID(pid)
        except Exception:
            break
        if pkg is None:
            break
        names.append(pkg.Name)
        pid = safe_get(pkg, "ParentID", 0)
    names.reverse()
    cache[package_id] = names
    return names
