"""Browser smoke test (needs playwright + a running server seeded by scripts.demo_data).
   python -m scripts.ui_smoke /some/output/dir   - saves screenshots, prints results."""
import sys, re
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8765/ui/"
SCR = sys.argv[1]
problems = []

def login(page, email):
    page.goto(BASE)
    page.fill("input[type=email]", email)
    page.fill("input[type=password]", "Demo-Pass-2026")
    page.click("form button[type=submit]")
    page.wait_for_selector("#tabs button")

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome") if False else p.chromium.launch()
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    page = ctx.new_page()
    page.on("console", lambda m: m.type in ("error", "warning") and problems.append(("console", m.text)))
    page.on("pageerror", lambda e: problems.append(("pageerror", str(e))))
    page.on("requestfailed", lambda r: problems.append(("reqfail", r.url)))

    # --- coach flow ---
    login(page, "coach@demo.slc.lk")
    page.wait_for_selector(".item")
    print("players listed:", page.locator(".item").count())
    page.screenshot(path=f"{SCR}/01_players.png")

    page.click(".item:has-text('Kavindu')")
    page.wait_for_selector("text=Fitness progress")
    page.wait_for_selector("table")
    page.screenshot(path=f"{SCR}/02_player.png", full_page=True)

    # screening
    page.click("button:has-text('Start screening')")
    page.wait_for_selector("text=Needs analysis")
    page.fill("textarea >> nth=1", "Take 30 wickets this season")
    page.check("input[name='n_SpeedAcceleration'][value=LOW]")
    page.check("input[name='n_Energy systemsATP-PC'][value=HIGH]")
    page.screenshot(path=f"{SCR}/03_screening.png", full_page=True)
    page.click("button:has-text('Save screening')")
    page.wait_for_selector("text=Take 30 wickets")
    assert page.locator("text=Speed – Acceleration").count() == 1
    print("screening saved + shown")

    # fitness entry (mid season)
    page.click("button:has-text('Enter / edit results')")
    page.wait_for_selector("text=Fitness results")
    page.select_option("form select", "mid_season")
    page.wait_for_timeout(500)
    inputs = page.locator("input[inputmode=decimal]")
    inputs.nth(2).fill("33.5")          # CMJ
    inputs.nth(6).fill("3.30")          # 20 m
    page.click("button:has-text('Save results')")
    page.wait_for_selector("text=Fitness progress")
    page.wait_for_timeout(500)
    txt = page.inner_text("main")
    assert "Countermovement jump" in txt, txt
    print("fitness progress row present; mid value 33.5 shown:", "33.5" in txt)
    page.screenshot(path=f"{SCR}/04_progress.png", full_page=True)
    for w in re.findall(r"\b(null|undefined|NaN|\[object Object\])\b", page.inner_text("main")): problems.append(("junk text", w))

    # invalid fitness entry shows readable error
    page.click("button:has-text('Enter / edit results')")
    page.wait_for_selector("text=Fitness results")
    page.locator("input[inputmode=decimal]").nth(6).fill("34")
    page.click("button:has-text('Save results')")
    page.wait_for_selector(".err:has-text('plausible')")
    print("implausible value rejected with message:", page.inner_text(".err")[:80])
    page.click("button:has-text('Cancel')")

    # calendar
    page.click("#tabs button:has-text('Calendar')")
    page.wait_for_selector("text=Practice match")
    page.screenshot(path=f"{SCR}/05_calendar.png", full_page=True)
    page.click("button:has-text('+ Event')")
    page.fill("form input[required] >> nth=0", "Bowling workload review")
    page.fill("input[type=datetime-local] >> nth=0", "2026-10-30T16:00")
    page.click("button:has-text('Save')")
    page.wait_for_selector("text=Bowling workload review")
    print("event added")

    # squad fitness table
    page.click("#tabs button:has-text('Fitness')")
    page.wait_for_selector("table")
    print("fitness table rows:", page.locator("tbody tr").count())
    page.screenshot(path=f"{SCR}/06_fitness.png", full_page=True)
    for w in re.findall(r"\b(null|undefined|NaN|\[object Object\])\b", page.inner_text("main")): problems.append(("junk text", w))

    # horizontal page overflow at phone width?
    over = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    print("horizontal overflow px at 390w:", over)

    # --- XSS probe: a hostile player name must render as text ---
    page.evaluate("""async () => { const t = sessionStorage.getItem('slc_token');
      const sq = await (await fetch('/squads',{headers:{Authorization:'Bearer '+t}})).json();
      await fetch('/players',{method:'POST',headers:{Authorization:'Bearer '+t,'Content-Type':'application/json'},
        body:JSON.stringify({squad_id:sq[0].id,full_name:'<img src=x onerror=window.__pwned=1>',date_of_birth:'2012-02-02',gender:'male',role:'batter'})}); }""")
    page.click("#tabs button:has-text('Players')")
    page.wait_for_selector(".item")
    page.wait_for_timeout(500)
    print("XSS executed:", page.evaluate("window.__pwned === 1"), "| literal text shown:", page.locator("text=<img src=x").count() >= 1)

    # --- sign out / physio sees medical; coach never does ---
    page.click("#logout")
    page.wait_for_selector("h1:has-text('Sign in')")
    login(page, "physio@demo.slc.lk")
    page.click(".item:has-text('Kavindu')")
    page.wait_for_selector("text=Medical & availability")
    page.select_option("form select >> nth=0", "modified")
    page.fill("input[placeholder*='Coach-safe']", "No bowling this week")
    page.fill("textarea >> nth=0", "Mild lower back stiffness")
    page.click("button:has-text('Save')")
    page.wait_for_selector(".chip.modified")
    page.screenshot(path=f"{SCR}/07_physio.png", full_page=True)
    page.click("#tabs button:has-text('Fitness')"); page.wait_for_selector("table")
    junk = re.findall(r"\b(null|undefined)\b", page.inner_text("main")); print("physio fitness tab junk text:", junk or "none")
    page.click("#tabs button:has-text('Players')")
    page.click(".item:has-text('Kavindu')"); page.wait_for_selector("text=Medical")
    page.click("#logout")
    login(page, "coach@demo.slc.lk")
    page.click(".item:has-text('Kavindu')")
    page.wait_for_selector("text=Fitness progress")
    body = page.inner_text("main")
    print("coach sees availability note:", "No bowling this week" in body, "| coach sees medical text:", "lower back" in body.lower() or "Medical" in body)
    page.click("#logout")

    # --- player flow ---
    login(page, "kavindu@demo.slc.lk")
    page.wait_for_selector(".item")
    print("player sees players:", page.locator(".item").count(), "| tabs:", page.locator("#tabs button").all_inner_texts())
    page.screenshot(path=f"{SCR}/08_player_home.png")

    # dark mode + desktop screenshot
    ctx2 = b.new_context(viewport={"width": 1100, "height": 800}, color_scheme="dark")
    pg2 = ctx2.new_page(); login(pg2, "coach@demo.slc.lk"); pg2.wait_for_selector(".item"); pg2.screenshot(path=f"{SCR}/09_desktop_dark.png")
    b.close()

print("PROBLEMS:", problems or "none")
