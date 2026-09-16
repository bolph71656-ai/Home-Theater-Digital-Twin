# Local development workspace policy

> Applies to the owned Windows development machine.

All local HTDT work is confined to:

`C:\Users\ka092\Desktop\HTDT\`

GitHub is the durable record for implementation, design, validation, plans, and progress. Local-only artifacts are disposable unless they are needed for real-device acceptance.

## Keep at HTDT root

The root should remain small and predictable. Long-lived entries are:

- `repo\` — primary Git checkout.
- `REW-5.40-beta135\` — installed REW API build used for real validation.
- `samples\` — externally acquired or real-device samples that are intentionally retained and are safe to keep locally.
- `tools-local\` — reusable local-only validation/development tools that do not belong in the product repository.
- `private\` — optional local-only device-specific/private data such as microphone calibration or serial-specific files; never commit secrets or personal device identifiers.

## Do not leave at HTDT root

One-off helper scripts, generated screenshots, test databases, browser caches, patch scripts, temporary `LOCALAPPDATA` trees, and ad-hoc fixture data must not accumulate at the root.

Examples of disposable patterns:

- `patch_*.py`
- `insert_*.py`
- temporary `create_*_fixture.py` scripts after their result is represented in product tests/docs
- `test-localappdata-*`
- `ui-review-*-data`
- `ui-review-*-localappdata`
- generated prototype screenshots
- temporary PR-body text files
- throwaway verification scripts whose findings are already recorded in GitHub

## Reusable local tools

If a helper remains useful for repeated real-machine acceptance, move it under a named directory in `tools-local\` instead of leaving it at the root.

Suggested layout:

```text
HTDT\
  repo\
  REW-5.40-beta135\
  samples\
  tools-local\
    ui-review\
    rew-validation\
    native-gui-validation\
  private\
```

`tools-local\` is not part of the product runtime and must not become an undeclared dependency of repository tests or normal execution.

## Temporary data

Tests and visual QA should use an explicitly isolated temporary data root. Prefer a single reusable container such as:

`C:\Users\ka092\Desktop\HTDT\.tmp\`

Each task may create a subdirectory and delete it after acceptance. The application must never use the real default `%LOCALAPPDATA%\HomeTheaterDigitalTwin` database during automated tests.

## Cleanup rule

Before finishing a milestone:

1. Confirm repository work and validation results are committed/pushed.
2. Stop test servers and child processes.
3. Delete reproducible test databases, screenshots, caches, and one-off patch scripts.
4. Move genuinely reusable acceptance scripts to `tools-local\`.
5. Keep private real-device data local and outside Git.
6. Verify `C:\Users\ka092\Desktop\HTDT\` root contains only intentional long-lived entries.

When uncertain whether a file contains unique evidence or user data, inspect it before deleting. Do not bulk-delete unknown files.
