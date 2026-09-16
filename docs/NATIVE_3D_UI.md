# Native 3D Spatial Editor

> Status: active redesign track, 2026-09-16

HTDTの主GUIを、フォーム中心のWeb UIから、部屋・スピーカー・MLP・制約・候補を同一3D scene内で直接操作するWindowsデスクトップUIへ再構成する。

## Decision

初期実装は PySide6 + PyVista/VTK + PyVistaQt を採用する。

- PySide6: Windows desktop shell、dock、scene tree、inspector、menus、undo/redo integration。
- PyVista/VTK: 3D room/equipment、point cloud、surface/volume field、picking、slice、measurement visualization。
- PyVistaQt: Qt central viewport integration。
- PyVista `AffineWidget3D`: CAD型のX/Y/Z translation / rotation gizmo。
- `pyvista-cad`は将来のSTEP/DXF/IFC import候補であり、初期必須依存にはしない。

FreeCAD/CQ-editorの `QMainWindow + central 3D viewer + dock panes + object tree` 構成を参考にするが、HTDTはOpenCascadeを主レンダラにはしない。HTDTは機械CADだけでなく、音圧分布、反射経路、候補点群、測定点、予測結果を同じsceneへ重ねるため、VTK/PyVistaのデータ可視化能力を優先する。

## Interaction contract

中央領域は3D viewportを主役とする。左dockはScene、右dockはInspectorとする。

- Room polygon: top viewで頂点を直接drag。grid snapを適用。
- Speaker / MLP: object選択後に3D gizmoで移動。
- Inspector: XYZや寸法の精密確認・微調整。フォームは主操作ではない。
- Camera: orbit / pan / wheel zoom、Top / Front / Right / Isometric presets。
- Selection: scene treeとviewport pickingを双方向同期。
- Constraints / Search candidates: scene overlayとして表示し、既存G10/O10データ契約を再利用する。

## Data contract

3D操作中に保存済みContextを書き換えない。最新Contextから編集Draftを作り、操作はUndo/Redo可能な履歴として保持する。Save時に既存`ContextCreate` validationを通し、新しいimmutable Context revisionを作る。

未知値を表示都合で既知へ昇格しない。特にSpeakerの`aim_xyz=None`は、移動だけでは`None`のまま保持する。ユーザーが回転gizmoを明示操作した場合のみaimを確定する。

Room polygonは既存G00/Shapely validationを再利用し、自己交差、室外点、duplicate vertex等を保存させない。

## Windows prototype acceptance

所有Windows 11 / Python 3.12で PySide6 6.11.2、PyVista 0.49.0、PyVistaQt 0.13.1、VTK 9.7.0を導入して確認した。

8頂点凹polygon room、FL/C/FR、MLPをネイティブQt windowへ表示し、room shellを半透明3D表示、speakerをcabinet形状、MLPをmarker表示した。FLへ`AffineWidget3D`を付け、RGB translation / rotation gizmoがWindows上で描画・操作可能なことを確認した。

prototype screenshotと一時検証コードは `C:\Users\ka092\Desktop\HTDT\` 配下に置き、製品repoにはcommitしない。

## First production milestone

N10 Native Spatial Editor:

1. Project / Context selection。
2. exact polygon room shell rendering。
3. Scene tree / viewport selection sync。
4. Speaker / MLP gizmo move + snap。
5. polygon vertex direct manipulation。
6. Inspector XYZ / room height editing。
7. Undo / Redo。
8. Save as new immutable Context revision。
9. Windows render smoke and interaction acceptance。

既存Web UIは移行期間のfallbackとして残す。N10受入後にlauncher既定をnativeへ切り替える。

## Architecture boundary

backend domain logic、SQLite、REW adapter、G00/G10/O10はGUIから独立したまま維持する。Native UIはこれらを直接再実装せず、同じPydantic/domain contractを使用する。

O20 Batch PredictionはWIP branchへ保全済みであり、Native Spatial Editorの基盤が成立してから3D候補cloud/予測overlayとして統合する。