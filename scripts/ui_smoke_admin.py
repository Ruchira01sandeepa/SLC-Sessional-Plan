"""Admin-mode browser smoke test. Server must run on :8765 with demo data and the default SLC_ENABLED_ROLES=admin.
   python -m scripts.ui_smoke_admin /output/dir"""
import sys, re
from playwright.sync_api import sync_playwright
BASE = "http://localhost:8765/ui/"; SCR = sys.argv[1]; problems = []
JUNK = r"\b(null|undefined|NaN|\[object Object\])\b"

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, accept_downloads=True).new_page()
    page.on("console", lambda m: m.type in ("error",) and problems.append(("console", m.text)))
    page.on("pageerror", lambda e: problems.append(("pageerror", str(e))))
    page.goto(BASE)
    # a coach cannot sign in while admin-only
    page.fill("input[type=email]", "coach@demo.slc.lk"); page.fill("input[type=password]", "Demo-Pass-2026")
    page.click("form button[type=submit]"); page.wait_for_selector(".err")
    print("coach blocked:", page.inner_text(".err")[:70])
    page.fill("input[type=email]", "admin@demo.slc.lk"); page.click("form button[type=submit]")
    page.wait_for_selector("#tabs button")
    print("tabs:", page.locator("#tabs button").all_inner_texts())
    page.click("#tabs button:has-text('Admin')"); page.wait_for_selector("text=New squad")
    page.screenshot(path=f"{SCR}/a1_admin.png", full_page=True)
    # create a user
    page.fill("form:has-text('Create user') input[type=email]", "coach2@demo.slc.lk")
    page.fill("form:has-text('Create user') input >> nth=1", "Second Coach")
    page.fill("input[type=password]", "Coach-Pass-2026"); page.click("button:has-text('Create user')")
    page.wait_for_selector("td:has-text('coach2@demo.slc.lk')"); print("user created")
    # edit phases of the demo season
    page.click("button:has-text('Edit phases')"); page.wait_for_selector("text=Phases –")
    page.click("button:has-text('Replace with a suggested split')"); page.wait_for_timeout(500)
    page.screenshot(path=f"{SCR}/a2_phases.png", full_page=True)
    page.click("button:has-text('Save phases')"); page.wait_for_selector("text=New squad")
    print("phases saved")
    # seasonal plan
    page.click("#tabs button:has-text('Seasonal plan')"); page.wait_for_selector("text=Role programmes")
    page.screenshot(path=f"{SCR}/a3_plan.png", full_page=True)
    print("plan rows (cards):", page.locator(".prow").count())
    page.click("button:has-text('Save plan')"); page.wait_for_selector("text=Re-save plan")
    page.locator(".prow >> nth=0 >> select").select_option("in_progress")
    page.locator(".prow >> nth=0 >> input").fill("Reviewed")
    page.locator(".prow >> nth=0 >> button:has-text('Save status')").click(); page.wait_for_selector("text=Saved")
    with page.expect_download() as d: page.click("button:has-text('Download Excel')")
    d.value.save_as(f"{SCR}/plan_download.xlsx"); print("downloaded:", d.value.suggested_filename)
    page.select_option("select[aria-label='Filter by development area']", "physical")
    print("physical rows shown (first phase open):", page.locator(".prow:visible").count())
    txt = page.inner_text("main"); [problems.append(("junk", w)) for w in re.findall(JUNK, txt)]
    print("overflow px:", page.evaluate("document.documentElement.scrollWidth - window.innerWidth"))
    # role measures on fitness entry
    page.click("#tabs button:has-text('Players')"); page.wait_for_selector(".item")
    page.click(".item >> nth=0"); page.wait_for_selector("text=Fitness progress")
    page.click("button:has-text('Enter / edit results')"); page.wait_for_selector("text=Role-specific measures")
    page.screenshot(path=f"{SCR}/a4_fitness.png", full_page=True)
    print("problems:", problems or "none")
    b.close()
