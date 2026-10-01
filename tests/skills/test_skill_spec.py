"""Lint every skill in the repo against the Agent Skills spec.

Checks, per ``skills/**/SKILL.md``:
- frontmatter is a strict YAML mapping (PyYAML ``safe_load``, no duplicate keys)
- ``name`` equals the directory name, is <= 64 chars and uses lowercase/digits/hyphens
- ``description`` is a non-empty string of <= 1024 chars
- SKILL.md has fewer than 500 lines
- relative files referenced from SKILL.md (``references/...``, ``scripts/...``,
  markdown links) exist
Airflow skills additionally use only portable frontmatter keys, and every vendored
copy of a ``skills/airflow/_shared`` file is byte-identical to the canonical file.

Violations in skills outside ``skills/airflow`` that predate this test are recorded in
``KNOWN_VIOLATIONS`` and reported as xfail instead of being fixed here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / "skills"
AIRFLOW = SKILLS / "airflow"
SHARED = AIRFLOW / "_shared"

SKILL_FILES = sorted(SKILLS.rglob("SKILL.md"))
AIRFLOW_SKILL_FILES = sorted(AIRFLOW.rglob("SKILL.md"))

# Keys defined by the Agent Skills spec (agentskills.io/specification).
PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_NAME = 64
MAX_DESCRIPTION = 1024
MAX_COMPATIBILITY = 500
MAX_LINES = 500

# (skill dir relative to skills/, check) -> reason. Pre-existing, owned by other skills.
KNOWN_VIOLATIONS = {
    ("altimate-code", "strict_yaml"): (
        "unquoted description contains ': ', which strict YAML rejects; "
        "owned by the altimate-code skill"),
}

# Relative file references inside SKILL.md: `references/x.md`, `<skill-dir>/scripts/x.py`,
# `SKILL_DIR/scripts/x.py`, and [text](relative/path) links.
REF_RE = re.compile(r"(?<![\w/.-])(?:<skill-dir>/|SKILL_DIR/)?((?:references|scripts|assets)/[\w./-]+\.\w+)")
LINK_RE = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys."""


def _no_duplicates(loader, node, deep=False):
    keys = [loader.construct_object(k, deep=deep) for k, _ in node.value]
    dupes = {k for k in keys if keys.count(k) > 1}
    if dupes:
        raise yaml.constructor.ConstructorError(None, None, f"duplicate keys: {sorted(dupes)}",
                                                node.start_mark)
    return loader.construct_mapping(node, deep=deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates)


def split_frontmatter(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)$", text, re.S)
    assert m, f"{path}: missing '---' frontmatter block at top of file"
    return m.group(1), m.group(2)


def load_frontmatter(path: Path) -> dict:
    raw, _ = split_frontmatter(path)
    data = yaml.load(raw, Loader=_StrictLoader)  # noqa: S506 - SafeLoader subclass
    assert isinstance(data, dict), f"{path}: frontmatter is not a mapping"
    return data


def skill_id(path: Path) -> str:
    return str(path.parent.relative_to(SKILLS))


def xfail_known(path: Path, check: str) -> None:
    key = (skill_id(path), check)
    if key in KNOWN_VIOLATIONS:
        pytest.xfail(KNOWN_VIOLATIONS[key])


def frontmatter_or_xfail(path: Path) -> dict:
    """Loads the frontmatter; a skill whose YAML is a known violation cannot be checked further."""
    try:
        return load_frontmatter(path)
    except yaml.YAMLError:
        xfail_known(path, "strict_yaml")
        raise


ids = [skill_id(p) for p in SKILL_FILES]


def test_skills_found():
    assert AIRFLOW_SKILL_FILES, "no airflow skills found"
    assert len(SKILL_FILES) >= len(AIRFLOW_SKILL_FILES)


@pytest.mark.parametrize("path", SKILL_FILES, ids=ids)
def test_frontmatter_is_strict_yaml(path):
    xfail_known(path, "strict_yaml")
    load_frontmatter(path)


@pytest.mark.parametrize("path", SKILL_FILES, ids=ids)
def test_name_matches_directory(path):
    xfail_known(path, "name")
    name = frontmatter_or_xfail(path).get("name")
    assert name == path.parent.name
    assert isinstance(name, str) and len(name) <= MAX_NAME
    assert NAME_RE.match(name), f"name {name!r} must be lowercase letters, digits and single hyphens"


@pytest.mark.parametrize("path", SKILL_FILES, ids=ids)
def test_description_length(path):
    xfail_known(path, "description")
    desc = frontmatter_or_xfail(path).get("description")
    assert isinstance(desc, str) and desc.strip(), "description must be a non-empty string"
    assert len(desc) <= MAX_DESCRIPTION, f"description is {len(desc)} chars (max {MAX_DESCRIPTION})"


@pytest.mark.parametrize("path", SKILL_FILES, ids=ids)
def test_skill_md_under_500_lines(path):
    xfail_known(path, "lines")
    n = len(path.read_text(encoding="utf-8").splitlines())
    assert n < MAX_LINES, f"SKILL.md has {n} lines (must be < {MAX_LINES}); move detail to references/"


@pytest.mark.parametrize("path", SKILL_FILES, ids=ids)
def test_referenced_files_exist(path):
    xfail_known(path, "references")
    _, body = split_frontmatter(path)
    refs = set(REF_RE.findall(body))
    refs |= {t for t in LINK_RE.findall(body) if "://" not in t and not t.startswith("mailto:")}
    missing = sorted(r for r in refs if not (path.parent / r).is_file())
    assert missing == [], f"referenced from {skill_id(path)}/SKILL.md but missing: {missing}"


@pytest.mark.parametrize("path", AIRFLOW_SKILL_FILES, ids=[skill_id(p) for p in AIRFLOW_SKILL_FILES])
def test_airflow_frontmatter_is_portable(path):
    fm = load_frontmatter(path)
    extra = sorted(set(fm) - PORTABLE_KEYS)
    assert extra == [], f"non-portable frontmatter keys: {extra}"
    if "compatibility" in fm:
        assert isinstance(fm["compatibility"], str) and len(fm["compatibility"]) <= MAX_COMPATIBILITY
    if "metadata" in fm:
        meta = fm["metadata"]
        assert isinstance(meta, dict)
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in meta.items()), \
            "metadata must map strings to strings (quote versions)"


def test_shared_dir_is_not_a_skill():
    """_shared holds canonical files vendored into each skill; it must never load as a skill."""
    assert SHARED.is_dir()
    assert not list(SHARED.rglob("SKILL.md"))
    manifest = REPO / ".claude-plugin" / "marketplace.json"
    if manifest.exists():
        listed = [s for p in json.loads(manifest.read_text())["plugins"] for s in p.get("skills", [])]
        assert not [s for s in listed if "_shared" in s]


def _vendored_copies() -> list[tuple[Path, Path]]:
    pairs = []
    for canonical in sorted(p for p in SHARED.iterdir() if p.is_file()):
        for skill_md in AIRFLOW_SKILL_FILES:
            pairs += [(canonical, c) for c in sorted(skill_md.parent.rglob(canonical.name))]
    return pairs


def test_every_airflow_skill_vendors_the_shared_files_it_references():
    for skill_md in AIRFLOW_SKILL_FILES:
        _, body = split_frontmatter(skill_md)
        for canonical in SHARED.iterdir():
            if canonical.name in body:
                assert list(skill_md.parent.rglob(canonical.name)), \
                    f"{skill_id(skill_md)} references {canonical.name} but has no vendored copy"


@pytest.mark.parametrize("canonical,copy", _vendored_copies(),
                         ids=[str(c.relative_to(AIRFLOW)) for _, c in _vendored_copies()])
def test_vendored_copy_is_byte_identical(canonical, copy):
    assert copy.read_bytes() == canonical.read_bytes(), \
        f"re-copy {canonical.relative_to(REPO)} to {copy.relative_to(REPO)}"
