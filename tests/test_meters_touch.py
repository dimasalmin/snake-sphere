#!/usr/bin/env python3.12
"""Тесты фиксов №2 (метраж) и №3 (гейт буста + тач-руление).
Метрика в метрах: mLen = arc * R (R=5). START_ARC=0.22 -> 1.1 m; капля +0.22 рад -> +1.1 м."""
import json
import re
from playwright.sync_api import sync_playwright

URL = "file:///home/xidden/snake-sphere/index.htm" + "l"
PASS, FAIL = [], []


def check(name, cond, info=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK  " if cond else "  FAIL") + " | " + name + ("" if cond else "  -> " + str(info)))


with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 700, "height": 500})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL)
    pg.wait_for_timeout(400)
    check("no page errors on load", not errs, errs)

    # ---- 1. Метры: старт ----
    r = pg.evaluate("({m: debug.lenMeters, pm: debug.peakMeters, a: debug.bodyArc})")
    check("start len ~1.1 m", abs(r["m"] - 1.1) < 0.05, r)
    check("start peak == len", abs(r["pm"] - r["m"]) < 0.01, r)

    # HUD
    h = pg.evaluate("({s: document.getElementById('score').textContent,"
                    " l: document.getElementById('len').textContent,"
                    " r: document.getElementById('rec').textContent})")
    check("HUD score slot = 1.1", h["s"] == "1.1", h)
    check("HUD rec slot = 0.0 (fresh)", h["r"] == "0.0", h)

    # ---- 2. Гейт буста: до START_ARC буст не работает ----
    pg.evaluate("debug.start();")
    pg.wait_for_timeout(30)
    pg.evaluate("debug.boostKey = true;")
    pg.wait_for_timeout(60)
    st1 = pg.evaluate("({b: debug.boosting, m: debug.lenMeters})")
    check("boost OFF at start length (gate)", st1["b"] is False, st1)

    # ---- 3. Рост: капля +1.1 м, peak обновляется ----
    pg.evaluate("debug.boostKey = false;")
    pg.evaluate("debug.placeFoodAhead(0);")
    pg.wait_for_timeout(150)  # дожидаемся, пока голова накроет каплю
    st2 = pg.evaluate("({m: debug.lenMeters, pm: debug.peakMeters, a: debug.bodyArc})")
    check("ate: len ~2.2 m", abs(st2["m"] - 2.2) < 0.15, st2)
    check("peak == len right after eat", abs(st2["pm"] - st2["m"]) < 0.05, st2)
    pg.evaluate("debug.kill();")
    pg.wait_for_timeout(30)
    rec = pg.evaluate("({best: debug.best, k: localStorage.getItem('snake_sphere_rec_m'),"
                      " hudRec: document.getElementById('rec').textContent})")
    check("record stored in new key (meters)", rec["k"] is not None and abs(float(rec["k"]) - st2["pm"]) < 0.15, rec)
    check("HUD rec updated after game over", rec["hudRec"] == rec["k"].split(".")[0] + "." + rec["k"].split(".")[1][:1] or float(rec["hudRec"]) == round(rec["best"], 1), rec)
    ov = pg.evaluate("document.getElementById('ovText').textContent")
    check("game-over text shows meters", ("м" in ov), ov)

    # ---- 4. Подтекание: peak фиксирован, текущая длина тает ----
    pg.evaluate("location.reload();")
    pg.wait_for_timeout(300)
    pg.evaluate("debug.start(); debug.placeFoodAhead(0);")
    pg.wait_for_timeout(150)
    p = pg.evaluate("debug.peakMeters;")
    pg.wait_for_timeout(900)  # ~0.9 с подтекания при ~2.2 м
    st3 = pg.evaluate("({m: debug.lenMeters, pm: debug.peakMeters})")
    check("leak: current < peak", st3["m"] < p - 0.05, (p, st3))
    check("leak: peak unchanged", abs(st3["pm"] - p) < 1e-6, st3)
    pg.evaluate("debug.kill();")

    # ---- 5. Миграция: старый рекорд в каплях НЕ подхватывается ----
    # старый ключ = 999 капель, НОВОГО ключа нет -> best должен остаться 0
    pg.evaluate("localStorage.removeItem('snake_sphere_rec_m');"
                "localStorage.setItem('snake_sphere_rec', '999'); location.reload();")
    pg.wait_for_timeout(300)
    best2 = pg.evaluate("debug.best;")
    check("old droplet record ignored", best2 == 0, best2)

    # ---- 6. Тач: палец-руль по identifier ----
    def touch(type_, acts, changed):
        # acts: список всех активных пальцев [(id,x,y)...]; changed: [id]
        acts_js = json.dumps(acts)
        ch_js = json.dumps(changed)
        pg.evaluate("""(p) => {
            const acts = JSON.parse(p.a), ch = JSON.parse(p.c), type = p.t;
            const mk = (id, x, y) => new Touch({identifier: id, target: document.body, clientX: x, clientY: y});
            const ev = new TouchEvent(type, {
                bubbles: true, cancelable: true,
                touches: acts.map(a => mk(a[0], a[1], a[2])),
                changedTouches: ch.map(id => { const a = acts.find(t => t[0] === id) || [id, 0, 0]; return mk(a[0], a[1], a[2]); }),
                targetTouches: acts.map(a => mk(a[0], a[1], a[2]))
            });
            window.dispatchEvent(ev);
        }""", {"a": acts_js, "c": ch_js, "t": type_})
        return pg.evaluate("({L: debug.keyL, R: debug.keyR, sid: debug.steerId, bk: debug.boostKey})")

    # чистый старт без рекорда
    pg.evaluate("localStorage.clear(); location.reload();")
    pg.wait_for_timeout(300)
    pg.evaluate("debug.start();")

    s = touch("touchstart", [[1, 60, 300]], [1])
    check("finger1 left -> steer L", s["L"] is True and s["sid"] == 1 and s["bk"] is False, s)

    s = touch("touchstart", [[1, 60, 300], [2, 320, 300]], [2])
    check("finger2 right -> boost only, steer stays L",
          s["L"] is True and s["sid"] == 1 and s["bk"] is True, s)

    # переместим палец-руль на правую половину
    s = touch("touchmove", [[1, 400, 300], [2, 320, 300]], [1])
    check("steer finger moved right -> R (pin follows)", s["R"] is True and s["L"] is False and s["sid"] == 1, s)

    # отпускаем палец-руль: остался один палец -> руль пуст, буст (нужно 2 пальца)
    # тоже снимается: поворот плавно останавливается, без «перескока» на буст-палец
    s = touch("touchend", [[2, 320, 300]], [1])
    check("steer lifted -> neutral, no jump to boost finger",
          s == {"L": False, "R": False, "sid": None, "bk": False}, s)

    # отпускаем буст-палец: всё чистое
    s = touch("touchend", [], [2])
    check("all lifted -> clean", s == {"L": False, "R": False, "sid": None, "bk": False}, s)

    # новый палец-руль после полного отпускания (x=400 > 350 = правая половина)
    s = touch("touchstart", [[3, 400, 300]], [3])
    check("new finger -> new steer R", s["R"] is True and s["sid"] == 3, s)

    b.close()

print()
print("PASS: %d  FAIL: %d" % (len(PASS), len(FAIL)))
if FAIL:
    print("failed:", FAIL)
    raise SystemExit(1)
