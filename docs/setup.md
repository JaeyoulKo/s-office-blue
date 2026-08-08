# 설치 — 처음부터 끝까지

Windows 기준. 각 단계마다 **검증 명령**이 있다. 그게 통과해야 다음으로 넘어간다.
막히면 넘어가지 말고 물어보는 편이 빠르다.

## 0. 준비물

| | 확인 | 없으면 |
| --- | --- | --- |
| git | `git --version` | https://git-scm.com/download/win |
| Codex CLI | `codex --version` (0.147.0 이상) | https://developers.openai.com/codex/cli |
| Python | `python --version` (3.10 이상) | 아래 1단계 |

> **함정**: Windows에서 `python`을 치면 Microsoft Store 창이 뜨거나 아무것도 안 나오는 경우가
> 많다. 그건 진짜 Python이 아니라 스토어 안내용 껍데기다. `python --version`이 버전 번호를
> 출력하지 않으면 설치가 안 된 것이다.

## 1. Python 설치

```powershell
winget install --id Python.Python.3.12 --scope user `
  --silent --accept-package-agreements --accept-source-agreements
```

설치 후 **PowerShell 창을 새로 연다.** (PATH가 새 창에만 반영된다.)

```powershell
python --version        # Python 3.12.x 가 나와야 한다
```

`winget`이 없거나 실패하면 https://www.python.org/downloads/ 에서 받아 설치한다.
설치 화면에서 **`Add python.exe to PATH` 체크를 반드시 켠다.**

## 2. 저장소 받기

```powershell
cd C:\dev
git clone https://github.com/JaeyoulKo/s-office-blue.git
cd s-office-blue
```

## 3. 가상환경과 의존성

가상환경(venv)은 이 프로젝트 전용 Python 방이다. 다른 프로젝트와 패키지가 섞이지 않는다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[ui,dev]"
```

`Activate.ps1` 실행이 막히면 (`이 시스템에서 스크립트를 실행할 수 없으므로`):

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

**검증** — 프롬프트 앞에 `(.venv)`가 붙어 있어야 한다.

```powershell
pytest -q               # 23 passed 가 나와야 한다
```

> 이후 새 터미널을 열 때마다 `.\.venv\Scripts\Activate.ps1`를 먼저 실행한다.
> 안 하면 `ModuleNotFoundError`가 난다.

## 4. Gmail 없이 전 과정 돌려보기

**Gmail 인증 없이도 여기까지 전부 동작한다.** 먼저 이걸 통과시키고 Gmail로 넘어간다.

```powershell
python -m experiments.seed_gmail --mode fixture
python -m experiments.ablation --arms A0,A3 --reps 1
```

몇 분 걸린다. 끝나면 `experiments/runs/<run-id>/report.md`가 생긴다.

```powershell
streamlit run ui/app.py
```

브라우저가 열리면 ① 수집 → ② 실행 → ③ 비교 순으로 눌러본다.

**여기까지 되면 개발 준비는 끝이다.** Gmail은 실메일로 실험할 때만 필요하다.

## 5. Codex 동작 확인

```powershell
codex --version
codex mcp list          # 연결된 MCP 서버와 인증 상태
```

`codex exec`가 실패하면 대개 둘 중 하나다.

- 로그인이 안 됐다 → `codex login`
- PATH에 필수 디렉터리가 없다 → `codex doctor`

## 6. Gmail 연결 (실메일 실험용)

**경로가 두 개 있고 서로 인증을 공유하지 않는다.** 어느 쪽을 표준으로 할지는 아직
정하지 않았으므로, 이미 붙여둔 쪽이 있으면 그것을 쓰고 팀에 알린다.

### 경로 A · OpenAI Gmail 커넥터 (설정이 간단하다)

Codex 설정에서 Gmail 커넥터를 켜고 OAuth로 연결한다. GCP 프로젝트나 OAuth 클라이언트를
직접 만들 필요가 없다. 도구 이름은 `mcp__codex_apps__gmail_*`이고 **읽기 전용**이다.

### 경로 B · 로컬 Gmail MCP 서버 (초안 생성까지 된다)

`~/.codex/mcp/gmail-local/server.mjs`를 stdio MCP 서버로 등록한다. 도구는
`search_threads`, `get_thread`, `list_drafts`, `list_labels`, `create_draft` 다섯 개이고
**발송·삭제·라벨 변경 도구는 존재하지 않는다.**

1인당 GCP 프로젝트와 OAuth 데스크톱 클라이언트를 만들어야 하고, 앱이 테스트 모드면
**refresh token이 7일마다 만료**되어 주기적으로 다시 로그인해야 한다.

### 어느 쪽이든 — 검증은 이것부터

**메일 본문을 읽지 않는 호출로 먼저 확인한다.**

```powershell
codex mcp list
# 그다음 codex 대화형 세션에서 list_labels 만 호출해 본다
```

`Transport send error: Auth required`가 나오면 그 경로의 인증이 안 된 것이다.
**다른 경로의 인증을 다시 해도 해결되지 않는다.** 두 경로는 OAuth를 공유하지 않는다.
`git clone`만으로 인증이 따라오지도 않는다.

### 실메일로 실험하기

```powershell
python -m experiments.ablation --collect connector --query "in:inbox is:unread newer_than:7d"
```

## 7. (선택) 가짜 메일 주입

실제 Gmail 메일함에 **정답이 붙은 실험용 메일**을 넣어 정확도를 재고 싶을 때만 한다.

```powershell
pip install google-api-python-client google-auth-oauthlib
$env:OFFICEBLUE_SEED_CLIENT_SECRET = "C:\path\client_secret.json"

python -m experiments.seed_gmail --mode insert --label OFFICEBLUE-TEST
python -m experiments.ablation --collect connector --query "label:OFFICEBLUE-TEST is:unread"
python -m experiments.seed_gmail --cleanup     # 끝나면 반드시 회수
```

이 스크립트는 이 저장소에서 유일하게 쓰기를 하고, **사람이 직접 실행한다.**
에이전트에게 도구로 주지 않으며 자격증명도 분리한다. ([AGENTS.md](../AGENTS.md))

`--mode insert`는 메일을 **발송하지 않고** 메일함에 직접 넣는다. 그래서 발신인을 CFO 등으로
자유롭게 재현할 수 있고 스팸 필터에도 걸리지 않는다. 앱 비밀번호만 있으면 되는 `--mode smtp`도
있지만, 발신인이 전부 본인이 되어 발신인 규칙 케이스가 검증되지 않는다.

## 자주 막히는 곳

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| `python`이 스토어를 연다 | 진짜 Python 미설치 | 1단계 |
| `ModuleNotFoundError: harness` | venv 활성화 안 함 | `.\.venv\Scripts\Activate.ps1` |
| `Activate.ps1 실행 불가` | 실행 정책 | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `codex 실행 파일을 찾을 수 없습니다` | PATH | 새 터미널, 그래도 안 되면 `codex doctor` |
| `Transport send error: Auth required` | 해당 Gmail 경로 미인증 | 6단계. 다른 경로 재인증은 소용없다 |
| `400 invalid_json_schema` | 스키마에 선택 필드가 있다 | 모든 `properties` 키를 `required`에 넣는다 |
| 결과 파일이 안 생김 | codex 실행 실패 | `experiments/runs/<id>/<arm>/rep-N/stdout.log` 확인 |

## git — 멘티용 5개 명령

```powershell
git checkout main; git pull            # 1. 최신으로 맞춘다
git checkout -b task/04-skill-classify # 2. 내 브랜치를 판다 (docs/tasks.md 참고)
git add .; git commit -m "무엇을 했는지"  # 3. 저장한다
git push -u origin task/04-skill-classify  # 4. 올린다
#                                        5. GitHub에서 Pull Request 를 연다
```

규칙 셋.

- **`main`에 직접 push하지 않는다.** 항상 브랜치 → PR → mentor 병합.
- **내 task의 소유 경로만 건드린다.** 남의 경로를 고쳐야 하면 먼저 말한다.
- **`experiments/runs/`가 커밋되지 않았는지 확인한다.** `git status`에 안 보이는 게 정상이다.
  보인다면 `.gitignore`가 깨진 것이니 커밋하지 말고 알린다.
