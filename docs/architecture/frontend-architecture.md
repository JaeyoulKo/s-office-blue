# 프런트엔드 아키텍처

## 목적

office-blue의 화면, 업무 기능, 외부 연동, 디자인 시스템을 분리해 여러 팀원이 같은
저장소에서 독립적으로 개발할 수 있게 한다. 스토리보드는 업무 흐름의 원본이고, 이
문서는 그 흐름을 코드로 배치하는 규칙이다.

현재 단계에서는 구조를 문서로 확정한다. 실제 Next.js, TypeScript, TSX 파일은 화면
구현을 시작할 때 이 계약에 맞춰 생성하고 Git으로 계속 관리한다. Skill을 실행할 때마다
소스 파일을 새로 생성하거나 초기화하지 않는다.

## 기술 방향

- 웹 프레임워크: Next.js App Router와 TypeScript
- 스타일: 디자인 토큰 기반 CSS. 구체적인 도구는 구현 시작 시 결정
- 서버 상태: 기능별 query/service 계층에서 관리
- 폼과 검증: 기능 폴더 안에서 스키마와 UI를 함께 관리
- 외부 연동: React 컴포넌트에서 MCP 도구를 직접 호출하지 않음
- 업무 규칙: Skill과 업무 문서를 기준으로 하며 UI에 중복 정의하지 않음

## 목표 디렉터리 구조

office-blue는 현재 하나의 웹앱이므로 모노레포 구조를 사용하지 않는다. 아래 구조도
처음부터 전부 만들지 않고 실제 화면을 구현할 때 필요한 폴더와 파일만 추가한다.

```text
office-blue/
├── app/                                 # 실제 페이지
│   ├── layout.tsx
│   ├── page.tsx                         # 시작 화면
│   ├── briefing/page.tsx                # 메일 브리핑
│   ├── reviews/[reviewId]/page.tsx      # 검토 화면
│   └── settings/integrations/page.tsx   # 연결 상태
├── features/                            # 화면별 업무 기능
│   ├── mail-briefing/
│   ├── purchase-approval/
│   └── discussion-email/
├── components/                          # 여러 화면이 함께 쓰는 부품
│   ├── ui/
│   └── layout/
├── lib/
│   └── integrations/                    # Gmail 등 외부 연결
├── styles/                              # 공통 색상과 화면 스타일
├── docs/
│   ├── architecture/
│   ├── design-system/
│   ├── screens/                         # 화면별 명세
│   └── storyboard/                      # 원본 사용자 흐름
└── .agents/
    └── skills/                          # 반복 가능한 업무 절차
```

지금 문서에 표시한 라우트와 기능 폴더는 파일이 놓일 자리를 설명한다. 모든 화면의 빈
파일을 미리 만들지는 않는다.

## 계층별 책임

### `app`

- URL과 레이아웃을 정의한다.
- 기능 컴포넌트를 조립하고 페이지 메타데이터를 제공한다.
- 업무 판단, Gmail 응답 변환, 복잡한 상태 관리를 작성하지 않는다.

### `features`

- 사용자가 수행하는 하나의 업무 기능을 소유한다.
- 기능 전용 컴포넌트, 상태, 스키마, 타입, 테스트를 함께 둔다.
- 다른 기능의 내부 파일을 직접 가져오지 않는다.
- 외부에 공개할 항목은 각 기능의 `index.ts`에서만 노출한다.

권장 기능 내부 구조는 다음과 같다.

```text
features/mail-briefing/
├── components/
├── model/
├── schemas/
├── services/
├── tests/
└── index.ts
```

### `components/ui`

- Button, Input, Select, Card처럼 업무 의미가 없는 기본 요소를 둔다.
- Gmail, 구매, 승인 같은 업무 용어를 사용하지 않는다.
- 디자인 토큰만 사용하며 기능별 색상이나 임의 값을 포함하지 않는다.

### `components/patterns`

- PageHeader, WorkflowStepper, ReviewChecklist처럼 두 개 이상의 기능에서 반복되는 조합을
  둔다.
- 특정 기능에서만 사용하는 조합은 해당 `features` 폴더에 둔다.

### `lib/integrations`

- Gmail MCP 결과를 앱 내부 타입으로 변환하는 경계다.
- UI가 MCP 도구명, 메시지 ID 형식, 공급자별 응답 구조에 의존하지 않게 한다.
- 읽기와 쓰기 기능을 구분하고 쓰기 작업은 명시적 승인 경계를 유지한다.

## 의존성 방향

```text
app
 ├── features
 ├── components/patterns
 └── components/ui

features
 ├── components/patterns
 ├── components/ui
 └── lib/integrations

components/ui
 └── design-system
```

반대 방향의 참조는 허용하지 않는다. 특히 디자인 시스템이나 공통 UI가 특정 기능을
가져오면 안 된다.

## 파일 생성 원칙

1. 화면 명세가 승인되기 전에는 `page.tsx`를 만들지 않는다.
2. 실제 URL이 필요한 경우에만 페이지를 만든다.
3. 한 화면 내부의 로딩, 빈 결과, 오류, 확인 단계는 별도 페이지 대신 상태로 구현한다.
4. 두 곳 이상에서 실제로 반복된 UI만 공통 컴포넌트로 승격한다.
5. 공통화 가능성을 예상했다는 이유만으로 추상 컴포넌트를 먼저 만들지 않는다.
6. 문서와 코드는 같은 PR에서 함께 갱신한다.
7. 기존 코드를 유지하며 필요한 부분만 수정하고 매 작업마다 재생성하지 않는다.
