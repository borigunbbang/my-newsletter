# 헬스케어 AI 데일리 — 뉴스레터 에이전트

헬스케어 AI 개발자·취준생을 위해 매일 07:00 KST에 기사를 수집·선별·요약·검수해 텔레그램으로 발행하는 LangGraph 파이프라인입니다. 설계와 결과는 [REPORT.md](REPORT.md)에 있습니다.

## 구조

```
graph.py             LangGraph 노드·엣지 (검수 재생성·대체 루프 포함)
run.py               실행 진입점 (로컬·GitHub Actions 공용)
state.py             State 정의
metrics.py           store/metrics.jsonl 기록
audience.yaml        독자·중요도 판단 문장·채택 소스·선별/검수 설정
nodes/               collect · select(예선·본문·본선) · summarize · review · publish
tools/eval_sources.py  소스 후보 실측 → store/source_eval.json
tests/               오류 주입 테스트 (요약 숫자 변조 → 검수 실패 → 재생성)
store/               metrics.jsonl · seen.json · source_eval.json
```

## 로컬 실행

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 입력
.venv/bin/python run.py
```

- 소스 재실측: `.venv/bin/python tools/eval_sources.py` (저장값으로 재판정만: `--rejudge`)
- 오류 주입 테스트: `.venv/bin/python tests/test_review_injection.py`

## 자동 실행 (GitHub Actions)

- `.github/workflows/newsletter.yml`: 매일 07:00 KST(`cron: 0 22 * * *` UTC) + 수동 실행(`workflow_dispatch`)
- 실행 후 `store/`의 변경을 `github-actions[bot]`이 커밋합니다 (`[skip ci]`).
- 필요한 Secrets: `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- GitHub의 예약 실행은 부하에 따라 몇 분~몇십 분 늦게 시작될 수 있습니다.

### 워크플로 끄기 (과제 제출 기간 이후)

- 웹: 저장소 → **Actions** 탭 → 왼쪽에서 `newsletter` 선택 → 오른쪽 위 **`···`** → **Disable workflow** (다시 켤 때는 같은 위치의 **Enable workflow**)
- CLI: `gh workflow disable newsletter` / `gh workflow enable newsletter`
- 영구 제거: `.github/workflows/newsletter.yml` 삭제 후 커밋
