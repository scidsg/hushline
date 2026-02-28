from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPO_ROOT / "docs"
LIBRARY_ROOT = DOCS_ROOT / "library"
REQUIRED_DOCS = [
    DOCS_ROOT / "README.md",
    LIBRARY_ROOT / "README.md",
    LIBRARY_ROOT / "welcome" / "README.md",
    LIBRARY_ROOT / "welcome" / "welcome-to-hush-line.md",
    LIBRARY_ROOT / "getting-started" / "README.md",
    LIBRARY_ROOT / "getting-started" / "start-here.md",
    LIBRARY_ROOT / "getting-started" / "new-user-onboarding.md",
    LIBRARY_ROOT / "getting-started" / "prep-your-account.md",
    LIBRARY_ROOT / "getting-started" / "secure-your-account.md",
    LIBRARY_ROOT / "getting-started" / "share-your-tip-line.md",
    LIBRARY_ROOT / "using-your-tip-line" / "README.md",
    LIBRARY_ROOT / "using-your-tip-line" / "your-inbox.md",
    LIBRARY_ROOT / "using-your-tip-line" / "reading-messages.md",
    LIBRARY_ROOT / "using-your-tip-line" / "tools.md",
    LIBRARY_ROOT / "using-your-tip-line" / "email-validation.md",
    LIBRARY_ROOT / "using-your-tip-line" / "vision-assistant.md",
    LIBRARY_ROOT / "using-your-tip-line" / "message-statuses.md",
    LIBRARY_ROOT / "using-your-tip-line" / "account-verification.md",
    LIBRARY_ROOT / "using-your-tip-line" / "download-your-data.md",
    LIBRARY_ROOT / "using-your-tip-line" / "dark-mode.md",
    LIBRARY_ROOT / "personal-server" / "README.md",
    LIBRARY_ROOT / "personal-server" / "the-hush-line-personal-server.md",
    LIBRARY_ROOT / "personal-server" / "specs.md",
]


def _iter_markdown_files() -> list[Path]:
    return [DOCS_ROOT / "README.md", *sorted(LIBRARY_ROOT.rglob("*.md"))]


def _iter_local_targets(markdown_path: Path) -> list[Path]:
    content = markdown_path.read_text(encoding="utf-8")
    targets: list[Path] = []
    cursor = 0

    while True:
        marker = content.find("](", cursor)
        if marker == -1:
            break

        start = content.rfind("[", 0, marker)
        end = content.find(")", marker + 2)
        cursor = marker + 2

        if start == -1 or end == -1:
            continue

        target = content[marker + 2 : end].strip()
        cursor = end + 1
        if not target or target.startswith("#"):
            continue
        if "://" in target or target.startswith("mailto:"):
            continue
        path_part = target.split("#", 1)[0]
        targets.append((markdown_path.parent / path_part).resolve())
    return targets


def test_library_docs_mirror_contains_required_pages() -> None:
    missing = [path.relative_to(REPO_ROOT) for path in REQUIRED_DOCS if not path.is_file()]
    assert not missing, f"Missing mirrored docs: {missing}"


def test_library_docs_relative_links_resolve() -> None:
    missing_targets: list[str] = []

    for markdown_path in _iter_markdown_files():
        for target in _iter_local_targets(markdown_path):
            if not target.exists():
                source = markdown_path.relative_to(REPO_ROOT)
                missing_targets.append(f"{source} -> {target.relative_to(REPO_ROOT)}")

    assert not missing_targets, f"Broken docs links: {missing_targets}"
