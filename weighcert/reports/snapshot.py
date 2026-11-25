import json
import hashlib
from decimal import Decimal
from datetime import datetime, date
from core.mongo import get_mongo_db
from core.models import LabSettings


def _dec_str(val) -> str:
    """Canonical decimal string representation independent of trailing zeros."""
    if val is None:
        return "0"
    d = Decimal(str(val))
    if d == 0:
        return "0"
    s = format(d.normalize(), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


class SnapshotDecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return _dec_str(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


def canonical_json_snapshot(data: dict) -> str:
    """Canonical JSON serialization for tamper-evident hashing."""
    return json.dumps(data, cls=SnapshotDecimalEncoder, sort_keys=True, separators=(",", ":"))


def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_report_snapshot_dict(session, report_number: str, revision: int, approved_by_user) -> dict:
    """
    Construct canonical dictionary representing all data of the issued report.
    Spec Section 6.5
    """
    instrument = session.instrument
    owner = instrument.owner
    lab = LabSettings.get_settings()

    snapshot = {
        "report_number": report_number,
        "revision": revision,
        "rule_set_version": session.rule_set_version,
        "lab": {
            "name": lab.lab_name,
            "address": lab.address,
            "authority": lab.authority_text,
            "accreditation": lab.accreditation_number,
        },
        "instrument": {
            "instrument_id": instrument.instrument_id,
            "owner_name": owner.name,
            "owner_address": owner.address,
            "manufacturer": instrument.manufacturer,
            "model": instrument.model,
            "serial_number": instrument.serial_number,
            "type_approval": instrument.type_approval_number,
            "software_id": instrument.software_id,
            "accuracy_class": instrument.accuracy_class,
            "max_g": _dec_str(instrument.max_capacity_g),
            "min_g": _dec_str(instrument.min_capacity_g),
            "e_g": _dec_str(instrument.e_g),
            "d_g": _dec_str(instrument.d_g),
            "n": _dec_str(instrument.n),
            "unit": instrument.unit,
            "is_multi_interval": instrument.is_multi_interval,
            "ranges": [
                {"order": r.order, "max_g": _dec_str(r.max_i_g), "e_g": _dec_str(r.e_i_g), "d_g": _dec_str(r.d_i_g)}
                for r in instrument.ranges.all()
            ],
            "indication_type": instrument.indication_type,
            "load_receptor_type": instrument.load_receptor_type,
            "points_of_support": instrument.points_of_support,
            "place_of_use": instrument.place_of_use,
        },
        "session": {
            "inspection_type": session.inspection_type,
            "limit_multiplier": session.limit_multiplier,
            "test_date": session.test_date.isoformat(),
            "place_type": session.place_type,
            "location": session.location_text,
            "inspector_name": session.inspector.get_full_name() or session.inspector.username,
            "approver_name": approved_by_user.get_full_name() or approved_by_user.username,
            "overall_result": session.overall_result,
            "remarks": session.remarks,
        },
        "weights_used": [
            {
                "label": sw.weight.label_id,
                "nominal_g": _dec_str(sw.weight.nominal_mass_g),
                "oiml_class": sw.weight.oiml_class,
                "cert_number": sw.weight.certificate_number,
                "due_date": sw.weight.calibration_due_date.isoformat(),
            }
            for sw in session.session_weights.select_related("weight").all()
        ],
        "zero_check": {
            "E0": _dec_str(session.zero_check.computed_e0) if hasattr(session, "zero_check") else "0",
            "passed": session.zero_check.passed if hasattr(session, "zero_check") else False,
        },
        "accuracy_readings": [
            {
                "phase": ar.phase,
                "seq": ar.sequence,
                "load_g": _dec_str(ar.load_g),
                "indication": _dec_str(ar.indication),
                "delta_l": _dec_str(ar.delta_l) if ar.delta_l is not None else None,
                "Ec": _dec_str(ar.Ec),
                "mpe": _dec_str(ar.mpe),
                "passed": ar.passed,
            }
            for ar in session.accuracy_readings.all()
        ],
        "repeatability": {
            "load_g": _dec_str(session.repeatability_test.load_g) if hasattr(session, "repeatability_test") else "0",
            "spread": _dec_str(session.repeatability_test.computed_spread) if hasattr(session, "repeatability_test") else "0",
            "limit": _dec_str(session.repeatability_test.spread_limit) if hasattr(session, "repeatability_test") else "0",
            "passed": session.repeatability_test.passed if hasattr(session, "repeatability_test") else False,
        },
        "eccentricity": {
            "mode": session.eccentricity_test.mode if hasattr(session, "eccentricity_test") else "",
            "load_g": _dec_str(session.eccentricity_test.actual_load_g) if hasattr(session, "eccentricity_test") else "0",
            "passed": session.eccentricity_test.passed if hasattr(session, "eccentricity_test") else False,
            "readings": [
                {
                    "pos": er.position_label,
                    "indication": _dec_str(er.indication),
                    "Ec": _dec_str(er.Ec),
                    "mpe": _dec_str(er.mpe),
                    "passed": er.passed,
                }
                for er in (session.eccentricity_test.readings.all() if hasattr(session, "eccentricity_test") else [])
            ],
        },
    }
    return snapshot


def save_report_snapshot(report) -> str:
    """
    Store canonical JSON snapshot in MongoDB and return SHA-256 hash.
    Spec Section 6.5
    """
    snapshot_dict = build_report_snapshot_dict(
        report.session, report.report_number, report.revision, report.approved_by
    )
    raw_json = canonical_json_snapshot(snapshot_dict)
    sha256_hash = compute_hash(raw_json)

    db = get_mongo_db()
    if db is not None:
        db["report_snapshots"].insert_one({
            "report_id": report.id,
            "report_number": report.report_number,
            "revision": report.revision,
            "canonical_json": raw_json,
            "snapshot_hash": sha256_hash,
            "created_at": datetime.now(),
        })

    return sha256_hash


def verify_report_integrity(report) -> tuple[bool, str]:
    """
    Verify report integrity:
    1. Recompute canonical JSON from current relational DB state.
    2. Compare hash against report.snapshot_hash.
    3. Check against MongoDB snapshot document if available.
    Returns (is_intact, message).
    """
    current_dict = build_report_snapshot_dict(
        report.session, report.report_number, report.revision, report.approved_by
    )
    current_raw = canonical_json_snapshot(current_dict)
    recomputed_hash = compute_hash(current_raw)

    if recomputed_hash != report.snapshot_hash:
        return False, "Database record has been modified! Hash mismatch detected."

    db = get_mongo_db()
    if db is not None:
        mongo_doc = db["report_snapshots"].find_one({
            "report_number": report.report_number,
            "revision": report.revision,
        })
        if mongo_doc and mongo_doc.get("snapshot_hash") != report.snapshot_hash:
            return False, "MongoDB immutable snapshot hash mismatch!"

    return True, "Integrity verified: Record matches the issued cryptographic signature."

