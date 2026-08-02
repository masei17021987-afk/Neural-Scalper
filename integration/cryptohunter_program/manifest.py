"""Template manifest for mounting Neural Scalper into CryptoHunter."""

PROGRAM_ID = "neural_scalper"

MANIFEST = {
    "id": PROGRAM_ID,
    "title": "Neural Scalper",
    "description": "Нейросетевой анализ стакана, обучение, бэктест и paper-trading.",
    "ready": False,
    "paper_ready": True,
    "live_execution": False,
    "requires_subscription": True,
    "runtime_kind": "process",
    "aliases": ["ai_scalper", "lob_scalper"],
}
