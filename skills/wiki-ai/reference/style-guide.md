# AI Research 위키 작성 가이드

기준 페이지: 키 파일의 `CONFLUENCE_TEMPLATE_PAGE_ID` (팀 레퍼런스 페이지).
매 실행 시 `get <id>`(내용)와 `get <id> --mode skeleton`(마크업 양식)으로 실제 페이지를 읽는다. 이 문서는 그 해석을 돕는 메모와 Confluence 문법이다. 둘이 다르면 **실제 참고 페이지**를 따른다.

> 이 문서의 예시(제목, 수치, 파일명, 수식)는 형식을 보여주기 위한 **가상의 값**이다. 실제 문체·수치 표현·그림 배치는 레퍼런스 페이지에서 확인하고, 그 페이지의 실제 예시를 우선한다.

**문체와 양식은 이 레퍼런스 하나로 통일한다.** 프로젝트 성격(실험, 툴, 에이전트, 분석)이 달라도 목차의 *역할*만 맞춰 바꾸고, 문체·블록 양식은 바꾸지 않는다.

## 1. 문체

- **개조식**. 불릿 + 명사형/간결체 종결: "~확인.", "~감소.", "~필요.", "~예측".
- 한국어 본문 + 영어 기술 용어 그대로 (MAE, Validation, Inlier, Fusion…). 억지 번역 금지.
- 불릿 2~3단계: 1단계 = 굵은 소제목(`<strong>실험 구성</strong>`), 2단계 = 내용, 3단계 = 근거·수치.
- "라벨 : 설명" 패턴: `<strong>Group A :</strong> 수집 조건 A 의 샘플 그룹.`
- **수치는 구체적으로**: "Baseline 대비 Metric X MAE 12.3~18.5% 감소", "Train 800 Samples | Validation 200 Samples".
- 결론에 **한계와 후속 과제**를 반드시 포함.
- 프로젝트 파일에서 확인한 사실만 쓴다. 수치를 지어내지 않는다. 불확실하면 "(확인 필요)" 로 표시하거나 뺀다.

## 2. 페이지 구성

번호 h1, 하위 `2.1`, `2.2.1`. 1번은 항상 **Introduction & Conclusion**. 레퍼런스의 4단 구성을 기본으로, 프로젝트에 맞게 섹션 이름만 바꾼다.

| # | 레퍼런스 (실험) | 역할 | 툴/에이전트 프로젝트라면 |
|---|---|---|---|
| 1 | Introduction & Conclusion | 한 화면 요약: 목적 한 줄(+관련 위키 링크) → 방법 요약 → 구성 → 검증 방향 → **Conclusion** (핵심 수치 + 한계/후속) | 목적 → 주요 기능 → 구성 → 평가 방식 → Conclusion (현재 상태, 한계, 다음 단계) |
| 2 | Experiments Models | 방법별 `2.x`: 구조도 → 입력·구조·특징 불릿 (필요 시 수식) | **Architecture**: 구성요소별 `2.x`: 구조도 → 역할·입출력 불릿 |
| 3 | Target Datasets | 데이터 표 | **Environment & Data**: 실행 환경, 입력 데이터, 설정 표 (+ 실행 명령 code 매크로) |
| 4 | Results | 지표 정의 → 실험별 `4.x`: 요약 비교 표 + 세부 그래프 expand | **Results / Evaluation**: 평가 기준 → 시나리오별 `4.x`: 결과 표 + 스크린샷/로그 expand |

결과가 아직 없는 프로젝트는 4번을 **Status & Next Steps** 로 두고 "무엇이 되고 무엇이 남았는지"를 같은 개조식으로 쓴다.

## 3. 보기 좋은 페이지 — 레퍼런스의 시각 양식

레퍼런스가 깔끔해 보이는 이유는 같은 역할의 블록이 항상 같은 모양이기 때문이다. 아래 양식을 페이지 전체에 일관되게 쓴다.

- **제목**: `<h1><strong>N. 제목</strong></h1>`, `<h2><strong>N.M 제목</strong></h2>`, h3 은 굵게 없이 `N.M.K 제목`. 번호는 실제 위치와 맞춘다.
- **방법/구성요소 섹션**: 구조도 이미지 1장 → 바로 아래 불릿으로 입력·구조·특징 설명.
- **데이터 표**: `Dataset Name | Information | Description` 3열. Information 칸은 `<p>총계</p>` + 세부 내역 `<ul>`.
- **결과 섹션**: 지표·그룹 정의(+ 평가 지표 수식) → 실험별 h2 → **해석 불릿 3~4줄** (`<strong>Method B :</strong>`, `<strong>Baseline 대비 (조건 A / B) :</strong> … % 감소` 처럼 비교 기준을 라벨에) → **수치 표** (조건별 `<p><strong>조건명</strong> (각 칸 : MAE / Mean / Std)</p>` + 표. 그룹 열은 `rowspan` 으로 묶고 `<strong>Group A</strong><br />N = 120`, 각 지표의 최고값 굵게) → 원본 캡처·스크린샷은 `… 원본 결과 캡처 펼치기....` expand → 세부 그래프 expand.
- **결과는 캡처 이미지 대신 위키 표로**. 프로젝트에 CSV/JSON 지표가 있으면 그 값으로 표를 만들고, 이미지밖에 없으면 이미지를 읽어 옮긴 뒤 원본 이미지는 expand 에 남긴다.
- **세부 그래프 expand**: 제목 `… 그래프 펼치기....`. 안에 2열 표 (`<th scope="row">` 항목명(가운데 정렬 `<p>` 두 줄: 지표 / (방법)) | 그래프 1200). 기준선·이전 방법 그래프는 그 칸 안에 다시 `… 비교하기....` expand 로 접는다.
- **표 공통**: `class="fixed-width"` (expand 안은 `fixed-width wrapped`), 머리글 `style="text-align: center;"`, `<colgroup><col style="width: …px;" />…</colgroup>` 로 열 너비 지정 (전체 폭 약 950~1650px).
- **수치 비교 표**: 가장 좋은 값을 `<strong>`. 단위는 머리글에 `MAE (deg)` 처럼.
- **그림 파일 이름**: `섹션_방법_지표_종류.png` (예: `4-1_methodB_metricX_scatter.png`, `2-2_methodB_architecture.png`).
- **그림 종류별 양식** — 그래프(결과)와 사진·개념 그림(설명)을 구분한다:
  | 종류 | 양식 |
  |---|---|
  | 구조도 (모델·시스템) | 섹션 제목 바로 아래 단독 이미지 1장 → 설명 불릿. 프로젝트에 쓸 만한 그림이 없으면 `diagram-guide.md` 로 직접 그린 SVG |
  | 결과 그래프·요약 | 해석 불릿 + 수치 표, 그래프·원본 캡처는 expand (위 "결과 섹션" 참고) |
  | **사진·개념 그림·측정 화면** (정의, 좌표·각도, 실물 사진, 화면 캡처, 전/후 비교) | **그림 패널**: 한 줄 2칸 표에 그림 두 장 (왼쪽 개념/원본 | 오른쪽 축·측정 예시/결과), 높이 250 → 바로 아래 불릿에서 "(왼쪽 그림 파란색)", "(오른쪽 그림 빨간색 축)" 처럼 그림을 짚어 설명 → 마지막에 `연관 데이터 :` 나 `출처 :` |
  | 정의 항목이 여러 개 | 항목마다 `<p><strong>항목명</strong></p>` + 그림 패널 + 불릿. 본문 흐름을 끊으면 `… 정의 펼치기....` expand 안에 |
- 그림 패널의 실제 모양은 레퍼런스 페이지 skeleton 에서 확인한다.
- 수식과 그림이 같은 개념을 다루면 **도입 → 수식 → 그림 패널 → 불릿(그림 속 수치를 식에 대입한 예시 포함)** 순서.
- **여백**: 블록 사이 간격은 제목과 문단으로 만든다. 빈 문단(`<p><br /></p>`)으로 띄우지 않는다. 이미지에 `ac:align` 을 쓰지 않는다.
- 편집기 메타데이터(`data-uuid`, `ac:macro-id`, `local-id`)는 쓰지 않는다.

## 4. Confluence storage format 문법

본문 파일은 XHTML (storage format). `&` → `&amp;`, `<` → `&lt;`. 모든 태그를 닫는다(`<br />`).

### 제목, 불릿
```xml
<h1><strong>1. Introduction &amp; Conclusion</strong></h1>
<ul>
  <li><strong>실험 구성</strong>
    <ul>
      <li><strong>Group A :</strong> 수집 조건 A 의 샘플 그룹.</li>
    </ul>
  </li>
</ul>
<h2><strong>2.1 Method A</strong></h2>
<h3>2.2.1 Method B &amp; Variant</h3>
```

### 표 (머리글 가운데 정렬)
```xml
<table class="fixed-width"><tbody>
  <tr><th style="text-align: center;">Dataset Name</th><th style="text-align: center;">Information</th><th style="text-align: center;">Description</th></tr>
  <tr><td>Dataset A (YY.MM.DD ~ YY.MM.DD)</td><td><p>sample total 1000</p><ul><li>Condition A : 900</li><li>Condition B : 100</li></ul></td><td>수집 조건과 대상 설명</td></tr>
</tbody></table>
```
결과 비교 표는 개선된 값을 `<strong>` 으로 강조.

### 이미지 (페이지 첨부파일)
```xml
<p><ac:image ac:width="800"><ri:attachment ri:filename="metric_x_scatter.png" /></ac:image></p>
```
- `ri:filename` 은 업로드할 첨부 이름과 정확히 일치해야 한다 (`--attach 경로=이름`).
- 이름은 **영문/숫자/_/- 만**, 페이지 안에서 고유하게: `exp1_metric_x_scatter.png`.
- 너비: 본문 그래프 800, 큰 대시보드형 1200, 작은 구조도 600.

### 그림 패널 (사진·개념 그림 두 장 나란히)
```xml
<table class="relative-table wrapped" style="width: 60.0%;">
  <colgroup><col style="width: 50.0%;" /><col style="width: 50.0%;" /></colgroup>
  <tbody><tr>
    <th style="vertical-align: middle;" scope="col"><div class="content-wrapper"><p><ac:image ac:height="250"><ri:attachment ri:filename="2-2-1_angle_concept.png" /></ac:image></p></div></th>
    <th style="vertical-align: middle;" scope="col"><div class="content-wrapper"><p><ac:image ac:height="250"><ri:attachment ri:filename="2-2-1_angle_example.png" /></ac:image></p></div></th>
  </tr></tbody>
</table>
<ul>
  <li>기준 방향(왼쪽 그림 파란색)과 측정 방향(빨간색) 사이의 각도.</li>
  <li>예) 오른쪽 그림 측정 방향 1.0°, 기준 방향 5.0° → θ<sub>err</sub> = 1.0 − 5.0 = <strong>−4.0°</strong>.</li>
  <li><strong>연관 데이터 :</strong> Metric X, Metric Y</li>
</ul>
```
- 그림은 `ac:height="250"` 으로 높이를 맞춘다 (너비 지정 X). 그림이 한 장뿐이면 1칸 표, `style="width: 30.0%;"`.
- 칸은 `<th>` (회색 배경으로 그림 패널이 본문 표와 구분됨). 패널 안에는 그림만, 설명은 아래 불릿에.
- 빈 칸·자투리 열(원본의 4% 폭 열)은 만들지 않는다.

### 접기 (expand) — 그래프가 많을 때
```xml
<ac:structured-macro ac:name="expand" ac:schema-version="1">
  <ac:parameter ac:name="title">Method B 그래프 펼치기....</ac:parameter>
  <ac:rich-text-body>
    <table class="fixed-width"><tbody>
      <tr><th style="text-align: center;">Metric X</th><td><ac:image ac:width="1000"><ri:attachment ri:filename="methodB_metric_x.png" /></ac:image></td></tr>
    </tbody></table>
  </ac:rich-text-body>
</ac:structured-macro>
```
참고 페이지처럼 핵심 그래프 1~2장만 본문에 두고, 나머지는 expand 안에 "항목명 | 그래프" 표로 넣는다. 제목은 `… 펼치기....` / `… 비교하기....` 형태.

### 수식 (MathJax 매크로 — 블록 전용)

실제 양식은 레퍼런스 페이지 skeleton 에서 확인한다.

**흐름: 도입 한 줄 → 수식 블록 1~2개 → 기호 풀이 불릿 → (필요 시) 수치 예시**
```xml
<p>Baseline 예측에 보정량을 더하는 Residual 구조:</p>
<ac:structured-macro ac:name="mathjax" ac:schema-version="1">
  <ac:plain-text-body><![CDATA[\hat{y} = y^{\mathrm{base}} + \Delta\hat{y}, \qquad \Delta\hat{y} = g\big(h(\mathbf{x})\big)]]></ac:plain-text-body>
</ac:structured-macro>
<ul>
  <li><strong>y<sup>base</sup> :</strong> Baseline 예측값.</li>
  <li><strong>h :</strong> 입력 x 의 Encoder. <strong>g :</strong> 보정량 Head.</li>
</ul>
<p>학습 목표는 정답 대비 Baseline 의 오차:</p>
<ac:structured-macro ac:name="mathjax" ac:schema-version="1">
  <ac:plain-text-body><![CDATA[\Delta y = y^{\mathrm{ref}} - y^{\mathrm{base}}]]></ac:plain-text-body>
</ac:structured-macro>
<ul><li>예) 4.1 조건 A, Metric X : 4.20 → 3.15 → <strong>25.0% 감소</strong>.</li></ul>
```
- **도입 한 줄** `<p>`: 무엇을 정의하는지 개조식으로, 끝은 `:`. 다음 식으로 이어갈 때도 짧은 연결 문장("역변환:", "학습 목표는 …:")을 쓴다.
- **수식 블록**: LaTeX 를 `$$` 없이 CDATA 안에 그대로. 서로 관련된 식은 한 블록에 `\qquad` 로 나란히, 짧은 주석은 `\quad(\text{+ : 부호 규약})`. 글자 기호는 `\mathrm{base}`, 벡터·행렬은 `\mathbf{x}`.
- **기호 풀이 불릿**: 식 바로 아래 `<ul>`. `<strong>기호 :</strong> 의미.` 로 식의 모든 기호를 풀고, 부호 규약·해석·구현 메모(`<code>함수명</code>`)를 덧붙인다.
- **문장 안 기호**는 매크로 대신 유니코드 + `<sub>`/`<sup>`: `ŷ`, `Δŷ`, `y<sup>base</sup>`, `h<sub>enc</sub>`, `θ<sub>err</sub>`, `σ²`, `≈`, `→`.
- **수치 예시**: 결과 표에 실제 값이 있으면 식에 대입한 예시를 하나 둔다 (지표·개선율 식).
- **어디에 넣나**: 방법 섹션(모델 구조, 입력 구성, 손실·학습 목표, 좌표·변환), 결과 섹션 맨 앞(평가 지표 정의, 개선율). 코드·노트북·논문 메모에 있는 핵심 식 위주로, 장식용 수식은 넣지 않는다.
- **정확도**: 코드나 문서에 근거가 있는 식을 우선한다. 본문 설명을 수식으로 옮긴 경우(구현과 세부가 다를 수 있음)에도 넣되, 확실하지 않은 상수·세부 연산은 `\mathrm{Ens}(\cdot)`, `g(\cdot)` 처럼 추상화해서 틀린 단정을 피한다.

### 코드
```xml
<ac:structured-macro ac:name="code" ac:schema-version="1">
  <ac:parameter ac:name="language">bash</ac:parameter>
  <ac:plain-text-body><![CDATA[python train.py --config configs/exp.yaml]]></ac:plain-text-body>
</ac:structured-macro>
```
language: `python`, `bash`, `java`, `js`, `sql`, `xml`, `yaml`, `text`. 긴 코드는 넣지 않고 핵심 명령/설정만.

### 링크
```xml
<a href="<CONFLUENCE_BASE_URL>/spaces/<SPACE_KEY>/pages/<PAGE_ID>/...">관련 페이지</a>
<ac:link><ri:page ri:content-title="관련 페이지 제목" ri:space-key="<SPACE_KEY>" /></ac:link>
```
`<CONFLUENCE_BASE_URL>`, `<SPACE_KEY>` 는 키 파일 값, 페이지 ID·제목은 `CF search` / `CF where` 로 확인한 실제 값.

### 강조 패널 (가끔만)
```xml
<ac:structured-macro ac:name="info" ac:schema-version="1"><ac:rich-text-body><p>핵심 메시지</p></ac:rich-text-body></ac:structured-macro>
```
`info` / `note` / `warning`. 레퍼런스는 패널을 쓰지 않으므로, 정말 주의가 필요한 곳에만.
