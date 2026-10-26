"""Package this repo as a Claude skill.

Builds a self-contained skill folder (SKILL.md, the engine, profiles, docs
as references/, helper scripts, the demo book) plus a zipped .skill file:

    python scripts/package_skill.py            # -> dist/photobook/ and dist/photobook.skill

Claude Code: copy dist/photobook/ to ~/.claude/skills/photobook/.
claude.ai: upload dist/photobook.skill under Settings > Capabilities > Skills.
"""
import argparse
import os
import re
import shutil
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_NAME = "photobook"

# repo path -> path inside the skill
COPY = {
    "skill/SKILL.md": "SKILL.md",
    "photobook": "photobook",
    "profiles": "profiles",
    "LICENSE": "LICENSE",
    "docs/GETTING_STARTED.md": "references/GETTING_STARTED.md",
    "docs/CHOOSING_PHOTOS.md": "references/CHOOSING_PHOTOS.md",
    "docs/ENGINE.md": "references/ENGINE.md",
    "docs/PIPELINE.md": "references/PIPELINE.md",
    "docs/TEXTE_VORLAGE_PROTOCOL.md": "references/TEXTE_VORLAGE_PROTOCOL.md",
    "docs/LESSONS_LEARNED.md": "references/LESSONS_LEARNED.md",
    "docs/DEVICE_DELIVERY.md": "references/DEVICE_DELIVERY.md",
    "schema/book_schema.md": "references/book_schema.md",
    "schema/manifest_schema.md": "references/manifest_schema.md",
    "scripts/build_index.py": "scripts/build_index.py",
    "scripts/suggest_selection.py": "scripts/suggest_selection.py",
    "scripts/make_manifest.py": "scripts/make_manifest.py",
    "scripts/gps_report.py": "scripts/gps_report.py",
    "scripts/photo_source.py": "scripts/photo_source.py",
    "scripts/heic_extract.py": "scripts/heic_extract.py",
    "scripts/batch_heic.py": "scripts/batch_heic.py",
    "scripts/build_contact_sheets.py": "scripts/build_contact_sheets.py",
    "scripts/extract_photos.py": "scripts/extract_photos.py",
    "examples/demo/book.json": "examples/demo/book.json",
    "examples/demo/make_demo_photos.py": "examples/demo/make_demo_photos.py",
}

IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")


def fix_links(text):
    """Docs and schemas sit side by side in references/ - repoint the
    relative links that crossed folders in the repo."""
    text = re.sub(r"\]\((?:\.\./)?(?:docs|schema)/([A-Za-z_]+\.md)", r"](\1", text)
    text = re.sub(r"\]\(\.\./examples/", "](../examples/", text)
    # the skill has no README; its starting guide is SKILL.md
    text = text.replace('"Starting a book with Claude" in the [README](../README.md)',
                        '"Before you start: the brief" in [SKILL.md](../SKILL.md)')
    text = text.replace("](../README.md)", "](../SKILL.md)")
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    args = ap.parse_args()

    skill_dir = os.path.join(args.out, SKILL_NAME)
    shutil.rmtree(skill_dir, ignore_errors=True)
    for src, dst in COPY.items():
        src_path, dst_path = os.path.join(ROOT, src), os.path.join(skill_dir, dst)
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dst_path, ignore=IGNORE)
        elif dst.startswith("references/"):
            with open(src_path) as f:
                text = fix_links(f.read())
            with open(dst_path, "w") as f:
                f.write(text)
        else:
            shutil.copy2(src_path, dst_path)

    archive = os.path.join(args.out, f"{SKILL_NAME}.skill")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _, files in os.walk(skill_dir):
            for name in sorted(files):
                path = os.path.join(base, name)
                z.write(path, os.path.relpath(path, args.out))
    print(f"skill folder: {skill_dir}\narchive:      {archive}")


if __name__ == "__main__":
    main()
