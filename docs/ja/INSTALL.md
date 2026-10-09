# インストール

インストールで確認できるのは Python パッケージのみです。実運用には各ブラウザーツールのアダプター接続、既存の利用者指示を上書きしない永続 Agent 指示への登録、共通 DB と現在画面の確認、読み取り専用の実ツール smoke test による隔離 capability の検証が必要です。アクセス権がなければインストール成功のみを報告してください。調整器自体はブラウザー操作も自動 heartbeat bridge も提供しません。

Python 3.10 以上とローカル POSIX ファイルシステムを使用します。検証は隔離した Linux 環境で行い、Windows、ネットワークファイルシステム、すべての Python/OS の組み合わせを認定するものではありません。SQLite は Python に含まれます。インストールだけでブラウザー、ポート、認証情報、サービスは設定されません。

このリポジトリをダウンロードまたは clone し、そのディレクトリで実行します。

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
agent-browser-coordinator --version
python -m agent_browser_coordinator --version
```

ソースのビルドには設定済み Python パッケージインデックスの Setuptools を使用します。オフラインでは、配布元と SHA-256 を検証した wheel を使用してください。

```sh
python -m pip install --no-index --no-deps ./agent_browser_coordinator-0.3.5-py3-none-any.whl
python -m scripts.validate_release
python -m scripts.package_release
```

後の二つの検証コマンドはソース checkout 内で実行します。PyPI への公開は主張していません。同名・類似名の別パッケージを代用しないでください。削除は `python -m pip uninstall agent-browser-coordinator` です。ワーカーの停止や稼働 DB の削除は別の作業です。

[設定](CONFIGURATION.md) · [使用例](USAGE.md) · [復旧](RECOVERY.md)
