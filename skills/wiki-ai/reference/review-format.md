# 검수 기록 형식 (`.wiki-ai/review.json`)

```json
{
  "draft_sha256": "CF review-stamp / review-mark --body 가 기록",
  "full_read": false,
  "questions": [
    {
      "id": "Q1",
      "anchor": "사내 코드 시험 티켓",
      "question": "TrackMan 티켓을 '시험 티켓'으로 부를까요, 실제 운영 티켓으로 부를까요?",
      "why": "티켓 제목은 [테스트]지만 실제 사내 코드 대상이라 파일로 확정할 수 없음",
      "options": ["시험 티켓 (현재)", "실제 티켓", "사내 코드 검증 티켓"],
      "status": "open",
      "answer": null
    }
  ],
  "auto_fixes": [
    {"severity": "높음", "finding": "101→47 은 1회 대 좋은 쪽 비교", "fix": "47~52단계·14~24분(v6 2회) 범위로 표기"},
    {"severity": "중간", "finding": "47→57% 구간·시기 차이", "fix": "95% 구간과 '시기가 다른 두 실험' 명시"}
  ]
}
```

- `questions` — 사람만 답할 수 있어 **남긴** 의문점만. 0~5개. 고칠 수 있는 지적은 여기 넣지 말고 고친다.
  - `anchor`: 본문에 그대로 있는 짧은 문구 (5~30자, 굵게·링크 같은 서식이 걸친 부분 X). 미리보기에서 이 문구에 노란 표시와 댓글이 붙는다. 못 찾으면 맨 위 목록에만 보인다.
  - `options`: 현재 표현을 맨 앞에. 사용자는 선택지 밖 답도 할 수 있다.
  - 답하면 `CF review-mark review.json --answer Q1 "<답>"` → `status: answered`.
- `auto_fixes` — 검수 에이전트 지적 중 직접 고친 것 전부. 고치지 않기로 한 지적은 `fix` 에 "유지: <이유>".
- `full_read` — 사용자가 미리보기로 전체를 읽고 괜찮다고 하면 `CF review-mark review.json --full-read`.
- 업로드 때 경고(진행은 가능): 남은 의문점, 전체 읽기 안 함, 검수 이후 초안 변경(해시 불일치).

## 웹 검토 의견 (`.wiki-ai/feedback.json`, `CF serve` 가 기록)
- `items`: 사용자가 드래그해서 남긴 수정 요청 `{id: F1, quote, comment, status: open|done, resolution}`. 반영 후 `CF feedback --resolve F1 --note "<처리 내용>"`.
- `answers`: 의문점 답 `{qid, answer, status: open|applied}`. 반영 후 `CF feedback --applied Q1` + `CF review-mark --answer Q1 "<답>"`.
- `done_reading`: 웹에서 "다 읽었음" 을 누르면 true → `CF review-mark --full-read`.
