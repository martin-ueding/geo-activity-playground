import argparse
import re
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Extract changelog for a specific version."
    )
    parser.add_argument(
        "changelog_path", type=Path, help="Path to the changelog markdown file."
    )
    parser.add_argument(
        "version", type=str, help="Version string to extract (e.g., 1.20.0)."
    )
    args = parser.parse_args()

    if not args.changelog_path.exists():
        print(f"Error: File not found: {args.changelog_path}", file=sys.stderr)
        sys.exit(1)

    with open(args.changelog_path, encoding="utf-8") as f:
        lines = f.readlines()

    # Pattern to match the version header.
    # Matches "## Version 1.20.0" followed by anything (e.g. date)
    version_pattern = re.compile(rf"^## Version {re.escape(args.version)}\b")
    # Pattern to match any new section starting with "## "
    section_pattern = re.compile(r"^## ")

    content = []
    capturing = False
    found = False

    for line in lines:
        if version_pattern.match(line):
            capturing = True
            found = True
            continue

        if capturing:
            if section_pattern.match(line):
                break
            content.append(line)

    if not found:
        print(
            f"Error: Version {args.version} not found in {args.changelog_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Strip leading/trailing empty lines
    text = "".join(content).strip()
    print(text)


if __name__ == "__main__":
    main()
