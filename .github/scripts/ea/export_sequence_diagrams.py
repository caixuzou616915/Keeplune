"""Export EA sequence diagrams as PlantUML (.puml) sequence diagrams.

Only converts diagrams whose EA Diagram.Type == "Sequence" (real modeled
sequence diagrams). Does NOT fabricate sequences - if no sequence diagrams
exist in the model this prints a clear message and exits without writing
any file.

IMPORTANT discovery note: Diagram.Type == "Sequence" IS the correct/only
literal type used in this model for genuine sequence diagrams - the earlier
"only 1 found" bug was NOT a wrong Type match, it was an incomplete walk.
Most of this model's per-scenario sequence diagrams are NOT owned by any
Package (so they never show up when walking Package.Diagrams) - they are
owned directly by an Element (Element.Diagrams), specifically by leaf
'Dyn_<SwSubSys>_Scenario(-io)_<Name>' UseCase elements nested (via
Element.Elements, NOT Package.Packages) under a parent 'Dyn_<SwSubSys>'
UseCase element, which itself lives directly inside the corresponding
SwSubSys_* package's Elements collection (not its Packages collection).
A full COM tree walk that recurses into every Package's Elements and then
every Element's nested Elements to find these is correct but WAY too slow
over COM for a ~800-package / tens-of-thousands-of-elements model (many
minutes, effectively hangs). Instead we use `Repository.SQLQuery()` to query
the underlying t_diagram table directly for `Diagram_Type='Sequence'`
(returns in well under a second for the whole model), then resolve each of
the (small number of) matching Diagram_IDs individually via the COM API for
full content (participants/messages) and breadcrumb path.

Fidelity notes (COM API limitations, documented rather than guessed):
  - Lifeline/participant order is derived from each DiagramObject's `Left`
    (x) position, left-to-right, matching the visual layout.
  - Message order is derived from the order of Diagram.DiagramLinks as
    returned by the EA COM API (creation order), since no reliable numeric
    "visual sequence number" is exposed on the Connector object for this
    EA version.
  - All messages are rendered as solid "->" arrows; EA's COM API does not
    expose a simple synchronous/return/dashed-arrow flag on Connector for
    this project, so arrow style (solid vs dashed) is not preserved.
  - UML combined fragments (alt/opt/loop) and free-floating notes are
    rendered as PlantUML `note over` annotations using their EA name/label
    (not full nested fragment blocks), since mapping fragment bounds to the
    exact enclosed messages is not reliable via DiagramObject geometry alone.

Usage:
    .venv32\\Scripts\\python.exe export_sequence_diagrams.py [--output DIR]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ea_connect as ea

DEFAULT_OUTPUT = os.path.join(ea.REPO_ROOT, "ai_output", "arch_design", "diagrams")

INVALID_FS_CHARS = re.compile(r'[<>:"/\\|?*]')

# EA element types that represent an actual sequence-diagram lifeline/participant
PARTICIPANT_TYPES = {"Actor", "Sequence", "Object", "Class", "Component", "Interface"}
FRAME_TYPES = {"Boundary"}
NOTE_TYPES = {"Note"}
FRAGMENT_TYPES = {"InteractionFragment"}


def sanitize_filename(name):
    cleaned = INVALID_FS_CHARS.sub("_", name).strip()
    return cleaned or "unnamed"


def puml_alias(name, used_aliases):
    base = re.sub(r"[^A-Za-z0-9_]", "_", name).strip("_") or "P"
    if base[0].isdigit():
        base = "P_" + base
    alias = base
    n = 1
    while alias in used_aliases:
        n += 1
        alias = f"{base}_{n}"
    used_aliases[alias] = name
    return alias


HTML_TAG_RE = re.compile(
    r"</?(?:b|i|u|ul|ol|li|a|br|p|span|font|div|table|tr|td|th|img|hr)\b[^>]*>",
    re.IGNORECASE,
)


def escape_puml_text(text):
    text = (text or "")
    text = HTML_TAG_RE.sub(" ", text)
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    # Any remaining literal angle brackets are UML placeholder markers (e.g.
    # "<stubbed function call>"), not HTML - escape them so PlantUML doesn't
    # try to interpret them as creole/HTML markup.
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    return text


def find_sequence_diagrams(repo):
    """Find every diagram with Type == 'Sequence' anywhere in the model and
    return a list of (Diagram, breadcrumb_path).

    Uses `repo.SQLQuery()` against the underlying `t_diagram` table
    (`Diagram_Type='Sequence'`) instead of a recursive COM Package/Element
    tree walk. Confirmed (2026-08-03) this correctly matches ALL genuine
    sequence/interaction diagrams in this model - including the
    'Dyn_<SwSubSys>_Scenario(-io)_<Name>' scenario diagrams (e.g.
    'Dyn_SwSubSys_AppModeMng_Scenerio_ApplicationOn', DiagramID 5271), which
    are owned directly by a leaf UseCase Element (Element.Diagrams) nested
    under a parent 'Dyn_<SwSubSys>' UseCase Element (Element.Elements) - NOT
    reachable via any Package.Diagrams walk. A prior version of this function
    only checked Package.Diagrams and so found just 1 diagram; a full COM
    tree walk that also recurses into every Element's nested Elements to find
    these IS correct but impractically slow for this model (many minutes /
    effective hang for ~800 packages / tens of thousands of elements).
    SQLQuery finds all matching Diagram_IDs directly against the repository
    file in well under a second; each ID is then resolved individually via
    the COM API (GetDiagramByID) for full content and a package breadcrumb -
    this is fast because it is O(matches), not O(whole model).
    """
    xml = repo.SQLQuery(
        "SELECT Diagram_ID FROM t_diagram WHERE Diagram_Type='Sequence'"
    )
    ids = [int(x) for x in re.findall(r"<Diagram_ID>(\d+)</Diagram_ID>", xml)]

    breadcrumb_cache = {}
    results = []
    for did in ids:
        try:
            d = repo.GetDiagramByID(did)
        except Exception:
            continue
        if d is None:
            continue
        breadcrumb = ea.resolve_package_breadcrumb(repo, d.PackageID, breadcrumb_cache)
        results.append((d, breadcrumb))
    return results


def resolve_participant_label(repo, elem):
    """Return a display label for a diagram-object element. Many lifeline
    Component instances in this model have a blank Element.Name (they are
    anonymous instances) with the real label only available via their linked
    Classifier (Element.ClassifierID -> Element.Name), e.g. an unnamed
    Component instance classified by the 'AmmSM' Component. Falls back to the
    element's own Name, then its Alias, never fabricates a label."""
    name = getattr(elem, "Name", "") or ""
    if name:
        return name
    classifier_id = getattr(elem, "ClassifierID", 0) or 0
    if classifier_id:
        try:
            classifier = repo.GetElementByID(classifier_id)
            if classifier is not None and classifier.Name:
                return classifier.Name
        except Exception:
            pass
    alias = getattr(elem, "Alias", "") or ""
    return alias


def diagram_to_plantuml(repo, diagram):
    do_list = []
    for i in range(diagram.DiagramObjects.Count):
        do = diagram.DiagramObjects.GetAt(i)
        elem = repo.GetElementByID(do.ElementID)
        do_list.append((do, elem))

    participants = [
        (do, e, resolve_participant_label(repo, e))
        for do, e in do_list
        if e.Type in PARTICIPANT_TYPES and resolve_participant_label(repo, e)
    ]
    notes = [(do, e) for do, e in do_list if e.Type in NOTE_TYPES]
    fragments = [(do, e) for do, e in do_list if e.Type in FRAGMENT_TYPES and e.Name]

    # left-to-right visual order
    participants.sort(key=lambda triple: triple[0].Left)

    lines = ["@startuml"]
    alias_map = {}
    used_aliases = {}
    for do, elem, label in participants:
        alias = puml_alias(label, used_aliases)
        alias_map[elem.ElementID] = alias
        kind = "actor" if elem.Type == "Actor" else "participant"
        lines.append(f'{kind} "{escape_puml_text(label)}" as {alias}')

    lines.append("")

    # PlantUML's `note over A, B` only accepts AT MOST two lifeline refs (it
    # draws a note spanning from the first to the second); listing 3+ refs
    # (or the non-existent `*` wildcard) is a hard syntax error, not merely a
    # rendering quirk. To visually span the whole diagram width we therefore
    # span from the leftmost to the rightmost participant only.
    #
    # Block form (`note over A, B` / text / `end note`) is used instead of
    # the inline `note over A, B : text` shorthand: fragment names routinely
    # contain their own colon (e.g. "Fragment: No light source error
    # detected"), and some PlantUML parsers/dialects mis-split the line on
    # that second colon, corrupting everything parsed afterwards. The block
    # form has no colon-based line splitting at all, so it is unambiguous
    # regardless of what characters appear in the fragment name.
    aliases = list(alias_map.values())
    if aliases:
        span = aliases[0] if len(aliases) == 1 else f"{aliases[0]}, {aliases[-1]}"
        for do, elem in fragments:
            lines.append(f"note over {span}")
            lines.append(f"Fragment: {escape_puml_text(elem.Name)}")
            lines.append("end note")

    n_messages = 0
    n_skipped = 0
    for i in range(diagram.DiagramLinks.Count):
        dl = diagram.DiagramLinks.GetAt(i)
        conn = repo.GetConnectorByID(dl.ConnectorID)
        client_alias = alias_map.get(conn.ClientID)
        supplier_alias = alias_map.get(conn.SupplierID)
        if not client_alias or not supplier_alias:
            n_skipped += 1
            continue
        label = escape_puml_text(conn.Name) or "(message)"
        lines.append(f"{client_alias} -> {supplier_alias} : {label}")
        n_messages += 1

    # Block form (`note left` / text / `end note`) instead of the inline
    # `note left: text` shorthand, for the same reason as the fragment notes
    # above: free-text EA notes frequently contain their own colon (e.g.
    # "Rational: ..."), which can corrupt inline-colon-delimited note syntax
    # in some PlantUML parsers.
    for do, elem in notes:
        note_text = escape_puml_text(getattr(elem, "Notes", "") or elem.Name)
        if note_text:
            lines.append("note left")
            lines.append(note_text)
            lines.append("end note")

    if len(lines) == 2:
        # No participants, fragments, messages, or notes were modeled at all
        # (a genuinely empty EA diagram, e.g. an unfilled placeholder). An
        # @startuml/@enduml block with nothing between them is itself a
        # PlantUML syntax error ("Empty description"), so emit a comment.
        lines.append("' No participants or messages were modeled for this diagram.")

    lines.append("@enduml")
    return "\n".join(lines), n_messages, n_skipped


def structural_selfcheck(puml_text):
    """Cheap structural lint of generated PlantUML text (no external plantuml
    dependency available in this environment). Does not guarantee the file
    renders, but catches the classes of structural mistakes this generator
    could plausibly introduce: unbalanced @startuml/@enduml, unbalanced
    note/end note blocks, and duplicate participant aliases. Returns a list
    of human-readable problem strings (empty list == no problems found)."""
    lines = puml_text.split("\n")
    problems = []

    starts = sum(1 for l in lines if l.strip() == "@startuml")
    ends = sum(1 for l in lines if l.strip() == "@enduml")
    if starts != 1 or ends != 1:
        problems.append(f"expected exactly one @startuml/@enduml pair, found {starts}/{ends}")

    note_opens = sum(
        1 for l in lines
        if l.strip() == "note left" or l.strip().startswith("note over ")
    )
    note_ends = sum(1 for l in lines if l.strip() == "end note")
    if note_opens != note_ends:
        problems.append(f"unbalanced note/end note blocks: {note_opens} opened, {note_ends} closed")

    aliases = []
    for l in lines:
        stripped = l.strip()
        if stripped.startswith("participant ") or stripped.startswith("actor "):
            m = re.search(r'\bas\s+(\S+)\s*$', stripped)
            if m:
                aliases.append(m.group(1))
    dupes = {a for a in aliases if aliases.count(a) > 1}
    if dupes:
        problems.append(f"duplicate participant alias(es): {sorted(dupes)}")

    return problems


MANIFEST_NAME = "_export_manifest.json"


def load_manifest(output_dir):
    path = os.path.join(output_dir, MANIFEST_NAME)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_manifest(output_dir, manifest):
    path = os.path.join(output_dir, MANIFEST_NAME)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    os.replace(tmp_path, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output directory for .puml files")
    parser.add_argument("--fresh", action="store_true",
                         help="Ignore any existing resume manifest and re-export every diagram "
                              "from scratch (default: resume, skipping diagrams already recorded "
                              "as successfully exported in a prior run).")
    parser.add_argument("--scope", default=None,
                         help="Only export sequence diagrams whose package breadcrumb path "
                              "contains this substring, e.g. 'SwSubSys_TouchCtl' (one subsystem) "
                              "or 'Platform' (whole platform subtree). Omit to export every "
                              "Sequence-type diagram in the model.")
    args = parser.parse_args()

    project = ea.resolve_project_path()
    print(f"[info] Opening: {project}")
    repo = ea.connect(project)

    try:
        seq_diagrams = find_sequence_diagrams(repo)
        if not seq_diagrams:
            print("[result] No Sequence-type diagrams found anywhere in the EA model. "
                  "Nothing to export - not fabricating any .puml content.")
            return

        if args.scope:
            before = len(seq_diagrams)
            seq_diagrams = [
                (d, bc) for d, bc in seq_diagrams if any(args.scope in part for part in bc)
            ]
            print(f"[info] --scope '{args.scope}' matched {len(seq_diagrams)} of {before} "
                  f"discovered sequence diagram(s).")
            if not seq_diagrams:
                print("[result] Nothing matched this --scope. Nothing to export.")
                return

        os.makedirs(args.output, exist_ok=True)
        print(f"[info] Found {len(seq_diagrams)} sequence diagram(s) in the model.")

        # Resume support: EA's COM automation server can become unstable and
        # crash the whole process (native crash, no Python exception/traceback)
        # after processing a large-but-variable number of diagrams in one
        # session. Rather than trying to prevent that (out of this script's
        # control), track per-diagram success in a manifest so a re-run picks
        # up where the previous one stopped instead of starting over.
        manifest = {} if args.fresh else load_manifest(args.output)
        if manifest:
            print(f"[info] Resuming: {len(manifest)} diagram(s) already exported in a prior run "
                  f"will be skipped (use --fresh to ignore and re-export everything).")

        used_filenames = {}
        n_exported = 0
        n_failed = 0
        n_skipped_resume = 0
        lint_issues = []
        for diagram, breadcrumb in seq_diagrams:
            key = str(diagram.DiagramID)
            prior = manifest.get(key)
            if prior and os.path.exists(os.path.join(args.output, prior["fname"] + ".puml")):
                used_filenames[prior["fname"]] = diagram.DiagramID
                n_skipped_resume += 1
                continue

            try:
                puml, n_msgs, n_skipped = diagram_to_plantuml(repo, diagram)
            except Exception as exc:
                n_failed += 1
                print(f"[FAILED] '{diagram.Name}' (path: {' / '.join(breadcrumb)}) -> {exc!r}")
                continue

            fname = sanitize_filename(diagram.Name or f"diagram_{diagram.DiagramID}")
            if fname in used_filenames:
                fname = f"{fname}__{diagram.DiagramID}"
            used_filenames[fname] = diagram.DiagramID
            out_path = os.path.join(args.output, f"{fname}.puml")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(puml)
            n_exported += 1
            manifest[key] = {"fname": fname}
            save_manifest(args.output, manifest)

            problems = structural_selfcheck(puml)
            if problems:
                lint_issues.append((fname, problems))
                print(f"[export] '{diagram.Name}' (path: {' / '.join(breadcrumb)})")
                print(f"          -> {out_path}  ({n_msgs} messages rendered, {n_skipped} links skipped "
                      f"[endpoint not a diagram participant]) -- LINT ISSUES: {problems}")
            else:
                print(f"[export] '{diagram.Name}' (path: {' / '.join(breadcrumb)})")
                print(f"          -> {out_path}  ({n_msgs} messages rendered, {n_skipped} links skipped "
                      f"[endpoint not a diagram participant])")

        print(f"\n[summary] Exported {n_exported} .puml file(s) this run, {n_skipped_resume} skipped "
              f"(already done in a prior run), {n_failed} diagram(s) failed to convert, "
              f"out of {len(seq_diagrams)} discovered Sequence-type diagram(s).")
        if lint_issues:
            print(f"[summary] {len(lint_issues)} file(s) have structural lint issues:")
            for fname, problems in lint_issues:
                print(f"  - {fname}: {problems}")
        else:
            print("[summary] Structural self-check: no issues found in any exported file.")
    finally:
        ea.disconnect(repo)


if __name__ == "__main__":
    main()
