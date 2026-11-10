"""The one door to Claude: the official claude CLI, signed in with the user's own plan.

Every call runs isolated: no tools, no MCP servers, no user hooks or plugins, no saved
session. Images go in as base64 blocks over stream-json, so Claude never touches files.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import config

CLI_FALLBACKS = ("/opt/homebrew/bin/claude", "/usr/local/bin/claude", str(Path.home() / ".local/bin/claude"))
JSON_RETRY_NOTE = "Your last reply was not valid JSON. Reply again with only the JSON object, nothing before or after it."


class BrainError(Exception):
    """Claude could not answer; the message is safe to show the user."""


def find_cli() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    return next((p for p in CLI_FALLBACKS if Path(p).exists()), None)


def _image_block(path: Path) -> dict:
    media = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}


def build_message(prompt: str, images: list[Path]) -> str:
    content = [_image_block(p) for p in images] + [{"type": "text", "text": prompt}]
    return json.dumps({"type": "user", "message": {"role": "user", "content": content}})


def friendly_cli_error(text: str) -> str:
    low = text.lower()
    if "not logged in" in low or "/login" in low or "invalid api key" in low:
        return "Claude isn't signed in on this Mac. Open Terminal, run: claude auth login, then press Retry."
    if "usage limit" in low or "rate limit" in low or "limit reached" in low:
        return f"Your Claude plan's usage limit was reached. Try again later. ({text.strip()[:160]})"
    return f"Claude couldn't answer: {text.strip()[:300]}"


def _call(prompt: str, system: str, images: list[Path], model: str, timeout: int) -> str:
    cli = find_cli()
    if not cli:
        raise BrainError("The claude command isn't installed. Open Terminal and run: npm install -g @anthropic-ai/claude-code")
    args = [cli, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
            "--setting-sources", "project", "--strict-mcp-config", "--tools", "", "--disable-slash-commands",
            "--no-session-persistence", "--system-prompt", system]
    if model:
        args += ["--model", model]
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_CODE_")}
    with tempfile.TemporaryDirectory(prefix="hookscope-") as workdir:
        try:
            done = subprocess.run(args, input=build_message(prompt, images), capture_output=True, text=True,
                                  timeout=timeout, cwd=workdir, env=env, check=False)
        except subprocess.TimeoutExpired as exc:
            raise BrainError("Claude took too long to answer. Press Retry.") from exc
    result = parse_result(done.stdout)
    if result is None:
        raise BrainError(friendly_cli_error(done.stderr or done.stdout or "no reply"))
    if result.get("is_error"):
        raise BrainError(friendly_cli_error(str(result.get("result") or result.get("error") or "unknown error")))
    return str(result.get("result") or "")


def parse_result(stdout: str) -> dict | None:
    for line in reversed((stdout or "").splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result":
            return event
    return None


def extract_json(text: str) -> dict | None:
    """Pull the first complete JSON object out of a reply, ignoring fences and chatter."""
    start = text.find("{")
    while start != -1:
        depth, in_string, escaped = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start: i + 1])
                    except ValueError:
                        break
                    return value if isinstance(value, dict) else None
        start = text.find("{", start + 1)
    return None


def ask_text(prompt: str, system: str, images: list[Path] | None = None, timeout: int = config.CLAUDE_TIMEOUT_SECONDS) -> str:
    return _call(prompt, system, images or [], config.load_settings().get("model", ""), timeout).strip()


def ask_json(prompt: str, system: str, images: list[Path] | None = None, timeout: int = config.CLAUDE_TIMEOUT_SECONDS) -> dict:
    model = config.load_settings().get("model", "")
    reply = _call(prompt, system, images or [], model, timeout)
    parsed = extract_json(reply)
    if parsed is not None:
        return parsed
    retry = f"{prompt}\n\n{JSON_RETRY_NOTE}\n\nYour last reply was:\n{reply[:6000]}"
    parsed = extract_json(_call(retry, system, [], model, timeout))
    if parsed is None:
        raise BrainError("Claude's answer couldn't be read. Press Retry.")
    return parsed


def auth_status() -> dict:
    cli = find_cli()
    if not cli:
        return {"ok": False, "detail": "claude command not installed"}
    try:
        done = subprocess.run([cli, "auth", "status"], capture_output=True, text=True, timeout=30, check=False)
        data = json.loads(done.stdout or "{}")
    except (subprocess.TimeoutExpired, ValueError):
        return {"ok": False, "detail": "couldn't read sign-in status"}
    if data.get("loggedIn"):
        return {"ok": True, "detail": f"signed in ({data.get('authMethod', 'claude')})"}
    return {"ok": False, "detail": "not signed in"}
