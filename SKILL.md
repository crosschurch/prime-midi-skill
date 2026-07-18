---
name: prime-midi-cues
description: Automate MIDI lyric cues in Loop Community Prime (worship multitrack app) by writing directly to its local SQLite database. Use when asked to add, generate, shift, retime, or fix lyric slide cues / MIDI notes for a song in Prime, to map ProPresenter slides to a Prime song, or when given ProPresenter slide-grid screenshots to build cues from. Triggers include "prime midi", "lyric cues", "automate lyrics", "slide cues", "map slides to a song".
---

# Prime MIDI Lyric Cues

Prime stores every song version's MIDI cues as JSON inside a plain SQLite DB.
Lyric cues are `noteNumber 19` on the `lyrics` bus, and **velocity = ProPresenter
slide number** (ProPresenter fires slide N on velocity N). Writing cues is
therefore: map each slide to an absolute beat, then write rows with
`scripts/prime.py`. Cues are anchored as (sectionId, 0-1 progress); the script
converts to/from absolute beats automatically.

## Hard rules

- **Never write while Prime is running** — the app clobbers DB edits from
  memory (the script enforces this for the live DB). If the user needs to quit
  Prime first, offer a background watcher: loop until `pgrep -qi "PRIME
  MultiTrack"` fails, then apply.
- **Always back up before writing** (the script does this automatically to
  `~/Documents/PrimeBackups/`).
- **Never touch non-lyric cues** (lights are notes 1/55 on lights buses,
  utility notes 0/18) unless explicitly asked. `write`/`shift` already
  preserve them.
- **Never overwrite user hand-edits.** `learn` diffs current positions against
  the last programmatic write; any moved slide belongs to the user.
- After every write the user must open Prime, verify, and **save the version
  to cloud** in-app. Cloud round-trips preserve DB-written cues (verified).

## Workflow

1. **Locate the song.** `python3 scripts/prime.py setlists`, then
   `songs <setlist>` — the `*ACTIVE*` marker shows what's loaded in the app.
   Use the version's `localId` everywhere below. `dump <version-id>` prints
   the section map (start/verse/chorus/turn beats) and every existing cue.

2. **Read the ProPresenter deck** from screenshots of the slide grid: capture
   slide number, lyric text, and group labels/colors (Verse 1, Chorus,
   Interlude...). Blank slides matter — they clear lyrics during turns,
   vamps, and instrumentals.

3. **Map slides to beats.** Match ProPresenter groups to Prime sections by
   order and lyric content, then place each slide at a musical target beat.
   Read [references/timing.md](references/timing.md) for the placement
   heuristics and the lead/timing patterns learned from hand-tuning — do not
   guess defaults.

4. **Write.** Build `[{"slide": N, "beat": B}, ...]` (absolute beats, lead
   already subtracted) and run:
   `python3 scripts/prime.py write <version-id> --cues cues.json`
   This replaces all lyric cues, preserves everything else, and saves a
   baseline sidecar for step 6.

5. **Bulk adjust** when asked ("everything 2 beats earlier", "chorus slides
   later"): `shift <version-id> --beats -2 [--slides 19-22,24]`.

6. **Learn from hand-edits.** After the user tunes some cues in Prime:
   `learn <version-id>` prints per-slide deltas vs the last write. Derive
   patterns from the moved slides (see timing.md) and transfer them to
   untouched sibling sections — same-length sections copy offsets 1:1.
   Re-check the diff at apply time so edits made since are never overwritten.

## Gotchas

- The DB is per-account: `database-<userId>.sqlite`; the script picks the most
  recently modified. Josh's account is 73207.
- Removing a song from a setlist deletes its editable version (DB trigger), so
  re-adding pulls a fresh copy from cloud — old version localIds go stale.
  Re-run `songs` after any setlist reshuffle.
- New cue IDs are numeric strings; the script allocates above the current max.
  The cloud accepts them (verified round-trip).
- A cue fired early lands in the *previous* section in Prime's editor — that
  is correct and expected; think in absolute beats, not sections.
