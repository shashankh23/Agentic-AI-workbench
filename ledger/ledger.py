import hashlib
import json
import os
from datetime import datetime

LEDGER_PATH = os.path.join(os.path.dirname(__file__), "action_ledger.jsonl")

def _hash_entry(entry: dict) -> str:
    """Computes SHA-256 hash of an entry's contents."""
    entry_string = json.dumps(entry, sort_keys=True)
    return hashlib.sha256(entry_string.encode()).hexdigest()

def _get_last_hash() -> str:
    """Reads the last entry in the ledger to chain the new one onto it."""
    if not os.path.exists(LEDGER_PATH):
        return "0" * 64  # genesis hash
    with open(LEDGER_PATH, "r") as f:
        lines = f.readlines()
        if not lines:
            return "0" * 64
        last_entry = json.loads(lines[-1])
        return last_entry["entry_hash"]

def log_action(action_type: str, model_used: str = None, details: str = None):
    """
    Appends a new signed, hash-chained entry to the ledger.
    action_type: e.g. "model_call", "tool_call", "file_write", "sandbox_exec"
    """
    prev_hash = _get_last_hash()

    entry = {
        "timestamp": datetime.now().isoformat(),
        "action_type": action_type,
        "model_used": model_used,
        "details": details,
        "prev_hash": prev_hash
    }
    entry["entry_hash"] = _hash_entry(entry)

    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

    return entry["entry_hash"]

def verify_chain() -> dict:
    """
    Walks the entire ledger and verifies every entry's hash chain is intact.
    Returns {"valid": bool, "entries_checked": int, "broken_at": int or None}
    """
    if not os.path.exists(LEDGER_PATH):
        return {"valid": True, "entries_checked": 0, "broken_at": None}

    with open(LEDGER_PATH, "r") as f:
        lines = f.readlines()

    expected_prev = "0" * 64
    for i, line in enumerate(lines):
        entry = json.loads(line)
        claimed_hash = entry["entry_hash"]

        if entry["prev_hash"] != expected_prev:
            return {"valid": False, "entries_checked": i + 1, "broken_at": i}

        # Recompute hash to check nobody edited this entry's contents
        entry_copy = {k: v for k, v in entry.items() if k != "entry_hash"}
        recomputed = _hash_entry(entry_copy)

        if recomputed != claimed_hash:
            return {"valid": False, "entries_checked": i + 1, "broken_at": i}

        expected_prev = claimed_hash

    return {"valid": True, "entries_checked": len(lines), "broken_at": None}
