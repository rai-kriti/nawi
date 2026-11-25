import json
import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from .mongo import get_mongo_db


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def canonical_json(data: dict) -> str:
    """Return canonical, sorted JSON string for hashing."""
    return json.dumps(data, cls=DecimalEncoder, sort_keys=True, separators=(",", ":"))


def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def log_audit(
    user,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict = None,
    after: dict = None,
    ip_address: str = None,
) -> bool:
    """
    Append an audit log entry to MongoDB with hash-chain integrity.
    Spec Section 6.5
    """
    db = get_mongo_db()
    if db is None:
        return False

    col = db["audit_log"]

    # Get last entry's hash
    last_entry = col.find_one(sort=[("_id", -1)])
    prev_hash = last_entry["hash"] if last_entry and "hash" in last_entry else "0" * 64

    entry_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user.id if user and hasattr(user, "id") else None,
        "username": user.username if user and hasattr(user, "username") else "anonymous",
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "before": before or {},
        "after": after or {},
        "ip_address": ip_address or "",
        "prev_hash": prev_hash,
    }

    # Hash canonical representation
    raw_for_hash = canonical_json(entry_data)
    entry_data["hash"] = compute_sha256(raw_for_hash)

    col.insert_one(entry_data)
    return True


def verify_audit_chain() -> tuple[bool, int, str]:
    """
    Verify the cryptographic hash chain of all entries in audit_log.
    Returns (is_valid, count, message).
    """
    db = get_mongo_db()
    if db is None:
        return False, 0, "MongoDB not connected."

    col = db["audit_log"]
    entries = list(col.find().sort("_id", 1))

    if not entries:
        return True, 0, "Audit log is empty."

    expected_prev = "0" * 64
    for i, entry in enumerate(entries):
        actual_prev = entry.get("prev_hash")
        if actual_prev != expected_prev:
            return False, i, f"Chain broken at entry #{i}: prev_hash mismatch."

        # Re-verify hash
        copy_data = {
            "timestamp": entry.get("timestamp"),
            "user_id": entry.get("user_id"),
            "username": entry.get("username"),
            "action": entry.get("action"),
            "entity_type": entry.get("entity_type"),
            "entity_id": str(entry.get("entity_id")),
            "before": entry.get("before", {}),
            "after": entry.get("after", {}),
            "ip_address": entry.get("ip_address", ""),
            "prev_hash": actual_prev,
        }
        recomputed = compute_sha256(canonical_json(copy_data))
        if recomputed != entry.get("hash"):
            return False, i, f"Tamper detected at entry #{i}: hash mismatch."

        expected_prev = entry.get("hash")

    return True, len(entries), f"All {len(entries)} audit records verified successfully. Chain intact."

