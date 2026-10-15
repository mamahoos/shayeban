"""Check that relative .md links under docs/ actually exist."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def main() -> int:
    broken = []
    n = 0

    for md in sorted(DOCS.rglob("*.md")):
        for href in MD_LINK.findall(md.read_text(encoding="utf-8")):
            target = href.strip().split("#", 1)[0].strip()
            if not target.endswith(".md"):
                continue
            if target.startswith(("http://", "https://", "mailto:")):
                continue

            n += 1
            dest = (md.parent / target).resolve()
            try:
                dest.relative_to(ROOT.resolve())
            except ValueError:
                broken.append(f"{md.relative_to(ROOT)}: outside repo ({href})")
                continue
            if not dest.is_file():
                broken.append(f"{md.relative_to(ROOT)}: {href}")

    if broken:
        print("broken docs links:")
        print("\n".join(broken))
        return 1

    print(f"ok ({n} links)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
