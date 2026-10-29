"""summarize: 본문 기반 한국어 제목·요약 3줄·인사이트 (검수 실패 기사는 실패 사유를 넣어 재생성)"""
import os
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel

from state import NewsState

BODY_FOR_SUMMARY = 8000


class Draft(BaseModel):
    title: str
    summary: list[str]
    dev_action: str
    market_context: str
    limits: str
    evidence: Literal["동료심사 논문", "프리프린트", "보도자료", "기사"]


def pending(state: NewsState) -> list[str]:
    """아직 검수를 통과하지도, 스킵되지도 않은 선발 기사"""
    done = set(state.get("approved", [])) | set(state.get("skipped", []))
    return [i for i in state["selected"] if i not in done]


def summarize(state: NewsState) -> dict:
    items = {it["id"]: it for it in state["candidates"]}
    drafts = dict(state.get("drafts", {}))
    client = OpenAI()
    for item_id in pending(state):
        it = items[item_id]
        history = state.get("review_results", {}).get(item_id, [])
        feedback = (f"\n\n[이전 초안의 검수 실패 사유 — 반드시 고칠 것]\n{history[-1]['feedback']}" if history else "")
        res = client.chat.completions.parse(
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            messages=[
                {"role": "system", "content": (
                    "헬스케어 AI 개발자·취준생을 위한 뉴스레터 편집자다. 아래 본문에 있는 사실만 쓴다.\n"
                    "- title: 한국어 제목 (영문 기사도 번역, 40자 이내)\n"
                    "- summary: 핵심 요약 정확히 3문장, 한국어. 수치·날짜·고유명사(기관·제품·모델명)는 원문 표기 그대로\n"
                    "- dev_action: 독자가 이번 주에 해볼 수 있는 것 1개 (본문 근거가 없으면 '관련 공개 자료 확인' 수준으로)\n"
                    "- market_context: 시장·규제 맥락에서 왜 중요한지 1문장. 본문에 없는 승인·입증·성과를 단정하지 않는다\n"
                    "- limits: 표본 수, 외부 검증 부재 등 본문에서 드러나는 한계. 없으면 빈 문자열\n"
                    "- evidence: 근거 수준 (arXiv는 프리프린트, 학술지 논문은 동료심사 논문)")},
                {"role": "user", "content": (
                    f"출처: {it['source']}\n원문 제목: {it['title']}\n\n본문:\n"
                    f"{state['bodies'][item_id][:BODY_FOR_SUMMARY]}{feedback}")},
            ],
            response_format=Draft,
        )
        d = res.choices[0].message.parsed
        drafts[item_id] = {**d.model_dump(), "title_original": it["title"], "source": it["source"],
                           "url": it["url"], "published_at": it["published_at"][:10]}
    return {"drafts": drafts}
