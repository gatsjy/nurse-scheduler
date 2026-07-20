# 간호사 근무 스케줄러 — 프로젝트 문서

> **경로**: `/Users/hanjuan/study/schedule`  
> **마지막 갱신**: 2026-06-30

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [기술 스택](#2-기술-스택)
3. [파일 구조](#3-파일-구조)
4. [데이터베이스 설계](#4-데이터베이스-설계)
5. [자동 스케줄러 (OR-Tools)](#5-자동-스케줄러-or-tools)
6. [UI 탭별 기능](#6-ui-탭별-기능)
7. [설정 키 목록](#7-설정-키-목록)
8. [간호사 등급 시스템](#8-간호사-등급-시스템)
9. [색상 시스템](#9-색상-시스템)
10. [개발 환경 설정](#10-개발-환경-설정)
11. [Windows 빌드 및 배포](#11-windows-빌드-및-배포)
12. [향후 과제](#12-향후-과제)

---

## 1. 프로젝트 개요

병원 간호사 월간 근무표(스케줄)를 자동 생성·관리하는 데스크탑 앱.

- **교대 종류**: D(낮) / E(저녁) / N(밤) / O(휴무)
- **핵심 기능**:
  - OR-Tools CP-SAT 기반 자동 스케줄 생성 (12가지 제약 + 균등화)
  - 간호사별 야간 불가, 등급(Skill Mix), 근무 요청 반영
  - 공휴일 등록, 팀 관리, 근무 요청 입력
  - 교대/헤더 색상 커스터마이징
  - 엑셀(.xlsx) 출력
  - Windows .exe 패키징 (GitHub Actions)

---

## 2. 기술 스택

| 항목 | 내용 |
|------|------|
| 언어 | Python 3.11 |
| UI | PyQt5 (Fusion 스타일) |
| 솔버 | Google OR-Tools CP-SAT (`ortools`) |
| DB | SQLite3 (파일: `schedule.db`) |
| 엑셀 출력 | openpyxl |
| 패키징 | PyInstaller (`schedule.spec`) |
| CI/CD | GitHub Actions (Windows 빌드 자동화) |

---

## 3. 파일 구조

```
schedule/
├── main.py               # 앱 진입점, MainWindow, 탭 구성
├── database.py           # 데이터 레이어 (SQLite CRUD + 마이그레이션)
├── scheduler.py          # OR-Tools 자동 스케줄 생성 엔진
├── excel_export.py       # 엑셀 출력
├── requirements.txt      # PyQt5, openpyxl, ortools, pyinstaller
├── schedule.spec         # PyInstaller 빌드 설정
├── build_windows.bat     # Windows 로컬 빌드 스크립트
├── schedule.db           # SQLite 데이터 파일 (git 제외 권장)
│
├── ui/
│   ├── __init__.py
│   ├── schedule_tab.py   # 스케줄 그리드 탭 (메인 화면)
│   ├── nurse_tab.py      # 간호사 관리 탭
│   ├── team_tab.py       # 팀 관리 탭
│   ├── request_tab.py    # 근무 요청 탭
│   ├── holiday_tab.py    # 공휴일 탭
│   └── settings_tab.py   # 설정 탭 (제약 + 색상)
│
└── .github/
    └── workflows/
        └── build-windows.yml  # Windows .exe 자동 빌드 워크플로우
```

---

## 4. 데이터베이스 설계

### 4-1. 테이블 목록

#### `nurses` — 간호사 정보
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | INTEGER PK | 자동 증가 |
| `name` | TEXT | 이름 |
| `position` | TEXT | 직책 (수간호사/책임/일반) |
| `hire_date` | TEXT | 입사일 (예: 2020-03-02) |
| `active` | INTEGER | 활성 여부 (1=활성) |
| `note` | TEXT | 메모 |
| `no_night` | INTEGER | 야간 불가 플래그 (1=불가) |
| `level` | TEXT | 숙련도 등급 (신규/일반/숙련/책임) |
| `team_id` | INTEGER | 소속 팀 ID (FK→teams) |

#### `schedules` — 월별 스케줄
| 컬럼 | 설명 |
|------|------|
| `nurse_id` | 간호사 ID |
| `year`, `month`, `day` | 날짜 |
| `shift` | 교대 (D/E/N/O) |
| UNIQUE | (nurse_id, year, month, day) |

#### `shift_requests` — 근무 요청
| 컬럼 | 설명 |
|------|------|
| `nurse_id` | 간호사 ID |
| `year`, `month`, `day` | 날짜 |
| `req_type` | 요청 종류 (off/D/E/N) |
| `note` | 비고 |

#### `teams` — 팀
| 컬럼 | 설명 |
|------|------|
| `id` | 팀 ID |
| `name` | 팀명 (UNIQUE) |
| `color` | 팀 색상 (hex) |

#### `settings` — 설정 key-value 저장소
key/value 쌍으로 모든 설정을 저장. 상세 목록은 [7. 설정 키 목록](#7-설정-키-목록) 참고.

#### `holidays` — 공휴일
| 컬럼 | 설명 |
|------|------|
| `year`, `month`, `day` | 날짜 (PK) |
| `name` | 공휴일명 |

### 4-2. 마이그레이션 정책

`init_db()` 실행 시 `ALTER TABLE … ADD COLUMN`을 try/except로 감싸 중복 실행에도 안전하게 처리.  
현재 적용된 마이그레이션:
- `nurses.no_night` 추가
- `nurses.level` 추가
- `nurses.team_id` 추가

### 4-3. DB 경로

```python
# database.py
if getattr(sys, 'frozen', False):   # PyInstaller exe
    DB_PATH = Path(sys.executable).parent / "schedule.db"
else:                                # 개발 환경
    DB_PATH = Path(__file__).parent / "schedule.db"
```

exe로 패키징 시 데이터가 임시 폴더가 아닌 exe 옆에 영구 저장됨.

---

## 5. 자동 스케줄러 (OR-Tools)

### 5-1. 동작 방식

`scheduler.generate(year, month)` 호출 → CP-SAT 모델 구성 → 풀기 → `{nurse_id: {day: shift}}` 반환

- **변수**: `x[nid, d, s]` — BoolVar (간호사 `nid`가 `d`일에 교대 `s` 근무 여부)
- **타임아웃**: 30초, 워커 4개
- **속도**: 균등화를 목적함수 최소화가 아닌 hard constraint(floor/ceil)로 처리 → 약 0.17초

### 5-2. 제약 목록 (C1–C12)

| 번호 | 이름 | 내용 |
|------|------|------|
| C1 | 하루 1교대 | 각 간호사·일자에 정확히 1개 교대 배정 (`AddExactlyOne`) |
| C2 | 교대별 최소 인원 | D/E/N 각각 설정값 이상 배정 |
| C3 | 최대 연속 야간 | `max_consec_night`일 초과 연속 N 금지 |
| C4 | 야간 후 의무 휴무 | N 시퀀스 종료 후 `rest_after_night`일 강제 O |
| C5 | 근무 요청 반영 | shift_requests 테이블의 요청 강제 적용 |
| C6 | 야간 불가 | `no_night=True` 간호사에게 N 배정 금지 |
| C7 | 월 최대 야간 횟수 | 1인당 `max_monthly_night` 초과 금지 |
| C8 | E→D 역방향 금지 | 저녁 다음날 낮 근무 금지 (생체리듬 보호) |
| C9 | 최대 연속 근무일 | D+E+N 합산 `max_consec_work`일 초과 금지 |
| C10 | Skill Mix (책임) | 교대당 최소 `min_charge_per_shift`명의 책임간호사 |
| C11 | Skill Mix (숙련) | 교대당 최소 `min_skilled_per_shift`명의 숙련자(숙련+책임) |
| C12 | 신규 단독 방지 | 교대에 신규만 있는 경우 차단 (비신규 최소 1명) |

C10·C11은 등급 해당자가 없거나 값이 0이면 적용되지 않아 Infeasible 방지.

### 5-3. 균등화 (Equalization)

목적함수 대신 hard constraint 사용 (속도 향상):

```python
work_floor  = total_work_slots  // n_nurses
work_ceil   = (total_work_slots + n_nurses - 1) // n_nurses
night_floor = total_night_slots // n_nurses
night_ceil  = (total_night_slots + n_nurses - 1) // n_nurses

# 각 간호사에 대해
model.Add(w  >= work_floor)
model.Add(w  <= work_ceil + 1)
model.Add(nv >= night_floor)
model.Add(nv <= night_ceil + 1)
```

주말 오프도 동일 방식으로 균등 분배.  
야간 불가 간호사는 야간 없는 만큼 총 근무 기대치 조정.

### 5-4. 예외 처리

```python
class NoSolutionError(Exception): ...
```

해를 찾지 못하면 `NoSolutionError` 발생. UI에서 catch하여 간호사 수·등급 구성 안내 메시지 표시.

---

## 6. UI 탭별 기능

### 6-1. 스케줄 탭 (`ui/schedule_tab.py`)

- 월별 그리드 (행: 간호사, 열: 날짜)
- 팀별 그룹 헤더 행 표시 (팀 색상 배경)
- 셀 더블클릭 → D→E→N→O→D 순환 수동 수정
- 컬럼: 날짜 + D합/E합/N합/휴합/근무합 집계
- 헤더: 날짜+요일 표시, 토요일·공휴일 색상 구분
- **자동 생성 버튼**: OR-Tools 실행 (생성 중 버튼 비활성화 + 대기 커서)
- **저장 버튼**: DB에 저장
- **엑셀 출력**: .xlsx 파일 저장
- 범례: 교대별 색상 표시 (DB 설정 반영)

### 6-2. 간호사 관리 탭 (`ui/nurse_tab.py`)

- 8컬럼 테이블: 이름 / 팀 / 직책 / 등급 / 입사일 / 상태 / 야간 불가 / 메모
- 등급별 배경색 (신규=분홍, 일반=흰색, 숙련=하늘, 책임=연두)
- 추가/수정/비활성화 기능
- `NurseDialog`: 이름·직책·등급·입사일·야간 불가·메모 입력

### 6-3. 팀 관리 탭 (`ui/team_tab.py`)

- 팀 생성·수정·삭제
- 팀별 색상 지정
- 간호사-팀 배정

### 6-4. 근무 요청 탭 (`ui/request_tab.py`)

- 간호사·날짜·요청종류(off/D/E/N) 입력
- 자동 생성 시 C5 제약으로 반드시 반영됨

### 6-5. 공휴일 탭 (`ui/holiday_tab.py`)

- 날짜·공휴일명 등록/삭제
- 스케줄 그리드 헤더에 자동 반영

### 6-6. 설정 탭 (`ui/settings_tab.py`)

QScrollArea 내 6개 그룹:

| 그룹 | 컨트롤 |
|------|--------|
| 교대별 최소 인원 | spin_min_d, spin_min_e, spin_min_n |
| 야간 근무 제약 | spin_max_consec_n, spin_rest, spin_max_monthly_n |
| 연속 근무 패턴 | spin_max_consec_work, chk_forbid_ed |
| Skill Mix | spin_min_charge, spin_min_skilled, chk_prevent_new |
| 교대 색상 | color_D/E/N/O 색상 피커 (즉시 저장) |
| 달력 헤더 색상 | color_sat/hol 색상 피커 + 초기화 버튼 |

---

## 7. 설정 키 목록

`settings` 테이블에 key-value로 저장. `database.get_settings()` → `dict` 반환.

| 키 | 기본값 | 설명 |
|----|--------|------|
| `min_day` | `5` | D(낮) 교대 최소 인원 |
| `min_eve` | `4` | E(저녁) 교대 최소 인원 |
| `min_night` | `3` | N(밤) 교대 최소 인원 |
| `max_consec_night` | `3` | 최대 연속 야간 일수 |
| `rest_after_night` | `2` | 야간 종료 후 의무 휴무 일수 |
| `max_monthly_night` | `99` | 1인당 월 최대 야간 횟수 (99=무제한) |
| `max_consec_work` | `5` | 최대 연속 근무일 (D+E+N 합산) |
| `min_charge_per_shift` | `1` | 교대당 최소 책임간호사 수 |
| `min_skilled_per_shift` | `1` | 교대당 최소 숙련자 수 (숙련+책임) |
| `prevent_new_only` | `1` | 신규 단독 교대 방지 (1=활성) |
| `forbid_ed` | `1` | E→D 역방향 배정 금지 (1=활성) |
| `color_D` | `#BDD7EE` | D 교대 셀 배경색 |
| `color_E` | `#FFE699` | E 교대 셀 배경색 |
| `color_N` | `#C5A8FF` | N 교대 셀 배경색 |
| `color_O` | `#F0F0F0` | 휴무 셀 배경색 |
| `color_sat` | `#CCE5FF` | 토요일 헤더 색상 |
| `color_hol` | `#FFD7D7` | 일요일/공휴일 헤더 색상 |

---

## 8. 간호사 등급 시스템

```
신규 < 일반 < 숙련 < 책임
```

| 등급 | 색상 | 설명 |
|------|------|------|
| 신규 | #FFE0E0 (분홍) | 숙련자 없는 교대 불가 (C12) |
| 일반 | #FFFFFF (흰색) | 기본 등급 |
| 숙련 | #E0F0FF (하늘) | Skill Mix 숙련자 카운트 포함 |
| 책임 | #E0FFE0 (연두) | Skill Mix 책임/숙련 모두 카운트 포함 |

**Skill Mix 적용 기준**:
- `charge_ids` = 등급이 '책임'인 간호사 집합
- `skilled_ids` = 등급이 '숙련' 또는 '책임'인 간호사 집합
- 등록된 해당 등급 간호사가 없으면 해당 제약 비활성화 (Infeasible 방지)

---

## 9. 색상 시스템

색상은 `settings` 테이블에 저장되며, `_load_colors()` 함수로 DB에서 실시간 로드.

```python
# ui/schedule_tab.py
def _load_colors():
    cfg = db.get_settings()
    return {k: QColor(cfg.get(f'color_{k}', v)) for k, v in COLOR_DEFAULTS.items()}
```

- 설정 탭에서 색상 피커로 변경하면 즉시 DB 저장
- 스케줄 탭 `refresh()` 호출 시 범례·셀 색상 모두 갱신
- 셀 수동 클릭 시에도 `_load_colors()` 재호출하여 최신 색상 적용

---

## 10. 개발 환경 설정

### macOS / Linux

```bash
cd /Users/hanjuan/study/schedule
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Windows

```bat
cd C:\path\to\schedule
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### requirements.txt

```
PyQt5
openpyxl
ortools
pyinstaller
```

### 임포트 검증

```bash
python3 -c "import database as db; db.init_db(); import scheduler; import ui.settings_tab; import ui.nurse_tab; print('OK')"
```

---

## 11. Windows 빌드 및 배포

### 방법 A: GitHub Actions (macOS에서도 가능)

1. GitHub 저장소 생성 후 코드 push
2. **Actions 탭** → **Build Windows EXE** → **Run workflow**
3. 빌드 완료 후 **Artifacts**에서 `NurseScheduler-Windows.zip` 다운로드

버전 태그 push 시 자동으로 GitHub Release 생성:

```bash
git tag v1.0
git push origin v1.0
```

### 방법 B: Windows PC에서 직접 빌드

`build_windows.bat` 더블클릭 → `dist\NurseScheduler\NurseScheduler.exe` 생성

### 빌드 구성 (`schedule.spec`)

- `collect_all('ortools')`: OR-Tools DLL 전체 수집
- `collect_all('openpyxl')`: 엑셀 템플릿 포함
- `console=False`: 콘솔창 숨김
- `--onedir` 방식: 폴더 형태로 배포 (DB 파일이 exe 옆에 생성됨)

### DB 경로 처리

exe 실행 시 DB가 임시 폴더가 아닌 exe 옆에 저장되도록 처리:

```python
# database.py
if getattr(sys, 'frozen', False):
    DB_PATH = Path(sys.executable).parent / "schedule.db"
else:
    DB_PATH = Path(__file__).parent / "schedule.db"
```

### 배포 시 포함 파일

```
NurseScheduler/
├── NurseScheduler.exe   # 실행 파일
├── *.dll                # OR-Tools, Qt DLL
└── ...                  # 기타 의존성
```

사용자는 `NurseScheduler/` 폴더 전체를 복사해서 사용.  
`schedule.db`는 첫 실행 시 자동 생성됨.

---

## 12. 향후 과제

| 항목 | 상태 | 설명 |
|------|------|------|
| 음력 공휴일 자동 계산 | 미완 | 추석, 설날, 부처님오신날 등 자동 등록 |
| 아이콘 설정 | 미완 | `schedule.spec`의 `icon=None`에 `.ico` 파일 경로 지정 |
| Windows .exe 코드서명 | 미완 | SmartScreen 경고 제거를 위한 인증서 적용 |
| 스케줄 인쇄 기능 | 미완 | QPrinter 활용 |
| 통계/보고서 탭 | 미완 | 월별 근무 통계 시각화 |

---

*이 문서는 프로젝트의 실제 코드를 기반으로 자동 작성되었습니다.*
