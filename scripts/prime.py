#!/usr/bin/env python3
"""CLI for reading and writing MIDI lyric cues in Loop Community Prime's local SQLite DB.

Prime stores each song version's MIDI cues as a JSON array in
multitrackVersion.midiCues. Lyric cues are noteNumber 19 on the "lyrics" bus,
with velocity = ProPresenter slide number. Cue positions are stored as
(multitrackSectionId, sectionProgress 0-1); this tool converts to/from
absolute beats using the song's section map.

Subcommands:
  setlists                          list setlists, newest first
  songs <setlist>                   songs in a setlist (name substring or localId)
  dump <version-id>                 sections + all cues with absolute beats
  backup                            copy the live DB to ~/Documents/PrimeBackups
  write <version-id> --cues f.json  replace lyric cues from [{"slide":N,"beat":B},...]
  shift <version-id> --beats D      shift lyric cues by D beats (--slides to filter)
  learn <version-id>                diff current lyric cues vs last-written baseline

Safety: write/shift refuse to run while Prime is open, always back up the DB
first, save a baseline sidecar for later `learn` diffs, and never touch
non-lyric cues (lights, utility notes).
"""
import argparse, datetime, glob, json, os, shutil, sqlite3, subprocess, sys

CONTAINER_DOCS = os.path.expanduser(
    '~/Library/Containers/com.loopcommunity.PRIMEMAC/Data/Documents')
BACKUP_DIR = os.path.expanduser('~/Documents/PrimeBackups')
BASELINE_DIR = os.path.join(BACKUP_DIR, 'baselines')
LYRIC_NOTE = 19


def find_db(override=None):
    if override:
        return override
    dbs = glob.glob(os.path.join(CONTAINER_DOCS, 'database-*.sqlite'))
    if not dbs:
        sys.exit('No Prime database found in ' + CONTAINER_DOCS)
    return max(dbs, key=os.path.getmtime)  # most recently used account


def prime_running():
    return subprocess.run(['pgrep', '-qi', 'PRIME MultiTrack'],
                          capture_output=True).returncode == 0


def require_closed(db_path):
    live = os.path.realpath(db_path).startswith(os.path.realpath(CONTAINER_DOCS))
    if live and prime_running():
        sys.exit('Prime is running. Quit it before writing '
                 '(the app keeps state in memory and will clobber DB edits).')


def backup(db_path, tag):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')
    dest = os.path.join(BACKUP_DIR, f'{os.path.basename(db_path)}-{stamp}-{tag}.bak')
    shutil.copy(db_path, dest)
    return dest


def load_version(db, vid):
    row = db.execute(
        'SELECT midiCues, multitrackId FROM multitrackVersion WHERE localId=?',
        (vid,)).fetchone()
    if not row:
        sys.exit(f'No multitrackVersion with localId {vid}')
    cues = json.loads(row[0] or '[]')
    sections = sorted(
        json.loads(db.execute('SELECT sections FROM multitrack WHERE localId=?',
                              (row[1],)).fetchone()[0]),
        key=lambda s: s['startBeat'])
    return cues, sections


def abs_beat(cue, smap):
    s = smap[cue['multitrackSectionId']]
    return s['startBeat'] + cue['sectionProgress'] * (s['endBeat'] - s['startBeat'])


def place(beat, sections):
    """absolute beat -> (sectionId, progress), clamped to song bounds"""
    beat = max(beat, sections[0]['startBeat'])
    target = sections[-1] if beat >= sections[-1]['endBeat'] else next(
        s for s in sections if s['startBeat'] <= beat < s['endBeat'])
    prog = (beat - target['startBeat']) / (target['endBeat'] - target['startBeat'])
    return target['id'], round(prog, 6)


def save_cues(db, db_path, vid, cues, tag):
    require_closed(db_path)
    backup(db_path, tag)
    db.execute('UPDATE multitrackVersion SET midiCues=? WHERE localId=?',
               (json.dumps(cues, sort_keys=True, separators=(',', ':')), vid))
    db.commit()
    lyric = {c['noteVelocity']: round(abs_beat(c, {s['id']: s for s in load_version(db, vid)[1]}), 4)
             for c in cues if c['noteNumber'] == LYRIC_NOTE}
    os.makedirs(BASELINE_DIR, exist_ok=True)
    with open(os.path.join(BASELINE_DIR, f'{vid}.json'), 'w') as f:
        json.dump(lyric, f, indent=1, sort_keys=True)


def next_cue_id(db):
    (m,) = db.execute(
        "SELECT max(CAST(json_extract(j.value,'$.id') AS INTEGER)) "
        'FROM multitrackVersion v, json_each(v.midiCues) j').fetchone()
    return (m or 0) + 100000


def cmd_setlists(db, _):
    for r in db.execute('SELECT localId, name, serviceDate FROM setlist '
                        'ORDER BY updatedAt DESC'):
        print('\t'.join(str(x) for x in r))


def cmd_songs(db, args):
    q = args.setlist
    row = db.execute('SELECT localId FROM setlist WHERE localId=? OR name LIKE ? '
                     'ORDER BY updatedAt DESC', (q, f'%{q}%')).fetchone()
    if not row:
        sys.exit(f'No setlist matching {q!r}')
    active = db.execute('SELECT activeMultitrackVersionId FROM setlist '
                        'WHERE localId=?', (row[0],)).fetchone()[0]
    for pos, slot, name, vname, vid, cues in db.execute(
            '''SELECT s.position, s.localId, m.name, v.name, v.localId,
                      (SELECT count(*) FROM json_each(v.midiCues))
               FROM setlistMultitrackVersion s
               JOIN multitrackVersion v ON v.localId = s.editableVersionId
               JOIN multitrack m ON m.localId = v.multitrackId
               WHERE s.setlistId=? ORDER BY s.position''', (row[0],)):
        mark = ' *ACTIVE*' if slot == active else ''
        print(f'{pos}\t{name} [{vname}]\t{vid}\tcues={cues}{mark}')


def cmd_dump(db, args):
    cues, sections = load_version(db, args.version_id)
    smap = {s['id']: s for s in sections}
    print('SECTIONS')
    for s in sections:
        print(f"  {s['id']}  {s['sectionType']:<14} beats {s['startBeat']}-{s['endBeat']}")
    print('CUES (sorted by beat)')
    for c in sorted(cues, key=lambda c: abs_beat(c, smap)):
        s = smap[c['multitrackSectionId']]
        print(f"  beat {abs_beat(c, smap):8.2f}  note={c['noteNumber']:>3} "
              f"vel={c['noteVelocity']:>3} bus={c.get('bus', '?'):<9} "
              f"sec={s['sectionType']}")


def cmd_backup(db, args):
    print(backup(args.db_path, 'manual'))


def cmd_write(db, args):
    with open(args.cues) as f:
        plan = json.load(f)  # [{"slide": N, "beat": B}, ...]
    cues, sections = load_version(db, args.version_id)
    kept = [c for c in cues if c['noteNumber'] != LYRIC_NOTE]
    base_id = next_cue_id(db)
    for i, p in enumerate(sorted(plan, key=lambda p: p['slide'])):
        sec_id, prog = place(p['beat'], sections)
        kept.append({'bus': 'lyrics', 'channel': 0, 'id': str(base_id + i),
                     'isMigratedToBus': True, 'messageType': {'noteOn': {}},
                     'multitrackSectionId': sec_id, 'noteNumber': LYRIC_NOTE,
                     'noteVelocity': p['slide'], 'sectionProgress': prog})
    save_cues(db, args.db_path, args.version_id, kept, 'pre-write')
    print(f'Wrote {len(plan)} lyric cues '
          f'({len(kept) - len(plan)} non-lyric cues preserved).')


def cmd_shift(db, args):
    only = None
    if args.slides:
        only = set()
        for part in args.slides.split(','):
            a, _, b = part.partition('-')
            only.update(range(int(a), int(b or a) + 1))
    cues, sections = load_version(db, args.version_id)
    smap = {s['id']: s for s in sections}
    n = 0
    for c in cues:
        if c['noteNumber'] != LYRIC_NOTE:
            continue
        if only and c['noteVelocity'] not in only:
            continue
        c['multitrackSectionId'], c['sectionProgress'] = place(
            abs_beat(c, smap) + args.beats, sections)
        n += 1
    save_cues(db, args.db_path, args.version_id, cues, 'pre-shift')
    print(f'Shifted {n} lyric cues by {args.beats:+g} beats.')


def cmd_learn(db, args):
    path = os.path.join(BASELINE_DIR, f'{args.version_id}.json')
    if not os.path.exists(path):
        sys.exit('No baseline for this version - write or shift first, '
                 'then hand-edit in Prime, then learn.')
    with open(path) as f:
        baseline = json.load(f)
    cues, sections = load_version(db, args.version_id)
    smap = {s['id']: s for s in sections}
    print(f"{'slide':>5} {'baseline':>9} {'current':>9} {'delta':>8}")
    for c in sorted((c for c in cues if c['noteNumber'] == LYRIC_NOTE),
                    key=lambda c: c['noteVelocity']):
        cur = abs_beat(c, smap)
        base = baseline.get(str(c['noteVelocity']))
        if base is None:
            print(f"{c['noteVelocity']:>5} {'-':>9} {cur:>9.2f}      new")
            continue
        d = cur - base
        print(f"{c['noteVelocity']:>5} {base:>9.2f} {cur:>9.2f} {d:>+8.2f}"
              f"{'  <-- MOVED' if abs(d) > 0.01 else ''}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', help='override DB path (default: newest in Prime container)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('setlists')
    p = sub.add_parser('songs'); p.add_argument('setlist')
    p = sub.add_parser('dump'); p.add_argument('version_id')
    sub.add_parser('backup')
    p = sub.add_parser('write'); p.add_argument('version_id')
    p.add_argument('--cues', required=True, help='JSON file: [{"slide":N,"beat":B},...]')
    p = sub.add_parser('shift'); p.add_argument('version_id')
    p.add_argument('--beats', type=float, required=True)
    p.add_argument('--slides', help='e.g. 19-22,24,30-31 (default: all)')
    p = sub.add_parser('learn'); p.add_argument('version_id')
    args = ap.parse_args()
    args.db_path = find_db(args.db)
    db = sqlite3.connect(args.db_path)
    {'setlists': cmd_setlists, 'songs': cmd_songs, 'dump': cmd_dump,
     'backup': cmd_backup, 'write': cmd_write, 'shift': cmd_shift,
     'learn': cmd_learn}[args.cmd](db, args)


if __name__ == '__main__':
    main()
