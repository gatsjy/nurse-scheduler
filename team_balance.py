"""팀 연차 밸런싱 — 간호사를 팀에 균등하게 배정.

입사일(hire_date)에서 연차를 계산하고, 시니어(연차·등급 높은 순)부터
뱀(snake) 순서로 배정해 팀별 평균 연차·책임/숙련 분포가 고르게 맞춰지도록 한다.
저장은 apply()에서만 수행 — balance_teams()는 배정안(미리보기)만 만든다.
"""
from __future__ import annotations
import datetime
from math import ceil
from collections import defaultdict
import database as db

LEVEL_RANK = {'신규': 0, '일반': 1, '숙련': 2, '책임': 3}


def seniority_years(hire_date: str, ref_year: int | None = None) -> int:
    """hire_date에서 연차(년)를 계산. 'YYYY-MM-DD'·'YYYYMMDD'(사번) 모두 처리."""
    if ref_year is None:
        ref_year = datetime.date.today().year
    digits = ''.join(ch for ch in (hire_date or '') if ch.isdigit())
    if len(digits) >= 4:
        try:
            y = int(digits[:4])
            if 1950 <= y <= ref_year:
                return ref_year - y
        except ValueError:
            pass
    return 0


def propose(nurses, n_teams: int, ref_year: int | None = None):
    """탐욕적 배정으로 n_teams개 팀에 나눠 담는다. 반환: list[list[Nurse]].

    두 가지를 동시에 맞춘다:
      - 등급 분산: 각 등급을 팀당 상한(ceil) 이하로 고르게 배분 → 책임/숙련 쏠림 방지
      - 연차 균형: 각 간호사를 '현재 연차합이 가장 적은 팀'에 배치
    등급이 높은(책임→숙련→…) 그룹부터, 그 안에서 연차 높은 사람부터 배치한다.
    """
    if n_teams <= 0:
        return []

    teams: list[list] = [[] for _ in range(n_teams)]
    totals = [0] * n_teams                         # 팀별 연차 합
    counts = [0] * n_teams                          # 팀별 인원
    lvl_counts: list[dict] = [defaultdict(int) for _ in range(n_teams)]
    size_cap = ceil(len(nurses) / n_teams)          # 팀당 최대 인원

    groups: dict[int, list] = defaultdict(list)
    for n in nurses:
        groups[LEVEL_RANK.get(n.level, 1)].append(n)

    for rank in sorted(groups, reverse=True):       # 책임(3) → 숙련(2) → 일반(1) → 신규(0)
        members = sorted(groups[rank],
                         key=lambda n: seniority_years(n.hire_date, ref_year),
                         reverse=True)
        lvl_cap = ceil(len(members) / n_teams)      # 이 등급을 팀당 몇 명까지
        for nrs in members:
            y = seniority_years(nrs.hire_date, ref_year)
            cands = [t for t in range(n_teams)
                     if counts[t] < size_cap and lvl_counts[t][rank] < lvl_cap]
            if not cands:                           # 상한에 다 걸리면 완화
                cands = [t for t in range(n_teams) if counts[t] < size_cap] \
                        or list(range(n_teams))
            # 연차합이 가장 적은 팀 → 인원 적은 팀 순
            best = min(cands, key=lambda t: (totals[t], counts[t]))
            teams[best].append(nrs)
            totals[best] += y
            counts[best] += 1
            lvl_counts[best][rank] += 1
    return teams


def summary(team_nurses, ref_year: int | None = None) -> dict:
    """팀 구성 요약: 인원/평균연차/총연차/등급분포."""
    ys = [seniority_years(n.hire_date, ref_year) for n in team_nurses]
    levels: dict[str, int] = {}
    for n in team_nurses:
        levels[n.level] = levels.get(n.level, 0) + 1
    return {
        'count': len(team_nurses),
        'avg_years': round(sum(ys) / len(ys), 1) if ys else 0.0,
        'total_years': sum(ys),
        'levels': levels,
    }


def balance_teams(ref_year: int | None = None):
    """DB의 팀·활성 간호사를 읽어 배정안을 만든다(저장 안 함).

    반환: (teams, proposal) — teams[i]에 proposal[i] 간호사들이 배정된 안.
    """
    teams = db.get_teams()
    # 팀(A~F)은 RN 대상 — NA&HA는 팀 편성에서 제외
    nurses = [n for n in db.get_nurses(active_only=True)
              if getattr(n, 'job_type', 'RN') != 'NA']
    if not teams:
        raise ValueError("등록된 팀이 없습니다. 팀 관리에서 먼저 팀을 만들어 주세요.")
    return teams, propose(nurses, len(teams), ref_year)


def apply(teams, proposal):
    """배정안을 DB에 저장 (nurses.team_id 갱신)."""
    for team, members in zip(teams, proposal):
        for n in members:
            db.set_nurse_team(n.id, team.id)
