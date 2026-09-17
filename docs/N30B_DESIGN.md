# N30b wall / opening design

> 2026-09-17 / Issue #53

N30aのroom footprintを正本とし、N30bでは壁と開口の**参照identity**を別layerとして追加する。footprintは室内仕上げ面、wall thicknessは外側表示属性であり、厚さによって室内容積を暗黙に縮めない。

## Domain boundary

- `RoomPrism`: ordered room vertices and height. Geometry validity is authoritative.
- `WallSegment`: stable `wall_id`, from/to vertex IDs, thickness, optional `source_wall_id`.
- `WallOpening`: stable `opening_id`, `wall_id`, wall-start offset, width, sill, height, kind/open state.
- `WallTopology`: boundary-edge-to-wall one-to-one mapping plus openings.

`WallTopology` is not a second polygon model. Every wall must correspond exactly to one ordered RoomPrism boundary edge.

## Edit rules

### Move wall

Move both endpoint vertices by one XY delta. Wall/opening IDs remain unchanged. The resulting RoomPrism must remain a valid simple polygon and all wall-local openings must still fit their referenced wall.

### Split wall

Insert one stable room vertex and replace the old wall with two new wall IDs. Both children retain `source_wall_id=old wall_id`.

An opening fully before the split remains on the first child. An opening fully after it moves to the second child and subtracts the split offset. An opening crossing the split point is ambiguous and rejects the entire edit before commit.

### Merge walls

Only ordered neighboring walls that are collinear, point in the same direction and have matching wall attributes can merge. The shared room vertex is removed. Openings on the second wall add the first wall length to their wall-local offset. Attribute conflicts reject instead of silently choosing one side.

## Transaction boundary

Topology functions are pure: they return a candidate `(RoomPrism, WallTopology)` or raise `WallTopologyError`. They do not touch CommandHistory or SQLite. The editor/WorkingDocument layer will validate the entire Scene snapshot and commit room + topology + migrated references as one command.

This separation is deliberate: preview can be invalid or ambiguous, while the saved SceneRevision cannot contain dangling wall/opening references.

## Next slice

1. persist wall topology in SceneDocument without changing legacy N05/N10/N20 canonical hashes;
2. add one atomic room+topology command to CommandHistory;
3. add constraint-reference migration adapter;
4. add native wall/opening editing UI;
5. run F3/A09 on the owned Windows machine.