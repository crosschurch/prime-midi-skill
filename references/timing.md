# Slide placement and timing

## Mapping ProPresenter slides to musical targets

- **Verses/choruses with one line per slide**: split the Prime section evenly
  across its slides (4 lines in a 36-beat verse = one line every 9 beats).
- **Double-line slides** hold two lines' worth of beats; give the section's
  remaining slides their normal single-line spans.
- **Repeated sections** (chorus 2, 3...) reuse their own slide group when the
  deck has one (24-27, then 28-31), or re-fire the same slides when it doesn't.
- **Refrains/tags sung over interludes or turns** get the lyric slide at that
  section's start (e.g. "He is Lord, Lord of all" over an interlude; a "my
  anchor holds" tag slide right after the verse it echoes).
- **Blank slides** map to turns, vamps, instrumentals, and outros — one blank
  per section boundary where lyrics should clear.

## Lead (fire-early) defaults — learned from hand-tuning, use as starting point

All values in beats, relative to the musical target the slide belongs to.
Learned from Josh's tuning of Cornerstone (72 BPM, July 2026); at very
different tempos scale proportionally and say so.

| Cue kind | Placement |
|---|---|
| First lyric line of a verse/section | ~2.7 before the downbeat |
| Middle lines | ~4 before their line |
| Last line of a verse | ~4.5 before its line |
| First lyric after a blank/boundary | ~1.4 before the downbeat |
| Blank/vamp/instrumental/outro slide | ~2.4 **after** the boundary (into the new section — never early, or it cuts the last lyric short) |

**Chorus phrasing is not an even grid.** Hand-tuned Cornerstone chorus
(24-beat section, offsets from section start): `-3.25, +3.68, +11.85, +19.70`
— lead shrinks each line and the final line ("Lord of all") fires after its
nominal gridline. Expect this shape in choruses generally: generate evenly
with ~3 beats lead first, then tune one chorus with the user and copy its
exact offsets to all same-length sibling choruses.

## The learn-and-transfer loop

1. Generate all cues with the defaults above; write.
2. User listens in Prime and hand-tunes one instance of each section type
   (one verse, one chorus, one blank).
3. `prime.py learn <version-id>` → per-slide deltas identify what moved.
4. Compute offsets of the tuned section relative to its section start;
   apply verbatim to sibling sections of the same length (scale
   proportionally if lengths differ).
5. Never modify slides the user moved; re-diff at apply time in case they
   edited more since.
