"""
関西学院千里国際中等部 編入チャレンジ — バックエンド
FastAPI + Anthropic SDK。Cloud Run で動かす想定。
APIキーは環境変数 ANTHROPIC_API_KEY から読み込む（コードには書かない）。
"""
import os
import json
import random
import ssl
import smtplib
import datetime
from email.mime.text import MIMEText
from email.header import Header

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from anthropic import Anthropic

MODEL = os.environ.get("MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 1024

# ---------- メール送信（履歴ログ用・任意） ----------
# Gmail で送る。未設定なら何も送らない（＝アプリは通常どおり動く）。
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
LOG_EMAIL_TO = os.environ.get("LOG_EMAIL_TO", "") or GMAIL_ADDRESS
LOG_EMAIL_CC = os.environ.get("LOG_EMAIL_CC", "")  # 任意：奥様など別アドレスにもCCで届ける
JST = datetime.timezone(datetime.timedelta(hours=9))


def now_jst() -> str:
    return datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M")


def _split_addrs(value: str) -> list:
    # カンマ区切りで複数アドレス可（例: "a@x.com, b@y.com"）
    return [a.strip() for a in value.replace(";", ",").split(",") if a.strip()]


def send_log_email(subject: str, text: str, raise_errors: bool = False) -> None:
    """採点/面接の履歴をメールで送る。失敗してもアプリ本体は止めない。"""
    to_list = _split_addrs(LOG_EMAIL_TO)
    cc_list = _split_addrs(LOG_EMAIL_CC)
    if not (GMAIL_ADDRESS and GMAIL_APP_PASSWORD and to_list):
        msg = "メール設定が未完了です（GMAIL_ADDRESS / GMAIL_APP_PASSWORD / LOG_EMAIL_TO のいずれかが空）"
        print(f"[mail] {msg}", flush=True)
        if raise_errors:
            raise RuntimeError(msg)
        return
    try:
        m = MIMEText(text, "plain", "utf-8")
        m["Subject"] = str(Header(subject, "utf-8"))
        m["From"] = GMAIL_ADDRESS
        m["To"] = ", ".join(to_list)
        if cc_list:
            m["Cc"] = ", ".join(cc_list)
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=20) as s:
            s.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            s.sendmail(GMAIL_ADDRESS, to_list + cc_list, m.as_string())
        print(f"[mail] 送信成功 → to={to_list} cc={cc_list}", flush=True)
    except Exception as e:
        print(f"[mail] 送信失敗: {type(e).__name__}: {e}", flush=True)
        if raise_errors:
            raise


app = FastAPI(title="Henyu Challenge")
_client = None


def client() -> Anthropic:
    global _client
    if _client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise HTTPException(500, "ANTHROPIC_API_KEY が設定されていません。")
        _client = Anthropic()
    return _client


def ask(system: str, messages: list) -> str:
    try:
        resp = client().messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, system=system, messages=messages
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    except HTTPException:
        raise
    except Exception as e:  # noqa
        raise HTTPException(502, f"Claude API エラー: {e}")


def parse_json(text: str):
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.strip("`")
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    s, e = t.find("{"), t.rfind("}")
    if s >= 0 and e >= 0:
        t = t[s:e + 1]
    try:
        return json.loads(t)
    except Exception:
        return None


def grade_from(n: int) -> str:
    return "A" if n >= 85 else "B" if n >= 70 else "C" if n >= 55 else "D"


# ---------- fallback prompts (API失敗時のみ) ----------
BANK = {
    "ja": {
        "quote": [
            {"prompt": "「失敗とは、より賢く再挑戦するためのよい機会である。」この言葉について、あなた自身の考えや経験を書きなさい。", "author": "ヘンリー・フォード"},
            {"prompt": "「大きなことができないなら、小さなことを大きな心で行いなさい。」この言葉に関連するあなたの考えや経験を書きなさい。", "author": "ナポレオン・ヒル"},
        ],
        "yn": [
            {"prompt": "「外国で暮らす経験は、誰にとっても価値がある。」この意見に賛成ですか、反対ですか。立場を明確にして理由を書きなさい。", "author": ""},
            {"prompt": "「環境が変わることは、人を成長させる。」この意見に賛成ですか、反対ですか。", "author": ""},
        ],
    },
    "en": {
        "quote": [
            {"prompt": "“If you cannot do great things, do small things in a great way.” Write about your own thoughts and experiences that connect to this quote.", "author": "Napoleon Hill"},
        ],
        "yn": [
            {"prompt": "“Living abroad is valuable for everyone.” Do you agree or disagree? State your position and give specific reasons.", "author": ""},
        ],
    },
}


# ---------- request models ----------
class PromptReq(BaseModel):
    type: str = "auto"     # auto | quote | yn
    lang: str = "ja"       # ja | en


class ScoreReq(BaseModel):
    prompt: str
    ptype: str = "quote"   # quote | yn
    author: str = ""
    answer: str
    core: str
    lang: str = "ja"


class Turn(BaseModel):
    role: str  # "q" | "a"
    text: str


class InterviewReq(BaseModel):
    lang: str = "ja"       # ja | en | mix
    core: str
    history: list[Turn] = []
    action: str = "answer"  # start | answer
    qcount: int = 0


# ---------- endpoints ----------
@app.post("/api/prompt")
def gen_prompt(r: PromptReq):
    want = r.type if r.type in ("quote", "yn") else random.choice(("quote", "yn"))
    lang_word = "英語" if r.lang == "en" else "日本語"
    system = f"""あなたは関西学院千里国際中等部・帰国生入試の作文エッセイの作問者です。中学3年生(帰国生)向けに、本番と同形式のお題を1問だけ作ります。
- quote(名言型): 実在の人物の名言を引用し、その名言に関連する自分の考えや経験を書かせる。
- yn(イエスノー型): ある意見を1文で示し、賛成/反対の立場を明確にして理由を書かせる。
出力は {lang_word} で。難しすぎず、中学生が自分の経験で書ける普遍的なテーマにすること。
必ず次のJSONのみを出力（説明や```は禁止）:
{{"type":"{want}","prompt":"お題本文","author":"名言型なら人物名・それ以外は空文字","hint":"書き出し(起)で自分の経験につなぐためのヒントを1文"}}"""
    try:
        j = parse_json(ask(system, [{"role": "user", "content": f"{want}型のお題を1問作ってください。"}]))
        if j and j.get("prompt"):
            j["type"] = want
            return j
    except HTTPException:
        pass
    pick = random.choice(BANK[r.lang][want])
    return {"type": want, "prompt": pick["prompt"], "author": pick["author"],
            "hint": "書き出しで、お題と自分の経験を一言でつなげましょう。" if r.lang == "ja"
            else "Connect the theme to your own experience in the opening."}


def _score_email(r: "ScoreReq", j: dict) -> tuple[str, str]:
    ptype = "イエスノー型" if r.ptype == "yn" else "名言型"
    lang = "英語" if r.lang == "en" else "日本語"
    subject = f"【小論文 {j.get('grade','')} {j.get('total','')}点】{r.prompt[:24]}"
    lines = [
        f"■ 小論文道場  {now_jst()}",
        f"形式: {ptype}／言語: {lang}",
        "",
        f"【お題】\n{r.prompt}" + (f"（{r.author}）" if r.author else ""),
        "",
        f"【息子さんの回答】\n{r.answer}",
        "",
        f"【採点】 {j.get('grade','')}  {j.get('total','')}点 / 100",
    ]
    if j.get("overall"):
        lines.append(f"総評: {j['overall']}")
    for ax in j.get("axes", []):
        lines.append(f"  ・{ax.get('name','')}: {ax.get('score','')}/{ax.get('max','')} — {ax.get('comment','')}")
    if j.get("good"):
        lines.append("良い点: " + " / ".join(j["good"]))
    if j.get("improve"):
        lines.append("改善点: " + " / ".join(j["improve"]))
    if j.get("rewrite_intro"):
        lines.append(f"書き出し例: {j['rewrite_intro']}")
    return subject, "\n".join(lines)


@app.post("/api/score")
def score(r: ScoreReq, background_tasks: BackgroundTasks):
    ptype = "イエスノー型" if r.ptype == "yn" else "名言型"
    system = f"""あなたは関西学院千里国際中等部・帰国生入試の作文エッセイを採点する経験豊富な指導者です。
受験生(中3・帰国生)は次の戦略をとっています：「承・転・結」はほぼ固定の【中心となる内容】を使い、「起」でその日のお題と中心内容を結びつける。
よって最重要の評価軸は『お題との整合性』——与えられたお題に正しく答えられているか、用意した転校・コミュニケーションの話を自然で説得力ある形でお題に結びつけられているか。
名言型なら名言の意味と経験の結びつき、イエスノー型なら賛成/反対の立場の明確さとその立場を経験で支えているかを見る。
回答は口頭(音声入力)を書き起こしたものの場合があるので、言い回しの細かな乱れは厳しく見ず、論理と内容を中心に評価すること。

【お題】({ptype}) {r.prompt} {('／' + r.author) if r.author else ''}

【受験生が準備している中心となる内容】
{r.core}

採点は4軸・合計100点：
- お題との整合性 (40点)
- 構成（起承転結／立場の明確さ）(20点)
- 内容の具体性・説得力 (25点)
- 表現・言葉づかい (15点)
評価ABCDは合計点で A:85-100 / B:70-84 / C:55-69 / D:0-54。
励ましつつ、中学生に伝わる具体的な日本語で。必ず次のJSONのみ（```や前後の文は禁止）:
{{"total":合計点(整数),"grade":"A|B|C|D","overall":"総評1〜2文","axes":[{{"name":"お題との整合性","score":整数,"max":40,"comment":"一言"}},{{"name":"構成","score":整数,"max":20,"comment":"一言"}},{{"name":"内容の具体性・説得力","score":整数,"max":25,"comment":"一言"}},{{"name":"表現","score":整数,"max":15,"comment":"一言"}}],"good":["良い点1","良い点2"],"improve":["改善点1","改善点2"],"rewrite_intro":"このお題なら、こんな『起』にすると整合性が上がる、という書き出し例(1〜2文)"}}"""
    j = parse_json(ask(system, [{"role": "user", "content": f"【受験生の答案】\n{r.answer}"}]))
    if not j or "total" not in j:
        raise HTTPException(502, "採点結果を解釈できませんでした。もう一度お試しください。")
    if not j.get("grade"):
        j["grade"] = grade_from(int(j["total"]))
    subject, body = _score_email(r, j)
    background_tasks.add_task(send_log_email, subject, body)
    return j


def _interview_email(r: "InterviewReq", j: dict) -> tuple[str, str]:
    question = ""
    answer = ""
    for t in r.history:
        if t.role == "q":
            question = t.text
        elif t.role == "a":
            answer = t.text
    lang = {"en": "英語", "mix": "ミックス"}.get(r.lang, "日本語")
    subject = f"【面接 {j.get('grade','')} {j.get('score','')}点】{question[:24]}"
    lines = [
        f"■ 面接シミュレーター  {now_jst()}",
        f"言語: {lang}／{r.qcount}問目",
        "",
        f"【質問】\n{question}",
        "",
        f"【息子さんの回答】\n{answer}",
        "",
        f"【採点】 {j.get('grade','')}  {j.get('score','')}点 / 100",
    ]
    if j.get("feedback"):
        lines.append(f"アドバイス: {j['feedback']}")
    return subject, "\n".join(lines)


@app.post("/api/interview")
def interview(r: InterviewReq, background_tasks: BackgroundTasks):
    lang_label = {"en": "英語のみ", "mix": "日本語と英語を自然に混ぜて(本番同様)"}.get(r.lang, "日本語のみ")
    end_note = ("これで5問終わりなので done を true にし、next_question は空、feedback を全体の総評にしてください。"
                if r.qcount >= 5 else "")
    system = f"""あなたは関西学院千里国際中等部・帰国生入試の面接官です。中学3年生の帰国生を、温かく丁寧に面接します。
言語は【{lang_label}】で話してください。質問は一度に1つだけ。志望理由・自己紹介・海外/転校の経験・長所と短所・入学後に挑戦したいこと・関心のあるニュースなどから自然に選びます。
受験生は「7回の転校→文化や国の違いの理解→コミュニケーション力を高めた」という強みを持っています(下記)。それを引き出すような質問・深掘りをするとよい。
回答は口頭(音声書き起こし)の場合があるので言い回しの乱れは厳しく見ないこと。
直前の受験生の回答を100点満点+ABCD(A:85+,B:70-84,C:55-69,D:55未満)で採点し、短いアドバイスと次の質問を返します。
{end_note}
必ず次のJSONのみ(```禁止): {{"score":整数,"grade":"A|B|C|D","feedback":"前の回答へのアドバイス(1〜2文・励まし)","next_question":"次の質問","done":false}}

【受験生の強み(中心の話)】
{r.core}"""

    if r.action == "start":
        msgs = [{"role": "user", "content": "面接を始めてください。軽く挨拶して、最初の質問を1つしてください(採点は0点・gradeは空でよい、feedbackは挨拶)。"}]
    else:
        msgs = []
        for t in r.history:
            msgs.append({"role": "assistant" if t.role == "q" else "user", "content": t.text})
        if not msgs or msgs[-1]["role"] != "user":
            raise HTTPException(400, "回答がありません。")

    j = parse_json(ask(system, msgs))
    if not j:
        raise HTTPException(502, "面接の応答を解釈できませんでした。")
    if not j.get("grade"):
        j["grade"] = grade_from(int(j.get("score", 0)))
    # 「start」は挨拶のみで採点がないのでメールしない。回答があったときだけ送る。
    if r.action == "answer":
        subject, body = _interview_email(r, j)
        background_tasks.add_task(send_log_email, subject, body)
    return j


@app.get("/healthz")
def healthz():
    return {"ok": True, "model": MODEL}


@app.get("/api/_mailtest")
def mailtest():
    """メール設定の診断用（一時的）。実際に1通送ってみて、結果と原因を返す。"""
    cfg = {
        "GMAIL_ADDRESS_set": bool(GMAIL_ADDRESS),
        "GMAIL_APP_PASSWORD_set": bool(GMAIL_APP_PASSWORD),
        "GMAIL_APP_PASSWORD_len": len(GMAIL_APP_PASSWORD),
        "GMAIL_APP_PASSWORD_has_space": (" " in GMAIL_APP_PASSWORD),
        "LOG_EMAIL_TO_count": len(_split_addrs(LOG_EMAIL_TO)),
        "LOG_EMAIL_CC_count": len(_split_addrs(LOG_EMAIL_CC)),
    }
    try:
        send_log_email("【テスト】メール設定の確認",
                       "これは編入チャレンジのメール設定が正しいか確認するテスト送信です。",
                       raise_errors=True)
        return {"ok": True, "config": cfg}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "config": cfg}


# 静的ファイル（フロント）をルートで配信。API ルートの後に mount すること。
app.mount("/", StaticFiles(directory="static", html=True), name="static")
