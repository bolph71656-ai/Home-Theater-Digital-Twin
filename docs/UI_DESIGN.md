# Native CAD UI / Interaction Design

> 2026-09-16 / 従来browser UIの主画面設計を置換する。
> 実装順は[ロードマップ](IMPLEMENTATION_ROADMAP.md)、値・履歴は[SPEC](CAD_EDITOR_SPEC.md)、判定は[受入仕様](CAD_EDITOR_ACCEPTANCE.md)。

## 1. 画面の中心

中央viewportを常に主作業領域にする。独立したRoom/Constraints/Search画面へ移動するたびに空間を見失うnavigationをやめ、同じsceneのtool・dock・layerを切り替える。

- 左: compactなScene tree。Add paletteは必要時に開く。
- 中央: 大きなviewport、view cube/preset、床grid、選択handle、必要な寸法。
- 右: 選択物のInspector。何も選ばない時はroom/projectの要約。
- 上: Project/Open/Save、Select/Add/Move/Rotate/Measure、snap、view。
- 下: 必要時だけFR/比較dock。通常のstatusは単位・snap・保存状態・短い操作hint。
- constraints/analysisは選択またはmodeに応じて開示する。空の画面に全panelを並べない。

白〜淡灰を基調、余白、弱い境界、読みやすい文字階層、主操作は青。viewportはgeometryの輪郭と選択が読み取れる照明/背景とし、写実的な素材より空間の理解を優先する。Qtの既定外観を置くだけで完成としない。

## 2. 最初の5分

1. 「部屋を作る」で長方形または自由作図を選ぶ。
2. 自動的にTop orthographicへ切り替わり、clickで頂点、始点clickまたはEnterで閉じる。
3. live寸法から幅/長さを精密化し、高さhandleまたはInspectorで天井高を設定する。
4. paletteからspeaker、seat、screenを置き、床面のghostで配置先を確認する。
5. Perspectiveで全体を確認し、gizmoで高さ/向き、寸法で距離を調整してSaveする。

CSV頂点列、ID文字列、設定項目の読み込みを主要導線にしない。配置はdrag/dropに加えて「選ぶ→sceneをclick」も用意する。

## 3. 操作の既定値

N05で衝突を確認しN20で固定する初期操作案。各操作はtoolbar/context menuでも実行できる。

| 入力 | 動作 |
|---|---|
| 左click | 物体選択。空白clickで解除 |
| Ctrl＋左click | 選択を追加/解除 |
| 選択後の左drag | 表示されたhandleまたはactive toolの平面で変形 |
| 中button drag | pan |
| 右button drag | orbit。orthographicでは必要に応じPerspectiveへ切替を明示 |
| wheel | cursor近傍を基準にzoom |
| 右click（移動なし） | context menu。作図/変形中はその操作をcancel |
| Esc | active操作を取消。IdleではtoolをSelectへ戻す |
| Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y | Undo / Redo |
| Ctrl+S / Delete / Ctrl+D | Save / Delete / Duplicate |
| F / Home | 選択物へfit / scene全体へfit |
| X/Y/Z（変形中） | axis constraint切替 |
| Shift（変形中） | precision move |
| Alt（変形中） | snap一時反転 |

textboxにfocusがある間は文字入力を優先し、Delete/X/Y/Z等をscene操作へ流さない。Altによるmenu競合は実機で確認し、不適切ならmodifierを変更する。trackpad利用者には画面上のpan/orbit/zoomを用意する。

frame/座標値/単位は常に一貫。world/local軸とpivotの現在値を見える位置に置く。N20のmulti-selectはworld軸・共通pivotのみを必須にする。

## 4. 直接見えるfeedback

| 状態 | 表示 |
|---|---|
| Hover | 弱い輪郭、対象名 |
| Selection | はっきりした輪郭とhandle、tree/Inspector同期 |
| Drag | ghost位置、変化量、active軸、snap先の記号 |
| Invalid geometry | 問題辺/頂点を強調、短い理由、確定不可 |
| 設置制約違反 | 対象と離隔線。理由を選ぶと該当箇所へfocus |
| Unknown aim | 方向矢印を確定表示しない。未設定記号 |
| 保存失敗 / 未保存 | document名付近に状態。失敗してもdraftを保つ |
| 過去測定 / 古い予測 | ghost・線種・短いbadgeで現revisionと区別 |

遠い壁が編集物を隠す場合はcutaway/透過をViewStateとして切り替える。自動透過でpick対象が不意に変わらないよう、選択規則を固定する。色だけに意味を持たせずshape/line/labelを併用する。

## 5. 精密入力・部屋編集

寸法はmm/cm/mを入力可能とし、単位付き値を内部mへ変換する。Inspectorは位置・高さ・向き・寸法を対象ごとに必要最小限表示する。multi-selectの異なる値は混在表示とし、一つの値で無言に上書きしない。

Room editでは頂点とedge midpoint handleを出し、壁clickで壁寸法/厚み/開口を編集する。作図中はpreview線と寸法、閉鎖可能な始点を示す。壁のsplit/mergeでopeningやconstraintへ影響する場合だけ、該当物を強調して解決操作を求める。

家具/座席/screenは幅・奥行・高さを持つprimitiveから始める。speakerは筐体中心と音響基準点の区別を表示できる。天井speakerの高さは床面dragとは別handleで編集する。

## 6. 制約・測定・候補

G10のallowed/exclusionはscene上で描き、壁離隔は壁を選んで指定する。IDを入力させない。feasibleは配置可能性であり、音が良いことを意味しない。

measurement point/speakerを選ぶと関連FRを絞り、測定側からもsceneへ逆選択できる。古い測定は当時の配置をghost表示する。

O10候補は位置の集合として表示し、音響評価前に優劣の色を付けない。予測後は目的値ごとの表示を切り替える。候補を選ぶとghost preview、適用を確定すると1 Undo。model・帯域・近似・staleは必要な判断情報として隠さない。

説明Helpは通常閉じるが、測定品質、適用限界、操作失敗まで隠してはならない。UUID、schema、内部job等は詳細表示へ置く。

## 7. Visual QA

対象はWindows native application、DPI、mouse、keyboard、focus、dockの折り畳み。主操作の可視性と所要時間/誤操作を[受入仕様](CAD_EDITOR_ACCEPTANCE.md)で確認する。pixel完全一致を必須にしない。

旧browserの1440/390 px、Playwright、G10/O10視覚検証の記録は[改訂前UI設計](https://github.com/bolph71656-ai/Home-Theater-Digital-Twin/blob/1b510206e7c2fe84ff15fe544a6e3fe2d896dc84/docs/UI_DESIGN.md)に保存されている。native GUIの合格証拠として流用しない。
