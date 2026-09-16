# UI / Interaction Design

> 更新: 2026-09-16
> HTDTのGUI原則と視覚受入基準。

## 1. 目標

HTDTは専門的な測定・配置情報を扱うが、通常操作で説明文を読ませない。
画面構造、位置関係、状態、単位、選択結果から次の操作を理解できることを優先する。

- premium minimal: 白〜淡灰、十分な余白、弱い境界、階層の明確なsurface。
- primary actionは青、通常状態は無彩色、warning/rejectのみ意味色を使う。
- 長い説明を常時表示せず、Help `?` で補助説明を開示する。
- IDやversion等の技術情報は主操作から一段下げ、provenanceとして残す。
- desktop / narrow viewportの双方で横スクロールを主操作にしない。
## 2. Navigation

主フローは番号ではなく機能名で示す。

`Project → Room → Constraints → Search → Measure → Compare → Model → Features`

上部workflow railから各surfaceへ直接移動できる。
旧来の「4./5./6.」等の番号は、機能追加で順序がずれるためUIから除去する。

HelpをOFFにした通常表示では、panel直下の補助説明を隠す。
解析警告、quality、provenance、reject理由など判断に必要な結果はHelpとは無関係に常時表示する。

## 3. Placement Constraints

G10は文章ではなくroom mapを主surfaceとする。

- exact room polygonを上面図で表示。
- Context基準位置とcandidate位置を同じ座標上で表示。
- candidate編集はentity別X/Y/Z card。
- constraint kindは7個のvisual tileから選択。
- allowed/exclusion regionはroom mapをクリックして頂点を描画する。
- 複数の非連結領域は`+ Area`で追加する。
- wall clearanceはwall ID文字列ではなく、room map上の壁を直接選ぶ。
- speaker/MLP選択はchip、axisはsegmented controlで行う。
- footprint radius / safety marginはentity cardで単位付き入力する。
- evaluationは`FEASIBLE` / `REJECTED`を大きく表示し、reject対象とconstraint IDを続けて示す。
- `feasible`は物理配置可否だけで、音響評価ではないことを契約として維持する。

## 4. Search Space

O10はConstraintSetの次に配置し、文章ではなく可動軸と候補雲を主surfaceとする。

- entityごとのX/Y/Zはsegmented controlで可動軸を追加する。
- min/max/stepは単位付きcardで編集し、raw candidate countを保存前にpreviewする。
- linked relationはOFF / A→B / B→Aでmaster方向を明示する。
- 保存済みSearchSpecはimmutable表示し、変更は`複製して編集`で新規版にする。
- 生成結果はraw / feasible / rejected / duplicateを別metricで表示する。
- exact room上面図へfeasible candidate cloudを描き、Context baselineを別記号で示す。
- candidate選択はmap上で強調し、可動entityのXYZを隣接detailに表示する。
- candidateは物理的にfeasibleという意味だけで、音響的な優劣を色や順位で示さない。

## 5. Visual QA

所有Windows PC上でVite production buildをFastAPIから配信し、Playwright Chromiumで実レンダリングを確認する。
G10受入fixtureは8頂点凹polygon、FL/C/FR/MLP、5 hard constraintsを使用する。

確認項目:

- 1440 px幅でroom mapとcandidate editorが同一視線内にある。
- 390 px幅でcard/gridが1列へreflowし、主操作が切れない。
- G10 builderでrule tile、entity chip、polygon drawing、wall pickerが操作可能。
- exclusion polygonの頂点追加が即時visual feedbackになる。
- 説明HelpをOFFにしても主操作の意味が失われない。
- browser zoom依存の固定pixel座標を保存データへ使用しない。

スクリーンショット等の一時QA成果物は`C:\Users\ka092\Desktop\HTDT\`配下に置き、製品repoへcommitしない。

### G10 visual acceptance — 2026-09-16

- Windows 11 / Chromiumで1440 px desktopと390 px narrow viewportを実レンダリング確認。
- 8頂点凹room、FL/C/FR/MLP、保存済みConstraintSetを使い、mapとcandidate editorの同時視認を確認。
- guided builderを開き、exclusion polygonを4点クリックして赤い半透明領域と頂点番号が即時表示されることを確認。
- workflow railはline SVG icon + 短い機能名とし、仮記号や段階番号へ依存しない。
- Help OFFでも主操作を維持し、Help ONは補助説明だけを追加する。
- local CI-equivalent: Python 3.12.10 `.venv`でbackend 119 tests pass、frontend production build、built-app smoke pass。

### O10 visual acceptance — 2026-09-16

- Windows 11 / Playwright Chromiumで1440 px desktopと390 px narrow viewportを実レンダリング確認。
- 8頂点凹polygon、FL/C/FR/MLP、保存済みG10 ConstraintSet / O10 SearchSpecを使用。
- 81 raw candidatesから62 feasible / 19 rejected / 0 duplicateを表示し、候補雲とreject集計が一致。
- 390 pxでSearch panelの`scrollWidth == clientWidth`を確認し、横はみ出しなし。
- candidate行を選ぶとmap強調とFL/FR XYZ detailが同期。
- 保存済みSearchSpecの`複製して編集`で2 axes / 2 linked derivationsがbuilderへ復元され、元specは不変。
- QA screenshotはrepo外`C:\Users\ka092\Desktop\HTDT\`に保存し、commitしない。
- local CI-equivalent: Python 3.12.10でbackend 132 tests pass、launcher CLI/PowerShell syntax pass、`npm ci` 0 vulnerabilities、production build、built-app smoke pass。
