import json
import re
import sys

PROTECTED_PATTERNS = [
    re.compile(r"(^|[\\/])\.env$"),
    re.compile(r"(^|[\\/])\.env\.[^\\/]+$"),
    re.compile(r"(^|[\\/])migrations[\\/]"),
    re.compile(r"(^|[\\/])package-lock\.json$"),
    re.compile(r"(^|[\\/])yarn\.lock$"),
]


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return 0

    normalized = file_path.replace("\\", "/")
    for pattern in PROTECTED_PATTERNS:
        if pattern.search(normalized):
            sys.stderr.write(
                f"Blocked: '{file_path}' is a protected file and cannot be modified by Claude Code.\n"
            )
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
