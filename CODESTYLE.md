# Code style

Judgement calls a reviewer applies to a diff. Mechanical rules live in ruff, ty
and the guard tests under `tests/`, not here.

## Configuration

- **Name the winner; never let order decide it.** When several source spellings
  map to one concept, declare one canonical label with the aliases it absorbs,
  as `reference_data/synonyms/synonyms_patient.yaml` does (`status:` absorbs
  `Status`, `patient status`, `patient status select`). A winner picked by list
  position or dict insertion order is invisible, untestable, and silently
  reversed by an unrelated edit.
- **An ambiguity the config cannot resolve is an error.** Raise; do not pick.
- **Derive downstream mappings from that same config** instead of restating
  them in code.
