# 安全な引き継ぎと検証後の復旧

## 通常の引き継ぎ

実行中の正確な呼び出しを終了し、最小 checkpoint と未保存状態を保持して yield または release します。次の所有者は現在の画面とサービス結果を確認します。他者のタブを閉じたり、公開・アップロード結果が不明なまま失敗とみなして繰り返したりしません。

ファイル選択とサーバー処理は別です。native ダイアログが消えたことや短いイベント timeout だけでは成功・失敗を判断しません。有限の観察期間内で実プレビュー、処理表示、適用/次へボタンの有効化、描画、保存、ダイアログ終了を確認します。万能な固定 sleep や結果不明の同一ファイル再送は避けます。

## 期限切れ・停止した所有者

安定版 0.3.4 は期限切れだけで所有権を自動回収しません。運用者が新規送信を停止し、freeze 後に正確な revision、owner token、shutdown token を読みます。

```sh
agent-browser-coordinator --db "$ABC_DB" freeze --actor coordinator-operator   --request freeze-001
agent-browser-coordinator --db "$ABC_DB" status
```

旧ワーカーが今後送信しないことと、送信済みの全ツール呼び出しが終了したことを別々に確認します。その後 recover に verified_idle=true、old_worker_quiescent=true、不透明な evidence 参照、正確な expected_revision / expected_token / expected_shutdown_token を渡します。存在しない token は null です。未確認の事実を true にするコピー用コマンドは提供しません。状態変更で拒否されたら強制せず再確認します。

復旧後は新しい generation を使い、旧 token を破棄します。タブ記録が残っても実タブ状態は確認が必要です。この手順はリモート呼び出しをキャンセルせず、外部状態を証明しません。

結果不明の呼び出しには、frozen の元 owner/action と運用者の exact-revision permit が必要です。diagnose-authorize → 元所有者の diagnose-begin/end を使い、manual-reconcile は元の unknown 結果と別途検証した手動結果を区別します。ブラウザー強制の読み取り専用 ACL ではありません。検証コードと合成診断テストを読み、timeout だけから終了証拠を作らないでください。

## ソースや DB の喪失

信頼できるリリースを新しい空ディレクトリに復元します。`python verify_backup.py ARCHIVE --sha256 EXPECTED_SHA256 --destination NEW_DIRECTORY` は信頼できる別記録のハッシュ、正確な許可リスト、各ファイルのハッシュを展開前に確認し、合成テストを実行します。既存の復元先は拒否します。稼働 DB は同梱・有効化しません。

元の DB が正常なら保持します。稼働中の DB/WAL/SHM をコピー・置換しません。DB が欠落・信頼不能なら、全ワーカーの停止と実呼び出し終了後にのみ新 DB/epoch を明示決定します。inventory 未確認で開始し、旧許可を破棄し、一つのゲートで実画面・結果を確認してから再取得を許可します。ソース復元はセッション復元ではありません。

[制限](LIMITATIONS.md) · [使用例](USAGE.md)

checksum は配布元の認証ではありません。復元検証はアーカイブ内のコードを実行するため、信頼したリリースだけを使い、新しい private 一時ディレクトリなど信頼できる親の下に新規パスを指定します。symlink の親と既存出力は拒否します。
