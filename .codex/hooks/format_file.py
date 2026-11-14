import json
import subprocess
import sys


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    tool_input = payload.get("tool_input", {})
    tool_response = payload.get("tool_response", {})
    file_path = tool_response.get("filePath") or tool_input.get("file_path", "")

    if not file_path.endswith(".py"):
        return 0

    subprocess.run(
        [sys.executable, "-m", "black", "--quiet", file_path],
        capture_output=True,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
