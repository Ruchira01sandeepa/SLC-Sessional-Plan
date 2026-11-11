"""Physical-test screens in the browser (admin-only server on :8765, demo data).  python -m scripts.ui_smoke_testing /out/dir"""
import re, sys
from playwright.sync_api import sync_playwright
BASE = "http://localhost:8765/ui/"; SCR = sys.argv[1]; problems = []
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1).new_page()
    page.on("console", lambda m: m.type == "error" and problems.append(("console", m.text)))
    page.on("pageerror", lambda e: problems.append(("pageerror", str(e))))
    page.goto(BASE); page.fill("input[type=email]", "admin@demo.slc.lk"); page.fill("input[type=password]", "Demo-Pass-2026")
    page.click("form button[type=submit]"); page.wait_for_selector("#tabs button")
    print("tabs:", page.locator("#tabs button").all_inner_texts())
    page.click("#tabs button:has-text('Tests')"); page.wait_for_selector("text=Import test results"); page.wait_for_selector("text=Categories")
    print("category rows:", page.locator("tr.click").count())
    with page.expect_download() as d:
        page.click("button:has-text('Download template')")
    print("template:", d.value.suggested_filename)
    page.screenshot(path=f"{SCR}/t1_tests.png", full_page=True)
    page.click("tr.click >> nth=0"); page.wait_for_selector("text=Physical tests (SLC U15 SOP)"); page.wait_for_selector("text=Rank in level")
    page.click("button:has-text('Show individual plan')"); page.wait_for_selector("text=Individual seasonal plan")
    txt = page.inner_text("main"); print("plan shown:", "focus session" in txt, "| readiness:", "Readiness" in txt)
    with page.expect_download() as d2:
        page.click("button:has-text('Download plan')")
    print("plan xlsx:", d2.value.suggested_filename)
    page.screenshot(path=f"{SCR}/t2_profile.png", full_page=True)
    for w in re.findall(r"\b(null|undefined|NaN|\[object Object\])\b", page.inner_text("main")): problems.append(("junk", w))
    print("overflow px:", page.evaluate("document.documentElement.scrollWidth - window.innerWidth"))
    print("problems:", problems or "none"); b.close()
