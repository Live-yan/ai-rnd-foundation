"""One short-lived LiteLLM ChatGPT process per operation (no shared auth.json).

Stdin/stdout are private parent/child pipes. Diagnostics never include tokens.
Private Authenticator methods are covered by an installed-SDK contract test.
"""
import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import sys


def execute(data: dict) -> dict:
    from factory.privacy import install_sdk_log_safety
    install_sdk_log_safety()
    import litellm
    import httpx
    from litellm.llms.chatgpt.authenticator import Authenticator
    from litellm.llms.chatgpt.common_utils import CHATGPT_DEVICE_TOKEN_URL, CHATGPT_DEVICE_VERIFY_URL
    litellm.turn_off_message_logging = True
    litellm.suppress_debug_info = True
    litellm.set_verbose = False
    auth = Authenticator()
    operation = data["operation"]
    if operation == "begin":
        result = dict(auth._request_device_code())
        result["verification_url"] = CHATGPT_DEVICE_VERIFY_URL
        return {"pending": result}
    if operation == "poll":
        pending = data["pending"]
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.post(CHATGPT_DEVICE_TOKEN_URL, json={
                "device_auth_id": pending["device_auth_id"], "user_code": pending["user_code"],
            })
        if response.status_code in {403, 404, 429}:
            return {"waiting": True, "slow_down": response.status_code == 429}
        if response.status_code != 200:
            raise RuntimeError("Device authorization was rejected")
        tokens = auth._exchange_code_for_tokens(response.json())
        return {"tokens": auth._build_auth_record(tokens)}
    if operation != "complete":
        raise ValueError("Unknown operation")
    record = data["tokens"]
    if not record.get("access_token") or not record.get("refresh_token"):
        raise RuntimeError("Login required")
    path = Path(auth.auth_file)
    path.write_text(json.dumps(record))
    path.chmod(0o600)
    # Completion must NEVER silently start a new device login or print a device code.
    def no_interactive_login(self):
        raise RuntimeError("Session expired; reconnect in the provider page")
    Authenticator._login_device_code = no_interactive_login
    kwargs = data["kwargs"]
    if kwargs["custom_llm_provider"] != "chatgpt" or not kwargs["model"].startswith("chatgpt/"):
        raise ValueError("Wrong subscription route")
    response = asyncio.run(litellm.acompletion(**kwargs))
    return {"content": response.choices[0].message.content, "tokens": json.loads(path.read_text())}


def main():
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        try:
            raw = sys.stdin.read(1000001)
            if len(raw) > 1000000:
                raise ValueError("Oversized job")
            result = execute(json.loads(raw))
        except Exception:
            result = {"error": "ChatGPT authorization/request failed; check account access and reconnect if necessary"}
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    main()
