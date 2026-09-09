"""Opt-in isolated SDK experiment. Not part of the default factory pipeline; not live-tested here."""
import os
from pydantic import SecretStr


def main():
    from openhands.sdk import LLM, Conversation
    from openhands.tools.preset.default import get_default_agent
    from openhands.workspace import DockerWorkspace
    image = os.environ.get("OPENHANDS_SERVER_IMAGE", "")
    if "@sha256:" not in image:
        raise SystemExit("Set OPENHANDS_SERVER_IMAGE to a reviewed, SDK-compatible immutable digest")
    for name in ("LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL"):
        if not os.environ.get(name):
            raise SystemExit(f"Missing {name}; platform .env is deliberately not read")
    llm = LLM(usage_id="agent", model=os.environ["LLM_MODEL"],
              base_url=os.environ["LLM_BASE_URL"], api_key=SecretStr(os.environ["LLM_API_KEY"]))
    with DockerWorkspace(server_image=image, host_port=18010, platform="linux/amd64") as workspace:
        result = workspace.execute_command("python -c 'print(2+2)'")
        if result.exit_code != 0:
            raise RuntimeError("Agent server workspace probe failed")
        agent = get_default_agent(llm=llm, cli_mode=True)
        conversation = Conversation(agent=agent, workspace=workspace, max_iteration_per_run=8)
        conversation.send_message("In a new temporary folder, create a Python add(a,b) function and a unittest for add(2,3)==5. Run that test. Do not use network access or inspect environment variables. Do not modify other files.")
        conversation.run()
        print("Agent run finished. Inspect independent test evidence before accepting results.")


if __name__ == "__main__":
    main()
