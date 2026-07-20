"""독립 솔버 프로세스 (PyQt 미포함).

패키징된 GUI exe 안에서는 PyQt(Qt DLL)와 OR-Tools가 공존하면 솔버가
세그폴트/멈춤을 일으킨다. 그래서 OR-Tools 계산은 PyQt가 전혀 없는 이 별도
프로세스에서만 수행하고, GUI와는 표준입출력(stdin/stdout)으로 통신한다.

프로토콜(한 줄당 JSON):
  요청  ← stdin : {"db": "<schedule.db 경로>", "year": 2026, "month": 7}
                 {"cmd": "quit"}  → 종료
  응답  → stdout: {"tag": "ok",    "result": {"<nurse_id>": {"<day>": "D"|...}}}
                 {"tag": "nosol", "msg": "..."}
                 {"tag": "err",   "msg": "..."}
"""
import sys
import os
import json
import multiprocessing


def main():
    multiprocessing.freeze_support()
    # GUI 부모와의 파이프 통신을 UTF-8로 고정(콘솔 기본 코드페이지가 cp949여도 안전).
    try:
        sys.stdin.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:                            # noqa: BLE001
        pass
    from pathlib import Path
    import database as db

    def respond(obj):
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + '\n')
        sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        if req.get('cmd') == 'quit':
            break
        try:
            db.DB_PATH = Path(req['db'])
            import scheduler  # database.DB_PATH를 설정한 뒤 사용 (get_conn이 동적 참조)
            result = scheduler.generate(int(req['year']), int(req['month']))
            enc = {str(nid): {str(d): s for d, s in days.items()}
                   for nid, days in result.items()}
            respond({'tag': 'ok', 'result': enc})
        except Exception as e:                       # noqa: BLE001
            # NoSolutionError 포함 — 이름으로 구분
            if type(e).__name__ == 'NoSolutionError':
                respond({'tag': 'nosol', 'msg': str(e)})
            else:
                respond({'tag': 'err', 'msg': f'{type(e).__name__}: {e}'})


if __name__ == '__main__':
    main()
