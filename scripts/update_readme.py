"""Copy the results from eval/results.md into README.md (between the results markers), so every
number in the README comes from the generated eval file.

    uv run python scripts/update_readme.py
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    results = (ROOT / "eval" / "results.md").read_text()
    body = results.split("\n", 2)[2].strip()  # drop the file's own title
    body = re.sub(r"^## ", "### ", body, flags=re.M)
    readme = ROOT / "README.md"
    text = readme.read_text()
    pattern = r"(<!-- results:start -->\n).*?(\n<!-- results:end -->)"
    new = re.sub(pattern, lambda m: m.group(1) + body + m.group(2), text, flags=re.S)
    readme.write_text(new)
    print("README results updated" if new != text else "README results unchanged")


if __name__ == "__main__":
    main()
