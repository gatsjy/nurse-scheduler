# 간호사 근무표 자동 생성기 (Nurse Scheduler)

병동 간호사(3교대) 월간 근무표를 **제약 최적화(OR-Tools CP-SAT)** 로 자동 생성·관리하는 Windows 데스크탑 앱.
실제 병동 운영 규칙(연차·프리셉터·나이트 전담·듀티 퍼스트 등)을 반영해, 버튼 한 번으로
규칙을 지키는 근무표를 만든다.

> **모든 근무 배정 규칙**은 [`SCHEDULING_RULES.md`](SCHEDULING_RULES.md)에 정리되어 있다.
> (하드/소프트 규칙, 가중치, 설정값 전체)
> **최근 변경 이력**은 [`CHANGELOG.md`](CHANGELOG.md) 참고.

---

## 주요 기능

- **자동 생성**: D(낮)/E(저녁)/N(밤)/O(휴무) 3교대 월간 근무표를 규칙에 맞춰 생성 (진행창 + **생성 중지** 버튼)
- **직군 분리**: RN(간호사) / NA&HA(간호조무사·보조인력)를 각각 편성
- **실제 병동 규칙 반영** (요약, 상세는 규칙 문서 참고)
  - 요일유형별 필요 인원(주말·공휴일 vs 평일), 전월 이월(월 경계 연속성)
  - 월 오프 목표, 연속 야간/근무 제한, 야간 후 의무 휴무, 야간 텀(블록 간격)
  - 연차별 야간 분배(고연차 적게), 듀티 퍼스트(각 교대 책임자), 스킬믹스
  - 프리셉터-프리셉티 근무 일치, 갑계장 야간 제외, 나이트 전담(NN-OO)
  - 퐁당퐁당 방지, D→E→N/5연속근무 회피
- **관리 기능**: 간호사(사번·직군·직책·등급·프리셉터·전담), 팀(연차 밸런싱 자동편성), 근무 요청, 공휴일, 설정
  - 간호사 **활성/비활성 토글**(비활성은 편성 제외, 회색 표시) 및 **완전 삭제**(관련 요청·스케줄 정리)
- **출력**: Excel(.xlsx), 인쇄용 PDF (화면 컬러 그리드 그대로)
- **UI**: 무료·오픈소스 고정폭 폰트 **D2Coding** 내장(한글 지원, 별도 설치 불필요)

---

## 다운로드 · 실행 (일반 사용자)

별도 설치 없이 **실행 파일 하나**로 동작한다(Python 불필요).

1. `NurseScheduler.exe` 를 받아 원하는 폴더에 둔다.
2. 더블클릭하면 실행된다. 같은 폴더에 `schedule.db`(데이터)가 자동 생성된다.

> - Windows 64bit 전용이다.
> - 처음 실행 시 백신(Defender 등)이 검사하느라 잠깐 느리거나 경고할 수 있다(PyInstaller exe 특성상 오탐 가능). 필요 시 해당 폴더를 백신 예외로 등록한다.
> - 데이터(`schedule.db`)는 exe와 같은 폴더에 저장되므로, 백업/이전 시 이 파일을 함께 옮긴다.

---

## 아키텍처 — 왜 실행파일이 두 개인가

패키징된 exe 안에서 **PyQt(Qt DLL)와 OR-Tools가 같은 프로세스에 공존하면 솔버가
네이티브 레벨에서 깨진다**(세그폴트/무한 멈춤 — 프리빌트 DLL 충돌). 그래서 계산 엔진을
UI와 **프로세스 단위로 완전히 분리**한다.

```
NurseScheduler.exe (GUI, PyQt5)
        │  요청/결과를 stdin·stdout(JSON 한 줄)으로 주고받음
        ▼
nurse_solver.exe   (OR-Tools 전용, PyQt 없음)   ← NurseScheduler.exe 안에 번들됨
```

- GUI는 앱 시작 시 솔버를 상주 서브프로세스로 띄워둔다(첫 생성이 빨라짐).
- **생성 중지**는 이 솔버 프로세스를 종료해 즉시 끊고, 새 솔버를 예열한다.
- 배포 시엔 `NurseScheduler.exe` 하나만 있으면 된다(`nurse_solver.exe`는 내부에 포함).

---

## 개발 환경에서 실행

```bash
python -m venv venv
venv\Scripts\activate            # (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
python main.py
```

개발 실행 시 솔버는 별도 exe 대신 `python solver_cli.py` 서브프로세스로 자동 실행된다.

### 데모 데이터 넣기 (선택)

```bash
python seed_dummy.py            # 익명 더미(간호사01… / 조무사01…, 합성 사번) 46명 등록
```
> `seed_dummy.py`에는 실명·실제 사번이 없다(익명 데이터). 실제 인원은 앱의 **간호사 관리** 탭에서 등록/수정한다.

---

## 빌드 (Windows exe)

메인 GUI exe와 솔버 exe를 각각 빌드한다. **솔버를 먼저** 빌드해야 메인 exe가 이를 번들할 수 있다.

```bash
pip install pyinstaller
pyinstaller nurse_solver.spec     --clean --noconfirm   # 1) 솔버 exe (dist/nurse_solver.exe)
pyinstaller schedule_onefile.spec --clean --noconfirm   # 2) 단일 GUI exe (dist/NurseScheduler.exe)
```
> `schedule.spec`은 폴더형 빌드(동일 원칙). 두 spec 모두 메인 exe에서 OR-Tools를 제외하고
> `nurse_solver.exe`를 번들한다.

---

## 화면 구성 (탭)

| 탭 | 기능 |
|----|------|
| 📅 스케줄 | 월별 그리드, 자동 생성(+생성 중지)/저장, 엑셀·PDF 출력, 셀 더블클릭 수동 수정 |
| 👩‍⚕️ 간호사 관리 | 등록/수정, **활성↔비활성 토글**, **삭제**, 사번·직군·직책·등급·프리셉터·전담 |
| 👥 팀 관리 | 팀 생성/색상, 간호사 배정, **연차 밸런싱 자동편성** |
| 📝 근무 요청 | 개인 근무/오프 신청 (근무표에 강제 반영) |
| 🎌 공휴일 | 공휴일 등록 (주말과 동일 인원 규칙 적용) |
| ⚙️ 설정 | 요일유형별 인원, 각종 규칙 설정값, **자동 생성 속도(계산 시간 상한)**, 색상 |

> **소규모 인원**은 기본 설정(주말 각 교대 5명 필요)으론 "생성 불가"가 날 수 있다.
> 실제 인원에 맞게 ⚙️ 설정에서 교대별 필요 인원을 조정한다.

---

## 기술 스택

| 항목 | 내용 |
|------|------|
| 언어 | Python 3.11 |
| UI | PyQt5 |
| 최적화 | Google OR-Tools (CP-SAT) — **별도 프로세스**에서 실행 |
| DB | SQLite (`schedule.db`, exe 옆에 생성) |
| 출력 | openpyxl(엑셀), QPrinter/QTextDocument(PDF) |
| 폰트 | D2Coding (OFL, 내장) |
| 패키징 | PyInstaller → Windows `.exe` (GUI exe + 솔버 exe) |

---

## 프로젝트 구조

```
nurse-scheduler/
├── main.py               # 앱 진입점 (탭 구성, 폰트 로드, 솔버 서비스 기동)
├── scheduler.py          # ★ 근무표 생성 엔진(OR-Tools, 모든 규칙) + 솔버 서브프로세스 서비스
├── solver_cli.py         # 독립 솔버 프로세스(PyQt 없음, stdin/stdout JSON 통신)
├── database.py           # SQLite 데이터/설정 레이어 + 마이그레이션
├── team_balance.py       # 팀 연차 밸런싱
├── excel_export.py       # 엑셀 출력
├── pdf_export.py         # 인쇄용 PDF 출력
├── seed_dummy.py         # 익명 더미 데이터 시드
├── assets/               # 내장 폰트(D2Coding.ttf 등)
├── ui/                   # PyQt5 탭들 (schedule/nurse/team/request/holiday/settings)
├── nurse_solver.spec     # 솔버 exe 빌드 스펙(PyQt 미포함)
├── schedule_onefile.spec # 단일 GUI exe 빌드 스펙(솔버 exe 번들)
├── schedule.spec         # 폴더형 GUI exe 빌드 스펙
├── SCHEDULING_RULES.md   # ★ 근무 배정 규칙 정의서 (하드/소프트/가중치/설정)
├── CHANGELOG.md          # 변경 이력
├── PROGRESS.md           # 개발 이력
└── requirements.txt
```

---

## 개인정보

- 저장소에는 **실명·실제 사번을 포함하지 않는다.** 더미 데이터(`seed_dummy.py`)는 익명(간호사01…, 합성 사번)이다.
- 실제 운영 데이터가 담긴 `schedule.db`, 생성된 근무표(`*.xlsx`, `*.pdf`)는 `.gitignore`로 저장소에서 제외된다.

---

## 라이선스 / 문의

내부 병동 운영용 프로젝트. 규칙 추가·변경은 [`SCHEDULING_RULES.md`](SCHEDULING_RULES.md)를,
동작 변경은 [`CHANGELOG.md`](CHANGELOG.md)를 함께 갱신할 것.
