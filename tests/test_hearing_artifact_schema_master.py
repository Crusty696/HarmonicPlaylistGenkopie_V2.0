"""Golden schema/version catalog for published hearing JSON artifacts."""
import json
from pathlib import Path

import pytest


@pytest.mark.artifact_contract
def test_published_hearing_json_versions_match_golden_catalog():
    from hpg_core import hearing_blind, hearing_calibration, hearing_managed, hearing_ratings
    from hpg_core import hearing_sources
    from tools import audit_candidate_set, rate_transitions

    catalog_path = Path(__file__).parent / "fixtures" / "hearing_artifact_schema_versions.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    actual = {
        "hearing_source_manifest": {
            "format": hearing_sources.SOURCE_FORMAT,
            "version_field": "format_version",
            "supported_versions": [1, 2, hearing_sources.SOURCE_VERSION],
            "root_keys": sorted(hearing_sources._MANIFEST_KEYS),
        },
        "candidate_manifest": {
            "version_field": "format_version",
            "normal_version": rate_transitions.KANDIDATEN_MANIFEST_VERSION,
            "three_notes_version": rate_transitions.DREINOTEN_MANIFEST_VERSION,
            "normal_root_keys": sorted(audit_candidate_set.ROOT_KEYS),
            "three_notes_root_keys": sorted(audit_candidate_set.ROOT_KEYS | {"rating_schema"}),
        },
        "dramaturgy_manifest": {
            "version_field": "format_version",
            "supported_versions": [rate_transitions.DRAMATURGIE_MANIFEST_VERSION],
            "root_keys": sorted(rate_transitions.DRAMATURGIE_MANIFEST_KEYS),
        },
        "calibration_proposal": {
            "format": hearing_calibration.PROPOSAL_FORMAT,
            "version_field": "version",
            "supported_versions": [hearing_calibration.PROPOSAL_VERSION],
            "root_keys": sorted(hearing_calibration.PROPOSAL_KEYS),
        },
        "candidate_audit_report": {
            "version_field": "format_version",
            "supported_versions": [audit_candidate_set.AUDIT_REPORT_VERSION],
            "root_keys": sorted(audit_candidate_set.AUDIT_REPORT_KEYS),
        },
        "candidate_ram_audit": {
            "format": audit_candidate_set.RAM_AUDIT_FORMAT,
            "version_field": "version",
            "supported_versions": [audit_candidate_set.RAM_AUDIT_VERSION],
            "root_keys": sorted(audit_candidate_set.RAM_AUDIT_KEYS),
        },
        "local_blind_public": {
            "format": hearing_blind.FORMAT,
            "version_field": "format_version",
            "supported_versions": [hearing_blind.VERSION],
            "root_keys": sorted(hearing_blind._PUBLIC_KEYS),
        },
        "local_blind_private": {
            "format": hearing_blind.FORMAT + "_key",
            "version_field": "format_version",
            "supported_versions": [hearing_blind.VERSION],
            "root_keys": sorted(hearing_blind._PRIVATE_KEYS),
        },
        "transition_ratings": {
            "format": hearing_ratings.TRANSITION_RATINGS_FORMAT,
            "format_encodes_version": 1,
            "root_keys": sorted(hearing_ratings.TRANSITION_RATINGS_KEYS),
        },
        "managed_association": {
            "supported_formats": [
                hearing_managed.ASSOCIATION_FORMAT_SINGLE,
                hearing_managed.ASSOCIATION_FORMAT_MULTI,
            ],
            "single_root_keys": sorted(hearing_managed.ASSOCIATION_SINGLE_KEYS),
            "multi_root_keys": sorted(hearing_managed.ASSOCIATION_MULTI_KEYS),
        },
    }
    assert actual == catalog
