"""데모용 더미 데이터 시드 (익명).

개인정보(실명·실제 사번)는 포함하지 않는다. 이름은 간호사01… / 조무사01… 로,
사번은 입사연도만 보존한 합성값(YYYY####)이다. 사번 앞 4자리(연도)로 연차·등급을
자동 도출한다. 이미 같은 사번이 있으면 건너뛴다(재실행 안전).

실행:  /usr/bin/python3 seed_dummy.py      (개발용 venv python 3.9)
"""
import database as db

# ── RN : (입사연도, 팀) — 이름/사번은 아래에서 합성 ─────────────────────────
#   연차 분포는 규칙 시연을 위해 다양하게 둔다(고연차 갑계장/듀티퍼스트, 저연차 야간 등).
RN_SPEC = [
    # A팀
    (1998, "A"), (2021, "A"), (2022, "A"), (2026, "A"), (2022, "A"), (2025, "A"),
    # B팀
    (2010, "B"), (2021, "B"), (2021, "B"), (2026, "B"), (2026, "B"), (2024, "B"),
    # C팀
    (2007, "C"), (2017, "C"), (2022, "C"), (2026, "C"), (2023, "C"), (2023, "C"),
    # D팀
    (1989, "D"), (2019, "D"), (2022, "D"), (2026, "D"), (2023, "D"), (2025, "D"),
    # E팀
    (2015, "E"), (2018, "E"), (2023, "E"), (2025, "E"), (2025, "E"), (2023, "E"),
    # F팀
    (2002, "F"), (2024, "F"), (2025, "F"),
]

# ── NA & HA : 입사연도만 ────────────────────────────────────────────────────
NA_SPEC = [2016, 2017, 2017, 2025, 2025, 2025, 2025, 2018, 2019, 2025, 2024, 2025, 2025]

# 이름/사번 합성 (실명·실제 사번 아님)
RN = [(f"{yr}{i + 1:04d}", f"간호사{i + 1:02d}", tm)
      for i, (yr, tm) in enumerate(RN_SPEC)]
NA_HA = [(f"{yr}{len(RN_SPEC) + j + 1:04d}", f"조무사{j + 1:02d}")
         for j, yr in enumerate(NA_SPEC)]

# ── 특수 역할 (합성 이름 기준) ──────────────────────────────────────────────
GAPGYEJANG = ['간호사01', '간호사19']            # 갑계장: 계장 + 야간 제외
NIGHT_ONLY = ['간호사06', '간호사24']            # 나이트 전담(밤/오프만, NN-OO)
PRECEPTOR_PAIRS = [                              # (프리셉터, 프리셉티) — 근무 일치
    ('간호사03', '간호사04'),
    ('간호사09', '간호사10'),
    ('간호사15', '간호사16'),
    ('간호사21', '간호사20'),
]


def hire_date_from_emp(emp_no: str) -> str:
    """사번(YYYY####)에서 입사일 문자열. 연도만 사용(YYYY-01-01)."""
    d = ''.join(c for c in emp_no if c.isdigit())
    if len(d) >= 8:
        y, m, dd = int(d[:4]), int(d[4:6]), int(d[6:8])
        if 1 <= m <= 12 and 1 <= dd <= 31:
            return f"{y:04d}-{m:02d}-{dd:02d}"
    y = int(d[:4]) if len(d) >= 4 else 2020
    return f"{y:04d}-01-01"


def level_from_year(year: int) -> str:
    """입사연도로 등급 추정(더미용). 실제 등급은 관리 탭에서 조정."""
    if year <= 2010:
        return "책임"
    if year <= 2018:
        return "숙련"
    if year <= 2023:
        return "일반"
    return "신규"


def main():
    db.init_db()

    # 팀 A~F 확보
    existing_teams = {t.name: t for t in db.get_teams()}
    palette = {'A': '#FFE0E0', 'B': '#FFF0D0', 'C': '#E0FFE0',
               'D': '#E0F0FF', 'E': '#F0E0FF', 'F': '#FFFFD0'}
    team_id = {}
    for name in "ABCDEF":
        if name in existing_teams:
            team_id[name] = existing_teams[name].id
        else:
            team_id[name] = db.add_team(name, palette[name])

    have = {n.emp_no for n in db.get_nurses(active_only=False) if n.emp_no}
    added = skipped = 0

    def add(emp, name, team=None, note="", job_type="RN"):
        nonlocal added, skipped
        if emp in have:
            skipped += 1
            return
        hd = hire_date_from_emp(emp)
        lv = level_from_year(int(hd[:4]))
        db.add_nurse(name=name, hire_date=hd, level=lv, emp_no=emp,
                     team_id=team_id[team] if team else None, note=note,
                     job_type=job_type)
        have.add(emp)
        added += 1

    for emp, name, team in RN:
        add(emp, name, team, job_type="RN")
    for emp, name in NA_HA:
        add(emp, name, note="NA&HA", job_type="NA")

    # ── 갑계장 / 나이트 전담 / 프리셉터 반영 (재실행 안전) ─────────────────────
    by_name = {n.name: n for n in db.get_nurses(active_only=False)}

    def upd(n, **ov):
        db.update_nurse(n.id, ov.get('name', n.name), ov.get('position', n.position),
                        n.hire_date, n.note, no_night=ov.get('no_night', n.no_night),
                        level=n.level, emp_no=n.emp_no, job_type=n.job_type,
                        preceptor_id=ov.get('preceptor_id', n.preceptor_id),
                        night_only=ov.get('night_only', n.night_only))

    for nm in GAPGYEJANG:
        if nm in by_name:
            upd(by_name[nm], position='갑계장', no_night=True)
    for nm in NIGHT_ONLY:
        if nm in by_name:
            upd(by_name[nm], night_only=True)
    for pre_name, tee_name in PRECEPTOR_PAIRS:
        if pre_name in by_name and tee_name in by_name:
            upd(by_name[tee_name], preceptor_id=by_name[pre_name].id)

    print(f"시드 완료: 추가 {added}명, 건너뜀(기존 사번) {skipped}명")
    print(f"  RN {len(RN)}명 (팀 A~F) + NA&HA {len(NA_HA)}명")
    print(f"  갑계장(야간제외): {GAPGYEJANG} / 나이트 전담: {NIGHT_ONLY}")
    print(f"  프리셉터 페어: {PRECEPTOR_PAIRS}")


if __name__ == "__main__":
    main()
