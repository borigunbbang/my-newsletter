"""compose: 검수 통과 기사 → 텔레그램 메시지 / publish: 전송·확인·기록

drafts[item_id] 형식 (summarize 노드가 채움):
  title(한국어 제목 — 영문 기사도 번역), title_original, source, url, published_at, evidence(근거 수준),
  summary(3줄 리스트), dev_action, market_context, limits(없으면 빈 문자열)
"""
import datetime as dt
import html
import json
import os
from pathlib import Path

import requests
from openai import OpenAI

import metrics
from state import NewsState

SEEN = Path(__file__).resolve().parent.parent / "store" / "seen.json"
TG_LIMIT = 4096
KST = dt.timezone(dt.timedelta(hours=9))


def headline(drafts: list[dict]) -> str:
    """오늘 기사 전체를 관통하는 흐름 1문장"""
    titles = "\n".join(f"- {d['title']}: {d['summary'][0]}" for d in drafts)
    res = OpenAI().chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
        messages=[
            {"role": "system", "content": (
                "헬스케어 AI 뉴스레터의 '오늘의 한 줄'을 쓴다. 아래 기사들만 근거로, "
                "공통 흐름을 한국어 한 문장(60자 이내)으로. 기사에 없는 사실은 쓰지 않는다.")},
            {"role": "user", "content": titles},
        ],
    )
    return res.choices[0].message.content.strip()


def item_message(d: dict) -> str:
    e = html.escape
    lines = [
        f"■ <b>{e(d['title'])}</b>",
        f"{e(d['source'])} · {e(d['published_at'])} · [{e(d['evidence'])}]",
        "",
        *[f"• {e(s)}" for s in d["summary"]],
        f"👩‍💻 개발자 관점: {e(d['dev_action'])}",
        f"📈 시장·규제 맥락: {e(d['market_context'])}",
    ]
    if d.get("limits"):
        lines.append(f"⚠️ 한계: {e(d['limits'])}")
    # 본문 아래 빈 줄 3개 후 원문 링크 → 그 아래에 미리보기 카드
    link = f"\n\n\n\n🔗 <a href=\"{e(d['url'])}\">원문 보기</a>"
    return "\n".join(lines)[:TG_LIMIT - len(link)] + link


def compose(state: NewsState) -> dict:
    drafts = [state["drafts"][i] for i in state["approved"]]
    today = dt.datetime.now(KST).strftime("%Y-%m-%d")
    header = f"📰 [{today}] 헬스케어 AI 데일리\n💡 오늘의 한 줄: {html.escape(headline(drafts))}"
    return {"newsletter": {"header": header, "messages": [item_message(d) for d in drafts]}}


def send(text: str, url: str | None = None) -> dict:
    # 기사 메시지: 원문 대표 사진을 크게, 본문 아래에 미리보기 / 헤더: 미리보기 없음
    preview = ({"url": url, "prefer_large_media": True, "show_above_text": False}
               if url else {"is_disabled": True})
    r = requests.post(
        f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
        json={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text, "parse_mode": "HTML",
              "link_preview_options": preview},
        timeout=20,
    )
    return r.json()


def send_with_retry(text: str, url: str | None = None) -> int | None:
    """성공하면 message_id, 1회 재시도 후에도 실패하면 None"""
    for _ in range(2):
        try:
            res = send(text, url)
            if res.get("ok") and res.get("result", {}).get("message_id"):
                return res["result"]["message_id"]
        except requests.RequestException:
            pass
    return None


def publish(state: NewsState) -> dict:
    nl = state["newsletter"]
    texts = [nl["header"], *nl["messages"]]
    urls = [None, *[state["drafts"][i]["url"] for i in state["approved"]]]
    message_ids = [send_with_retry(t, u) for t, u in zip(texts, urls)]
    ok = all(message_ids)
    status = "published" if ok else "partial"

    # 발행에 성공한 기사 URL만 seen.json에 추가 (message_ids[0]은 헤더)
    sent_items = [i for i, mid in zip(state["approved"], message_ids[1:]) if mid]
    seen = set(json.loads(SEEN.read_text())) if SEEN.exists() else set()
    seen |= {state["drafts"][i]["url"] for i in sent_items}
    SEEN.parent.mkdir(exist_ok=True)
    SEEN.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2))

    metrics.log(state["run_id"], "publish", status=status, message_ids=message_ids,
                char_counts=[len(t) for t in texts], item_ids=sent_items)
    errors = state.get("errors", []) + ([] if ok else ["telegram: 일부 메시지 전송 실패"])
    return {"publish_result": {"status": status, "message_ids": message_ids}, "errors": errors}
