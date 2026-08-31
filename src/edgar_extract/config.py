import os

from dotenv import load_dotenv

load_dotenv()

# Opus 5. Model choice is one of the cost levers this project is meant to
# measure — see evals/README.md. Swap it, re-run the eval, compare accuracy
# against cost per filing. That comparison is a result worth publishing.
MODEL = os.getenv("EDGAR_MODEL", "claude-opus-5")

# Pricing per 1M tokens, USD. Update if you change MODEL.
# claude-opus-5: $5.00 input / $25.00 output
PRICE_INPUT_PER_MTOK = float(os.getenv("EDGAR_PRICE_IN", "5.00"))
PRICE_OUTPUT_PER_MTOK = float(os.getenv("EDGAR_PRICE_OUT", "25.00"))

SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "")
SEC_RATE_LIMIT_PER_SEC = 8  # SEC's documented ceiling is 10; stay under it.

DATA_DIR = os.getenv("EDGAR_DATA_DIR", "data")
