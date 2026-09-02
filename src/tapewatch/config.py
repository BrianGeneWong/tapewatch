import os

from dotenv import load_dotenv

load_dotenv()

# Model routing is the cost lever this project exists to measure. The
# primary model sees every event; escalation runs only when the primary
# abstains or reports low confidence. Swap either, re-run the eval, and
# compare accuracy against cost per thousand events — that comparison is
# the result worth publishing.
PRIMARY_MODEL = os.getenv("TAPEWATCH_PRIMARY_MODEL", "claude-haiku-4-5")
ESCALATION_MODEL = os.getenv("TAPEWATCH_ESCALATION_MODEL", "claude-opus-5")

# USD per 1M tokens, (input, output). Verify against current pricing docs
# before quoting a cost figure in the README — these change.
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

# `output_config.effort` is rejected by Haiku 4.5 and other pre-4.6
# models. Sending it anywhere is a 400, so gate on the model rather than
# setting it globally.
EFFORT_CAPABLE = {"claude-opus-5", "claude-sonnet-5"}

# Escalate when the primary model reports confidence at or below this.
ESCALATE_ON_CONFIDENCE = os.getenv("TAPEWATCH_ESCALATE_ON", "low")

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")

SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "")
SEC_RATE_LIMIT_PER_SEC = 8  # SEC's documented ceiling is 10; stay under it.

DATA_DIR = os.getenv("TAPEWATCH_DATA_DIR", "data")


def price(model: str) -> tuple[float, float]:
    """Input/output price per 1M tokens. Unknown models cost nothing —
    which shows up as a suspicious $0.00 in metrics rather than a crash
    mid-run."""
    return PRICING.get(model, (0.0, 0.0))
