import sqlite3
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# exe로 패키징됐을 때 DB를 실행 파일 옆에 저장
if getattr(sys, 'frozen', False):
    DB_PATH = Path(sys.executable).parent / "schedule.db"
else:
    DB_PATH = Path(__file__).parent / "schedule.db"


@dataclass
class Team:
    id: int
    name: str
    color: str = '#E0E0E0'


@dataclass
class Nurse:
    id: int
    name: str
    position: str  # 수간호사/책임/일반
    hire_date: str
    active: bool = True
    note: str = ""
    no_night: bool = False  # 야간 불가 플래그
    level: str = "일반"    # 신규/일반/숙련/책임
    team_id: Optional[int] = None
    emp_no: str = ""       # 사번
    job_type: str = "RN"   # RN(간호사) / NA(간호조무사·보조인력)
    preceptor_id: Optional[int] = None  # 프리셉터(이 사람이 프리셉티일 때 짝의 id)
    night_only: bool = False            # 나이트 전담(밤/오프만, NN-OO 패턴)


@dataclass
class ShiftRequest:
    id: int
    nurse_id: int
    year: int
    month: int
    day: int
    req_type: str  # 'off' | 'D' | 'E' | 'N'
    note: str = ""


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS nurses (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                name     TEXT NOT NULL,
                position TEXT DEFAULT '일반',
                hire_date TEXT DEFAULT '',
                active   INTEGER DEFAULT 1,
                note     TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS shift_requests (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                nurse_id INTEGER NOT NULL,
                year     INTEGER NOT NULL,
                month    INTEGER NOT NULL,
                day      INTEGER NOT NULL,
                req_type TEXT NOT NULL,
                note     TEXT DEFAULT '',
                UNIQUE(nurse_id, year, month, day)
            );
            CREATE TABLE IF NOT EXISTS schedules (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                nurse_id INTEGER NOT NULL,
                year     INTEGER NOT NULL,
                month    INTEGER NOT NULL,
                day      INTEGER NOT NULL,
                shift    TEXT NOT NULL,
                UNIQUE(nurse_id, year, month, day)
            );
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS holidays (
                year  INTEGER NOT NULL,
                month INTEGER NOT NULL,
                day   INTEGER NOT NULL,
                name  TEXT NOT NULL,
                PRIMARY KEY (year, month, day)
            );
            CREATE TABLE IF NOT EXISTS teams (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                name  TEXT NOT NULL UNIQUE,
                color TEXT DEFAULT '#E0E0E0'
            );
        """)
        # 기본 설정
        defaults = [
            ('min_day', '5'), ('min_eve', '4'), ('min_night', '3'),
            ('max_consec_night', '3'), ('rest_after_night', '2'),
            ('max_monthly_night', '99'),
            ('solve_seconds', '3'),   # 직군별 솔버 시간 상한(초). 낮추면 빠르지만 너무 낮으면 실패 위험

            ('color_D', '#6FA8DC'), ('color_E', '#FFCE47'),
            ('color_N', '#A47BE0'), ('color_O', '#E0E0E0'),
            ('color_sat', '#9FCAF2'), ('color_hol', '#FFAFAF'),
            ('we_day',   '5'), ('we_eve', '5'), ('we_night', '5'),  # 주말·공휴일 필요 인원(RN)
            ('wd_night', '5'),                                       # 평일 야간 필요 인원(RN)
            # NA&HA 직군 필요 인원 (잠정 기본값 — 실제 값은 설정 탭에서 조정)
            ('na_we_day', '2'), ('na_we_eve', '2'), ('na_we_night', '1'),
            ('na_wd_day', '2'), ('na_wd_eve', '2'), ('na_wd_night', '1'),
            ('monthly_off', '11'),                                  # 월 기본 오프 수(신청 없을 때)
            ('night_gap',   '5'),                                   # 야간 블록 간 최소 간격(텀)
            ('night_only_target', '15'),                            # 나이트 전담 월 야간 목표
            ('night_regular_cap', '6'),                             # 비전담 월 야간 상한(~)
            ('first_min_years',   '8'),                             # 듀티 퍼스트(책임자) 최소 연차
            ('max_consec_work',       '5'),
            ('min_charge_per_shift',  '1'),
            ('min_skilled_per_shift', '1'),
            ('prevent_new_only',      '1'),
            ('forbid_ed',             '1'),
        ]
        for k, v in defaults:
            conn.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (k, v))

        # 마이그레이션: no_night 칼럼이 없으면 추가
        try:
            conn.execute("ALTER TABLE nurses ADD COLUMN no_night INTEGER DEFAULT 0")
        except Exception:
            pass
        # 마이그레이션: level 칼럼이 없으면 추가
        try:
            conn.execute("ALTER TABLE nurses ADD COLUMN level TEXT DEFAULT '일반'")
        except Exception:
            pass
        # 마이그레이션: team_id 칼럼이 없으면 추가
        try:
            conn.execute("ALTER TABLE nurses ADD COLUMN team_id INTEGER REFERENCES teams(id)")
        except Exception:
            pass
        # 마이그레이션: emp_no(사번) 칼럼이 없으면 추가
        try:
            conn.execute("ALTER TABLE nurses ADD COLUMN emp_no TEXT DEFAULT ''")
        except Exception:
            pass
        # 마이그레이션: job_type(직군) 칼럼이 없으면 추가
        try:
            conn.execute("ALTER TABLE nurses ADD COLUMN job_type TEXT DEFAULT 'RN'")
        except Exception:
            pass
        # 마이그레이션: preceptor_id(프리셉터) 칼럼이 없으면 추가
        try:
            conn.execute("ALTER TABLE nurses ADD COLUMN preceptor_id INTEGER")
        except Exception:
            pass
        # 마이그레이션: night_only(나이트 전담) 칼럼이 없으면 추가
        try:
            conn.execute("ALTER TABLE nurses ADD COLUMN night_only INTEGER DEFAULT 0")
        except Exception:
            pass


# ── Nurse CRUD ──────────────────────────────────────────────────────────────
def get_nurses(active_only=True) -> list[Nurse]:
    with get_conn() as conn:
        q = "SELECT * FROM nurses" + (" WHERE active=1" if active_only else "") + " ORDER BY position DESC, name"
        return [Nurse(**dict(r)) for r in conn.execute(q)]


def add_nurse(name, position='일반', hire_date='', note='', no_night=False,
              level='일반', emp_no='', team_id=None, job_type='RN', preceptor_id=None,
              night_only=False) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO nurses (name,position,hire_date,note,no_night,level,emp_no,team_id,job_type,preceptor_id,night_only) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (name, position, hire_date, note, int(no_night), level, emp_no, team_id,
             job_type, preceptor_id, int(night_only))
        )
        return cur.lastrowid


def update_nurse(nurse_id, name, position, hire_date, note, no_night=False,
                 level='일반', emp_no='', job_type='RN', preceptor_id=None, night_only=False):
    with get_conn() as conn:
        conn.execute(
            "UPDATE nurses SET name=?,position=?,hire_date=?,note=?,no_night=?,level=?,emp_no=?,job_type=?,preceptor_id=?,night_only=? "
            "WHERE id=?",
            (name, position, hire_date, note, int(no_night), level, emp_no, job_type,
             preceptor_id, int(night_only), nurse_id)
        )


def deactivate_nurse(nurse_id):
    with get_conn() as conn:
        conn.execute("UPDATE nurses SET active=0 WHERE id=?", (nurse_id,))


def reactivate_nurse(nurse_id):
    with get_conn() as conn:
        conn.execute("UPDATE nurses SET active=1 WHERE id=?", (nurse_id,))


def set_nurse_active(nurse_id, active: bool):
    with get_conn() as conn:
        conn.execute("UPDATE nurses SET active=? WHERE id=?", (int(bool(active)), nurse_id))


def delete_nurse(nurse_id):
    """간호사를 완전 삭제하고 관련 데이터(근무요청·스케줄)도 함께 정리한다.
    이 간호사를 프리셉터로 지정한 다른 간호사의 preceptor_id는 NULL로 초기화한다."""
    with get_conn() as conn:
        conn.execute("DELETE FROM shift_requests WHERE nurse_id=?", (nurse_id,))
        conn.execute("DELETE FROM schedules WHERE nurse_id=?", (nurse_id,))
        conn.execute("UPDATE nurses SET preceptor_id=NULL WHERE preceptor_id=?", (nurse_id,))
        conn.execute("DELETE FROM nurses WHERE id=?", (nurse_id,))


# ── Shift Requests ───────────────────────────────────────────────────────────
def get_requests(year, month) -> list[ShiftRequest]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM shift_requests WHERE year=? AND month=?", (year, month)
        )
        return [ShiftRequest(**dict(r)) for r in rows]


def set_request(nurse_id, year, month, day, req_type, note=''):
    with get_conn() as conn:
        if req_type is None:
            conn.execute(
                "DELETE FROM shift_requests WHERE nurse_id=? AND year=? AND month=? AND day=?",
                (nurse_id, year, month, day)
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO shift_requests (nurse_id,year,month,day,req_type,note) VALUES (?,?,?,?,?,?)",
                (nurse_id, year, month, day, req_type, note)
            )


# ── Schedule ─────────────────────────────────────────────────────────────────
def get_schedule(year, month) -> dict:
    """반환: {nurse_id: {day: shift}}"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT nurse_id, day, shift FROM schedules WHERE year=? AND month=?", (year, month)
        )
        result = {}
        for r in rows:
            result.setdefault(r['nurse_id'], {})[r['day']] = r['shift']
        return result


def save_schedule(year, month, schedule: dict):
    """schedule: {nurse_id: {day: shift}}"""
    with get_conn() as conn:
        conn.execute("DELETE FROM schedules WHERE year=? AND month=?", (year, month))
        rows = [
            (nid, year, month, day, shift)
            for nid, days in schedule.items()
            for day, shift in days.items()
        ]
        conn.executemany(
            "INSERT INTO schedules (nurse_id,year,month,day,shift) VALUES (?,?,?,?,?)", rows
        )


def set_shift(nurse_id, year, month, day, shift):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO schedules (nurse_id,year,month,day,shift) VALUES (?,?,?,?,?)",
            (nurse_id, year, month, day, shift)
        )


# ── Teams ────────────────────────────────────────────────────────────────────
def get_teams() -> list:
    with get_conn() as conn:
        return [Team(**dict(r)) for r in conn.execute("SELECT * FROM teams ORDER BY name")]


def add_team(name: str, color: str = '#E0E0E0') -> int:
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO teams (name, color) VALUES (?,?)", (name, color))
        return cur.lastrowid


def update_team(team_id: int, name: str, color: str):
    with get_conn() as conn:
        conn.execute("UPDATE teams SET name=?, color=? WHERE id=?", (name, color, team_id))


def delete_team(team_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE nurses SET team_id=NULL WHERE team_id=?", (team_id,))
        conn.execute("DELETE FROM teams WHERE id=?", (team_id,))


def set_nurse_team(nurse_id: int, team_id: Optional[int]):
    with get_conn() as conn:
        conn.execute("UPDATE nurses SET team_id=? WHERE id=?", (team_id, nurse_id))


# ── Settings ─────────────────────────────────────────────────────────────────
def get_settings() -> dict:
    with get_conn() as conn:
        return {r['key']: r['value'] for r in conn.execute("SELECT * FROM settings")}


def set_setting(key, value):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, str(value)))


# ── 공휴일 ────────────────────────────────────────────────────────────────────
def get_holidays(year: int, month: int) -> dict:
    """반환: {day: name}"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT day, name FROM holidays WHERE year=? AND month=?", (year, month)
        )
        return {r['day']: r['name'] for r in rows}


def set_holiday(year: int, month: int, day: int, name: str):
    with get_conn() as conn:
        if name:
            conn.execute(
                "INSERT OR REPLACE INTO holidays (year,month,day,name) VALUES (?,?,?,?)",
                (year, month, day, name)
            )
        else:
            conn.execute(
                "DELETE FROM holidays WHERE year=? AND month=? AND day=?",
                (year, month, day)
            )
