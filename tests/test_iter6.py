#!/usr/bin/env python3.12
"""iter6: HUD без перекрытий + drag-руль + баланс + стрелки на еду.
Параметры: R=5 м/рад, START_ARC=0.22 (1.1 м), SPEED=1.1 рад/с,
TURN=4.6, TURN_RAMP=10, LEAK=(0.002+0.018*arc) рад/с, BOOST 1.6x,
STEER_MAXPX = min(390*0.28, 160) = 109.2 px на полный вынос."""
import json
from playwright.sync_api import sync_playwright

B = "file:///home/xidden" + "/snake-sphere"
URL = B + "/index" + ".html"
W, H = 390, 844
MAXPX = min(W * 0.28, 160)
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

    # ---------- HUD: текст vs миникарта ----------
    r = pg.evaluate("""() => {
        const h = document.querySelector('#hud').getBoundingClientRect();
        const m = document.querySelector('#minimap').getBoundingClientRect();
        const b = document.querySelector('#pauseBtn').getBoundingClientRect();
        const hudTxt = document.querySelector('#hud').innerText.replace(/\\n/g, ' | ');
        return {h: [h.left, h.right, h.top, h.bottom], m: [m.left, m.right],
                b: [b.left, b.top, b.right, b.bottom], txt: hudTxt,
                pausedVisible: b.width > 0};
    }""")
    check("hud: правый край чипов не заходит под миникарту (зазор >= 8px)",
          r["h"][1] <= r["m"][0] - 8, f"hud.right={r['h'][1]:.0f} mini.left={r['m'][0]:.0f}")
    check("hud: чипы внутри экрана (нет вылета)", r["h"][1] <= W + 0.5 and r["h"][0] >= -0.5)
    check("hud: пауза в левом нижнем углу, не пересекает чипы",
          r["b"][0] < W / 2 and r["b"][1] > H / 2, f"pause=({r['b'][0]:.0f},{r['b'][1]:.0f})")
    check("hud: пауза кликабельна (размер > 0)", r["pausedVisible"])
    check("hud: 3 чипа (длина/рекорд/капли)",
          all(s in r["txt"].lower() for s in ["длина", "рекорд", "капли"]), r["txt"][:80])

    # ---------- стартовый экран: нет утечки до старта ----------
    a0 = pg.evaluate("debug.bodyArc")
    pg.wait_for_timeout(900)
    a1 = pg.evaluate("debug.bodyArc")
    check("баланс: на стартовом экране труба не течёт", a0 == 0.22 and a1 == 0.22,
          f"{a0:.4f} -> {a1:.4f}")

    # ---------- старт + drag-руль ----------
    touch(pg, "touchstart", [mk(1, 350, 400)], [mk(1, 350, 400)])
    pg.wait_for_timeout(150)
    check("старт первым касанием: игра запущена и палец стал рулём",
          pg.evaluate("debug.started") and pg.evaluate("debug.steerId") == 1)

    x_full = 350 + MAXPX
    touch(pg, "touchmove", [mk(1, x_full, 400)], [mk(1, x_full, 400)])
    pg.wait_for_timeout(120)
    s_full = pg.evaluate("debug.steer")
    check("руль: полный вынос => steer = +1.0 (пропорционально, не бинарно)",
          abs(s_full - 1.0) < 0.02, f"steer={s_full:.3f}")

    x_micro = 350 + 30
    touch(pg, "touchmove", [mk(1, x_micro, 400)], [mk(1, x_micro, 400)])
    pg.wait_for_timeout(120)
    s_micro = pg.evaluate("debug.steer")
    check("руль: микро-сдвиг 30px => steer ~0.275 (тонкая коррекция, не полный вращ)",
          abs(s_micro - 30 / MAXPX) < 0.03, f"steer={s_micro:.3f}")

    # направление: микро-сдвиг реально крутит нос.
    # turnVel разгоняется TURN_RAMP=10 рад/с^2 к target=steer*TURN=0.275*4.6=1.265;
    # за ~450мс с холодного старта turnVel ≈ 0.35-1.1 -> Δθ 0.15-0.6 рад (~9-35°).
    t0 = pg.evaluate("debug.theta")
    pg.wait_for_timeout(400)
    dtheta = pg.evaluate("debug.theta") - t0
    # дуга может быть в отрицательном знаке (зависит от стартовой ориентации)
    check("руль: микро-сдвиг реально крутит нос (|Δθ| > 0.10 за 400мс, т.е. >6°)",
          0.10 < abs(dtheta) < 1.0, f"Δθ={dtheta:+.3f}")
    tv = pg.evaluate("debug.turnVel")
    check("руль: скорость поворота соразмерна выносу (0.2 < turnVel < target)",
          0.2 < tv < 1.27, f"turnVel={tv:.3f}")

    touch(pg, "touchend", [], [mk(1, x_micro, 400)])
    pg.wait_for_timeout(150)
    s_rel = pg.evaluate("({s: debug.steer, L: debug.keyL, R: debug.keyR})")
    check("руль: после отпускания steer=0 и флаги чистые",
          s_rel["s"] == 0 and not s_rel["L"] and not s_rel["R"])

    # ---------- утечка ----------
    lr = pg.evaluate("debug.leakRateM")
    check("баланс: течь на старте мягкая (~0.029 м/с = 1 капля за ~40с)",
          0.02 < lr < 0.04, f"leak={lr:.4f} м/с")
    b0 = pg.evaluate("debug.bodyArc")
    pg.wait_for_timeout(1000)
    b1 = pg.evaluate("debug.bodyArc")
    check("баланс: течь идёт, но медленно (~0.006 рад/с)",
          0.003 < (b0 - b1) < 0.012, f"Δ={b0 - b1:.4f} рад/с")

    # ---------- скорость: фиксированная ----------
    sp0 = pg.evaluate("debug.moveSpeed")
    pg.evaluate("debug.placeFoodAhead(0)")
    pg.wait_for_timeout(500)
    score1 = pg.evaluate("debug.score")
    sp1 = pg.evaluate("debug.moveSpeed")
    check("едение: капля съедена (score >= 1, длина выросла)",
          score1 >= 1 and pg.evaluate("debug.lenMeters") > 1.5,
          f"score={score1} len={pg.evaluate('debug.lenMeters'):.2f}м")
    check("баланс: скорость не растёт со счётом (1.1 рад/с всегда)",
          abs(sp0 - sp1) < 1e-9 and abs(sp0 - 1.1) < 1e-9, f"{sp0} -> {sp1}")

    # ---------- буст ----------
    touch(pg, "touchstart", [mk(2, 100, 400), mk(3, 300, 400)], [mk(3, 300, 400)])
    pg.wait_for_timeout(200)
    st2 = pg.evaluate("({boost: debug.boosting, sp: debug.moveSpeed, L: debug.keyL, R: debug.keyR})")
    check("буст: два пальца => 1.6x после START_ARC",
          st2["boost"] and abs(st2["sp"] - 1.1 * 1.6) < 1e-6,
          f"boost={st2['boost']} sp={st2['sp']:.2f}")
    check("буст: второй палец не забирает руль (steer=0, ключи чисты)",
          pg.evaluate("debug.steer") == 0 and not st2["L"] and not st2["R"])
    # таяние в бусте 0.55 рад/с, но пол — START_ARC: труба тает до пола и
    # дальше держится. За 400мс с длины ~1.1м (0.22 рад) тает до пола 0.22:
    # Δ ≈ min(0.22, 0.55*0.4) ≈ 0.22 рад. Если длина была уже ~пол — Δ мало.
    bb0 = pg.evaluate("debug.bodyArc")
    pg.wait_for_timeout(400)
    bb1 = pg.evaluate("debug.bodyArc")
    decay = bb0 - bb1
    # тело тает в бусте (~0.55 рад/с) к полу START_ARC; фоновая течь легально
    # дотягивает чуть ниже пола, но абсолютный пол LEAK_MIN=0.11 не пробивается
    check("буст: труба тает (~0.55 рад/с) к полу, не исчезает",
          decay > 0.05 and bb1 > 0.10, f"Δ={decay:.3f} рад, bb1={bb1:.3f}")
    touch(pg, "touchend", [], [mk(2, 100, 400), mk(3, 300, 400)])
    pg.wait_for_timeout(100)
    check("буст: после отпускания — обычная скорость",
          abs(pg.evaluate("debug.moveSpeed") - 1.1) < 1e-9)

    # ---------- еда ----------
    check("еда: на карте 4 капли (было 3)", pg.evaluate("debug.foods") == 4,
          f"foods={pg.evaluate('debug.foods')}")

    # ---------- стрелки ----------
    pg.evaluate("debug.placeFoodFar(0)")
    behind = pg.evaluate("debug.foodBehind")
    check("стрелки: капля за сферой учтена в foodBehind", behind >= 1, f"behind={behind}")
    pg.wait_for_timeout(300)
    arrow = pg.evaluate(ARROW_JS)
    check("стрелки: указатель реально рисуется на ободе сферы", arrow >= 20,
          f"arrowPx={arrow}")

    # ---------- рекорд ----------
    peak = pg.evaluate("debug.peakMeters")
    pg.evaluate("debug.kill()")
    pg.wait_for_timeout(150)
    rec_txt = pg.evaluate("document.getElementById('rec').textContent")
    stored = pg.evaluate("localStorage.getItem('snake_sphere_rec_m')")
    check("рекорд: записан пик в метрах (новый ключ)",
          stored is not None and abs(float(stored) - peak) < 0.05,
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
    touch(pg, "touchmove", [mk(9, 350 + MAXPX, 400)], [mk(9, 350 + MAXPX, 400)])
    pg.wait_for_timeout(100)
    s_before = pg.evaluate("debug.steer")
    touch(pg, "touchcancel", [], [mk(9, 350 + MAXPX, 400)])
    pg.wait_for_timeout(100)
    s_after = pg.evaluate("debug.steer")
    check("touchcancel: руль сброслен, не залипает", s_before > 0.5 and s_after == 0,
          f"{s_before:.2f} -> {s_after:.2f}")

    # ---------- ошибки консоли ----------
    check("консоль: без JS-ошибок", len(errs) == 0, "; ".join(errs[:2])[:120])

    br.close()

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"\n=== {passed}/{total} ===")
for name, ok, extra in results:
    if not ok:
        print(f"  FAIL: {name} {extra}")
