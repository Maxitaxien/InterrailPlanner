"""Local source readiness and repeatable, explicit MOTIS preparation.

Status reads files only. Prepare keeps previously prepared sources, adds selected
ones, then delegates to the existing staged/checksummed GTFS preparation. It
never downloads Swedish data, reads keys, starts MOTIS, or imports timetables.
"""
import argparse
import json
from pathlib import Path

from prepare import prepare

ROOT = Path(__file__).resolve().parent
SOURCES = {
    'france': 'feeds.france.json',
    'sweden': 'feeds.sweden.example.json',
    'denmark': 'feeds.denmark.example.json',
    'austria': 'feeds.austria.example.json',
    'switzerland': 'feeds.switzerland.example.json',
}


def previous_feeds(work_dir):
    path = Path(work_dir) / 'feeds-status.json'
    if not path.exists():
        return []
    try:
        records = json.loads(path.read_text())['feeds']
        if not isinstance(records, list) or any(not isinstance(row, dict) or not isinstance(row.get('id'), str) for row in records):
            raise ValueError
        return records
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError('Cannot read previous prepared sources; repair metadata before preparing a replacement.') from None


def source_report(work_dir, root=ROOT):
    records = {row['id']: row for row in previous_feeds(work_dir)}
    result = []
    for name, filename in SOURCES.items():
        feed = json.loads((root / filename).read_text())['feeds'][0]
        archive = root / feed['path'] if feed.get('path') else None
        record = records.get(feed['id'])
        result.append({'source': name, 'feed_id': feed['id'],
                       'input': 'public_download' if archive is None else 'archive_present' if archive.is_file() else 'archive_missing',
                       'prepared': record is not None,
                       'rail_service_start': record.get('rail_service_start') if record else None,
                       'rail_service_end': record.get('rail_service_end') if record else None,
                       'source_url': feed['source_url']})
    return result


def expansion_manifests(work_dir, include, root=ROOT):
    previous = {row['id'] for row in previous_feeds(work_dir)}
    defaults = {row['id'] for row in json.loads((root / 'feeds.json').read_text())['feeds']}
    selected, known = set(include), set(defaults)
    if selected - SOURCES.keys():
        raise ValueError('Unknown expansion source')
    for name, filename in SOURCES.items():
        ids = {row['id'] for row in json.loads((root / filename).read_text())['feeds']}
        known.update(ids)
        if previous & ids:
            selected.add(name)
    if previous - known:
        raise ValueError('Previously prepared custom sources detected. Use prepare.py with your complete manifest set to preserve them.')
    # Never silently skip an approved source whose original local archive is missing.
    for name in selected:
        for feed in json.loads((root / SOURCES[name]).read_text())['feeds']:
            if feed.get('path') and not (root / feed['path']).is_file():
                raise ValueError(f'Missing authorized archive for {name}; previous prepared data is unchanged.')
    return [root / SOURCES[name] for name in sorted(selected)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'prepare'], nargs='?', default='status')
    parser.add_argument('--include', choices=list(SOURCES), action='append', default=[])
    parser.add_argument('--work-dir', type=Path, default=ROOT / 'work')
    args = parser.parse_args()
    try:
        if args.action == 'status':
            print(json.dumps({'sources': source_report(args.work_dir), 'import_verified': False,
                              'notice': 'Archive presence and prepared dates do not prove a running import or connecting service.'}, indent=2))
        else:
            manifests = expansion_manifests(args.work_dir, args.include)
            records = prepare(ROOT / 'feeds.json', args.work_dir, extra_manifests=manifests)
            print(f'Prepared {len(records)} feeds. Previous known expansions retained. No MOTIS import or restart performed.')
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, 'Source preparation failed. Check archives, manifest selection and previous metadata. No import or restart performed.\n')


if __name__ == '__main__':
    main()
