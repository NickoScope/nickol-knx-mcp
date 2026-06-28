<!-- Thanks for contributing! -->

## What does this PR do?

## Checklist
- [ ] `python tests/test_pipeline.py` passes locally
- [ ] Safety invariant preserved: `project.py` stays the only `.knxproj` reader and stays read-only; no networking/bus libraries added
- [ ] Generators remain conservative (ambiguous → `review`, not guessed)
- [ ] New classification/behavior is covered by a case in `tests/test_pipeline.py`
- [ ] Docs updated if user-facing (README / CHANGELOG)

## Related issues
Closes #
