# 各実呼び出しを所有権の手順で囲む

## 短い占有と作業分類

アダプターは `agent_browser_coordinator.guard.run_guarded` により、新規・非再生の begin 応答と actor/token/action の一致を確認した後だけコールバックを実行できます。コールバックは `(terminated, value)` を返します。例外や終了不明の場合は active action を診断のため残します。参加ラッパーの `YIELD_REQUIRED` 後の呼び出しを防ぎますが、ラッパー外の直接呼び出しは遮断できません。新しい画面の読み取りは `kind='observation'`、有用な作業は `kind='work'`（既定）と指定します。チェックポイントから再開した owner は最大二回の呼び出しの中で観察後に作業一回を完了する機会を得ます。観察二回で予算は延長されず、lease 失効と連続占有上限は維持します。

UI 外で準備中の作業者は `readiness --actor worker-a --request ready-001 --args '{"state":"preparing"}'` を記録し、準備完了時に `state=ready` に変更できます。preparing の待機者は選択から除外されます。`status.next_ready_actor` は従来の FIFO・優先度・aging に従う次の ready 作業者を示し、`status.handoff_ready` は現在の owner が安全な境界でチェックポイント後に譲る信号です。これは状態信号であり、作業者の生成・実行を保証しません。従来クライアントの acquire は既定で ready です。

UI の占有は有限の呼び出し一回に限り、acquire → owner/token 確認 → begin → 一回のツール呼び出し → end の後、安全な境界で yield/release します。文書準備、ファイル分析、サーバー生成、レビュー、公開の待機は UI 占有の外で行います。再開時は新しい token を取得して現在の画面を再確認します。待機者がいる場合、設定可能な時間枠（既定180秒）を次の begin で確認します。既存の queue aging 120秒と連続占有上限30分も維持します。実行中の呼び出しを中断・強奪せず、待機者が取り消された場合は不要な交代を避けます。

`heartbeat` は手動の作業者生存観測のみを記録します。lease を更新せず、ツールの進行結果も証明しません。実行環境の自動 heartbeat bridge はありません。`last_keep_alive_at` と `active`、owner deadline を別々に確認してください。

`classify_work(kind, capability=...)` は保守的な計画ヒントです。不明な作業、共有画面・キーボード、ネイティブのファイル選択、モーダル、ブラウザー UI は逐次占有します。ファイル分析とサーバー生成待機は占有外で並列化できます。`tab_id` だけでは並列安全性を証明できません。アダプター識別子・証拠参照・検証済み capability とセッション/入力/フォーカス/ダイアログの隔離がそろったタブ API のみ並列*候補*です。このライブラリはホストの証拠検証も並列ブラウザー実行も行いません。

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

`python examples/safe_mock_worker.py` は一時 DB の完全な模擬フロー、`python examples/two_workers.py` は二つのワーカーの引き継ぎです。どちらもブラウザーを操作しません。

呼び出しが終わった安全な地点で checkpoint を残して引き継ぎます。

```sh
agent-browser-coordinator --db "$ABC_DB" yield --actor worker-a   --request yield-a-001   --args '{"token":"CURRENT_TOKEN","safe":true,"checkpoint":"resume-a-001"}'
```

yield は自身を再びキューに入れ、タブを保持します。release は再登録せず現在の所有を終えます。待機取消は自身の actor の cancel を使います。再開時は新しい token を取得します。期限後の自発返却には active がなく、実際の未完了呼び出しがないことを確認して no_pending_ui=true も必要です。拒否された begin を無視して保存をクリックしません。

tab は working/paused/held/complete と unsaved の論理記録です。自分のタブで完了・保存を実確認したものだけ close-begin → 実際に閉じる → close-end を使います。記録はタブの生存証明ではありません。inventory complete=true には実際の全体確認が必要です。ブラウザー終了は owner/queue/tabs/active が空で inventory 確認済みのときだけ shutdown prepare/start/end を使います。

`dashboard --output status.html` はローカルの読み取り専用スナップショットです。サーバー、自動更新、heartbeat、自動復旧ではありません。

[引き継ぎと復旧](RECOVERY.md) · [制限](LIMITATIONS.md)
