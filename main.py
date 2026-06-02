"""
関西学院千里国際中等部 編入チャレンジ — バックエンド
FastAPI + Anthropic SDK。Render で動かす想定。
- APIキーは環境変数 ANTHROPIC_API_KEY から読み込む（コードには書かない）。
- 採点・面接の履歴は、環境変数 SHEET_WEBHOOK_URL を設定すると
  Google スプレッドシートに自動で1行ずつ記録される（任意）。
"""
import os
import json
import random
import datetime
import urllib.request

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from anthropic import Anthropic

MODEL = os.environ.get("MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 1024

# ---------- スプレッドシート記録（履歴ログ用・任意） ----------
# Google Apps Script のウェブアプリURL。HTTPSなので Render でも確実に動く。
# 未設定なら何も記録しない（＝アプリは通常どおり動く）。
SHEET_WEBHOOK_URL = os.environ.get("SHEET_WEBHOOK_URL", "")

JST = datetime.timezone(datetime.timedelta(hours=9))


def now_jst() -> str:
    return datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M")


def send_to_sheet(payload: dict, raise_errors: bool = False) -> None:
    """採点/面接の履歴を Google スプレッドシートに1行追記する。
    HTTPS通信なので Render の SMTP 制約に影響されない。失敗してもアプリ本体は止めない。"""
    if not SHEET_WEBHOOK_URL:
        msg = "SHEET_WEBHOOK_URL が未設定です"
        print(f"[sheet] {msg}", flush=True)
        if raise_errors:
            raise RuntimeError(msg)
        return
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            SHEET_WEBHOOK_URL, data=data,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read(300).decode("utf-8", "ignore")
        print(f"[sheet] 記録成功: {body[:100]}", flush=True)
    except Exception as e:
        print(f"[sheet] 記録失敗: {type(e).__name__}: {e}", flush=True)
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
            {"prompt": "「多様性とは、招待されること。包摂とは、踊りに誘われること。」この言葉について、あなた自身の経験をもとに考えを書きなさい。", "author": "ヴァーナ・マイヤーズ"},
            {"prompt": "「教育とは、世界を変えるために使える最も強力な武器である。」この言葉について、あなたの経験や将来の目標と結びつけて書きなさい。", "author": "ネルソン・マンデラ"},
            {"prompt": "「人を理解するには、その人の立場に立って考えなければならない。」この考えについて、あなた自身の経験をもとに書きなさい。", "author": "ハーパー・リー"},
            {"prompt": "「変化を恐れるのではなく、変化から学びなさい。」この言葉について、あなたの経験をもとに考えを書きなさい。", "author": "作者不詳"},
            {"prompt": "「言葉は人と人を分ける壁にも、つなぐ橋にもなる。」この言葉について、あなた自身の経験をもとに書きなさい。", "author": "作者不詳"},
            {"prompt": "「本当の強さとは、違いを受け入れながら自分らしさを失わないことである。」この言葉について、あなたの考えを書きなさい。", "author": "作者不詳"},
        ],
        "yn": [
            {"prompt": "「外国で暮らす経験は、誰にとっても価値がある。」この意見に賛成ですか、反対ですか。立場を明確にして理由を書きなさい。", "author": ""},
            {"prompt": "「環境が変わることは、人を成長させる。」この意見に賛成ですか、反対ですか。", "author": ""},
            {"prompt": "「学校では、同じ考えの友人よりも、自分と違う考えの友人から多くを学べる。」この意見に賛成ですか、反対ですか。", "author": ""},
            {"prompt": "「コミュニケーションで一番大切なのは、正しい言葉よりも相手を理解しようとする姿勢である。」この意見に賛成ですか、反対ですか。", "author": ""},
            {"prompt": "「便利な翻訳アプリがあれば、外国語を学ぶ必要は少なくなる。」この意見に賛成ですか、反対ですか。", "author": ""},
            {"prompt": "「中学生は、失敗を避けるよりも新しいことに挑戦する方が大切である。」この意見に賛成ですか、反対ですか。", "author": ""},
            {"prompt": "「海外経験がある人は、その経験を周りの人のために活かす責任がある。」この意見に賛成ですか、反対ですか。", "author": ""},
            {"prompt": "「リーダーに必要なのは、人前で話す力よりも、人の話を聞く力である。」この意見に賛成ですか、反対ですか。", "author": ""},
        ],
    },
    "en": {
        "quote": [
            {"prompt": "“If you cannot do great things, do small things in a great way.” Write about your own thoughts and experiences that connect to this quote.", "author": "Napoleon Hill"},
            {"prompt": "“Education is the most powerful weapon which you can use to change the world.” Write about your thoughts and experiences connected to this quote.", "author": "Nelson Mandela"},
            {"prompt": "“Change is not something to fear, but something to learn from.” Write about your own experience connected to this idea.", "author": ""},
            {"prompt": "“Words can become walls, but they can also become bridges.” Write about your thoughts and experiences connected to this quote.", "author": ""},
        ],
        "yn": [
            {"prompt": "“Living abroad is valuable for everyone.” Do you agree or disagree? State your position and give specific reasons.", "author": ""},
            {"prompt": "“Students learn more from classmates who think differently from them than from classmates who think the same way.” Do you agree or disagree?", "author": ""},
            {"prompt": "“The most important part of communication is not perfect language, but the effort to understand others.” Do you agree or disagree?", "author": ""},
            {"prompt": "“Middle school students should try new things even if they might fail.” Do you agree or disagree?", "author": ""},
        ],
    },
}


# ---------- request models ----------
class PromptReq(BaseModel):
    type: str = "auto"     # auto | quote | yn
    lang: str = "ja"       # ja | en
    avoid: list[str] = []


class ScoreReq(BaseModel):
    prompt: str
    ptype: str = "quote"   # quote | yn
    author: str = ""
    answer: str
    core: str
    lang: str = "ja"


class ModelAnswerReq(BaseModel):
    prompt: str
    ptype: str = "quote"   # quote | yn
    author: str = ""
    answer: str = ""
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
    avoid = "\n".join(f"- {p[:180]}" for p in r.avoid[:40] if p)
    avoid_note = f"\n最近出したお題（これらと同じ名言・同じ主張・同じ切り口は避ける）:\n{avoid}\n" if avoid else ""
    system = f"""あなたは関西学院千里国際中等部・帰国生入試の作文エッセイの作問者です。中学3年生(帰国生)向けに、本番と同形式のお題を1問だけ作ります。
- quote(名言型): 実在の人物の名言を引用し、その名言に関連する自分の考えや経験を書かせる。
- yn(イエスノー型): ある意見を1文で示し、賛成/反対の立場を明確にして理由を書かせる。
出力は {lang_word} で。難しすぎず、中学生が自分の経験で書ける普遍的なテーマにすること。
テーマは毎回変えること。例: 失敗、挑戦、異文化理解、言葉、友情、リーダーシップ、聞く力、テクノロジー、学校生活、将来の貢献、多様性、自己表現。
帰国生の「転校経験・文化差・コミュニケーション力」につなげやすいが、露骨に同じ話題へ誘導しすぎないこと。
{avoid_note}
必ず次のJSONのみを出力（説明や```は禁止）:
{{"type":"{want}","prompt":"お題本文","author":"名言型なら人物名・それ以外は空文字","hint":"書き出し(起)で自分の経験につなぐためのヒントを1文"}}"""
    try:
        j = parse_json(ask(system, [{"role": "user", "content": f"{want}型のお題を1問作ってください。"}]))
        if j and j.get("prompt"):
            j["type"] = want
            return j
    except HTTPException:
        pass
    candidates = [p for p in BANK[r.lang][want] if p["prompt"] not in set(r.avoid)]
    pick = random.choice(candidates or BANK[r.lang][want])
    return {"type": want, "prompt": pick["prompt"], "author": pick["author"],
            "hint": "書き出しで、お題と自分の経験を一言でつなげましょう。" if r.lang == "ja"
            else "Connect the theme to your own experience in the opening."}


@app.post("/api/score")
def score(r: ScoreReq, background_tasks: BackgroundTasks):
    ptype = "イエスノー型" if r.ptype == "yn" else "名言型"
    chars = len(r.answer)
    system = f"""あなたは関西学院千里国際中等部・帰国生入試の作文エッセイを採点する経験豊富な指導者です。
受験生(中3・帰国生)は次の戦略をとっています：「承・転・結」はほぼ固定の【中心となる内容】を使い、「起」でその日のお題と中心内容を結びつける。
ただし採点は、学校から示された本番評価表を最優先する。『お題との整合性』は特に「構成」と「内容」の中で評価する。
名言型なら名言の意味と経験の結びつき、イエスノー型なら賛成/反対の立場の明確さとその立場を経験で支えているかを見る。
回答は口頭(音声入力)を書き起こしたものの場合があるので、言い回しの細かな乱れは厳しく見ず、論理と内容を中心に評価すること。

【字数の要件】本番の作文は800字以上が必要です。今回の答案は約{chars}字です。
- 800字に満たない場合は字数不足として評価に必ず反映する（特に「構成」と「内容」を減点）。総評と改善点でも字数不足を具体的に指摘し、あと約{max(0, 800 - chars)}字必要だと伝えること。
- 800字以上ある場合は字数要件を満たしている旨を一言添える。

【お題】({ptype}) {r.prompt} {('／' + r.author) if r.author else ''}

【受験生が準備している中心となる内容】
{r.core}

【本番評価表に基づく採点】
3項目をそれぞれ0〜3点で採点する（合計9点満点）。total は 9点満点を100点換算した整数にする。

1) 構成（論の組み立て）
3点: よく考えられ、効果的に論が展開されている。明確で論理的に論が組み立てられており、読みやすい。
2点: 論の展開が十分されている。論が適切に組み立てられており、読み手は十分に展開を追うことができる。
1点: 論の展開が十分にされていない。展開を追うのがいくぶん難しい。
0点: 展開の計画がないままに書かれている。質問に関わりの無い内容である。

2) 内容（考えの質）
3点: 独自の興味深い考えを述べている。裏づけに説得力がある。説明が詳細かつ明解である。
2点: 課題にそった考えを述べている。裏づけが明解で課題が通っている。説明が十分されている。
1点: 考えが不明瞭、あるいは浅い。裏づけになる事柄を述べようとした形跡がある。説明があいまいで詳細に欠ける。
0点: 考えが意義に欠ける、または不明瞭。裏づけが足りない、または全く無い。説明が不明瞭、関係性が薄い、または全く無い。質問に関わりの無い内容である。

3) 言語表現
3点: 自分が選んだ言語で、考えを表現豊かに伝えることができる。
2点: 自分が選んだ言語で、考えを適切に伝えることができる。
1点: 自分が選んだ言語でうまく伝えられないことがある。
0点: 自分が選んだ言語で考えを明確に伝えることができない。

評価ABCDは100点換算で A:85-100 / B:70-84 / C:55-69 / D:0-54。
励ましつつ、中学生に伝わる具体的な日本語で。必ず次のJSONのみ（```や前後の文は禁止）:
{{"total":100点換算の合計点(整数),"grade":"A|B|C|D","overall":"総評1〜2文。9点満点の合計も含める","axes":[{{"name":"構成","score":0〜3の整数,"max":3,"comment":"本番評価表に照らした一言"}},{{"name":"内容","score":0〜3の整数,"max":3,"comment":"本番評価表に照らした一言"}},{{"name":"言語表現","score":0〜3の整数,"max":3,"comment":"本番評価表に照らした一言"}}],"good":["良い点1","良い点2"],"improve":["改善点1","改善点2"],"rewrite_intro":"このお題なら、こんな『起』にすると構成と内容の評価が上がる、という書き出し例(1〜2文)"}}"""
    j = parse_json(ask(system, [{"role": "user", "content": f"【受験生の答案】\n{r.answer}"}]))
    if not j or "total" not in j:
        raise HTTPException(502, "採点結果を解釈できませんでした。もう一度お試しください。")
    axes = j.get("axes") or []
    raw = 0
    for a in axes:
        try:
            if int(a.get("max", 0)) == 3:
                raw += int(a.get("score", 0))
        except Exception:
            pass
    if axes and 0 <= raw <= 9:
        j["total"] = round(raw / 9 * 100)
        j["overall"] = f"本番評価表では9点満点中{raw}点相当です。{j.get('overall', '')}"
    j["grade"] = grade_from(int(j["total"]))
    axes_txt = " / ".join(f"{a.get('name','')}{a.get('score','')}/{a.get('max','')}" for a in j.get("axes", []))
    char_note = f"{chars}字" + ("（800字以上）" if chars >= 800 else f"（800字まであと{800 - chars}字）")
    detail = char_note + " ｜ " + axes_txt
    if j.get("good"):
        detail += "｜良:" + "・".join(j["good"])
    if j.get("improve"):
        detail += "｜改:" + "・".join(j["improve"])
    background_tasks.add_task(send_to_sheet, {
        "datetime": now_jst(),
        "type": "小論文",
        "lang": "英語" if r.lang == "en" else "日本語",
        "topic": (r.prompt + (f"（{r.author}）" if r.author else "")),
        "answer": r.answer,
        "score": j.get("total", ""),
        "grade": j.get("grade", ""),
        "comment": j.get("overall", ""),
        "detail": detail,
    })
    return j


@app.post("/api/model-answer")
def model_answer(r: ModelAnswerReq, background_tasks: BackgroundTasks):
    ptype = "イエスノー型" if r.ptype == "yn" else "名言型"
    lang_label = "英語" if r.lang == "en" else "日本語"
    stance_note = "イエスノー型では、賛成/反対の立場を最初から明確にしてください。" if r.ptype == "yn" else "名言型では、名言の意味を自分の経験と自然に結びつけてください。"
    system = f"""あなたは関西学院千里国際中等部・帰国生入試の作文エッセイを指導する先生です。
受験生(中3・帰国生)が次のお題で練習したあとに読む、模範回答を作ってください。

条件:
- 出力は{lang_label}。
- 中学生本人が本番で書ける自然な文体にする。
- 準備している中心内容「7回の転校→違いの理解→コミュニケーション力」を使う。
- ただし、丸暗記の文章ではなく、その日のお題に合わせた「起」で自然につなぐ。
- {stance_note}
- 日本語なら800字以上、英語なら300〜450 words程度を目安にする。
- 最後は千里国際で学びたい姿勢につなげる。

【お題】({ptype}) {r.prompt} {('／' + r.author) if r.author else ''}

【受験生が準備している中心となる内容】
{r.core}

必ず次のJSONのみ（```や前後の文は禁止）:
{{"title":"短い題名","answer":"模範回答本文","points":["真似したいポイント1","真似したいポイント2","真似したいポイント3"]}}"""
    user = "このお題の模範回答を作ってください。"
    if r.answer:
        user += f"\n\n参考: 受験生が先ほど書いた答案\n{r.answer}"
    j = parse_json(ask(system, [{"role": "user", "content": user}]))
    if not j or not j.get("answer"):
        raise HTTPException(502, "模範回答を作成できませんでした。もう一度お試しください。")
    if not isinstance(j.get("points"), list):
        j["points"] = []
    model_text = j.get("answer", "")
    if j.get("points"):
        model_text += "\n\n真似したいポイント:\n" + "\n".join(f"- {p}" for p in j["points"])
    background_tasks.add_task(send_to_sheet, {
        "action": "update_model_answer",
        "topic": (r.prompt + (f"（{r.author}）" if r.author else "")),
        "answer": r.answer,
        "model_answer": model_text,
    })
    return j


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
    # 「start」は挨拶のみで採点がないので記録しない。回答があったときだけ記録する。
    if r.action == "answer":
        question = answer = ""
        for t in r.history:
            if t.role == "q":
                question = t.text
            elif t.role == "a":
                answer = t.text
        background_tasks.add_task(send_to_sheet, {
            "datetime": now_jst(),
            "type": "面接",
            "lang": {"en": "英語", "mix": "ミックス"}.get(r.lang, "日本語"),
            "topic": question,
            "answer": answer,
            "score": j.get("score", ""),
            "grade": j.get("grade", ""),
            "comment": j.get("feedback", ""),
            "detail": f"{r.qcount}問目 ／ {len(answer)}字",
        })
    return j


@app.get("/healthz")
def healthz():
    return {"ok": True, "model": MODEL}


# 静的ファイル（フロント）をルートで配信。API ルートの後に mount すること。
app.mount("/", StaticFiles(directory="static", html=True), name="static")
