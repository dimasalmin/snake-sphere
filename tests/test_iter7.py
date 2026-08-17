#!/usr/bin/env python3.12
"""iter7: половины экрана + поворот постоянной скорости (без разгона).
Параметры: SPEED=1.1 рад/с (фикс), TURN=2.2 рад/с (мгновенно, без TURN_RAMP),
хвост отпуска 30 рад/с^2 (~73мс до нуля), буст 1.6x, START_ARC=0.22, R=5м.
Экран 390x844: центр X=195; левая половина <195, правая >195."""
from playwright.sync_api import sync_playwright

B = "file:///home/xidden" + "/snake-sphere"
URL = B + "/index" + ".html"
W, H = 390, 844
TURN = 2.2
results = []
def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""))

def mk(i, x, y):
    return {"identifier": i, "clientX": x, "clientY": y, "pageX": x, "pageY": y}

TCH = """(p) => {
    const T = t => new Touch({identifier: t.identifier, target: document.body,
        clientX: t.clientX, clientY: t.clientY, pageX: t.pageX, pageY: t.pageY});
    const acts = p.a.map(T), chT = p.c.map(T);
    window.dispatchEvent(new TouchEvent('%TYPE%', {touches: acts, targetTouches: acts, changedTouches: chT, cancelable: true}));
}"""

def touch(pg, type_, acts, changed):
    pg.evaluate(TCH.replace("%TYPE%", type_), {"a": acts, "c": changed})

ARROW_JS = """() => {
    const c = document.querySelector('#c'), ctx = c.getContext('2d');
    const W = c.width, Hh = c.height;
    const img = ctx.getImageData(0, 0, W, Hh).data;
    const cx = W/2, cy = Hh/2, Rpx = Math.min(W, Hh)/2;
    let arrowPx = 0;
    for (let y = 0; y < Hh; y += 2) for (let x = 0; x < W; x += 2) {
        const dx = x - cx, dy = y - cy, r = Math.hypot(dx, dy) / Rpx;
        if (r < 0.80 || r > 0.995) continue;
        const i4 = (y * W + x) * 4;
        const rr = img[i4], gg = img[i4+1], bb = img[i4+2];
        if (rr > 60 && bb > 150 && gg > 120 && rr < 250 && Math.abs(gg - bb) < 90) arrowPx++;
        else if (rr > 200 && gg > 150 && bb < 140) arrowPx++;
    }
    return arrowPx;
}"""

with sync_playwright() as p:
    br = p.chromium.launch()
    pg = br.new_page(viewport={"width": W, "height": H}, has_touch=True)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL)
    pg.wait_for_timeout(400)

    # ---------- HUD ----------
    r = pg.evaluate("""() => {
        const h = document.querySelector('#hud').getBoundingClientRect();
        const m = document.querySelector('#minimap').getBoundingClientRect();
        const b = document.querySelector('#pauseBtn').getBoundingClientRect();
        const hudTxt = document.querySelector('#hud').innerText.replace(/\\n/g, ' | ');
        return {h: [h.left, h.right, h.top, h.bottom], m: [m.left, m.right],
                b: [b.left, b.top, b.right, b.bottom], txt: hudTxt,
                pausedVisible: b.width > 0};
    }""")
    check("hud: правый край чипов не заходит под миникарту",
          r["h"][1] <= r["m"][0] - 8, f"hud.right={r['h'][1]:.0f} mini.left={r['m'][0]:.0f}")
    check("hud: чипы внутри экрана", r["h"][1] <= W + 0.5 and r["h"][0] >= -0.5)
    check("hud: пауза в левом нижнем углу", r["b"][0] < W / 2 and r["b"][1] > H / 2)
    check("hud: пауза кликабельна", r["pausedVisible"])
    check("hud: 3 чипа", all(s in r["txt"].lower() for s in ["длина", "рекорд", "капли"]), r["txt"][:80])

    # ---------- нет утечки до старта ----------
    a0 = pg.evaluate("debug.bodyArc")
    pg.wait_for_timeout(900)
    a1 = pg.evaluate("debug.bodyArc")
    check("баланс: на стартовом экране труба не течёт", a0 == 0.22 and a1 == 0.22,
          f"{a0:.4f} -> {a1:.4f}")

    # ---------- старт + половины ----------
    touch(pg, "touchstart", [mk(1, 350, 400)], [mk(1, 350, 400)])  # правая половина
    pg.wait_for_timeout(120)
    st = pg.evaluate("({s: debug.started, id: debug.steerId, L: debug.keyL, R: debug.keyR})")
    check("старт первым касанием: запущена, палец=руль, правая половина",
          st["s"] and st["id"] == 1 and st["R"] and not st["L"], str(st))

    # ---------- мгновенный поворот постоянной скорости ----------
    pg.wait_for_timeout(80)  # дать step() успеть
    tv = pg.evaluate("debug.turnVel")
    check("поворот: ВКЛЮЧАЕТСЯ мгновенно (turnVel == TURN, без разгона)",
          abs(tv - TURN) < 0.05, f"turnVel={tv:.3f} (ожид. {TURN})")

    # скорость поворота постоянна во время удержания
    tv2 = pg.evaluate("debug.turnVel")
    pg.wait_for_timeout(300)
    tv3 = pg.evaluate("debug.turnVel")
    check("поворот: скорость ПОСТОЯННА во время удержания (не разгоняется)",
          abs(tv2 - TURN) < 0.05 and abs(tv3 - TURN) < 0.05,
          f"{tv2:.3f} -> {tv3:.3f}")

    # реальный поворот носа: угол между D(t0) и D(t1) (истинная дуга, не проекция)
    pg.evaluate("debug.capD()")
    pg.wait_for_timeout(400)
    ang = pg.evaluate("debug.angleD()")
    # за 400мс при 2.2 рад/с ожидаем ~0.88 рад
    check("поворот: нос реально крутится с постоянной скоростью (~0.88 рад за 400мс)",
          abs(ang - 0.88) < 0.12, f"Δθ={ang:.3f} рад (истинная дуга)")

    # ---------- разворот: смена направления мгновенная ----------
    # переводим тот же палец (pinned) на левую половину
    touch(pg, "touchmove", [mk(1, 50, 400)], [mk(1, 50, 400)])
    pg.wait_for_timeout(80)
    tv_flip = pg.evaluate("debug.turnVel")
    fl = pg.evaluate("({L: debug.keyL, R: debug.keyR})")
    check("поворот: разворот (перенос пальца) => смена направления",
          fl["L"] and not fl["R"] and tv_flip < 0,
          f"L={fl['L']} R={fl['R']} turnVel={tv_flip:.3f}")
    pg.wait_for_timeout(60)
    tv_flip2 = pg.evaluate("debug.turnVel")
    check("поворот: разворот МГНОВЕННЫЙ (turnVel == -TURN, без гашения через ноль)",
          abs(tv_flip2 + TURN) < 0.05, f"turnVel={tv_flip2:.3f} (ожид. {-TURN})")

    # ---------- отпускание: короткий хвост, не залипает ----------
    touch(pg, "touchend", [], [mk(1, 50, 400)])
    pg.wait_for_timeout(120)  # хвост ~73мс
    tv_rel = pg.evaluate("debug.turnVel")
    rel = pg.evaluate("({L: debug.keyL, R: debug.keyR})")
    check("поворот: после отпускания flags чисты и turnVel пошёл к нулю",
          not rel["L"] and not rel["R"] and abs(tv_rel) < TURN * 0.5,
          f"L={rel['L']} R={rel['R']} turnVel={tv_rel:.3f}")
    pg.wait_for_timeout(150)
    tv_zero = pg.evaluate("debug.turnVel")
    check("поворот: «хвост» быстро гасит до нуля (предсказуемо, без инерции)",
          abs(tv_zero) < 0.05, f"turnVel={tv_zero:.3f}")

    # ---------- течь ----------
    lr = pg.evaluate("debug.leakRateM")
    check("баланс: течь на старте мягкая (~0.029 м/с)", 0.02 < lr < 0.04, f"leak={lr:.4f}")
    b0 = pg.evaluate("debug.bodyArc")
    pg.wait_for_timeout(1000)
    b1 = pg.evaluate("debug.bodyArc")
    check("баланс: течь идёт, но медленно (~0.006 рад/с)", 0.003 < (b0 - b1) < 0.012,
          f"Δ={b0 - b1:.4f}")

    # ---------- скорость фиксированная ----------
    sp0 = pg.evaluate("debug.moveSpeed")
    pg.evaluate("debug.placeFoodAhead(0)")
    pg.wait_for_timeout(500)
    score1 = pg.evaluate("debug.score")
    sp1 = pg.evaluate("debug.moveSpeed")
    check("едение: капля съедена (score>=1, длина выросла)",
          score1 >= 1 and pg.evaluate("debug.lenMeters") > 1.5,
          f"score={score1} len={pg.evaluate('debug.lenMeters'):.2f}м")
    check("баланс: скорость не растёт со счётом (1.1 рад/с всегда)",
          abs(sp0 - sp1) < 1e-9 and abs(sp0 - 1.1) < 1e-9, f"{sp0} -> {sp1}")

    # ---------- буст (два пальца) ----------
    # в touches — ВСЕ активные пальцы (n = touches.length); changedTouches — только новый
    touch(pg, "touchstart", [mk(2, 350, 400)], [mk(2, 350, 400)])          # палец-руль (правая)
    pg.wait_for_timeout(60)
    touch(pg, "touchstart", [mk(2, 350, 400), mk(3, 300, 400)], [mk(3, 300, 400)])  # +палец = буст
    pg.wait_for_timeout(200)
    st2 = pg.evaluate("({boost: debug.boosting, sp: debug.moveSpeed, L: debug.keyL, R: debug.keyR})")
    check("буст: два пальца => 1.6x", st2["boost"] and abs(st2["sp"] - 1.1 * 1.6) < 1e-6,
          f"boost={st2['boost']} sp={st2['sp']:.2f}")
    check("буст: руль (pinned-палец) не сбит вторым пальцем", st2["R"] and not st2["L"],
          f"L={st2['L']} R={st2['R']}")
    bb0 = pg.evaluate("debug.bodyArc")
    pg.wait_for_timeout(400)
    bb1 = pg.evaluate("debug.bodyArc")
    decay = bb0 - bb1
    check("буст: труба тает к полу, не исчезает", decay > 0.05 and bb1 > 0.10,
          f"Δ={decay:.3f} рад, bb1={bb1:.3f}")
    touch(pg, "touchend", [mk(2, 350, 400)], [mk(3, 300, 400)])  # буст-палец ушёл, руль остаётся
    pg.wait_for_timeout(100)
    check("буст: после отпускания 2-го пальца — обычная скорость",
          abs(pg.evaluate("debug.moveSpeed") - 1.1) < 1e-9)
    touch(pg, "touchend", [], [mk(2, 350, 400)])
    pg.wait_for_timeout(60)

    # ---------- еда ----------
    check("еда: на карте 4 капли", pg.evaluate("debug.foods") == 4,
          f"foods={pg.evaluate('debug.foods')}")

    # ---------- стрелки ----------
    pg.evaluate("debug.placeFoodFar(0)")
    behind = pg.evaluate("debug.foodBehind")
    check("стрелки: капля за сферой учтена", behind >= 1, f"behind={behind}")
    pg.wait_for_timeout(300)
    arrow = pg.evaluate(ARROW_JS)
    check("стрелки: указатель рисуется на ободе", arrow >= 20, f"arrowPx={arrow}")

    # ---------- рекорд ----------
    peak = pg.evaluate("debug.peakMeters")
    pg.evaluate("debug.kill()")
    pg.wait_for_timeout(150)
    rec_txt = pg.evaluate("document.getElementById('rec').textContent")
    stored = pg.evaluate("localStorage.getItem('snake_sphere_rec_m')")
    check("рекорд: записан пик в метрах", stored is not None and abs(float(stored) - peak) < 0.05,
          f"peak={peak:.2f} stored={stored}")
    check("рекорд: HUD обновился после смерти", float(rec_txt) >= peak - 0.05, f"rec={rec_txt}")

    # ---------- миграция ----------
    pg.evaluate("""localStorage.removeItem('snake_sphere_rec_m');
                  localStorage.setItem('snake_sphere_rec', '999');""")
    pg.reload()
    pg.wait_for_timeout(400)
    best = pg.evaluate("debug.best")
    check("миграция: старый рекорд (999 капель) НЕ читается", best == 0, f"best={best}")

    # ---------- touchcancel ----------
    pg.evaluate("debug.start()")
    pg.wait_for_timeout(100)
    touch(pg, "touchstart", [mk(9, 350, 400)], [mk(9, 350, 400)])
    pg.wait_for_timeout(100)
    s_before = pg.evaluate("({L: debug.keyL, R: debug.keyR, tv: debug.turnVel})")
    touch(pg, "touchcancel", [], [mk(9, 350, 400)])
    pg.wait_for_timeout(150)
    s_after = pg.evaluate("({L: debug.keyL, R: debug.keyR})")
    check("touchcancel: руль сброслен, не залипает",
          (s_before["R"] or s_before["L"]) and not s_after["L"] and not s_after["R"],
          f"before={s_before} after={s_after}")

    # ---------- ошибки консоли ----------
    check("консоль: без JS-ошибок", len(errs) == 0, "; ".join(errs[:2])[:120])

    br.close()

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"\n=== {passed}/{total} ===")
for name, ok, extra in results:
    if not ok:
        print(f"  FAIL: {name} {extra}")
