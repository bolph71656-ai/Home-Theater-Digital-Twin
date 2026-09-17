# S01 / O20 progress

Tracking: Issue #67  
Parent N80 tracking: Issue #65  
Branch: `feat/s01-rew-roomsim-o20`  
Base main: `0e29c24e7176174e26714b8975da15dd63701022`

## 2026-09-18 — start

- N80a merged through PR #66 as `7473bb3efdbc511369c9a023b0b210eb5cde3553`.
- N80a post-merge status sync is main `0e29c24e7176174e26714b8975da15dd63701022`.
- Main CI #326 / run `35286358348` passed completely.
- Issue #65 remains open for N80b/c.
- Created Issue #67 for S01/O20 REW Room Simulator contract and batch prediction.

## Existing code

`backend/src/htdt/rew_api.py` already contains a read-only Room Simulator adapter:

- `get_roomsim_snapshot()`;
- `get_roomsim_frequency_response()`;
- HTDT ↔ REW coordinate conversion;
- explicit `predicted_rew_room_simulator` classification;
- `rectangular_room_only` model metadata.

`backend/tests/test_rew_roomsim.py` already has captured REW 5.40 Beta 135 / API 0.9.8 state and FR fixtures and verifies that the current adapter performs GET only.

## Current external contract finding

Current official REW API documentation states that `/roomsim` provides full Room Simulator control. Room size, surface absorption, sources, source position/configuration, mic offsets, options and Room Simulator frequency responses are exposed by the API. REW also documents that GET is generally available and most model endpoints support PUT/POST; the Pro restriction applies to automated sweep measurements, not ordinary Room Simulator model control.

The model remains rectangular-room-only and Room Simulator sources are treated as omnidirectional. HTDT therefore uses it only as a rectangular low-frequency baseline and keeps non-rectangular exact prediction out of S01.

## Implementation sequence

1. Add a constrained JSON request helper and typed Room Simulator writer methods.
2. Add canonical supported-state serialization/hash.
3. Add reversible Room Simulator transaction with mandatory verified restore.
4. Add focused fake-API tests for write/restore/error/cancel invariants.
5. Add a compact live OpenAPI/transaction probe script.
6. Run CI.
7. Use RDC once to run the owned-Windows probe/acceptance against installed REW.
8. Record S01 evidence before connecting N80 candidate batches to the model.
