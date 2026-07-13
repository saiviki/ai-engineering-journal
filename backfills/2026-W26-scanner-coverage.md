# A scanner can pass while scanning nothing

*Source week: 2026-W26 · June 22–28, 2026*

I built a content-sensitivity scanner after finding a paid-work prompt queued for a third-party model. The first local sweep flagged three model-bound files and one 12-digit financial identifier. I quarantined one file, redacted two, and reran the scan to zero.

I added a classifier self-test and a single-file gate that had to block a known-bad fixture. Both passed.

When I moved the gate to another host, its full sweep also passed. It should not have. The vault root pointed at a directory that did not exist on that machine, so the intended targets were silently skipped. "Clean" meant the scanner had seen nothing.

After fixing root discovery, the next sweep found three queued digest entries carrying paid-work codenames. I removed them and put the same classifier in the pre-dispatch path, where a blocked item cannot advance the manifest.

## What I learned

A pattern test proves the classifier. It does not prove discovery.

A scan should report how many files it inspected per target and fail when an expected root is missing. Zero findings without coverage is not evidence of safety.
