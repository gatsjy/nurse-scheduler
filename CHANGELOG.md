# 변경 이력 (CHANGELOG)

## 2026-07-20 — 버그 수정 · 기능 추가 · 배포 개선

이번 작업에서 수정/추가된 내용을 정리한다. 관련 규칙 정의는 [`SCHEDULING_RULES.md`](SCHEDULING_RULES.md), 개발 이력은 [`PROGRESS.md`](PROGRESS.md) 참고.

---

### 🐛 버그 수정

#### 1. exe 실행 즉시 종료 (numpy 누락)
- **증상**: PyInstaller로 만든 exe가 실행 직후 조용히 종료(창이 뜨는 듯하다 사라짐). windowed 모드라 오류 메시지가 안 보였다.
- **원인**: `schedule.spec`의 `excludes`에 `numpy`, `pandas`가 포함돼 있었는데, **OR-Tools 9.15가 내부적으로 `numpy`/`pandas`를 import**한다(`ortools/sat/python/cp_model.py`). 패키징 시 제외되어 `ModuleNotFoundError: No module named 'numpy'`로 크래시.
- **수정**: `schedule.spec` / `schedule_onefile.spec`의 `excludes`에서 `numpy`, `pandas` 제거.
  ```
  excludes=['matplotlib', 'numpy', 'pandas', 'PIL', 'tkinter']   # 변경 전
  excludes=['matplotlib', 'PIL', 'tkinter']                      # 변경 후
  ```

#### 2. "자동 생성" 버튼 클릭 시 프로그램 강제 종료 (세그폴트)
- **증상**: 스케줄 자동 생성 버튼을 누르면 프로그램이 통째로 뻗음(Segmentation fault, exit 139). `try/except`로도 잡히지 않음.
- **원인**: OR-Tools(CP-SAT) 솔버를 **메인 스레드가 아닌 곳(`QThread`·`threading.Thread` 모두)에서 실행**하면 네이티브 세그폴트가 발생한다. 세그폴트는 파이썬 예외가 아니라 프로세스 전체가 죽는다. (워커 수를 1로 줄여도, 스레드 종류를 바꿔도 동일 → 비(非)메인 스레드 실행 자체가 원인)
- **수정**: 솔버를 **별도 프로세스(`multiprocessing` spawn)의 메인 스레드**에서 실행. `QThread`는 그 결과만 받아 UI에 전달한다. → 세그폴트 해결 + UI 안 얼림.
  - `main.py`: 패키징된 exe에서 자식 프로세스가 GUI를 재실행하지 않도록 `multiprocessing.freeze_support()`를 최상단에 호출

#### 2-1. 자동 생성이 매번 느림 (프로세스 매번 새로 생성)
- **증상**: 간호사 수가 적어도(예: 5명) 생성 버튼을 누를 때마다 수 초씩 걸림.
- **원인**: 위 세그폴트 수정에서 **생성 때마다 별도 프로세스를 새로 띄웠는데**, 그때마다 OR-Tools를 다시 import(약 1.4초)하고, 패키징 exe에선 부트로더까지 재기동해 오버헤드가 컸다. (솔버 자체는 5명이면 0.1초로 빠름)
- **수정**: **상주(persistent) 솔버 워커 프로세스** 도입. 앱 시작 시 워커를 딱 한 번 띄워 OR-Tools를 미리 import 해두고, 생성 요청마다 그 워커를 재사용한다.
  - 효과(측정): 5명 기준 — 앱 실행 후 첫 생성 ~0.8초, **이후 생성 ~0.05초**. (기존: 매번 수 초)
  - `scheduler.py`: `start_solver_service()` / `request_generate()` / `_worker_loop()` / `shutdown_solver_service()` 추가
  - `ui/schedule_tab.py`: `_GenWorker`가 상주 워커에 요청만 보냄
  - `main.py`: 시작 시 `scheduler.start_solver_service()`, 종료 시 정리

#### 3. 간호사 "비활성화"가 동작하지 않는 것처럼 보임
- **증상**: 비활성화해도 목록에서 아무 변화가 없어 보임.
- **원인**: DB 로직은 정상이었다(`active=0`으로 바뀌고, 스케줄 자동 생성은 `active_only=True`라 실제로 제외됨). 다만 **간호사 관리 탭은 모든 간호사를 표시**하는데 비활성 간호사에 시각적 구분이 없었고(상태 칸 글자만 변경), **재활성화 수단도 없었다**.
- **수정** (`ui/nurse_tab.py`):
  - 비활성 간호사 행 전체를 **회색 + 취소선**으로 흐리게 표시
  - 비활성/활성 **토글 버튼**: 선택한 간호사 상태에 따라 `🚫 비활성화` ↔ `✅ 활성화` 자동 전환 (재활성화 가능)

---

#### 2-2. 패키징된 exe에서 "생성 중" 무한 멈춤 / 세그폴트 (핵심)
- **증상**: 개발 환경에선 되는데, 배포용 exe에서 자동 생성을 누르면 "생성 중..."에서 끝나지 않고 멈춤(또는 강제 종료). 인원 30~46명(생성 가능 규모)에서도 발생.
- **원인**: **패키징된 exe 안에서 PyQt(Qt DLL)와 OR-Tools가 같은 프로세스에 공존하면 CP-SAT 솔버가 네이티브 레벨에서 깨진다**(프리빌트 DLL 충돌). 진단 결과:
  - PyQt 번들 exe의 메인 프로세스에서 `Solve()` → **세그폴트**
  - PyQt 번들 exe가 spawn한 자식(같은 exe 재실행)에서 `Solve()` → **무한 멈춤**
  - PyQt가 전혀 없는 exe에서는 → **정상**
  - (앞서 `multiprocessing` 상주 워커로 바꾼 것도 결국 같은 exe를 재실행해서 이 문제를 피하지 못했음)
- **수정**: **OR-Tools 계산을 PyQt가 전혀 없는 별도 실행파일 `nurse_solver.exe`로 완전 분리.** GUI(`NurseScheduler.exe`)는 이 솔버를 상주 서브프로세스로 띄우고 표준입출력(한 줄 JSON)으로 통신한다.
  - `solver_cli.py`(신규): 독립 솔버 서버(stdin으로 요청, stdout으로 결과). stdin/stdout UTF-8 고정.
  - `nurse_solver.spec`(신규): PyQt를 절대 포함하지 않는 솔버 exe 빌드.
  - `scheduler.py`: `ortools`를 지연 import(메인 GUI 프로세스는 OR-Tools를 아예 로드하지 않음). 서비스 함수(`start_solver_service`/`submit_generate`/`poll_result`/`cancel_generate`)를 서브프로세스+파이프 방식으로 재작성. `num_search_workers`는 격리됐으므로 4로 유지(풀이 성공률).
  - `schedule_onefile.spec`: 메인 exe에서 `ortools`/`numpy`/`pandas` 제외, `nurse_solver.exe`를 번들.
- **검증**: 실제 GUI exe에서 46명 근무표가 `tag=ok`로 정상 생성됨(멈춤/크래시 없음).

### ✨ 기능 추가

#### 3-1. 자동 생성 "생성 중지" 버튼
- 자동 생성 진행 대화상자에 **`생성 중지` 버튼** 추가. 인원이 많아 풀이가 오래 걸릴 때 중간에 끊을 수 있다.
- 중지 시 상주 솔버 워커 프로세스를 종료해 현재 풀이를 즉시 중단하고(측정 ~0.03초), 다음 생성이 다시 빠르도록 새 워커를 즉시 예열한다(중지 직후 재생성 ~0.06초).
- `scheduler.py`: `submit_generate` / `poll_result` / `cancel_generate` 추가(취소 가능한 제출·폴링 구조)
- `ui/schedule_tab.py`: `_GenWorker`에 `cancel()`·`canceled` 시그널, 진행창의 `생성 중지`와 연결

#### 3-2. 생성 속도 개선 + 시간 상한 설정화
- 솔버가 각 직군을 5초씩(합 ~10초) 최적화하던 것을 **기본 3초**로 낮춰 46명 기준 **약 11초 → 6.6초**로 단축(스케줄 품질은 거의 동일: 근무건 835 → 826).
- ⚙️ 설정 탭에 **"자동 생성 속도 → 직군별 계산 시간 상한(초)"** 항목 추가. 1~30초 조절 가능(권장 3초). 인원이 많아 "생성 불가"가 나면 값을 높이면 된다.
- `database.py`: 설정 `solve_seconds`(기본 3) 추가 / `scheduler.generate`: 인자 미지정 시 설정값 사용(하한 1초)

#### 4. 간호사 완전 삭제
- 간호사 관리 탭에 **`🗑️ 삭제` 버튼** 추가 (강력한 확인 대화상자, "편성 제외만 원하면 비활성화 권장" 안내).
- `database.py`에 `delete_nurse(nurse_id)` 추가 — 간호사뿐 아니라 **관련 근무 요청·저장된 스케줄**까지 함께 삭제하고, 그 간호사를 프리셉터로 지정한 다른 간호사의 `preceptor_id`를 `NULL`로 초기화(고아 데이터 방지).
- 보조 함수 `reactivate_nurse`, `set_nurse_active`도 추가.

---

### 🎨 UI/폰트

#### 5. 글씨체 변경 → D2Coding 내장
- 앱 전역 폰트를 `맑은 고딕` → **D2Coding**(네이버, 무료·오픈소스 고정폭 폰트)으로 변경. 약간 옛날 프로그램 느낌의 monospace이며 **한글까지 지원**해 영문·한글이 일관되게 보인다.
- 폰트 파일을 `assets/`에 두고 exe에 **번들**(별도 설치 불필요). 실행 시 `QFontDatabase`로 로드하며, 실패하면 시스템 기본 폰트로 폴백.
- 파일: `assets/D2Coding.ttf`, `assets/D2CodingBold.ttf`

---

### 📦 빌드 / 배포

- **단일 파일 exe** 빌드 스펙 추가: `schedule_onefile.spec` → `dist/NurseScheduler.exe` 하나로 어느 Windows 64bit PC에서든 실행(Python 미설치 무관).
  ```
  pyinstaller schedule_onefile.spec --clean --noconfirm
  ```
- 기존 폴더형 빌드(`schedule.spec`)도 위 numpy·폰트 수정 반영.
- **DB 초기화**: 배포본은 빈 상태로 시작하도록 `schedule.db`를 제거(앱 최초 실행 시 빈 DB 자동 생성).

---

### 변경된 파일 요약
| 파일 | 내용 |
|------|------|
| `scheduler.py` | 자식 프로세스 진입점 `_subprocess_generate` 추가 |
| `ui/schedule_tab.py` | `_GenWorker`를 별도 프로세스 실행으로 변경(세그폴트 해결) |
| `ui/nurse_tab.py` | 비활성 행 흐림 표시, 활성/비활성 토글, 삭제 버튼 |
| `database.py` | `delete_nurse`, `reactivate_nurse`, `set_nurse_active` 추가 |
| `main.py` | `freeze_support`, D2Coding 폰트 로드 |
| `schedule.spec` / `schedule_onefile.spec` | numpy/pandas 제외 해제, 폰트 번들 |
| `assets/D2Coding*.ttf` | 내장 폰트(신규) |
