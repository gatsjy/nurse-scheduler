"""간호사 스케줄 자동 생성 — OR-Tools CP-SAT solver."""
from __future__ import annotations
import calendar
import os
import sys
import time
# NOTE: ortools는 여기서 import하지 않는다(지연 import).
#   메인 GUI 프로세스(PyQt 포함)에 OR-Tools DLL이 로드되면 솔버가 세그폴트/멈춤을
#   일으키므로, ortools는 실제 계산을 하는 _solve_pool 안에서만 import한다.
#   (_solve_pool은 PyQt 없는 별도 솔버 프로세스에서만 호출된다.)
from database import get_nurses, get_requests, get_settings, get_schedule, get_holidays

SHIFTS = ['D', 'E', 'N', 'O']


def _log_path():
    base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) \
        else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'nurse_debug.log')


def _dbg(msg):
    """진단 로그(프로세스별 pid 포함). 기본 비활성 — 환경변수 NURSE_DEBUG=1일 때만 기록.
    (문제 재현 시 이 변수를 켜고 실행하면 nurse_debug.log가 생성된다.)"""
    if not os.environ.get('NURSE_DEBUG'):
        return
    try:
        with open(_log_path(), 'a', encoding='utf-8') as f:
            f.write('%s pid=%s %s\n' % (time.strftime('%H:%M:%S'), os.getpid(), msg))
    except Exception:
        pass


class NoSolutionError(Exception):
    """제약 조건을 만족하는 스케줄이 없을 때."""
    pass


# ── 별도 솔버 프로세스 (PyQt와 완전 분리) ────────────────────────────────────
# 패키징된 GUI exe 안에서는 PyQt(Qt DLL)와 OR-Tools가 같은 프로세스에 공존하면
# 솔버가 세그폴트/멈춤을 일으킨다(프리빌트 DLL 충돌). 자식 프로세스로 spawn 해도
# 같은 exe를 재실행하므로 동일 문제가 난다.
# → OR-Tools 계산은 PyQt가 전혀 없는 별도 솔버 실행파일(nurse_solver.exe / dev에선
#   solver_cli.py)에서만 수행하고, GUI는 그것을 상주 서브프로세스로 띄워 stdin/stdout
#   (한 줄 JSON)으로 통신한다.
import json as _json
import subprocess as _subprocess
import threading as _threading
import queue as _queue

_solver_proc = None      # subprocess.Popen
_out_q = None            # 솔버 stdout 응답 줄 큐 (reader 스레드가 채움)
_reader_thread = None


def _solver_command():
    """솔버 실행 명령. 패키징 exe면 번들된 nurse_solver.exe, 개발이면 solver_cli.py."""
    if getattr(sys, 'frozen', False):
        return [os.path.join(sys._MEIPASS, 'nurse_solver.exe')]
    here = os.path.dirname(os.path.abspath(__file__))
    return [sys.executable, os.path.join(here, 'solver_cli.py')]


def _db_path_str():
    import database as _db
    return str(_db.DB_PATH)


def _reader(proc, out_q):
    """솔버 stdout을 한 줄씩 읽어 큐에 넣는다(OR-Tools 없음 → 이 스레드는 안전)."""
    try:
        for line in proc.stdout:
            out_q.put(line)
    except Exception:                            # noqa: BLE001
        pass
    out_q.put(None)                              # EOF 신호(솔버 종료)


def start_solver_service():
    """상주 솔버 서브프로세스를 띄운다(이미 살아있으면 무시). 앱 시작 시 1회 호출.
    솔버가 OR-Tools를 미리 import 해두므로 첫 생성이 빨라진다."""
    global _solver_proc, _out_q, _reader_thread
    if _solver_proc is not None and _solver_proc.poll() is None:
        return
    creationflags = 0x08000000 if os.name == 'nt' else 0   # CREATE_NO_WINDOW(콘솔창 숨김)
    try:
        _solver_proc = _subprocess.Popen(
            _solver_command(),
            stdin=_subprocess.PIPE, stdout=_subprocess.PIPE, stderr=_subprocess.DEVNULL,
            text=True, encoding='utf-8', bufsize=1, creationflags=creationflags)
    except Exception as e:                        # noqa: BLE001
        _dbg('SERVICE: 솔버 실행 실패 %r' % e)
        _solver_proc = None
        return
    _out_q = _queue.Queue()
    _reader_thread = _threading.Thread(target=_reader, args=(_solver_proc, _out_q), daemon=True)
    _reader_thread.start()
    _dbg('SERVICE: 솔버 서브프로세스 시작 pid=%s' % _solver_proc.pid)


def submit_generate(year, month):
    """솔버에 생성 요청만 보낸다(논블로킹). 결과는 poll_result로 받는다."""
    start_solver_service()
    if _solver_proc is None:
        raise RuntimeError('솔버 프로세스를 시작할 수 없습니다.')
    req = _json.dumps({'db': _db_path_str(), 'year': int(year), 'month': int(month)},
                      ensure_ascii=False)
    _dbg('SUBMIT: %s' % req)
    _solver_proc.stdin.write(req + '\n')
    _solver_proc.stdin.flush()


def poll_result(timeout):
    """결과를 timeout초 동안 기다린다. 아직 없으면 queue.Empty를 던진다.
    반환: ('ok', {nurse_id:{day:shift}}) | ('nosol', msg) | ('err', msg)"""
    q = _out_q
    if q is None:
        raise _queue.Empty
    line = q.get(timeout=timeout)                # 없으면 queue.Empty
    if line is None:                             # EOF — 솔버 죽음
        return ('err', '솔버 프로세스가 예기치 않게 종료되었습니다.')
    obj = _json.loads(line)
    tag = obj.get('tag')
    if tag == 'ok':
        result = {int(nid): {int(d): s for d, s in days.items()}
                  for nid, days in obj['result'].items()}
        return ('ok', result)
    if tag == 'nosol':
        return ('nosol', obj.get('msg', ''))
    return ('err', obj.get('msg', '알 수 없는 오류'))


def request_generate(year, month):
    """생성 요청 후 결과가 올 때까지 블로킹하고 (tag, payload)를 반환한다.
    반드시 메인 스레드가 아닌 곳(QThread)에서 호출한다."""
    submit_generate(year, month)
    while True:
        try:
            return poll_result(1.0)
        except _queue.Empty:
            if _solver_proc is None or _solver_proc.poll() is not None:
                return ('err', '솔버 프로세스가 종료되었습니다.')


def cancel_generate():
    """진행 중인 생성을 중지한다: 솔버 프로세스를 종료해 풀이를 즉시 끊고,
    다음 생성이 빠르도록 새 솔버를 미리 예열한다."""
    global _solver_proc, _out_q, _reader_thread
    try:
        if _solver_proc is not None and _solver_proc.poll() is None:
            _solver_proc.terminate()
            try:
                _solver_proc.wait(timeout=2)
            except Exception:                    # noqa: BLE001
                _solver_proc.kill()
    except Exception:                            # noqa: BLE001
        pass
    _solver_proc = None
    _out_q = None
    _reader_thread = None
    try:
        start_solver_service()
    except Exception:                            # noqa: BLE001
        pass


def shutdown_solver_service():
    """솔버 프로세스를 정리한다(앱 종료 시)."""
    global _solver_proc
    try:
        if _solver_proc is not None and _solver_proc.poll() is None:
            try:
                _solver_proc.stdin.write('{"cmd":"quit"}\n')
                _solver_proc.stdin.flush()
                _solver_proc.wait(timeout=2)
            except Exception:                    # noqa: BLE001
                _solver_proc.terminate()
    except Exception:                            # noqa: BLE001
        pass


def _seniority_years(n, ref_year: int) -> int:
    """입사연도로 연차(년) 추정. hire_date 또는 사번(앞4자리) 사용."""
    for src in ((getattr(n, 'hire_date', '') or ''), (getattr(n, 'emp_no', '') or '')):
        digs = ''.join(c for c in src if c.isdigit())
        if len(digs) >= 4:
            y = int(digs[:4])
            if 1950 <= y <= ref_year:
                return ref_year - y
    return 0


def _rn_staffing(cfg) -> dict:
    """RN 직군 필요 인원: 주말 D/E/N 고정, 평일 N 고정, 평일 D/E 최소."""
    return {
        'we_day':   int(cfg.get('we_day',   5)),
        'we_eve':   int(cfg.get('we_eve',   5)),
        'we_night': int(cfg.get('we_night', 5)),
        'wd_day':   int(cfg.get('min_day',  5)),
        'wd_eve':   int(cfg.get('min_eve',  4)),
        'wd_night': int(cfg.get('wd_night', 5)),
    }


def _na_staffing(cfg) -> dict:
    """NA&HA 직군 필요 인원(별도 설정, 기본값은 잠정치)."""
    return {
        'we_day':   int(cfg.get('na_we_day',   2)),
        'we_eve':   int(cfg.get('na_we_eve',   2)),
        'we_night': int(cfg.get('na_we_night', 1)),
        'wd_day':   int(cfg.get('na_wd_day',   2)),
        'wd_eve':   int(cfg.get('na_wd_eve',   2)),
        'wd_night': int(cfg.get('na_wd_night', 1)),
    }


def generate(year: int, month: int, history: dict | None = None,
             solve_seconds: float | None = None) -> dict:
    """월간 스케줄 생성. RN / NA&HA 직군을 나눠 각각 풀고 합친다.

    history: 전월(직전 달) 스케줄 {nurse_id: {day: shift}}.
             None이면 DB에서 직전 달 저장분을 자동으로 불러온다(전월 이월).
    solve_seconds: 직군별 솔버 시간 상한(초). 스킬믹스 소프트 목적함수가 있으면
             최적 증명에 시간이 걸리므로, 좋은 해를 빨리 받고 끊기 위한 상한.
             None이면 설정값(solve_seconds, 기본 3초)을 사용한다.
    """
    nurses = get_nurses(active_only=True)
    if not nurses:
        return {}
    cfg = get_settings()
    if solve_seconds is None:
        try:
            solve_seconds = float(cfg.get('solve_seconds', 3))
        except (TypeError, ValueError):
            solve_seconds = 3.0
        solve_seconds = max(1.0, solve_seconds)   # 하한 1초(너무 낮으면 실패 위험)

    if history is None:
        py, pm = (year - 1, 12) if month == 1 else (year, month - 1)
        history = get_schedule(py, pm)

    rn = [n for n in nurses if getattr(n, 'job_type', 'RN') != 'NA']
    na = [n for n in nurses if getattr(n, 'job_type', 'RN') == 'NA']

    result: dict = {}
    if rn:
        result.update(_solve_pool(year, month, rn, cfg, _rn_staffing(cfg),
                                  history, skill_mix=True, solve_seconds=solve_seconds))
    if na:
        result.update(_solve_pool(year, month, na, cfg, _na_staffing(cfg),
                                  history, skill_mix=False, solve_seconds=solve_seconds))
    return result


def _solve_pool(year, month, nurses, cfg, st, history,
                skill_mix=True, solve_seconds=12.0) -> dict:
    """한 직군(pool)의 스케줄을 푼다. 필요 인원은 st(staffing)로 받는다."""
    if not nurses:
        return {}

    from ortools.sat.python import cp_model   # 지연 import(솔버 프로세스에서만 로드)

    # ── 요일유형별 필요 인원 ──────────────────────────────────────────────────
    #   주말·공휴일: D/E/N 각 we_* 명 (고정)
    #   평일:        N은 wd_night 명 (고정), D/E는 wd_day/wd_eve 최소
    we_day,  we_eve,  we_night = st['we_day'], st['we_eve'], st['we_night']
    wd_day,  wd_eve,  wd_night = st['wd_day'], st['wd_eve'], st['wd_night']

    # ── 야간 제약 ─────────────────────────────────────────────────────────────
    max_consec = int(cfg.get('max_consec_night',  3))
    rest_days  = int(cfg.get('rest_after_night',  2))
    max_night  = int(cfg.get('max_monthly_night', 99))

    # ── 연속 근무 / 패턴 제약 ─────────────────────────────────────────────────
    max_consec_work = int(cfg.get('max_consec_work', 5))
    forbid_ed       = cfg.get('forbid_ed', '1') == '1'

    # ── Skill Mix 설정 ────────────────────────────────────────────────────────
    min_charge       = int(cfg.get('min_charge_per_shift',  1))
    min_skilled      = int(cfg.get('min_skilled_per_shift', 1))
    prevent_new_only = cfg.get('prevent_new_only', '1') == '1'

    days      = calendar.monthrange(year, month)[1]
    nurse_ids = [n.id for n in nurses]
    nurse_set = set(nurse_ids)
    n_nurses  = len(nurse_ids)

    # 등급별 집합
    charge_ids   = {n.id for n in nurses if n.level == '책임'}            & nurse_set
    skilled_ids  = {n.id for n in nurses if n.level in ('숙련', '책임')} & nurse_set
    new_ids      = {n.id for n in nurses if n.level == '신규'}             & nurse_set
    non_new_ids  = nurse_set - new_ids
    # 야간 제외: no_night 플래그 또는 직책이 '갑계장'
    no_night_set = {n.id for n in nurses
                    if getattr(n, 'no_night', False) or n.position == '갑계장'} & nurse_set
    # 나이트 전담: 밤/오프만, NN-OO 패턴
    night_only_set = {n.id for n in nurses if getattr(n, 'night_only', False)} & nurse_set

    # 요청 맵
    reqs = get_requests(year, month)
    req_map: dict[int, dict[int, str]] = {}
    for r in reqs:
        req_map.setdefault(r.nurse_id, {})[r.day] = r.req_type

    # 주말 날짜 (토=5, 일=6)
    weekend_days = [d for d in range(1, days + 1)
                    if calendar.weekday(year, month, d) >= 5]

    # 주말 또는 공휴일 → 주말과 동일 인원 규칙 적용
    holiday_days = set(get_holidays(year, month).keys())
    def _we(d):
        return calendar.weekday(year, month, d) >= 5 or d in holiday_days
    we_list = [d for d in range(1, days + 1) if _we(d)]

    # ── 전월 이월 (월 경계 연속성) ────────────────────────────────────────────
    # 전월 말일 근무를 offset(≤0)으로 매핑: 전월 마지막날=0, 그 전날=-1 …
    # 창 기반 제약이 참조할 만큼(H일)만 보관한다.
    H = max(max_consec, rest_days + 1, max_consec_work + 1, 2)
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    prev_days = calendar.monthrange(prev_year, prev_month)[1]
    if history is None:
        history = {}

    hist: dict[int, dict[int, str]] = {}
    for nid in nurse_ids:
        day_map = (history or {}).get(nid, {})
        h = {}
        for day, sh in day_map.items():
            off = day - prev_days           # 전월 마지막날 → 0
            if 1 - H <= off <= 0:
                h[off] = sh
        if h:
            hist[nid] = h

    model = cp_model.CpModel()

    # ── 변수 ──────────────────────────────────────────────────────────────────
    x: dict = {}
    for nid in nurse_ids:
        for d in range(1, days + 1):
            for s in SHIFTS:
                x[nid, d, s] = model.NewBoolVar(f'x_{nid}_{d}_{s}')

    def xv(nid, d, s):
        """이달 날짜면 BoolVar, 전월 날짜(d≤0)면 상수(0/1), 범위 밖이면 0.
        창 기반 제약이 월 경계를 신경 쓰지 않고 동일한 식으로 쓸 수 있게 한다."""
        if 1 <= d <= days:
            return x[nid, d, s]
        if d <= 0:
            return 1 if hist.get(nid, {}).get(d) == s else 0
        return 0

    # ── C1: 하루 정확히 한 교대 ──────────────────────────────────────────────
    for nid in nurse_ids:
        for d in range(1, days + 1):
            model.AddExactlyOne([x[nid, d, s] for s in SHIFTS])

    # ── C2: 교대별 일일 필요 인원 (주말·공휴일 vs 평일) ──────────────────────
    for d in range(1, days + 1):
        cntD = sum(x[nid, d, 'D'] for nid in nurse_ids)
        cntE = sum(x[nid, d, 'E'] for nid in nurse_ids)
        cntN = sum(x[nid, d, 'N'] for nid in nurse_ids)
        if _we(d):
            # 주말·공휴일: D/E/N 각 고정 인원
            model.Add(cntD == we_day)
            model.Add(cntE == we_eve)
            model.Add(cntN == we_night)
        else:
            # 평일: N 고정, D/E는 최소 인원
            model.Add(cntD >= wd_day)
            model.Add(cntE >= wd_eve)
            model.Add(cntN == wd_night)

    # ── C3: 최대 연속 야간 (전월 이월) ───────────────────────────────────────
    for nid in nurse_ids:
        for d in range(1 - max_consec, days - max_consec + 1):
            if d + max_consec < 1 or d > days:
                continue   # 이달 날짜를 하나도 안 건드리는 창은 제외
            model.Add(
                sum(xv(nid, d + k, 'N') for k in range(max_consec + 1)) <= max_consec
            )

    # ── C4-경계: 전월 야간 시퀀스가 이달로 이어질 때 의무 휴무 ───────────────
    for nid in nurse_ids:
        h = hist.get(nid, {})
        if not h:
            continue
        # 전월 내부에서 야간이 끝난 경우(과거 t가 N, t+1이 N 아님) → 휴무가 이달로 넘어옴
        for t in range(1 - H, 0):
            if h.get(t) == 'N' and h.get(t + 1) != 'N':
                for k in range(1, rest_days + 1):
                    day = t + k
                    if 1 <= day <= days:
                        model.Add(x[nid, day, 'O'] == 1)
        # 전월 마지막날이 N → 이달 1일이 N이 아니면(=시퀀스 종료) 휴무 강제
        if h.get(0) == 'N':
            for k in range(1, rest_days + 1):
                if 1 <= k <= days:
                    model.AddImplication(x[nid, 1, 'N'].Not(), x[nid, k, 'O'])

    # ── C4: 야간 시퀀스 종료 후 의무 휴무 ────────────────────────────────────
    for nid in nurse_ids:
        for d in range(1, days):
            ne = model.NewBoolVar(f'ne_{nid}_{d}')
            model.AddBoolAnd([x[nid, d, 'N'], x[nid, d + 1, 'N'].Not()]).OnlyEnforceIf(ne)
            model.AddBoolOr([x[nid, d, 'N'].Not(), x[nid, d + 1, 'N']]).OnlyEnforceIf(ne.Not())
            for k in range(1, rest_days + 1):
                if d + k <= days:
                    model.AddImplication(ne, x[nid, d + k, 'O'])

    # ── 야간 텀: 야간 블록 시작 사이 최소 night_gap일 간격 (하드) ─────────────
    #   나이트 블록에 너무 자주 들어가지 않도록 블록 시작을 띄운다.
    night_gap = int(cfg.get('night_gap', 5))
    if night_gap > 1:
        for nid in nurse_ids:
            if nid in no_night_set or nid in night_only_set:
                continue                       # 전담은 NN-OO(간격 짧음)라 제외
            ns = {}
            for d in range(1, days + 1):
                nsv = model.NewBoolVar(f'ns_{nid}_{d}')   # 야간 블록 시작 = N[d] & ¬N[d-1]
                prevN = xv(nid, d - 1, 'N')
                model.Add(nsv <= x[nid, d, 'N'])
                model.Add(nsv <= 1 - prevN)
                model.Add(nsv >= x[nid, d, 'N'] - prevN)
                ns[d] = nsv
            for d in range(1, days + 1):
                win = [ns[d + k] for k in range(night_gap) if d + k <= days]
                if len(win) > 1:
                    model.Add(sum(win) <= 1)

    # ── C5: 근무 요청 ────────────────────────────────────────────────────────
    for nid, day_map in req_map.items():
        if nid not in nurse_set:
            continue
        for d, rt in day_map.items():
            if not (1 <= d <= days):
                continue
            if rt == 'off':
                model.Add(x[nid, d, 'O'] == 1)
            elif rt in ('D', 'E', 'N'):
                model.Add(x[nid, d, rt] == 1)

    # ── C6: 야간 불가 간호사 ─────────────────────────────────────────────────
    for nid in no_night_set:
        for d in range(1, days + 1):
            model.Add(x[nid, d, 'N'] == 0)

    # ── C7: 월 최대 야간 횟수 ────────────────────────────────────────────────
    if max_night < 99:
        for nid in nurse_ids:
            if nid in night_only_set:
                continue                       # 나이트 전담은 월 상한 제외
            model.Add(
                sum(x[nid, d, 'N'] for d in range(1, days + 1)) <= max_night
            )

    # ── C8: 역방향 배정 금지 (생체리듬 보호) ────────────────────────────────
    # E→D, E→O→D, N→O→D 패턴 모두 금지
    if forbid_ed:
        for nid in nurse_ids:
            # E 다음날 D 금지 (d=0이면 전월 마지막날 E → 이달 1일 D 금지)
            for d in range(0, days):
                if 1 <= d + 1 <= days:
                    model.Add(xv(nid, d, 'E') + xv(nid, d + 1, 'D') <= 1)
            # E→O→D, N→O→D 금지 (도착 D가 이달에 있는 경우, 출발일은 전월 가능)
            for d in range(-1, days - 1):
                if 1 <= d + 2 <= days:
                    model.Add(xv(nid, d, 'E') + xv(nid, d + 1, 'O') + xv(nid, d + 2, 'D') <= 2)
                    model.Add(xv(nid, d, 'N') + xv(nid, d + 1, 'O') + xv(nid, d + 2, 'D') <= 2)

    # 경계(전월 이월)를 넘는 연속근무 제약은 소프트로 처리하기 위한 페널티 모음.
    # (월내 창은 하드. 경계 창을 하드로 두면 월말에 몰린 근무블록이 다음달 초를
    #  대량 강제오프시켜 다음달이 infeasible이 되는 문제가 있음.)
    boundary_penalties = []

    # ── C9: 최대 연속 근무일 (월내 하드 / 경계 소프트) ──────────────────────
    if max_consec_work > 0:
        W2 = max_consec_work
        for nid in nurse_ids:
            for d in range(1 - W2, days - W2 + 1):
                if d + W2 < 1 or d > days:
                    continue
                wsum = sum(xv(nid, d + k, s)
                           for k in range(W2 + 1) for s in ('D', 'E', 'N'))
                if d >= 1:
                    model.Add(wsum <= W2)                      # 월내: 하드
                else:
                    ex = model.NewIntVar(0, W2 + 1, f'c9b_{nid}_{d}')
                    model.Add(ex >= wsum - W2)                 # 경계: 소프트
                    boundary_penalties.append(25 * ex)

    # ── C13: 연속 근무 한계 후 2일 의무 휴무 (월내 하드 / 경계 소프트) ───────
    if max_consec_work > 0:
        W = max_consec_work
        for nid in nurse_ids:
            for d in range(1 - W, days - W):
                if d + W + 1 < 1 or d + W + 1 > days:
                    continue
                wsum = (sum(xv(nid, d + k, s) for k in range(W) for s in ('D', 'E', 'N'))
                        + sum(xv(nid, d + W,     s) for s in ('D', 'E', 'N'))
                        + sum(xv(nid, d + W + 1, s) for s in ('D', 'E', 'N')))
                if d >= 1:
                    model.Add(wsum <= W)                       # 월내: 하드
                else:
                    ex = model.NewIntVar(0, W + 2, f'c13b_{nid}_{d}')
                    model.Add(ex >= wsum - W)                  # 경계: 소프트
                    boundary_penalties.append(25 * ex)

    # ── C10/C11: Skill Mix (소프트 제약) ─────────────────────────────────────
    #   하드 제약이면 책임/숙련이 부족한 로스터에서 해가 아예 없어진다(Infeasible).
    #   대신 교대별 부족분(shortage)을 목적함수로 최소화해, 스케줄 생성은 항상
    #   성공하면서 '가능한 최대 커버리지'를 확보한다. 책임 부족에 더 큰 가중치.
    skill_penalties = []
    if skill_mix and charge_ids and min_charge > 0:
        for d in range(1, days + 1):
            for s in ('D', 'E', 'N'):
                short = model.NewIntVar(0, min_charge, f'ch_short_{d}_{s}')
                model.Add(short >= min_charge - sum(x[nid, d, s] for nid in charge_ids))
                skill_penalties.append(3 * short)
    if skill_mix and skilled_ids and min_skilled > 0:
        for d in range(1, days + 1):
            for s in ('D', 'E', 'N'):
                short = model.NewIntVar(0, min_skilled, f'sk_short_{d}_{s}')
                model.Add(short >= min_skilled - sum(x[nid, d, s] for nid in skilled_ids))
                skill_penalties.append(1 * short)

    # ── C12: 신규간호사 단독 교대 방지 ───────────────────────────────────────
    if skill_mix and prevent_new_only and new_ids and non_new_ids:
        for d in range(1, days + 1):
            for s in ('D', 'E', 'N'):
                model.Add(
                    sum(x[nid, d, s] for nid in non_new_ids) >= 1
                )

    # ── 월 오프 상한(하드) + 목표 맞추기(소프트) ────────────────────────────
    #   오프 신청이 없으면 월 monthly_off개까지만 오프(상한). 신청분이 더 많으면 인정.
    #   상한은 하드로 절대 안 넘고, 목표(=상한)에 최대한 붙도록 부족분을 소프트로 최소화
    #   한다(정확히 ==로 박으면 다른 제약과 충돌해 해가 없어짐).
    monthly_off = int(cfg.get('monthly_off', 11))
    off_penalties = []
    W_OFF = 3
    for nid in nurse_ids:
        if nid in night_only_set:
            continue                           # 전담은 오프 수가 다름(아래서 별도 처리)
        req_off = sum(1 for d, rt in req_map.get(nid, {}).items()
                      if rt == 'off' and 1 <= d <= days)
        # 신청 오프(바탕색 오프)가 목표보다 많으면 그만큼 인정
        target = min(max(monthly_off, req_off), days)
        off_sum = sum(x[nid, d, 'O'] for d in range(1, days + 1))
        # 목표 위·아래 모두 소프트로 억제 → 오프가 target(≈11)에 수렴.
        over = model.NewIntVar(0, days, f'off_over_{nid}')
        under = model.NewIntVar(0, days, f'off_under_{nid}')
        model.Add(over >= off_sum - target)
        model.Add(under >= target - off_sum)
        off_penalties.append(W_OFF * over)
        off_penalties.append(W_OFF * under)

    # ── 야간 상한(과다 방지) ─────────────────────────────────────────────────
    #   총 야간은 C2로 이미 매일 고정. 여기선 1인 몰림만 막는다(하한 강제 X:
    #   하한을 강제하면 야간후휴무가 늘어 오프 목표와 충돌).
    n_we = len(we_list)
    n_wd = days - n_we
    total_night_slots = we_night * n_we + wd_night * n_wd
    n_night_workers = max(1, n_nurses - len(no_night_set))
    night_ceil = (total_night_slots + n_night_workers - 1) // n_night_workers
    for nid in nurse_ids:
        if nid in no_night_set or nid in night_only_set:
            continue
        nv = sum(x[nid, d, 'N'] for d in range(1, days + 1))
        model.Add(nv <= night_ceil + 2)

    # ── 나이트 전담: 밤/오프만, NN-OO(2연속 야간→2오프), 월 ~night_only_target ─
    night_only_target = int(cfg.get('night_only_target', 15))
    for nid in night_only_set:
        for d in range(1, days + 1):
            model.Add(x[nid, d, 'D'] == 0)          # 낮 금지
            model.Add(x[nid, d, 'E'] == 0)          # 저녁 금지
            # 단독 야간 금지: N이면 인접에도 N (→ 런 길이 ≥2, 퐁당 없음)
            model.Add(x[nid, d, 'N'] <= xv(nid, d - 1, 'N') + xv(nid, d + 1, 'N'))
        for d in range(1, days - 1):                # 3연속 금지 (→ 런 정확히 2)
            model.Add(x[nid, d, 'N'] + x[nid, d + 1, 'N'] + x[nid, d + 2, 'N'] <= 2)
        # 월 야간 수 ~ target (소프트 수렴)
        nights = sum(x[nid, d, 'N'] for d in range(1, days + 1))
        n_over = model.NewIntVar(0, days, f'no_over_{nid}')
        n_under = model.NewIntVar(0, days, f'no_under_{nid}')
        model.Add(n_over >= nights - night_only_target)
        model.Add(n_under >= night_only_target - nights)
        off_penalties.append(W_OFF * n_over)
        off_penalties.append(W_OFF * n_under)

    # ── 퐁당퐁당(고립 근무/휴무) 방지 — 소프트 ──────────────────────────────
    #   근무-휴-근무(고립 휴무), 휴-근무-휴(고립 근무)를 페널티로 억제해
    #   "연속 근무 → 몰아서 휴무" 패턴을 선호하게 한다. 전월 이월(xv) 반영.
    W_ISO = 2
    pattern_penalties = []
    for nid in nurse_ids:
        for d in range(1, days + 1):
            w_prev = xv(nid, d-1, 'D') + xv(nid, d-1, 'E') + xv(nid, d-1, 'N')
            w_next = xv(nid, d+1, 'D') + xv(nid, d+1, 'E') + xv(nid, d+1, 'N')
            o_prev = xv(nid, d-1, 'O')
            o_next = xv(nid, d+1, 'O')
            off_d  = x[nid, d, 'O']
            work_d = x[nid, d, 'D'] + x[nid, d, 'E'] + x[nid, d, 'N']
            # 근무-휴-근무 → 고립 휴무
            iso_off = model.NewBoolVar(f'iso_off_{nid}_{d}')
            model.Add(iso_off >= w_prev + off_d + w_next - 2)
            # 휴-근무-휴 → 고립 근무
            iso_wk = model.NewBoolVar(f'iso_wk_{nid}_{d}')
            model.Add(iso_wk >= o_prev + work_d + o_next - 2)
            pattern_penalties.append(W_ISO * iso_off)
            pattern_penalties.append(W_ISO * iso_wk)

    # ── 쓰리나이트(3연속 야간) 최대한 회피 — 소프트 ─────────────────────────
    #   C3가 4연속은 하드로 금지하지만 3연속은 허용한다. 여기서 3연속에 페널티를
    #   줘 되도록 1~2연속으로 쪼개도록 유도한다(야간후휴무가 늘어 오프와 상충 가능).
    W_3N = 2
    night3_penalties = []
    for nid in nurse_ids:
        for d in range(1, days - 1):           # d, d+1, d+2 모두 이달
            n3 = model.NewBoolVar(f'n3_{nid}_{d}')
            model.Add(n3 >= x[nid, d, 'N'] + x[nid, d+1, 'N'] + x[nid, d+2, 'N'] - 2)
            night3_penalties.append(W_3N * n3)

    # ── 프리셉터-프리셉티 근무 일치 — 소프트(높은 가중치) ──────────────────
    #   프리셉티는 프리셉터와 매일 같은 교대가 되도록(=근무표가 거의 같게) 유도.
    #   불일치 교대에 페널티. 둘 다 같은 풀(직군)에 있을 때만 적용.
    W_PRECEP = 8
    precep_penalties = []
    for n in nurses:
        pre = getattr(n, 'preceptor_id', None)
        if not pre or pre not in nurse_set or pre == n.id:
            continue
        for d in range(1, days + 1):
            for s in SHIFTS:
                diff = model.NewBoolVar(f'prec_{n.id}_{d}_{s}')
                model.Add(diff >= x[n.id, d, s] - x[pre, d, s])
                model.Add(diff >= x[pre, d, s] - x[n.id, d, s])
                precep_penalties.append(W_PRECEP * diff)

    # ── 연차 기반 야간 분배 — 소프트 ────────────────────────────────────────
    #   연차가 높을수록 야간에 페널티를 크게 줘, 야간이 저연차로 쏠리게 한다
    #   (연차 높음=적게, 낮음=많이). 4단계 티어로 완만한 그래디언트.
    W_SEN = 3
    senior_penalties = []
    reg_night_cap = int(cfg.get('night_regular_cap', 6))   # 비전담 월 야간 상한(~6, 소프트)
    for n in nurses:
        if n.id in no_night_set or n.id in night_only_set:
            continue
        nights = sum(x[n.id, d, 'N'] for d in range(1, days + 1))
        # 연차 기반: 연차 높을수록 야간 페널티↑
        y = _seniority_years(n, year)
        tier = 3 if y >= 15 else 2 if y >= 8 else 1 if y >= 3 else 0
        if tier:
            senior_penalties.append(W_SEN * tier * nights)
        # 비전담 야간 ~6 상한 (소프트)
        cap_over = model.NewIntVar(0, days, f'ncap_{n.id}')
        model.Add(cap_over >= nights - reg_night_cap)
        senior_penalties.append(3 * cap_over)

    # ── D→E→N 연속 회피 + 5일 연속근무 회피 — 소프트 ───────────────────────
    W_DEN = 3   # 데이-이브닝-나이트 3일 연속
    W_5W  = 3   # 5일 연속 근무
    misc_penalties = []
    for nid in nurse_ids:
        for d in range(1, days - 1):           # D(d)-E(d+1)-N(d+2)
            den = model.NewBoolVar(f'den_{nid}_{d}')
            model.Add(den >= x[nid, d, 'D'] + x[nid, d + 1, 'E'] + x[nid, d + 2, 'N'] - 2)
            misc_penalties.append(W_DEN * den)
        for d in range(1 - 4, days - 3):       # 5일 연속 근무 (전월 이월)
            if d + 4 < 1 or d > days:
                continue
            w5 = model.NewBoolVar(f'w5_{nid}_{d}')
            model.Add(w5 >= sum(xv(nid, d + k, s)
                                for k in range(5) for s in ('D', 'E', 'N')) - 4)
            misc_penalties.append(W_5W * w5)

    # ── 듀티 퍼스트: 각 교대에 연차 first_min_years+ 1명 이상(책임자) — 소프트 ─
    #   각 날 D/E/N에 고연차(기본 10년+) '퍼스트'가 최소 1명. 가중치가 커서
    #   밤에도 시니어 1명이 퍼스트로 들어간다(연차-야간회피보다 우선).
    first_penalties = []
    if skill_mix:
        first_min_years = int(cfg.get('first_min_years', 10))
        first_ids = {n.id for n in nurses
                     if _seniority_years(n, year) >= first_min_years} & nurse_set
        if first_ids:
            for d in range(1, days + 1):
                for s in ('D', 'E', 'N'):
                    fshort = model.NewBoolVar(f'first_{d}_{s}')
                    model.Add(fshort >= 1 - sum(x[nid, d, s] for nid in first_ids))
                    first_penalties.append(15 * fshort)

    # ── 목적함수: … + D-E-N/5연속근무 회피 + 듀티 퍼스트 ────────────────────
    objective = (skill_penalties + pattern_penalties + off_penalties
                 + boundary_penalties + night3_penalties + precep_penalties
                 + senior_penalties + misc_penalties + first_penalties)
    if objective:
        model.Minimize(sum(objective))

    # ── 풀기 ──────────────────────────────────────────────────────────────────
    # 이 코드는 PyQt가 없는 별도 솔버 프로세스(nurse_solver.exe / solver_cli.py)에서만
    # 실행되므로 CP-SAT 멀티스레드(4워커)를 안전하게 쓸 수 있다(풀이 성공률↑).
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = solve_seconds
    solver.parameters.num_search_workers  = 4
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise NoSolutionError(
            '제약 조건을 만족하는 스케줄을 찾을 수 없습니다.\n'
            '간호사 수나 등급 구성을 확인해주세요.\n\n'
            f'대상 인원: {n_nurses}명\n'
            f'책임: {len(charge_ids)}명  숙련: {len(skilled_ids - charge_ids)}명  '
            f'일반: {n_nurses - len(skilled_ids) - len(new_ids)}명  신규: {len(new_ids)}명\n'
            f'주말 D/E/N: {we_day}/{we_eve}/{we_night}  평일 N: {wd_night}  '
            f'평일 D/E 최소: {wd_day}/{wd_eve}'
        )

    result: dict[int, dict[int, str]] = {}
    for nid in nurse_ids:
        result[nid] = {}
        for d in range(1, days + 1):
            for s in SHIFTS:
                if solver.Value(x[nid, d, s]):
                    result[nid][d] = s
                    break

    return result


def count_shifts(schedule: dict, nurse_id: int) -> dict:
    counts = {'D': 0, 'E': 0, 'N': 0, 'O': 0}
    for s in schedule.get(nurse_id, {}).values():
        if s in counts:
            counts[s] += 1
    return counts
