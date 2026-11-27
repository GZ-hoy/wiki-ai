# GZ-airesearch-wiki

Claude Code에서 작업한 프로젝트 디렉토리(코드, 실험 결과, 그래프, 노트)를 분석해서 **AI Research Confluence 위키**(docs.golfzon.company)에 정리 페이지로 올려주는 플러그인입니다. 정리 스타일은 팀 레퍼런스 페이지(키 파일의 `CONFLUENCE_TEMPLATE_PAGE_ID`)를 실행할 때마다 위키에서 읽어 따르고, MathJax 수식, 그래프 첨부, 접기(expand) 매크로를 지원합니다.

## 요구 사항

- **Claude Code** 최신 버전 (`claude update`), 터미널·VS Code 확장 모두 가능
- **Python 3.9 이상** (`python3` 명령으로 실행됨, 추가 패키지 없음)
- **git**, 그리고 `github.com` 접속 (공개 저장소라 로그인 불필요)
- 사내망에서 `https://docs.golfzon.company` 접속 가능
- Confluence 권한: 레퍼런스 페이지(161383239) **보기**, 올릴 스페이스 **편집**
- 웹 검토 화면: 로컬 PC면 기본 브라우저, VS Code 원격(SSH)이면 VS Code가 포트를 자동 연결해 PC 브라우저로 열림

## 설치

Claude Code 대화창(터미널·VS Code 모두)에 아래 문장을 그대로 붙여넣으면 Claude가 설치해 줍니다.

```
GZ-airesearch-wiki 플러그인 설치해줘. 마켓플레이스는 https://github.com/GZ-hoy/wiki-ai 이고, 플러그인은 GZ-airesearch-wiki@gz-airesearch 야. claude가 PATH에 없으면 ~/.local/bin이나 VS Code 확장 폴더에서 찾아서 실행해줘.
```

- 설치한 뒤 Claude Code를 **재시작**(새 세션, VS Code는 `Ctrl+Shift+P` → `Developer: Reload Window`)해야 `/wiki-ai`가 보입니다. 자동완성에는 `/GZ-airesearch-wiki:wiki-ai` 로 보일 수도 있습니다.

<details>
<summary>직접 명령으로 설치하기</summary>

터미널(bash, PowerShell)에서:

```bash
claude plugin marketplace add GZ-hoy/wiki-ai
claude plugin install GZ-airesearch-wiki@gz-airesearch
```

- `claude: command not found` 이면 `~/.local/bin/claude`(Windows는 `~/.local/bin/claude.exe`)처럼 전체 경로로 실행합니다.
- `/plugin …` 슬래시 명령은 터미널용 Claude Code 안에서만 동작합니다. VS Code 대화창에서는 "/plugin isn't available in this environment"가 뜨고, bash에 직접 치면 `No such file or directory`가 뜹니다.

</details>

### 업데이트

대화창에 붙여넣기:

```
GZ-airesearch-wiki 플러그인 최신 버전으로 업데이트해줘. 마켓플레이스 gz-airesearch 를 갱신한 다음 GZ-airesearch-wiki@gz-airesearch 를 업데이트하면 돼. claude가 PATH에 없으면 ~/.local/bin이나 VS Code 확장 폴더에서 찾아서 실행해줘.
```

직접 명령으로는 `claude plugin marketplace update gz-airesearch` → `claude plugin update GZ-airesearch-wiki@gz-airesearch`. 그 다음 재시작합니다. 현재 버전은 `claude plugin list` 로 확인합니다.

## 개인 설정 (최초 1회)

토큰과 업로드 위치는 사람마다 다르므로 각자 키 파일을 만듭니다.

1. Confluence 우측 상단 프로필 → **설정 → 개인 액세스 토큰 → 토큰 만들기**에서 토큰을 발급합니다.
2. 키 파일을 만듭니다. `/wiki-ai`를 처음 실행하면 템플릿이 자동으로 생성되고, 직접 만들어도 됩니다.
   ```bash
   mkdir -p ~/.config/gz-airesearch-wiki
   cp key.example ~/.config/gz-airesearch-wiki/key
   chmod 600 ~/.config/gz-airesearch-wiki/key
   ```
3. 값을 채웁니다.

| 변수 | 설명 |
|---|---|
| `CONFLUENCE_BASE_URL` | `https://docs.golfzon.company` |
| `CONFLUENCE_API_TOKEN` | 1번에서 발급한 개인 액세스 토큰 |
| `CONFLUENCE_EMAIL` | 비워두세요 (Atlassian Cloud일 때만 사용) |
| `CONFLUENCE_SPACE_KEY` | `airesearch` |
| `CONFLUENCE_TEMPLATE_PAGE_ID` | 스타일 레퍼런스 페이지 ID (기본 161383239). 팀 스타일 통일을 위해 바꾸지 않는 것을 권장 |

키 파일 위치를 바꾸려면 환경변수 `GZ_WIKI_KEY_FILE=/경로/파일`을 지정합니다.

## 사용법

정리하고 싶은 프로젝트 디렉토리에서 Claude Code를 열고 실행합니다.

```
/wiki-ai
/wiki-ai 결과 섹션 위주로, 수식 자세히
/wiki-ai OO 프로젝트 페이지 아래에 올려줘
/wiki-ai https://docs.golfzon.company/spaces/airesearch/pages/123456/다른부모 제목은 OO 모델 v2
/wiki-ai ~/projects/my-project
```

1. 참고 페이지의 내용과 실제 양식(뼈대)을 읽고 스타일 카드(`.wiki-ai/style-card.md`)를 정리한 뒤, 프로젝트를 분석해서 초안을 `.wiki-ai/page.xhtml`에 작성합니다. 작성 후 참고 페이지와 나란히 비교하는 자체 검토를 거칩니다.
2. **작성 방향 질문**: 분석 결과를 바탕으로 무엇을 강조할지(핵심 메시지, 깊이, 뺄 것)를 먼저 묻고, 그 방향으로 씁니다.
3. **검수**: 초안과 함께 **근거 장부**(주장·수치마다 파일:줄 / 계산 / 추론 표시)를 만들고 → 자동 검사(근거 없는 수치, 민감 정보, 위키 대비 변경점) → **독립 검수 에이전트**(초안과 프로젝트만 보고 사실·과장·누락 지적) → 지적은 **Claude가 직접 고치고**, 파일로 확정할 수 없거나 작성자가 정할 것만 **의문점**으로 남깁니다(0~5개).
4. **사람 검수 (웹)**: 검토용 웹 화면이 브라우저에 바로 열립니다(VS Code 원격이면 포트 자동 연결). 페이지 전체를 읽으면서 문장을 드래그해 💬 수정 요청을 남기고, 의문점은 댓글의 선택지로 답하고, **검수 완료**를 누르면 Claude가 바로 반영하고 화면이 자동으로 새로 고쳐집니다. 의견 없이 검수 완료를 누르면 업로드 단계로 넘어갑니다.
5. **업로드 위치를 고릅니다**: 기본 위치는 없습니다. 프로젝트 키워드로 관련 페이지가 모인 곳, 최근 올린 곳, 최근 작업한 곳을 근거와 함께 추천하고, 그중 고르거나 URL·페이지 이름을 직접 입력합니다. 제목도 이때 확인합니다.
6. 형식 검증(서버 변환 검사 포함) 후, 업로드 전에 **최종 경로, 목차, 첨부, 검수 상태를 보여주며 확인을 받습니다**. 남은 의문점이 있거나, 전체를 읽지 않았거나, 검수 후 초안이 바뀌었으면 경고하고(진행은 가능) 검수 상태를 `state.json`에 기록합니다.
7. 확인하면 고른 위치 아래에 새 페이지를 만들거나 기존 페이지를 업데이트합니다. 업데이트할 때 다른 위치를 고르면 페이지가 이동합니다.

- 같은 프로젝트에서 다시 실행하면 **같은 페이지를 업데이트**합니다. 페이지 정보는 `.wiki-ai/state.json`에 저장되고, 이 폴더는 git에서 자동으로 무시됩니다.
- 위키에서 사람이 직접 고친 내용이 있으면 덮어쓰기 전에 알려주고, 그 내용을 반영할지 묻습니다.
- 그래프는 변경된 파일만 다시 업로드합니다.

## 문제 해결

| 증상 | 확인 |
|---|---|
| `/wiki-ai` 가 안 보임 | 설치 후 재시작했는지, `claude plugin list` 에 enabled 인지 |
| 인증 실패 / anonymous | 키 파일의 토큰(PAT) 만료 여부. `python3 <플러그인>/skills/wiki-ai/scripts/confluence.py check` |
| 업로드 시 HTTP 403 | 고른 위치(스페이스)에 편집 권한이 없음 → 다른 위치 선택 |
| 검토 화면이 안 열림 | 채팅에 나온 `http://localhost:<포트>/` 를 직접 열기. VS Code 원격이면 하단 "포트" 탭에서 해당 포트 열기 |
| 검토 화면이 "반영 중"에서 멈춤 | F5(새로고침) |
| 수식이 안 보임 | 브라우저가 MathJax(cdn.jsdelivr.net)를 받을 수 있는지. 위키 업로드에는 영향 없음 |

## 관리자: 새 버전 배포

1. 수정 후 **`.claude-plugin/plugin.json` 과 `marketplace.json` 의 `version` 을 함께 올립니다** (같지 않으면 팀원 쪽에서 업데이트로 인식하지 않음).
2. `claude plugin validate .` 로 검사.
3. 커밋·푸시. 원하면 `claude plugin tag .` 로 `GZ-airesearch-wiki--v<버전>` 태그.
4. 팀원에게 "업데이트" 명령과 바뀐 점을 공지.

## 구성

```
.claude-plugin/plugin.json        플러그인 정의 (이름·버전)
.claude-plugin/marketplace.json   팀 마켓플레이스 정의 (gz-airesearch)
skills/wiki-ai/SKILL.md           /wiki-ai 작업 절차
skills/wiki-ai/reference/style-guide.md      작성 규칙, Confluence 문법 (MathJax, expand, 표, 이미지, 그림 패널)
skills/wiki-ai/reference/reviewer-prompt.md  독립 검수 에이전트 지시문
skills/wiki-ai/reference/review-format.md    검수 기록(review.json)·웹 의견(feedback.json) 형식
skills/wiki-ai/scripts/confluence.py         Confluence REST·검사·미리보기·검토 서버 (Python 표준 라이브러리만 사용)
key.example                        개인 키 파일 템플릿
```

`confluence.py`는 직접 실행할 수도 있습니다: `check`, `templates`, `suggest --keywords …`, `check-draft`, `serve`, `feedback`, `preview`, `review-stamp`, `review-mark`, `search <키워드>`, `where <URL|ID>`, `get <URL|ID|template> [--mode text|skeleton]`, `render <초안>`, `find --title`, `validate`, `publish --dry-run`
