# 編入チャレンジ — 関西学院千里国際中等部 面接・小論文 練習アプリ

息子さんのスマホ（iPhone / Android）に「ホーム画面アプリ」として入れて使える Web アプリ（PWA）です。
Cloud Run にデプロイし、出てきた URL を LINE で送る → スマホで開いて「ホーム画面に追加」するだけで、アプリのように起動します。

- **小論文道場**：名言型／イエスノー型のお題を生成 → 声かテキストで回答 → 「お題との整合性」を最重視した **100点満点＋ABCD** 採点
- **面接シミュレーター**：面接官と1問1答（日本語／英語／ミックス）。1問ごとに点数とアドバイス
- **中心の文**：承・転・結で使う固定内容を編集・保存（採点はこの内容との整合性を見ます）

採点の中心ロジック：起でお題と「7回の転校→違いの理解→コミュニケーション力」をどうつなぐか、を最重要40点で評価します。

---

## 構成

```
henyu-app/
├─ main.py                 # FastAPI（静的配信 + /api/* 3エンドポイント。プロンプトはサーバ側）
├─ requirements.txt
├─ Dockerfile              # Cloud Run 用
├─ .gcloudignore
└─ static/
   ├─ index.html           # フロント本体（バニラJS・PWA）
   ├─ manifest.webmanifest
   ├─ service-worker.js
   └─ icon-*.png
```

APIキーはコードに書かず、環境変数 `ANTHROPIC_API_KEY` から読みます。モデルは既定で `claude-sonnet-4-6`（環境変数 `MODEL` で変更可。安く速くするなら `claude-haiku-4-5-20251001`）。

---

## 1) ローカルで試す

```bash
cd henyu-app
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # ご自身のキー
uvicorn main:app --reload --port 8080
# → http://localhost:8080
```

## 2) Cloud Run にデプロイ（ソースから一発・推奨）

`gcloud` が入っていてプロジェクト設定済みなら、これだけです。

```bash
cd henyu-app

# 任意：APIキーを Secret Manager に置く（推奨）
echo -n "sk-ant-..." | gcloud secrets create anthropic-key --data-file=-

gcloud run deploy henyu-challenge \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --set-secrets ANTHROPIC_API_KEY=anthropic-key:latest
# （Secretを使わない場合は ↑の代わりに）
# --set-env-vars ANTHROPIC_API_KEY=sk-ant-...
```

完了すると `https://henyu-challenge-xxxxx-an.a.run.app` のような URL が表示されます。これをLINEで送ってください。

> モデルを変えたい場合は `--set-env-vars MODEL=claude-haiku-4-5-20251001` を追加。

## 3) 息子さんのスマホに「アプリとして入れる」

LINEで届いた URL を開いて：

- **iPhone（Safari）**：共有ボタン □↑ →「ホーム画面に追加」
- **Android（Chrome）**：右上 ⋮ →「アプリをインストール／ホーム画面に追加」

これでホーム画面にアイコンが出て、全画面のアプリのように起動します（ブラウザのバーが消えます）。
※ LINE内ブラウザからは追加できないことがあるので、上の操作は **Safari / Chrome で開いてから** 行ってください（LINEのメニューで「外部ブラウザで開く」）。

---

## 音声入力について（重要）

- **Android (Chrome)**：🎤ボタンの音声認識が動きます。
- **iPhone (Safari)**：標準の音声認識(Web Speech API)が**非対応〜不安定**です。うまく取れない場合は、画面の案内どおり**キーボード入力**に切り替えてください（採点ロジックは入力方法に依存しません）。
- iPhoneでも確実に声で答えさせたい場合は、`MediaRecorder` で音声を録って `/api/transcribe` を増設し、**Google Cloud Speech-to-Text**（GCP上なので相性◎）で文字起こしする構成が確実です。ご希望ならこのエンドポイントを追加します。

## 費用の目安

採点1回・面接1ターンあたり Sonnet 4.6 でおおむね数百〜千数百トークン程度。練習用途（1日数十回）なら少額で収まります。さらに抑えるなら `MODEL=claude-haiku-4-5-20251001`。

## セキュリティ

`--allow-unauthenticated` は「URLを知っていれば誰でも開ける」状態です。家族内利用なら通常問題ありませんが、気になる場合は簡易パスワード（合言葉）チェックを足せます。これも必要なら対応します。
