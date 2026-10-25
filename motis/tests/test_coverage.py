import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('motis_coverage', ROOT / 'coverage.py')
coverage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage)


def previous(tmp_path, ids):
    (tmp_path / 'feeds-status.json').write_text(json.dumps({'feeds': [{'id': value} for value in ids]}))


def test_status_has_no_network_or_credentials_and_does_not_claim_import(tmp_path):
    report = coverage.source_report(tmp_path)
    assert {row['source'] for row in report} == set(coverage.SOURCES)
    assert all(not row['prepared'] for row in report)
    assert 'key' not in json.dumps(report)
    assert coverage.expansion_manifests(tmp_path, ['france']) == [ROOT / 'feeds.france.json']


def test_previous_expansions_are_retained_and_custom_feeds_never_silently_dropped(tmp_path):
    previous(tmp_path, ['frsncf', 'defv'])
    assert coverage.expansion_manifests(tmp_path, []) == [ROOT / 'feeds.france.json']
    previous(tmp_path, ['customsource'])
    with pytest.raises(ValueError, match='custom sources'):
        coverage.expansion_manifests(tmp_path, ['france'])


def test_missing_authorized_archives_and_broken_metadata_fail_closed(tmp_path):
    root = tmp_path / 'motis'; root.mkdir()
    for filename in ['feeds.json', *coverage.SOURCES.values()]:
        (root / filename).write_bytes((ROOT / filename).read_bytes())
    previous(tmp_path, ['dkrejseplan'])
    with pytest.raises(ValueError, match='Missing authorized archive'):
        coverage.expansion_manifests(tmp_path, ['france'], root)
    (tmp_path / 'feeds-status.json').write_text('broken')
    with pytest.raises(ValueError, match='previous prepared sources'):
        coverage.expansion_manifests(tmp_path, [])
