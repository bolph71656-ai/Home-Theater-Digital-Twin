# REW API read-only integration

> 状態: 実装済み・mock検証済み / 実REW接続は未検証

## 方針

HTDTのREW API連携は、ファイル取込を置き換える必須経路ではなく任意の読取省力化機能とする。初期アダプターにはHTTP **GETだけ**を実装し、REWの測定・設定・EQ・ファイルを変更するPOST/PUT/DELETEは実装しない。

REW公式APIは既定で `http://127.0.0.1:4735`。HTDTも既定値をこれに固定し、接続先ホストは `127.0.0.1` または `localhost` のみ許可する。LAN上の別ホストへ向ける機能は作らない。

必要なら環境変数 `HTDT_REW_API_URL` でlocalhost上の別ポートを指定できる。

~~~powershell
$env:HTDT_REW_API_URL = "http://127.0.0.1:4735"
python -m htdt
~~~

## HTDT側のエンドポイント

| HTDT endpoint | 動作 |
|---|---|
| `GET /api/rew/status` | REW APIへの到達可否と測定数を確認 |
| `GET /api/rew/measurements` | REWに現在ロードされている測定summaryを読取 |
| `GET /api/rew/measurements/{uuid}/frequency-response` | 指定測定の周波数応答を読取・デコード |

REWのindex番号は測定の追加・削除・group変更で動き得るため、HTDTは永続参照にindexを使わずUUIDを使う。

## 配列デコード契約

REW APIの数値配列は32-bit floatのraw bytesをBase64化した文字列で、公式仕様ではbyte orderは**big-endian**。HTDTは `struct.unpack(">...f")` 相当で復号する。

公式の検証例

- Base64: `PgAAAD6AAAA+wAAAPwAAAA==`
- 復号値: `0.125, 0.25, 0.375, 0.5`

を自動テストへ含める。

FrequencyResponseについては、

- `startFreq`
- `ppo` または `freqStep`
- `magnitude`
- optional `phase`
- `unit`
- `smoothing`

を保持する。log spacingの場合は `f[i] = startFreq * exp(i * ln(2) / ppo)`、linear spacingの場合は `f[i] = startFreq + i * freqStep` で周波数軸を復元する。

HTDTから96 PPOを要求しても、REW側が返す`smoothing`を必ず来歴として扱う。96 PPOで取得したことを「未平滑化raw測定」とは呼ばない。

## 対応形状の防御

REW 5.40 beta系ではAPIモデルの改訂が続いているため、測定一覧は配列形式・object keyed形式の両方を正規化できるようにする。ただし未知のレスポンス形状を推測して無言変換せずエラーにする。

周波数応答はmagnitude/phaseの長さ不一致、壊れたBase64、4 byte境界でない配列、startFreq/spacing欠損を拒否する。

## 現時点で実装しない操作

- 自動スイープ開始
- REW測定の削除・名称変更
- EQ/Filter変更
- Room Simulator設定変更
- REWへのファイルimport
- AVR設定変更

これらはHTDTの読取連携に不要であり、測定条件を知らないまま変更する事故を避けるため初期アダプターに含めない。

## 実機受入条件

REWを実際に導入したら次を確認する。

1. REW APIをlocalhostで起動する。
2. `/api/rew/status` がconnectedになる。
3. FL/FRのsummary UUID・title・帯域がREW画面と一致する。
4. 同一測定についてREW text exportとAPI取得を比較する。
5. ppo/smoothing/unitを記録し、許容差を決めて数値を照合する。
6. REWを停止するとHTDTは保存済みデータを失わず、APIだけunavailableになる。

ここまで通るまでは「REW API実機互換性確認済み」としない。

## 公式資料

- REW API: https://www.roomeqwizard.com/help/help/html/api.html
- REW beta API help: https://mail.roomeqwizard.com/betahelp/help/html/api.html
- REW beta releases: https://www.roomeqwizard.com/beta.html
