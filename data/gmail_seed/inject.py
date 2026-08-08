from __future__ import annotations

import argparse
import json
from email.message import EmailMessage
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_SCENARIO = HERE / "scenarios" / "purchase-request.json"
OUTBOX = HERE / "outbox"


def render_eml(scenario: dict) -> bytes:
    """Render a synthetic scenario without contacting Gmail."""
    subject = str(scenario.get("subject", ""))
    if not subject.startswith("[OFFICE-BLUE-TEST]"):
        raise ValueError("Test seed subjects must start with [OFFICE-BLUE-TEST].")
    message = EmailMessage()
    message["From"] = str(scenario["from"])
    message["To"] = ", ".join(scenario["to"])
    message["Subject"] = subject
    message.set_content(str(scenario["body"]))
    return message.as_bytes()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render a synthetic Gmail seed as .eml; no Gmail write is performed."
    )
    parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    output = args.output or OUTBOX / f"{args.scenario.stem}.eml"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(render_eml(scenario))
    print(f"Rendered test email: {output}")
    print("Gmail write performed: no")


if __name__ == "__main__":
    main()
