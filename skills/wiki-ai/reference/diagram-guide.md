# 구조도 작성 가이드 (SVG)

방법·구성요소 섹션의 **구조도**를 직접 그린다. 도구: `python3 ${CLAUDE_SKILL_DIR}/scripts/diagram.py` (아래 `DG`). 표준 라이브러리만 사용, 설치 불필요.
결과물은 SVG 한 장이며 Confluence 에 그대로 첨부한다 (사내 Confluence 9.2 에서 `ac:image` 로 정상 표시 확인됨).

## 1. 언제 그리나

- **그린다**: 2번 섹션(Method / Architecture)에 구조도가 필요한데, 프로젝트에 쓸 만한 구조도 이미지가 없거나 있어도 낡았거나 읽기 어려울 때.
- **그리지 않는다**: 프로젝트에 이미 좋은 구조도가 있으면 그것을 쓴다. 결과 그래프(산점도, 곡선)는 이 도구 대상이 아니다 — 프로젝트의 그래프 이미지를 쓴다.
- 보통 페이지당 1~2장: 전체 구조 1장(+ 필요하면 핵심 모듈 1장). 장식용으로 늘리지 않는다.

## 2. 무엇을 그리나 — 근거가 있는 것만

- 박스·화살표 하나하나가 **프로젝트 파일에서 확인한 구성요소와 흐름**이어야 한다 (모듈, 클래스, 스크립트, 데이터 경로, 외부 서비스).
- 근거 장부에 구조도 항목을 한 줄씩 넣는다: `| 12 | 구조도: Encoder → Head (2-1_architecture.svg) | model.py:40-88 | 확인 |`. 흐름을 코드에서 직접 못 봤으면 `추론`.
- 노드 이름은 **코드·본문과 같은 이름**을 쓴다 (본문은 "Fusion Head" 인데 그림은 "결합부" 같은 불일치 금지). 부제(`sub`)에는 파일명·핵심 설정·텐서 크기처럼 확인 가능한 정보.

## 3. 레이아웃 패턴

| 패턴 | 쓰는 곳 | 배치 |
|---|---|---|
| **파이프라인** | 데이터 → 처리 → 출력, 에이전트 흐름 | 왼쪽 → 오른쪽 그룹 2~4개, 그룹 안 카드는 위 → 아래 |
| **계층** | 시스템 아키텍처 (클라이언트 / 서버 / 저장소) | 위 → 아래 그룹(가로로 긴 그룹), 카드는 가로 나열 |
| **모델 구조** | 신경망·추론 그래프 | 입력 → 모듈들 → 출력 가로 흐름. 브랜치는 위아래로 나눈 뒤 결합 카드로 합침. 아이콘 없이 `align: center` 카드도 좋다 |

- **격자**: 좌표는 2 의 배수, 카드 크기 통일 (보통 높이 64, 폭 200~260). 같은 열은 x 를, 같은 행은 y 를 정확히 맞춘다. 카드 간격 16~20, 그룹 안쪽 여백 18, 그룹 사이 40~48.
- **그룹 제목 줄**: 그룹 위쪽 44px 는 제목 자리 → 첫 카드는 `group.y + 50` 정도부터.
- **캔버스**: 폭 900~1200 (본문 폭에 맞음), 높이는 내용에 맞게. 제목을 쓰면 위 60px 확보.
- **흐름 방향은 하나**로. 되돌아가는 화살표(피드백, 사람 개입)는 `dashed`.
- **번호 배지**(`num`)는 실제로 순서가 있는 단계에만.
- 한 그림에 카드 15개 이하. 넘으면 그림을 나누거나 묶는다.

## 4. 색·아이콘

- **색은 그룹당 하나**. 그룹 색은 로고가 있으면 브랜드 색 자동(Simple Icons), 없으면 `PALETTE` 이름(`blue`, `teal`, `violet`, `amber`, `slate` …) 또는 `#RRGGBB`. 카드는 속한 그룹 색을 이어받는다. 한 그림에 강조색 3~4개 이하.
- **로고 (`si:`)**: 실제 쓰는 기술·제품만 (Python, PyTorch, Docker, Redis, PostgreSQL, Confluence …). 그룹 제목 옆에 둔다. 찾기: `DG icons si <이름>`.
- **일반 아이콘 (`lu:`)**: 역할을 나타내는 것 하나씩 (데이터 `database`, 파일 `file-text`, 코드 `file-code`, 모델 `brain-circuit`, GPU `cpu`, 서버 `server`, API `plug`, 큐 `layers`, 사용자 `user`, 웹 `globe`, 검색 `search`, 설정 `settings`, 로그 `scroll-text`, 그래프 `chart-line`, 카메라 `camera`, 센서 `radar`). 찾기: `DG icons lu <영어 단어>`.
- 회사·사내 시스템처럼 로고가 없는 것은 일반 아이콘 + 이름으로. **로고를 직접 그리거나 비슷하게 흉내 내지 않는다.** 외부 이미지(Flaticon 등)를 넣지 않는다.

## 5. 사양 형식 (`PROJECT/.wiki-ai/diagrams/<이름>.json`)

```json
{
  "width": 864, "height": 290,
  "title": "전체 구조", "subtitle": "입력 → 처리 → 출력",
  "groups": [
    {"id": "data", "x": 24, "y": 60, "w": 250, "h": 196, "title": "데이터", "logo": "si:python"},
    {"id": "model", "x": 318, "y": 60, "w": 522, "h": 196, "title": "모델", "logo": "si:pytorch"}
  ],
  "nodes": [
    {"id": "raw", "x": 42, "y": 110, "w": 214, "h": 64, "icon": "lu:database", "title": "원본 데이터", "sub": "data/raw/*.csv"},
    {"id": "enc", "x": 338, "y": 110, "w": 230, "h": 64, "icon": "lu:brain-circuit", "title": "Encoder", "sub": "model.py · 4 layers", "num": 1},
    {"id": "out", "x": 590, "y": 110, "w": 230, "h": 64, "title": "Head", "sub": "출력 3개", "align": "center"}
  ],
  "edges": [
    {"from": "raw", "to": "enc", "label": "전처리"},
    {"from": "enc", "to": "out"},
    {"from": "out", "to": "raw", "style": "dashed", "from_side": "bottom", "to_side": "bottom", "via": 222}
  ],
  "notes": [{"x": 24, "y": 278, "text": "점선: 평가 시에만 사용"}]
}
```

- **groups**: `id x y w h title` + 선택 `logo`(`si:`/`lu:`), `color`.
- **nodes**: `id x y w h title` + 선택 `sub`, `icon`, `num`, `color`(기본: 속한 그룹 색), `group`(기본: 좌표로 자동), `align: "center"`(아이콘 없을 때), `fill`.
- **edges**: `from to` (카드 가장자리 중앙끼리 직교 경로 자동). 선택 `from_side`/`to_side`(`left right top bottom`), `via`(꺾이는 x 또는 y), `style: "dashed"`, `label`, `label_at: [x, y]`, `color`, `both: true`(양방향). 그룹 가장자리 등 임의 경로는 `points: [[x,y], …]` (수평·수직 선분만).
- **notes**: 자유 위치 짧은 글 (`x y text` + `size color anchor`).
- 예시 전체: `${CLAUDE_SKILL_DIR}/reference/diagram-example.json` (이 플러그인 자체의 구조도).

## 6. 만들기 → 검사 → 눈으로 확인

```
DG build PROJECT/.wiki-ai/diagrams/architecture.json PROJECT/.wiki-ai/diagrams/2-1_architecture.svg --png
```
1. 출력의 `✗`(겹침, 글자 넘침, 화살표가 다른 카드 관통, 그룹 밖으로 나감)는 **모두 고친다**. `!` 는 판단해서 고친다. 글자가 넘치면 글자를 줄이거나 카드를 넓힌다 (글자 크기를 줄이지 않는다).
2. `--png` 로 PNG 가 만들어지면(Chrome/Edge/Chromium 이 있을 때) **Read 로 직접 보고** 확인한다: 정렬이 맞는가, 화살표가 엉키지 않는가, 빈 공간이 한쪽에 몰리지 않았는가, 읽는 순서가 자연스러운가. 고칠 것이 있으면 사양을 고쳐 다시 build. 브라우저가 없으면 검사 결과만 믿고, 사람 검수 웹 화면에서 확인받는다.
3. 아이콘을 못 받으면(오프라인) 대체 도형이 들어가고 경고가 나온다 → 사용자에게 알린다.

## 7. 본문에 넣기

- 첨부 이름: `섹션_내용.svg` (예: `2-1_architecture.svg`). `attach.txt` 에 `.wiki-ai/diagrams/2-1_architecture.svg=2-1_architecture.svg`. 사양 JSON 은 올리지 않는다 (로컬 `.wiki-ai/diagrams/` 에 남아 다음 업데이트 때 고쳐 쓴다).
- 섹션 제목 바로 아래 단독 이미지, 그 아래 구성요소 설명 불릿 (style-guide "구조도" 양식):
  ```xml
  <p><ac:image ac:width="1000"><ri:attachment ri:filename="2-1_architecture.svg" /></ac:image></p>
  ```
  `ac:width` 는 캔버스 폭 이하 (보통 900~1100). 작은 그림은 600~800.
- 업데이트 모드: 사양을 고쳐 같은 파일 이름으로 다시 build → 바뀐 첨부만 다시 올라간다.
