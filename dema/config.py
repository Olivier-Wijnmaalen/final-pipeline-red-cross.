"""Project paths and pinned model/prompt configuration."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_ENV = PROJECT_ROOT / ".env"
DEFAULT_CHUNKS = PROJECT_ROOT / "data" / "chunks"
DEFAULT_BASE_BANK = PROJECT_ROOT / "data" / "base_evidence_bank.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "dema_run"

EXTRACTION_PROMPT_NAME = "dema-lenient-calibration/evidence-extraction"
EXTRACTION_PROMPT_VERSION = 6
EXTRACTION_PROMPT_SHA256 = "d2436f48ec0c9ff693f2b4f1964adc21e179995ec11905d1bf70902bcd8c355c"

SCORING_PROMPT_NAME = "dema-stage2-final-strategy-20260916-p5"
SCORING_PROMPT_VERSION = 1
SCORING_PROMPT_API_SHA256 = "19520d1d71c80ba4a4eac3db09107e82f53ff932fd1ab4bb3b935a1cdadfeeec"
SCORING_PROMPT_CRLF_SHA256 = "a3734a364931d5aaa90188c82eee400b0812023a5d4dcb14da70d917067669af"

