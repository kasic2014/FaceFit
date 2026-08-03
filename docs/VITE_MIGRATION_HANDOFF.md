# FaceFit Next.js → React+Vite 전환 인수인계

> 작성일: 2026-07-20  
> 작업 위치: `C:\Users\SMHRD\Documents\fafit`  
> 상태: **React+Vite 전환 완료 — Docker 런타임 검증만 로컬 Docker 부재로 미실행**

이 문서는 전환 작업 기록과 VS Code 인수인계 자료다. 코드·배포 설정·문서 전환과 품질 검사는 완료했으며, 이 환경에 Docker 명령이 없어 Nginx 컨테이너의 실제 실행만 확인하지 못했다.

## 완료 업데이트

- `npm ci`와 `npm run check`를 통과했다. ESLint는 기존 `button.tsx`의 Fast Refresh 경고 1건만 보고하며 오류는 없다.
- Vite 개발 서버 및 production preview에서 `/session/live`, `/voice-profile`, `/report` 직접 접근을 확인했다.
- 개발 서버에서 12개 기존 경로와 임의의 404 경로가 모두 SPA fallback으로 200 응답하는 것을 확인했다.
- Playwright로 브랜드 404, 면접 시작, 면접 종료 확인 모달을 확인했고, `/session/live`의 1440px·390px 스크린샷도 확인했다.
- Docker CLI와 Bash는 이 Windows 환경에 없어, Nginx 실행 검증과 `sync-agent-rules.sh`의 Bash 실행은 하지 못했다. 플랫폼별 에이전트 규칙은 스크립트의 동작과 동일하게 수동 동기화했다.

아래의 “진행해야 할 작업”은 전환 당시의 체크리스트를 보존한 것이다. 현재 남은 실질 확인 항목은 Docker/Nginx 실행 검증뿐이다.

## 1. 지금까지 진행한 작업

### 1.1 전환 전 기준선 확인

- 기존 Next.js 상태에서 `npm run check`가 통과하는 것을 확인했다.
- 기존 12개 화면 경로와 Next.js 정적 빌드 결과를 확인했다.
- API Route, Server Action, 핵심 SSR 의존성이 없는 클라이언트 중심 프로토타입임을 확인했다.

### 1.2 패키지와 실행 명령 전환

- `next`, `eslint-config-next`를 제거했다.
- 다음 Vite/React Router/ESLint 패키지를 추가 또는 갱신했다.
  - `vite`
  - `@vitejs/plugin-react`
  - `react-router-dom`
  - `@eslint/js`
  - `typescript-eslint`
  - `eslint-plugin-react-hooks`
  - `eslint-plugin-react-refresh`
  - `globals`
- `package.json` 명령을 Vite 기준으로 변경했다.
  - `npm run dev`: Vite 개발 서버
  - `npm run build`: `tsc -b && vite build`
  - `npm run preview`, `npm start`: Vite preview
  - `npm run typecheck`: TypeScript project build 검사
  - `npm run check`: lint → typecheck → build
- `package-lock.json`이 새 의존성 기준으로 갱신됐다.

### 1.3 Vite·TypeScript·ESLint 기본 구성

다음 파일을 추가 또는 변경했다.

- `vite.config.ts`
  - React 플러그인
  - `@` → `src` 별칭
  - 개발/preview 포트 `3000`
- `tsconfig.json`
  - 앱/설정 파일용 project reference로 변경
- `tsconfig.app.json`
- `tsconfig.node.json`
- `eslint.config.mjs`
  - Next.js ESLint 설정 대신 React Hooks/React Refresh/TypeScript flat config 적용
- `index.html`
  - `lang="ko"`, 제목, 설명, Open Graph 메타데이터
  - Space Grotesk와 Pretendard 폰트 로딩
  - `/src/main.tsx` 진입점
- `.gitignore`
  - Next.js 전용 ignore 항목 제거
- `next.config.ts`, `next-env.d.ts` 삭제
- `components.json`
  - `rsc: false`
  - CSS 경로를 `src/index.css`로 변경

### 1.4 React Router 애플리케이션 골격

- `src/main.tsx`를 추가하고 `StrictMode`, `BrowserRouter`, 전역 CSS를 초기화했다.
- `src/App.tsx`를 추가하고 다음 경로를 연결했다.
  - `/`
  - `/login`
  - `/signup`
  - `/onboarding`
  - `/equipment`
  - `/voice-profile`
  - `/session/live`
  - `/analysis`
  - `/report`
  - `/dashboard`
  - `/pricing`
  - `/design-preview`
  - `*` 브랜드형 404
- `PrototypeFeedback`을 모든 라우트 밖의 공통 UI로 유지했다.
- `src/pages/NotFoundPage.tsx`를 추가했다.

### 1.5 페이지 이동과 내부 링크 일부 전환

- `src/app/**/page.tsx`의 12개 화면을 `src/pages/*Page.tsx`로 이동했다.
- 이동한 페이지의 `"use client"`를 제거했다.
- 다수의 `next/link`를 React Router의 `Link`와 `to` 속성으로 변경했다.
- `Footer`, `LandingHeader`, `States`의 내부 링크를 일부 정리했다.
  - 내부 경로: React Router `Link`
  - `mailto:`, 같은 페이지 해시: 일반 `<a href>`

### 1.6 이미지·전역 CSS 일부 전환

- `src/app/globals.css`를 `src/index.css`로 이동했다.
- 제목 폰트 변수를 `Space Grotesk` 일반 웹폰트 기준으로 변경했다.
- `html`, `body`, `#root`의 최소 높이를 유지했다.
- 확인된 `next/image` 사용처를 일반 `<img>`로 변경했다.
  - fill 이미지는 기존 absolute 레이아웃 유지
  - 우선 이미지는 `loading="eager"`, `fetchPriority="high"`
  - 나머지는 lazy loading

## 2. 아직 진행해야 할 작업

### 2.1 Next.js 잔여 코드 제거

현재 아래 항목이 남아 있다.

- 여러 컴포넌트 첫 줄의 `"use client"`
- `Dockerfile`, `Dockerfile.dev`, `docker-compose.yml`의 `.next`, `NEXT_TELEMETRY` 참조
- 전환 전 빌드가 만든 루트 `.next/` 디렉터리
- `src/app/favicon.ico`와 비어 있는 `src/app/` 디렉터리 구조

처리 방법:

1. 모든 `"use client"` 지시문을 제거한다.
2. `src/app/favicon.ico`를 `public/favicon.ico`로 이동한다.
3. 비어 있는 `src/app/` 디렉터리를 제거한다.
4. 루트 `.next/`는 생성물임을 확인한 뒤 제거한다.
5. 다음 검색 결과가 코드·운영 설정에서 0건인지 확인한다.

```powershell
rg -n 'next/|"use client"|\.next|NEXT_PUBLIC_|NEXT_TELEMETRY' src package.json tsconfig*.json vite.config.ts eslint.config.mjs components.json Dockerfile Dockerfile.dev docker-compose.yml vercel.json
```

### 2.2 링크·이미지 전수 점검

- `<Link href=...>` 또는 내부 경로용 `<a href="/...">`가 남았는지 확인한다.
- 외부 URL, `mailto:`, 같은 페이지 앵커만 `<a href>`로 유지한다.
- `next/image`, `<Image>`가 0건인지 확인한다.
- `<img>` 변환 후 비율, overlay, `object-cover`, 부모 `relative`가 유지되는지 확인한다.

권장 검색:

```powershell
rg -n 'next/link|next/image|<Image|<Link[^>]+href=|<a[^>]+href="/' src
```

### 2.3 배포 설정 전환

#### Vercel

`vercel.json`을 다음 기준으로 변경한다.

- framework: Vite
- build command: `npm run build`
- output directory: `dist`
- 모든 SPA 직접 접근을 `/index.html`로 rewrite

#### 운영 Docker

- Node 24 빌드 단계에서 `npm ci`, `npm run build`
- Nginx 정적 배포 단계에서 `dist` 제공
- `nginx.conf` 추가
  - `try_files $uri $uri/ /index.html`
  - 해시 정적 자산 장기 캐시
  - `index.html` no-cache
- 운영 컨테이너 내부 포트는 `80`

#### 개발 Docker

- Node 24 기반
- Vite를 `0.0.0.0:3000`으로 실행
- `.next` volume과 Next telemetry 환경변수 제거
- 기존 호스트 포트 체계는 유지

### 2.4 문서와 에이전트 규칙 동기화

- `README.md`의 프레임워크, 실행, 빌드, Vercel, Docker, 프로젝트 구조를 Vite 기준으로 수정한다.
- `AGENTS.md`의 Next.js 전용 규칙과 `src/app` 구조를 React+Vite 기준으로 변경한다.
- `AGENTS.md` 수정 후 반드시 실행한다.

```bash
bash scripts/sync-agent-rules.sh
```

- `docs/product/`에서 현재 상태를 “Next.js 프로토타입”이 아니라 “React+Vite 전환 완료”로 갱신한다.
- OpenAvatarChat + MuseTalk 실시간 면접관 연동 계약은 이번 전환에서 변경하지 않는다.
- 기존 미커밋 `README.md`, `docs/product/` 변경은 사용자 산출물이므로 덮어쓰거나 되돌리지 않는다.

### 2.5 정적 검사와 빌드 오류 수정

현재 Vite 전환 후 검사는 아직 실행하지 않았다. 잔여 코드 정리 뒤 다음 순서로 실행한다.

```powershell
npm ci
npm run lint
npm run typecheck
npm run build
npm run check
```

주의:

- `npm install` 결과 audit 경고가 있었지만 자동 `npm audit fix`는 실행하지 않았다.
- React Router 설치 버전은 현재 `7.18.1`이며, 코드에서는 호환되는 declarative API(`BrowserRouter`, `Routes`, `Route`, `Link`)를 사용한다.
- `package.json`/설정 파일의 줄바꿈이 일부 혼재할 수 있으므로 `git diff --check`도 실행한다.

### 2.6 브라우저 회귀 검증

Vite 개발 서버와 production preview에서 아래를 확인한다.

```powershell
npm run dev
# 별도 터미널
npm run preview
```

검증 대상:

- 12개 기존 경로와 임의의 404 경로
- 주소창 직접 접근, 내부 링크 이동, 새로고침
- `/session/live`, `/voice-profile`, `/report` 직접 접근
- 온보딩 선택·취소 모달
- 장치 선택·카메라 미리보기 목업
- 음성 프로필 녹음 단계·건너뛰기
- 면접 온보딩·답변 완료·Space·종료 모달
- 분석 단계·나중에 확인하기
- 리포트 탭·음성 재생·대시보드 이동
- 1440px와 390px 레이아웃
- 이미지 비율, overlay, 폰트 줄바꿈, 전역 스타일

### 2.7 Docker 검증

Docker daemon이 사용 가능하면 다음을 검증한다.

1. production 이미지 빌드
2. Nginx 컨테이너 실행
3. `/session/live`, `/voice-profile`, `/report` 직접 요청이 200인지 확인
4. 정적 자산 캐시 헤더와 SPA fallback 확인
5. 테스트용 컨테이너만 정확한 이름으로 종료·삭제

Vercel 배포 자체는 이번 작업 범위가 아니며, `vercel.json` 정적 설정까지만 검증한다.

## 3. VS Code 권장 작업 순서

1. VS Code에서 `C:\Users\SMHRD\Documents\fafit`를 연다.
2. Source Control에서 기존 미커밋 파일을 확인하고 사용자 문서 변경을 보존한다.
3. Next.js 잔여 지시문·파일·생성물을 제거한다.
4. 링크와 이미지 변환을 전수 검색한다.
5. Vercel/Docker/Nginx 설정을 전환한다.
6. README, AGENTS, 제품 문서를 동기화한다.
7. `npm ci` 후 `npm run check`를 통과시킨다.
8. 개발 서버와 production preview에서 전체 경로와 상호작용을 검증한다.
9. 가능하면 Docker/Nginx 직접 경로 접근을 검증한다.
10. 마지막으로 아래 명령으로 변경 범위와 잔여 흔적을 확인한다.

```powershell
git status --short
git diff --check
rg -n 'next/|"use client"|\.next|NEXT_PUBLIC_|NEXT_TELEMETRY' src package.json tsconfig*.json vite.config.ts eslint.config.mjs components.json Dockerfile Dockerfile.dev docker-compose.yml vercel.json
```

## 4. 완료 조건

- `npm ci` 및 `npm run check` 통과
- 12개 화면과 브랜드 404가 직접 URL·내부 링크·새로고침에서 정상
- production `dist`가 정적 서버와 Nginx에서 정상
- Vercel SPA rewrite와 Docker SPA fallback 구성 완료
- 코드·운영 설정의 Next.js 전용 참조 0건
- README, AGENTS, 제품 산출물의 현재 상태가 React+Vite로 일치
- 기존 기능·디자인·URL·OpenAvatarChat/MuseTalk 연동 계약에 의도하지 않은 변경 없음

## 5. 현재 워크트리 주의사항

- 현재 변경사항은 아직 커밋하거나 stage하지 않았다.
- `README.md`와 `docs/product/`에는 전환 전부터 진행하던 사용자 산출물 수정이 포함되어 있다.
- `.next/`는 `.gitignore` 변경 때문에 현재 untracked로 보이며, 소스가 아닌 기존 Next.js 빌드 생성물이다.
- 전환 후 `npm run check`를 아직 실행하지 않았으므로, 타입·lint·빌드 오류가 남아 있을 수 있다.
- 삭제로 보이는 `src/app/**/page.tsx`는 대응하는 `src/pages/*Page.tsx`로 이동 중인 파일이다.
