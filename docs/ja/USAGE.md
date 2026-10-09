# 各実呼び出しを所有権の手順で囲む

CLI は JSON を返し、拒否・不正な要求では終了コード 2 を返します。ok、replay、owner.actor、owner.token、active を確認します。キュー登録は所有権取得ではありません。再生された begin の成功結果は、実ツールを再実行する許可ではありません。

以下を一括実行しないでください。acquire の現在の owner が worker-a の場合だけ、その正確な token で CURRENT_TOKEN を置き換えます。新しい要求 ID を使い、begin が新規成功で replay=false の場合だけ、承認済みの有限なツール呼び出しを一度実行します。

```sh
agent-browser-coordinator --db "$ABC_DB" acquire --actor worker-a   --request acquire-a-001 --args '{"priority":20,"lease":120}'
agent-browser-coordinator --db "$ABC_DB" begin --actor worker-a   --request begin-a-001 --args '{"token":"CURRENT_TOKEN","action":"action-a-001"}'
# ONE authorized bounded tool call, only after non-replay begin success.
agent-browser-coordinator --db "$ABC_DB" end --actor worker-a   --request end-a-001 --args '{"token":"CURRENT_TOKEN","action":"action-a-001"}'
```

end はその正確な呼び出しが確実に終了した場合だけ実行します。確定した失敗も終了として記録できますが、開始・完了が不明なら未解決状態を保持し、運用者に調整を依頼します。無条件の finally で不明状態を消さないでください。再取得・再開の最初の読み取りで実画面、URL/アカウント、対象、保存状態、前回の結果を確認し、古い handle や座標を使いません。

Python API も同じ規約です。

```python
from agent_browser_coordinator import Coordinator
co = Coordinator("/absolute/path/to/existing-shared.db")
snapshot = co.status()  # read-only; missing DB is not created
```

`python examples/safe_mock_worker.py` は一時 DB の完全な模擬フロー、`python demo.py` は二つのワーカーの引き継ぎです。どちらもブラウザーを操作しません。

呼び出しが終わった安全な地点で checkpoint を残して引き継ぎます。

```sh
agent-browser-coordinator --db "$ABC_DB" yield --actor worker-a   --request yield-a-001   --args '{"token":"CURRENT_TOKEN","safe":true,"checkpoint":"resume-a-001"}'
```

yield は自身を再びキューに入れ、タブを保持します。release は再登録せず現在の所有を終えます。待機取消は自身の actor の cancel を使います。再開時は新しい token を取得します。期限後の自発返却には active がなく、実際の未完了呼び出しがないことを確認して no_pending_ui=true も必要です。拒否された begin を無視して保存をクリックしません。

tab は working/paused/held/complete と unsaved の論理記録です。自分のタブで完了・保存を実確認したものだけ close-begin → 実際に閉じる → close-end を使います。記録はタブの生存証明ではありません。inventory complete=true には実際の全体確認が必要です。ブラウザー終了は owner/queue/tabs/active が空で inventory 確認済みのときだけ shutdown prepare/start/end を使います。

`dashboard --output status.html` はローカルの読み取り専用スナップショットです。サーバー、自動更新、heartbeat、自動復旧ではありません。

[引き継ぎと復旧](RECOVERY.md) · [制限](LIMITATIONS.md)
