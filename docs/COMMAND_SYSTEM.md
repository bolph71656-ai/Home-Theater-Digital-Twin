# Command Registry / Command Palette

> Issue #118 / UX110 command system foundation.  
> 正本はこの文書と `backend/src/htdt/command_registry.py` のcommand metadata。

## 目的

HTDTの操作入口をwidgetごとの文字列・shortcut・callback定義から分離し、`Ctrl+K` の単一検索入口からnavigation commandとscene/task commandを扱う。

command layerが保持するのは次だけ。

- stable command ID
- 日本語表示名
- shortcut metadata
- context
- availability / disabled reason
- workspace deep-link metadata
- 既存authorityを呼ぶcallback

Scene保存、Undo/Redo、測定、予測、Pareto計算などのdomain authorityはcommand layerへ移さない。

## 実装

- `backend/src/htdt/command_registry.py`
  - Qt非依存のcentral registry
  - command metadata / search / availability / execution
  - `WorkspaceDeepLink`
  - text input focus時のshortcut policy
- `backend/src/htdt/command_palette.py`
  - `Ctrl+K` palette
  - disabled reason表示
  - `CommandShortcutBinder`
- `backend/src/htdt/native_command_adapter.py`
  - 現行native windowの既存method/actionへdelegateするadapter
  - save / undo / redo / room draw / speaker add / REW import / prediction / candidate compare
- `backend/src/htdt/native_cad.py`
  - 現行windowへpaletteを最小接続

## 初期command

| command ID | 表示 | shortcut | context | deep-link |
|---|---|---|---|---|
| `navigation.overview` | 概要 | — | global / overview | `overview` |
| `navigation.room` | 部屋 | — | global / room | `room` |
| `navigation.measurements` | 測定 | — | global / measurements | `measurements` |
| `navigation.optimization` | 最適化 | — | global / optimization | `optimization` |
| `project.save` | 保存 | Ctrl+S | global | — |
| `edit.undo` | 元に戻す | Ctrl+Z | global / room | — |
| `edit.redo` | やり直す | Ctrl+Y / Ctrl+Shift+Z | global / room | — |
| `room.draw` | 部屋作図 | — | room | `room/geometry` |
| `room.add_speaker` | スピーカー追加 | — | room | `room/speakers` |
| `measurements.import_rew` | REW読み込み | — | measurements | `measurements/import` |
| `prediction.run` | 予測実行 | — | room | `room/acoustics` |
| `optimization.compare_candidates` | 候補比較 | — | optimization | `optimization/candidates` |

## Agent A / shell integration

navigation commandはshell本体をこのPRで実装しない。registryはdeep-link handlerを後付けできる。

~~~python
controller = install_native_command_palette(
    window,
    deep_link_handler=workspace_router.open_deep_link,
    context_provider=workspace_router.current_command_context,
)
~~~

またはshell生成後に既存controllerへ接続してよい。

~~~python
window.command_palette_controller.registry.set_deep_link_handler(
    workspace_router.open_deep_link
)
~~~

deep-link handler未接続時、navigation commandはpaletteに残るがdisabledになり、
「画面切替の準備が完了すると利用できます」と理由を表示する。
これは旧dock構造へnavigation authorityを二重実装しないための意図的な境界。

task commandにもdeep-link metadataを持たせる。Agent Aは必要に応じて該当workspaceを開いてから
同じcommand IDを実行できる。command callback自体は既存authorityへのdelegateのまま維持する。

## command追加方法

1. `default_command_definitions()` にstable ID、日本語表示名、context、keywords、必要ならshortcut/deep-linkを追加する。
2. 実行処理が既存native authorityにある場合、`native_command_adapter.py` の `bindings` へcallbackを接続する。
3. availabilityは既存actionの `isEnabled()`、既存precondition method、repositoryのread-only state等を参照する。domain判定をcommand側へ再実装しない。
4. disabled時は短い日本語理由を返す。
5. scene/document shortcutを追加する場合は `ShortcutBehavior.FOCUS_SAFE` を使う。
6. shell navigationだけのcommandはexecutorを作らず `WorkspaceDeepLink` を指定する。
7. registry contractを変える場合だけ `backend/tests/test_command_registry.py` を更新する。単なるmetadata追加のために不要なGUI testを増やさない。

例:

~~~python
CommandDefinition(
    command_id='room.add_seat',
    display_name='座席追加',
    contexts=frozenset({CommandContext.ROOM}),
    keywords=('座席を追加', 'add seat'),
    deep_link=WorkspaceDeepLink(WorkspaceId.ROOM, 'objects'),
)
~~~

adapter:

~~~python
'room.add_seat': (
    lambda: window.add_object('seat'),
    lambda: existing_availability_check(window),
),
~~~

## shortcut / focus contract

text、numeric、search fieldにfocusがある間、scene/document editing shortcutを奪わない。

- `ShortcutBehavior.GLOBAL`
  - text入力中も有効にしてよいもの。例: `Ctrl+K`、保存。
- `ShortcutBehavior.FOCUS_SAFE`
  - text/numeric/search入力中は無効化するもの。例: Undo/Redo、将来の `M` / `R` 等scene shortcut。

`CommandShortcutBinder` は `QLineEdit`、`QAbstractSpinBox`、`QTextEdit`、
`QPlainTextEdit`、editable `QComboBox` をtext inputとして扱い、focus change時にshortcut自体をdisableする。
trigger後に無視する方式ではないため、入力widget側の通常shortcutを先に奪わない。

現行legacy toolbarのshortcut全面移行はこのPRのscope外。Agent D等のCAD shortcut実装時は、
新しいshortcutをregistry metadataへ集約し、widgetごとの重複定義を増やさない。

## authority boundary

command adapterは以下を直接実装しない。

- SceneRevision保存 semantics
- Undo/Redo stack
- room geometry validation
- measurement revision binding / raw asset保存
- prediction job guard / stale判定
- SearchSpec / objective / Pareto authority

それぞれ現行window/service/repository methodへdelegateする。
command availabilityはUIの入口を説明するためのread-only判定であり、
最終的なdomain validationを置き換えない。

## 現在の残件

- Agent Aのworkspace router接続前は4 navigation commandが理由付きdisabled。
- entity search、設定、ヘルプはIssue #118の後続scope。registry APIを拡張せず追加可能。
- legacy toolbar/actionのshortcutを一括削除・置換する作業はこのPRでは行わない。
- visual token適用はAgent Bのtheme foundationへ委譲する。paletteはQt palette roleだけを使用し、独自色を持たない。
