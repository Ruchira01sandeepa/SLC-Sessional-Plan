"use strict";
/* SLC junior (U15 / U17) web UI. No build step, no dependencies.
   Security rule: API data is only ever inserted as text (textContent / createTextNode), never as HTML. */

// ───────────── tiny helpers ─────────────
// DOM append()/replaceChildren() turn a null/false child into the text "null"/"false". Conditional children
// (`cond ? node : null`) are used everywhere here, so make both calls skip empty values (and unwrap arrays).
for (const name of ["append", "replaceChildren"]) {
  const native = Element.prototype[name];
  Element.prototype[name] = function (...kids) { return native.apply(this, kids.flat().filter((k) => k != null && k !== false)); };
}
const $ = (s) => document.querySelector(s);
const T = (k) => (I18N[LANG] && I18N[LANG][k]) || I18N.en[k] || k;      // translation hook (Sinhala/Tamil arrive in Phase 6)
const I18N = { en: {} };
let LANG = "en";

function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (k in el && k !== "list" && k !== "form") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const fmt = (v, d = 2) => (v == null ? "–" : typeof v === "number" ? +v.toFixed(d) : v);
const ROLE = { fast_bowler: "Fast bowler", spin_bowler: "Spin bowler", batter: "Batter", bat_wicketkeeper: "Batting wicketkeeper", all_rounder: "All-rounder" };
const EVT = { training: "Training", match: "Match", fitness_test: "Fitness test", rest: "Rest", review: "Review", camp: "Camp" };
const PHASE = { baseline: "Baseline", mid_season: "Mid-season", end_season: "End-season" };

let toastTimer;
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), 3200);
}

// ───────────── state & api ─────────────
const S = { token: null, user: null, squads: [], squad: null, seasons: [], season: null, tab: "players", pid: null };
const TOKEN_KEY = "slc_token", EMAIL_KEY = "slc_email";
const store = {
  get() { try { return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY); } catch { return null; } },
  /** remember=true keeps the sign-in across browser restarts (until the token expires); otherwise it ends with the tab. */
  set(v, remember = false) {
    try {
      sessionStorage.removeItem(TOKEN_KEY); localStorage.removeItem(TOKEN_KEY);
      if (v) (remember ? localStorage : sessionStorage).setItem(TOKEN_KEY, v);
    } catch { /* private mode: stay in memory */ }
  },
  email() { try { return localStorage.getItem(EMAIL_KEY) || ""; } catch { return ""; } },
  rememberEmail(v) { try { v ? localStorage.setItem(EMAIL_KEY, v) : localStorage.removeItem(EMAIL_KEY); } catch { /* ignore */ } },
};

async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || "GET",
    headers: { ...(opts.body ? { "Content-Type": "application/json" } : {}), ...(S.token ? { Authorization: "Bearer " + S.token } : {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && S.token) { signOut(); throw new Error("Session expired - please sign in again"); }
    if (res.status === 403 && data.detail === "password_change_required") { showChangePassword(); throw new Error("Change your password to continue"); }
    const d = data.detail;
    throw new Error(Array.isArray(d) ? d.map((e) => (e.msg || "").replace(/^Value error, /, "")).join("; ") : d || "Something went wrong");
  }
  return data;
}
const can = (...roles) => roles.includes(S.user.role);

// ───────────── auth views ─────────────
function signOut() {
  S.token = null; S.user = null; store.set(null);
  ["#top", "#tabs"].forEach((s) => ($(s).hidden = true));
  showLogin();
}

// --- auth building blocks ---
const SIGNUP_ROLE_LABEL = { coach: "Coach", sc_coach: "S&C coach", physio: "Physiotherapist", player: "Player", admin: "Administrator" };
let AUTH_CFG = null;
async function authConfig() {
  if (!AUTH_CFG) { try { AUTH_CFG = await api("/auth/config"); } catch { AUTH_CFG = { signup_enabled: false, signup_roles: [], enabled_roles: [] }; } }
  return AUTH_CFG;
}

function svgIcon(paths) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("aria-hidden", "true"); svg.setAttribute("class", "icon");
  for (const d of paths) { const p = document.createElementNS(NS, "path"); p.setAttribute("d", d); svg.append(p); }
  return svg;
}
const EYE = ["M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z", "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"];
const EYE_OFF = ["M3 3l18 18", "M10.6 5.1A10.6 10.6 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.2 4.1M6.6 6.6C3.8 8.4 2 12 2 12s3.6 7 10 7c1.8 0 3.4-.5 4.8-1.3", "M9.9 9.9a3 3 0 0 0 4.2 4.2"];

/** Password input with a show/hide toggle and a caps-lock warning. */
function pwField(label, autocomplete) {
  const input = h("input", { type: "password", autocomplete, required: true, maxLength: 200, spellcheck: false });
  const toggle = h("button", { type: "button", class: "pw-toggle", "aria-label": "Show password", "aria-pressed": "false" }, svgIcon(EYE));
  toggle.addEventListener("click", () => {
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    toggle.setAttribute("aria-pressed", String(show)); toggle.setAttribute("aria-label", show ? "Hide password" : "Show password");
    toggle.replaceChildren(svgIcon(show ? EYE_OFF : EYE)); input.focus();
  });
  const caps = h("div", { class: "hint warn", hidden: true }, "Caps Lock is on");
  const onKey = (e) => { if (e.getModifierState) caps.hidden = !e.getModifierState("CapsLock"); };
  input.addEventListener("keydown", onKey); input.addEventListener("keyup", onKey);
  input.addEventListener("blur", () => (caps.hidden = true));
  return { input, el: h("label", {}, label, h("div", { class: "pw" }, input, toggle), caps) };
}

/** Live checklist + strength meter that mirrors the server rule (10+ chars, upper, lower, digit). */
function pwStrength(input) {
  const rules = [["10 or more characters", (v) => v.length >= 10], ["Upper and lower case letters", (v) => /[a-z]/.test(v) && /[A-Z]/.test(v)], ["At least one number", (v) => /\d/.test(v)]];
  const items = rules.map(([t]) => h("li", {}, t));
  const segs = [0, 1, 2, 3].map(() => h("span"));
  const word = h("span", { class: "meter-word" });
  const meter = h("div", { class: "meter s0" }, h("div", { class: "meter-bar" }, segs), word);
  const update = () => {
    const v = input.value, ok = rules.map(([, f]) => f(v));
    ok.forEach((pass, i) => items[i].classList.toggle("ok", pass));
    const all = ok.every(Boolean);
    const score = !v ? 0 : !all ? Math.max(1, ok.filter(Boolean).length - 1) : (v.length >= 14 || /[^A-Za-z0-9]/.test(v)) ? 4 : 3;
    meter.className = "meter s" + score;
    word.textContent = ["", "Weak", "Fair", "Good", "Strong"][score];
  };
  input.addEventListener("input", update); update();
  return { el: h("div", { class: "pw-strength" }, meter, h("ul", { class: "rules" }, items)), valid: () => rules.every(([, f]) => f(input.value)) };
}

function submitButton(label, busyLabel) {
  const b = h("button", { type: "submit", class: "block" }, label);
  return { el: b, busy(on) { b.disabled = on; b.classList.toggle("busy", on); b.textContent = on ? busyLabel : label; } };
}

let BRANDING = null;
async function branding() {
  if (!BRANDING) { try { BRANDING = await api("/branding"); } catch { BRANDING = { logo: null, name: "Sri Lanka Cricket" }; } }
  return BRANDING;
}

/** The organisation's logo (app/static/brand/logo.svg|png, when present) above a clean wordmark. */
function brandMark(b) {
  return h("div", { class: "brand-mark" + (b.logo ? " has-logo" : "") },
    b.logo ? h("img", { class: "brand-logo", src: b.logo, alt: b.name, decoding: "async" })
      : h("div", { class: "brand-word" }, h("span", { class: "bw-1" }, "Sri Lanka"), h("span", { class: "bw-2" }, "Cricket")));
}

/** An original, abstract cricket ground drawn in lines: boundary, inner circle, pitch and creases. Draws itself in. */
function fieldArt() {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 600 600"); svg.setAttribute("class", "field-art"); svg.setAttribute("aria-hidden", "true");
  const add = (tag, attrs) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); svg.append(e); return e; };
  add("ellipse", { cx: 300, cy: 300, rx: 280, ry: 260, class: "fa-line fa-1", pathLength: 1 });
  add("ellipse", { cx: 300, cy: 300, rx: 150, ry: 140, class: "fa-line fa-2", pathLength: 1 });
  add("rect", { x: 284, y: 236, width: 32, height: 128, rx: 2, class: "fa-line fa-3", pathLength: 1 });
  add("line", { x1: 272, y1: 252, x2: 328, y2: 252, class: "fa-line fa-4", pathLength: 1 });
  add("line", { x1: 272, y1: 348, x2: 328, y2: 348, class: "fa-line fa-4", pathLength: 1 });
  return svg;
}

async function authShell(...content) {
  document.body.classList.add("auth-mode");
  ["#top", "#tabs"].forEach((s) => ($(s).hidden = true));
  const box = $("#main .auth .auth-box");
  if (box) return box.replaceChildren(...content);            // switching tabs: keep the brand panel (and its animation) as it is
  const b = await branding();
  $("#main").replaceChildren(h("div", { class: "auth centred" },
    h("div", { class: "aurora", "aria-hidden": "true" }, h("span"), h("span"), h("span")), fieldArt(),
    h("div", { class: "auth-column" },
      h("div", { class: "auth-head" }, brandMark(b), h("div", { class: "brand-tag" }, "Player Development")),
      h("section", { class: "auth-card" }, h("div", { class: "auth-box" }, content)),
      h("div", { class: "auth-copy" }, `© ${new Date().getFullYear()} ${b.name}`))));
}

/** Opening splash: the crest, the product name and a short progress line. Once per browser session; any click or key skips it;
 *  never shown to people who prefer reduced motion. Resolves when the page behind it may appear. */
async function splash() {
  let seen = false;
  try { seen = sessionStorage.getItem("slc_splash") === "1"; sessionStorage.setItem("slc_splash", "1"); } catch { /* private mode: show it */ }
  if (seen || (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)) return;
  const b = await branding();
  const el = h("div", { class: "splash", "aria-hidden": "true" },
    h("div", { class: "aurora" }, h("span"), h("span"), h("span")),
    h("div", { class: "splash-core" },
      h("div", { class: "splash-ring" }), h("div", { class: "splash-ring r2" }),
      h("div", { class: "splash-logo" }, b.logo ? h("img", { src: b.logo, alt: "" }) : h("div", { class: "brand-word" }, h("span", { class: "bw-1" }, "Sri Lanka"), h("span", { class: "bw-2" }, "Cricket"))),
      h("div", { class: "splash-title" }, "Player Development"),
      h("div", { class: "splash-bar" }, h("span"))));
  document.body.append(el);
  await new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      el.classList.add("out");
      setTimeout(() => el.remove(), 700);
      resolve();
    };
    setTimeout(finish, 2200);
    el.addEventListener("click", finish);
    window.addEventListener("keydown", finish, { once: true });
  });
}

// --- screens ---
const AUTH_HASH = { signin: "#/signin", signup: "#/signup" };
async function showLogin(mode = "signin", notice = null) {
  const cfg = await authConfig();
  if (mode === "signup" && !cfg.signup_enabled) mode = "signin";
  S.authMode = mode;
  if (location.hash !== AUTH_HASH[mode]) location.hash = AUTH_HASH[mode];       // its own address: Back and bookmarks work
  document.title = (mode === "signup" ? "Sign up" : "Sign in") + " · SLC Player Development";
  await authShell(mode === "signin" ? signInForm(cfg, notice) : signUpForm(cfg));
  const fields = [...document.querySelectorAll(".auth-box input:not([type=checkbox])")];
  const first = fields.find((i) => !i.value) || fields[0];                    // remembered email: start in the password box
  if (first) first.focus();
}
window.addEventListener("hashchange", () => {
  if (S.token) return;
  const mode = location.hash === AUTH_HASH.signup ? "signup" : location.hash === AUTH_HASH.signin ? "signin" : null;
  if (mode && mode !== S.authMode) showLogin(mode);
});
const switchLink = (text, label, mode) => h("p", { class: "auth-switch" }, text + " ", h("a", { href: AUTH_HASH[mode], class: "link-strong" }, label));

function signInForm(cfg, notice) {
  const err = h("div", { class: "err", role: "alert" });
  const saved = store.email();
  const email = h("input", { type: "email", autocomplete: "username", required: true, maxLength: 255, spellcheck: false, value: saved });
  const pw = pwField("Password", "current-password");
  const remember = h("input", { type: "checkbox", checked: !!saved });
  const btn = submitButton("Sign in", "Signing in…");
  const help = h("p", { class: "hint", hidden: true }, "Ask your administrator to reset it.");
  const form = h("form", { class: "auth-form", oninput: () => (err.textContent = ""), onsubmit: async (e) => {
    e.preventDefault(); err.textContent = ""; btn.busy(true);
    try {
      const r = await api("/auth/login", { method: "POST", body: { email: email.value.trim(), password: pw.input.value } });
      S.token = r.access_token; store.set(S.token, remember.checked);
      store.rememberEmail(remember.checked ? email.value.trim() : "");
      history.replaceState(null, "", location.pathname);
      document.title = "SLC Player Development";
      r.must_change_password ? showChangePassword() : start();
    } catch (x) {
      err.textContent = x.message === "account_pending" ? "Your request is waiting for approval." : x.message;
      btn.busy(false); pw.input.select();
      form.classList.remove("shake"); void form.offsetWidth; form.classList.add("shake");
    }
  } },
    h("h1", {}, "Sign in"),
    notice ? h("div", { class: "notice ok", role: "status" }, notice) : null,
    h("label", {}, "Email", email), pw.el,
    h("div", { class: "auth-options" },
      h("label", { class: "check" }, remember, h("span", {}, "Remember me")),
      h("button", { type: "button", class: "link", onclick: () => (help.hidden = !help.hidden) }, "Forgot password?")),
    help, err, btn.el,
    cfg.signup_enabled ? switchLink("Don't have an account?", "Sign up", "signup") : null);
  return form;
}

function signUpForm(cfg) {
  const err = h("div", { class: "err", role: "alert" });
  const name = h("input", { autocomplete: "name", required: true, minLength: 2, maxLength: 200 });
  const email = h("input", { type: "email", autocomplete: "email", required: true, maxLength: 255, spellcheck: false });
  const role = h("select", { required: true }, h("option", { value: "" }, "Select your role…"),
    cfg.signup_roles.map((r) => h("option", { value: r }, SIGNUP_ROLE_LABEL[r] || r)));
  const roleHint = h("div", { class: "hint", hidden: true });
  role.addEventListener("change", () => {
    const off = role.value && !cfg.enabled_roles.includes(role.value);
    roleHint.hidden = !off;
    roleHint.textContent = off ? `${SIGNUP_ROLE_LABEL[role.value]} sign-in is not open yet.` : "";
  });
  const note = h("textarea", { maxLength: 300, rows: 2, placeholder: "e.g. Head coach, Western Province U17" });
  const pw = pwField("Password", "new-password");
  const strength = pwStrength(pw.input);
  const confirm = pwField("Confirm password", "new-password");
  const btn = submitButton("Sign up", "Creating account…");
  return h("form", { class: "auth-form", oninput: () => (err.textContent = ""), onsubmit: async (e) => {
    e.preventDefault(); err.textContent = "";
    if (!strength.valid()) { err.textContent = "Choose a password that meets all three rules."; return pw.input.focus(); }
    if (pw.input.value !== confirm.input.value) { err.textContent = "The two passwords do not match."; return confirm.input.focus(); }
    btn.busy(true);
    try {
      const r = await api("/auth/signup", { method: "POST", body: { full_name: name.value.trim(), email: email.value.trim(), role: role.value,
        note: note.value.trim() || null, password: pw.input.value } });
      await authShell(h("div", { class: "auth-done" }, h("div", { class: "done-mark", "aria-hidden": "true" }, "✓"), h("h1", {}, "Account created"),
        h("p", { class: "sub" }, "An administrator will activate it. You can sign in once it is approved."),
        h("button", { type: "button", class: "block", onclick: () => showLogin("signin") }, "Go to sign in")));
    } catch (x) { err.textContent = x.message; btn.busy(false); }
  } },
    h("h1", {}, "Create an account"), h("p", { class: "auth-lead" }, "New accounts are activated by an administrator."),
    h("label", {}, "Full name", name), h("label", {}, "Email", email),
    h("label", {}, "Role", role), roleHint,
    h("label", {}, "About you ", h("span", { class: "opt" }, "(optional)"), note),
    pw.el, strength.el, confirm.el, err, btn.el,
    switchLink("Already have an account?", "Sign in", "signin"));
}

async function showChangePassword() {
  const err = h("div", { class: "err", role: "alert" });
  const cur = pwField("Current (temporary) password", "current-password");
  const nw = pwField("New password", "new-password");
  const strength = pwStrength(nw.input);
  const confirm = pwField("Confirm new password", "new-password");
  const btn = submitButton("Save password", "Saving…");
  await authShell(h("form", { class: "auth-form", oninput: () => (err.textContent = ""), onsubmit: async (e) => {
    e.preventDefault(); err.textContent = "";
    if (!strength.valid()) { err.textContent = "Choose a password that meets all three rules."; return nw.input.focus(); }
    if (nw.input.value !== confirm.input.value) { err.textContent = "The two passwords do not match."; return confirm.input.focus(); }
    btn.busy(true);
    try { await api("/auth/change-password", { method: "POST", body: { current_password: cur.input.value, new_password: nw.input.value } }); toast("Password changed"); start(); }
    catch (x) { err.textContent = x.message; btn.busy(false); }
  } }, h("h1", {}, "Set a new password"),
    cur.el, nw.el, strength.el, confirm.el, err, btn.el,
    h("p", { class: "auth-alt" }, h("button", { type: "button", class: "link", onclick: signOut }, "Sign out"))));
  cur.input.focus();
}

// ───────────── shell ─────────────
async function start() {
  try {
    S.user = await api("/auth/me");
    S.squads = await api("/squads");
  } catch (x) { return showLogin(); }
  document.body.classList.remove("auth-mode");
  if (location.hash.startsWith("#/sign")) history.replaceState(null, "", location.pathname);
  $("#who").textContent = S.user.full_name;
  $("#who-role").textContent = SIGNUP_ROLE_LABEL[S.user.role] || S.user.role;
  $("#avatar").textContent = S.user.full_name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
  branding().then((b) => { if (b.logo && !$("#top .top-logo")) $("#top .brand").prepend(h("img", { class: "top-logo", src: b.logo, alt: b.name })); });
  S.tab = can("player") ? "players" : "overview"; S.pid = null;
  $("#top").hidden = false;
  const sel = $("#squad");
  sel.replaceChildren(...S.squads.map((s) => h("option", { value: s.id }, s.name)));
  sel.onchange = () => selectSquad(+sel.value);
  if (!S.squads.length) {
    S.squad = null; S.seasons = []; S.season = null;
    if (can("admin")) { S.tab = "admin"; drawTabs(); return go("admin"); }
    $("#tabs").hidden = true; return $("#main").replaceChildren(h("div", { class: "empty" }, "You are not assigned to any squad yet. Ask an administrator."));
  }
  await selectSquad(S.squads[0].id);
}

async function selectSquad(id) {
  S.squad = S.squads.find((s) => s.id === id); S.pid = null;
  $("#top .mark").textContent = S.squad.age_group || "U15";
  $("#squad").value = id;
  S.seasons = await api(`/squads/${id}/seasons`);
  S.season = S.seasons[0] || null;
  drawTabs(); go(S.tab);
}

function drawTabs() {
  const tabs = S.squad ? [["players", "Players"], ["calendar", "Calendar"]] : [];
  if (S.squad && !can("player")) tabs.unshift(["overview", "Overview"]);
  if (S.squad && !can("player")) tabs.push(["fitness", "Fitness"]);
  if (S.squad && can("coach", "sc_coach", "physio", "admin")) tabs.push(["workload", "Workload"]);
  if (S.squad && can("coach", "sc_coach", "admin")) tabs.push(["tests", "Tests"]);
  if (S.squad && can("coach", "admin")) tabs.push(["plan", "Seasonal plan"]);
  if (can("admin")) tabs.push(["admin", "Admin"]);
  const nav = $("#tabs"); nav.hidden = false;
  nav.replaceChildren(...tabs.map(([k, label]) => h("button", { "aria-current": S.tab === k ? "page" : null, onclick: () => { S.pid = null; go(k); } }, label)));
}

function go(tab) {
  S.tab = tab; drawTabs();
  Charts.hide();
  document.body.classList.toggle("wide", tab === "overview");
  const view = { overview: overviewTab, players: S.pid ? () => playerView(S.pid) : playersTab, calendar: calendarTab, fitness: fitnessTab, workload: workloadTab, tests: testingTab, plan: () => planTab(), admin: adminTab }[tab];
  Promise.resolve(view()).catch((x) => $("#main").replaceChildren(h("div", { class: "err" }, x.message)));
}

const field = (label, input) => h("label", {}, label, input);
const seasonPicker = (onchange) => S.seasons.length
  ? h("select", { "aria-label": "Season", onchange: (e) => { S.season = S.seasons.find((s) => s.id === +e.target.value); onchange(); } },
      S.seasons.map((s) => h("option", { value: s.id, selected: S.season && s.id === S.season.id }, s.name)))
  : null;

// ───────────── overview dashboard ─────────────
// Colour follows the entity: each player role always has the same slot, whatever is filtered or missing.
const ROLE_ORDER = ["fast_bowler", "spin_bowler", "batter", "bat_wicketkeeper", "all_rounder"];
const ROLE_CLS = Object.fromEntries(ROLE_ORDER.map((r, i) => [r, "c-s" + (i + 1)]));
const AVAIL = [["fit", "Fit", "c-good"], ["modified", "Modified", "c-warning"], ["unavailable", "Unavailable", "c-critical"]];
const ACWR_STATE = (v) => (v == null ? null : v >= 1.5 ? ["High", "c-critical"] : v >= 1.3 ? ["Raised", "c-warning"] : v < 0.8 ? ["Low", "c-info"] : ["In range", "c-good"]);
const card = (title, sub, ...body) => h("section", { class: "card viz-card" }, h("div", { class: "card-head" }, h("h2", {}, title), sub ? h("p", { class: "sub" }, sub) : null), body);

async function overviewTab() {
  const main = $("#main");
  main.replaceChildren(h("div", { class: "empty loading" }, "Loading overview…"));
  const now = new Date();
  if (!S.ages) S.ages = await api("/meta/age-groups").catch(() => []);
  const ageProf = S.ages.find((a) => a.code === S.squad.age_group) || null;
  const lim = ageProf ? ageProf.fast_limits : null;
  const [players, rows, alerts, events] = await Promise.all([
    api(`/players?squad_id=${S.squad.id}`), api(`/squads/${S.squad.id}/workload/overview`), api(`/squads/${S.squad.id}/alerts`),
    api(`/squads/${S.squad.id}/events?from=${encodeURIComponent(now.toISOString())}&to=${encodeURIComponent(new Date(+now + 14 * 864e5).toISOString())}`)]);
  const openPlayer = (id) => () => { S.pid = id; go("players"); };
  const n = players.length;
  const count = (k) => players.filter((p) => p.availability === k).length;
  const fit = count("fit"), pctFit = n ? Math.round((fit / n) * 100) : 0;
  const stop = alerts.filter((a) => a.severity === "stop").length, warn = alerts.filter((a) => a.severity === "warn").length;
  const loads = rows.map((r) => r.acute_load_7d || 0).filter((v) => v > 0);
  const avgLoad = loads.length ? Math.round(loads.reduce((a, b) => a + b, 0) / loads.length) : null;
  const nextMatch = events.find((e) => e.event_type === "match");

  const head = h("div", { class: "page-head" },
    h("div", {}, h("h1", {}, "Squad overview"), h("p", { class: "sub" }, [S.squad.name, ageProf ? ageProf.label : S.squad.age_group, S.season ? "Season " + S.season.name : null,
      now.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })].filter(Boolean).join(" · "))),
    h("div", { class: "row" }, h("button", { class: "small ghost", onclick: () => go("workload") }, "Workload details"), h("button", { class: "small ghost", onclick: () => go("players") }, "All players")));

  const kpis = h("div", { class: "kpis" },
    Charts.stat({ label: "Players", value: n, sub: `${players.filter((p) => BOWLS.includes(p.role)).length} bowl · ${players.filter((p) => BATS.includes(p.role)).length} bat` }),
    Charts.stat({ label: "Fit to train", value: n ? `${pctFit}%` : "–", sub: `${fit} of ${n} players`, tone: n && fit < n ? "warning" : n ? "good" : null }),
    Charts.stat({ label: "Open alerts", value: alerts.length, sub: alerts.length ? `${stop} stop · ${warn} warning` : "Nothing needs attention", tone: stop ? "critical" : warn ? "warning" : "good" }),
    Charts.stat({ label: "Average 7-day load", value: avgLoad == null ? "–" : avgLoad.toLocaleString(), sub: avgLoad == null ? "No sessions logged this week" : `units · ${loads.length} player(s) logged` }),
    Charts.stat({ label: "Next match", value: nextMatch ? new Date(fixTz(nextMatch.start_at)).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "–",
      sub: nextMatch ? nextMatch.title : "None in the next 14 days" }));

  const availability = Charts.donut({ title: "Availability", parts: AVAIL.map(([k, label, cls]) => ({ label, value: count(k), cls })),
    center: { value: n ? pctFit + "%" : "–", label: "fit" } });
  const roles = Charts.donut({ title: "Squad by role", parts: ROLE_ORDER.map((r) => ({ label: ROLE[r], value: players.filter((p) => p.role === r).length, cls: ROLE_CLS[r] })),
    center: { value: n, label: "players" } });

  const byLoad = [...rows].sort((a, b) => (b.acute_load_7d || 0) - (a.acute_load_7d || 0));
  const loadChart = Charts.hbars({ ariaLabel: "Load in the last 7 days by player",
    data: byLoad.map((r) => ({ label: r.name, sub: ROLE[r.role], value: r.acute_load_7d || 0, cls: ROLE_CLS[r.role], onClick: openPlayer(r.player_id),
      display: (r.acute_load_7d || 0).toLocaleString(), tip: [r.name, `${(r.acute_load_7d || 0).toLocaleString()} units in 7 days`, ROLE[r.role],
        r.vs_last_week_pct == null ? null : `${r.vs_last_week_pct > 0 ? "+" : ""}${r.vs_last_week_pct}% vs last week`] })),
    refs: avgLoad ? [{ value: avgLoad, label: "avg " + avgLoad.toLocaleString() }] : [], empty: "No players yet." });
  const presentRoles = ROLE_ORDER.filter((r) => rows.some((x) => x.role === r));

  const withRatio = rows.filter((r) => r.acwr != null).sort((a, b) => b.acwr - a.acwr);
  const waiting = rows.length - withRatio.length;
  const ratioChart = Charts.hbars({ ariaLabel: "Load ratio by player", max: 2,
    data: withRatio.map((r) => { const [word, cls] = ACWR_STATE(r.acwr); return { label: r.name, value: r.acwr, cls, display: `${r.acwr} · ${word}`, onClick: openPlayer(r.player_id),
      tip: [r.name, `Load ratio ${r.acwr} (${word.toLowerCase()})`, "Last 7 days ÷ 4-week weekly average"] }; }),
    refs: [{ value: 1.3, label: "1.3" }, { value: 1.5, label: "1.5" }],
    empty: "No player has 3 weeks of logged sessions yet, so there is no load ratio." });

  const bowlers = rows.filter((r) => BOWLS.includes(r.role)).sort((a, b) => (b.overs_7d || 0) - (a.overs_7d || 0));
  const oversChart = Charts.hbars({ ariaLabel: "Overs bowled in the last 7 days", format: (v) => Charts.num(v, 1),
    data: bowlers.map((r) => ({ label: r.name, sub: `${r.bowling_days_7d} bowling day(s)`, value: r.overs_7d || 0, cls: ROLE_CLS[r.role], onClick: openPlayer(r.player_id),
      display: Charts.num(r.overs_7d || 0, 1), tip: [r.name, `${Charts.num(r.overs_7d || 0, 1)} overs in 7 days`, `${r.bowling_days_7d} bowling day(s)`, ROLE[r.role]] })),
    empty: "No bowlers in this squad." });

  const upcoming = events.length ? h("ol", { class: "agenda" }, events.slice(0, 6).map((e) => {
    const d = new Date(fixTz(e.start_at));
    return h("li", {}, h("span", { class: "agenda-date" }, h("span", { class: "agenda-day" }, d.getDate()), h("span", { class: "agenda-mon" }, d.toLocaleDateString(undefined, { month: "short" }))),
      h("span", { class: "agenda-text" }, h("strong", {}, e.title), h("span", { class: "sub" }, d.toLocaleDateString(undefined, { weekday: "short" }) + " " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) + (e.venue ? " · " + e.venue : ""))),
      h("span", { class: "chip " + e.event_type }, EVT[e.event_type]));
  })) : h("p", { class: "sub" }, "Nothing scheduled in the next 14 days.");

  const ageNotice = ageProf && ageProf.code !== "U15" ? h("div", { class: "age-notice", role: "note" },
    h("strong", {}, `${ageProf.label} rules are provisional. `),
    `Fast bowlers: ${lim.max_spell_overs} overs a spell, ${lim.max_match_day_overs} a match day (caution at ${lim.caution_match_day_overs}), ${lim.max_bowling_days_week} bowling days in 7. `,
    "These are placeholders until SLC confirms them. Tests use the " + ageProf.test_battery + ".") : null;
  main.replaceChildren(head, ageNotice, kpis,
    h("div", { class: "dash-grid two" },
      card("Availability", "Set by the physiotherapist.", availability),
      card("Squad by role", null, roles)),
    h("div", { class: "dash-grid wide-left" },
      card("Training load, last 7 days", "RPE × minutes. Line = squad average.",
        presentRoles.length > 1 ? Charts.legend(presentRoles.map((r) => ({ cls: ROLE_CLS[r], label: ROLE[r] }))) : null, loadChart),
      card("Open alerts", alerts.length ? `${alerts.length} open` : null, alertList(alerts.slice(0, 5)),
        alerts.length > 5 ? h("button", { class: "small ghost", onclick: () => go("workload") }, `See all ${alerts.length} alerts`) : null)),
    h("div", { class: "dash-grid wide-left" },
      card("Load ratio", "7-day ÷ 4-week average. Raised above 1.3, high above 1.5." + (waiting ? ` ${waiting} need 3 weeks of logs.` : ""), ratioChart),
      card("Coming up", "Next 14 days", upcoming)),
    bowlers.length ? card("Bowling, last 7 days", lim ? `${S.squad.age_group} fast-bowler limits: ${lim.max_spell_overs} a spell · ${lim.max_match_day_overs} a day · ${lim.max_bowling_days_week} days in 7` : null, oversChart) : null);
}
const fixTz = (s) => (s.endsWith("Z") || /[+-]\d\d:\d\d$/.test(s) ? s : s + "Z");

// ───────────── players ─────────────
async function playersTab() {
  const players = await api(`/players?squad_id=${S.squad.id}`);
  const main = $("#main");
  main.replaceChildren(
    h("div", { class: "bar" }, h("h1", {}, S.squad.name), can("coach", "admin") ? h("button", { onclick: () => addPlayerForm() }, "+ Add player") : null),
    players.length ? h("div", { class: "list" }, players.map((p) => h("button", { class: "item", onclick: () => { S.pid = p.id; go("players"); } },
      h("span", {}, h("strong", {}, (p.squad_no ? "#" + p.squad_no + "  " : "") + p.full_name), h("br"), h("span", { class: "sub" }, ROLE[p.role] + " · age " + p.age)),
      h("span", { class: "chip " + p.availability }, p.availability)))) : h("div", { class: "empty" }, "No players in this squad yet."));
}

function addPlayerForm() {
  const f = { name: h("input", { required: true }), dob: h("input", { type: "date", required: true }), no: h("input", { type: "number", min: 1, max: 99 }),
    gender: h("select", {}, h("option", { value: "male" }, "Male"), h("option", { value: "female" }, "Female")),
    role: h("select", {}, Object.entries(ROLE).map(([k, v]) => h("option", { value: k }, v))) };
  const err = h("div", { class: "err", role: "alert" });
  $("#main").replaceChildren(h("form", { class: "card", onsubmit: async (e) => {
    e.preventDefault(); err.textContent = "";
    try {
      const p = await api("/players", { method: "POST", body: { squad_id: S.squad.id, full_name: f.name.value.trim(), date_of_birth: f.dob.value, gender: f.gender.value, role: f.role.value, squad_no: f.no.value ? +f.no.value : null } });
      toast("Player added"); S.pid = p.id; go("players");
    } catch (x) { err.textContent = x.message; }
  } }, h("h1", {}, "Add player"), h("div", { class: "grid" }, field("Full name", f.name), field("Date of birth", f.dob), field("Squad number", f.no), field("Gender", f.gender), field("Role", f.role)),
    err, h("div", { class: "row" }, h("button", { type: "submit" }, "Save"), h("button", { type: "button", class: "ghost", onclick: () => go("players") }, "Cancel"))));
}

async function playerView(id) {
  const [p, screenings] = await Promise.all([api("/players/" + id), api(`/players/${id}/screenings`)]);
  const main = $("#main");
  const back = h("button", { class: "ghost small", onclick: () => { S.pid = null; go("players"); } }, "← Players");
  const head = h("div", { class: "card" }, h("div", { class: "bar" }, h("h1", {}, p.full_name), h("span", { class: "chip " + p.availability }, p.availability)),
    h("div", { class: "sub" }, `${ROLE[p.role]} · age ${p.age} · ${p.gender}` + (p.school_or_club ? " · " + p.school_or_club : "")),
    p.availability_note ? h("p", {}, "Note: " + p.availability_note) : null,
    h("div", { class: "sub" }, [p.batting_hand && "Bats " + p.batting_hand, p.bowling_arm && "Bowls " + p.bowling_arm, p.guardian_name && "Guardian: " + p.guardian_name].filter(Boolean).join(" · ")));
  main.replaceChildren(back, head);

  // screening
  const sc = screenings[0];
  const scCard = h("div", { class: "card" }, h("div", { class: "bar" }, h("h2", {}, "Initial screening"),
    can("coach", "sc_coach", "admin") ? h("button", { class: "small", onclick: () => screeningForm(p) }, sc ? "New screening" : "Start screening") : null));
  if (!sc) scCard.append(h("div", { class: "sub" }, "No screening recorded yet."));
  else {
    scCard.append(h("div", { class: "sub" }, "Screened on " + sc.screening_date),
      sc.this_year_objective ? h("p", {}, h("strong", {}, "This year's objective: "), sc.this_year_objective) : null,
      sc.life_ambition ? h("p", {}, h("strong", {}, "Ambition: "), sc.life_ambition) : null);
    if (sc.needs.length) scCard.append(h("h3", {}, "Needs analysis"), h("div", { class: "scroll" }, h("table", {}, h("tbody", {},
      sc.needs.map((n) => h("tr", {}, h("td", {}, n.category + " – " + n.item), h("td", { class: n.level === "LOW" ? "down" : n.level === "HIGH" ? "up" : "flat" }, n.level)))))));
  }
  main.append(scCard);

  // fitness
  const fit = h("div", { class: "card" });
  main.append(fit);
  await drawProgress(p, fit);

  // workload
  const wl = h("div", { class: "card" });
  main.append(wl);
  await workloadCard(p, wl);

  // SLC U15 physical tests (coach, S&C, admin; never players)
  if (can("coach", "sc_coach", "admin")) { const pc = h("div", { class: "card" }); main.append(pc); await pdpCard(p, pc); }
  if (can("coach", "sc_coach", "admin")) { const rc = h("div", { class: "card" }); main.append(rc); await roleSkillsCard(p, rc); }
  if (can("coach", "sc_coach", "admin")) { const tc = h("div", { class: "card" }); main.append(tc); await testingCard(p, tc); }

  // medical (physio only)
  if (can("physio")) await medicalPanel(p);
}

// ───────────── screening form ─────────────
async function screeningForm(p) {
  const grid = await api("/meta/needs-grid");
  const f = {
    date: h("input", { type: "date", required: true, value: new Date().toISOString().slice(0, 10) }),
    band: h("select", {}, [["", "–"], ["less_than_5", "Less than 5 years"], ["5_to_10", "5-10 years"], ["over_10", "Over 10 years"]].map(([v, l]) => h("option", { value: v }, l))),
    start: h("input", { type: "number", min: 3, max: 16 }),
    f3: h("input", { type: "number", min: 0, max: 100 }), f1: h("input", { type: "number", min: 0, max: 100 }), ft: h("input", { type: "number", min: 0, max: 100 }),
    bowler: h("input"), shot: h("input"), plan: h("textarea"), obj: h("textarea"), amb: h("textarea"), yoyo: h("input"), twok: h("input"),
  };
  const err = h("div", { class: "err", role: "alert" });
  const needs = [];
  const needsEl = Object.entries(grid).map(([cat, items]) => h("div", {}, h("h3", {}, cat), items.map((it) => {
    const name = "n_" + cat + it;
    const ctl = ["LOW", "MOD", "HIGH"].map((lv) => h("label", {}, h("input", { type: "radio", name, value: lv }), lv));
    needs.push({ cat, it, name });
    return h("div", { class: "need" }, h("span", {}, it), h("span", { class: "opts" }, ctl));
  })));
  $("#main").replaceChildren(h("form", { class: "card", onsubmit: async (e) => {
    e.preventDefault(); err.textContent = "";
    const pct = { "3day": +f.f3.value || 0, oneday: +f.f1.value || 0, t20: +f.ft.value || 0 };
    const body = { screening_date: f.date.value, years_playing_band: f.band.value || null, start_age: f.start.value ? +f.start.value : null,
      format_played_pct: Object.values(pct).some(Boolean) ? pct : null, favourite_bowler_to_bat: f.bowler.value || null, favourite_shot: f.shot.value || null,
      game_plan_tactic: f.plan.value || null, this_year_objective: f.obj.value || null, life_ambition: f.amb.value || null,
      yoyo_last_time: f.yoyo.value || null, two_km_last_time: f.twok.value || null,
      needs: needs.map((n) => ({ n, v: document.querySelector(`input[name="${CSS.escape(n.name)}"]:checked`) })).filter((x) => x.v).map((x) => ({ category: x.n.cat, item: x.n.it, level: x.v.value })) };
    try { await api(`/players/${p.id}/screenings`, { method: "POST", body }); toast("Screening saved"); go("players"); } catch (x) { err.textContent = x.message; }
  } }, h("h1", {}, "Initial screening – " + p.full_name),
    h("div", { class: "grid" }, field("Screening date", f.date), field("Years playing", f.band), field("Age started", f.start), field("Yo-Yo score last time", f.yoyo), field("2 km time last time", f.twok)),
    h("h2", {}, "Formats played (%)"), h("div", { class: "grid" }, field("3-day", f.f3), field("One-day", f.f1), field("T20", f.ft)),
    h("div", { class: "grid" }, field("Favourite bowler to bat against", f.bowler), field("Favourite shot", f.shot)),
    field("Game plan and tactic", f.plan), field("This year's objective", f.obj), field("Life ambition", f.amb),
    h("h2", {}, "Needs analysis"), needsEl, err,
    h("div", { class: "row" }, h("button", { type: "submit" }, "Save screening"), h("button", { type: "button", class: "ghost", onclick: () => go("players") }, "Cancel"))));
}

// ───────────── medical (physio) ─────────────
async function medicalPanel(p) {
  const m = await api(`/players/${p.id}/medical`);
  const inj = m.injury_history || {};
  const av = h("select", {}, ["fit", "modified", "unavailable"].map((v) => h("option", { value: v, selected: p.availability === v }, v)));
  const note = h("input", { maxLength: 300, value: p.availability_note || "", placeholder: "Coach-safe wording only" });
  const health = h("textarea", {}, m.current_health || ""), notes = h("textarea", {}, inj.notes || "");
  const err = h("div", { class: "err", role: "alert" });
  $("#main").append(h("form", { class: "card", onsubmit: async (e) => {
    e.preventDefault(); err.textContent = "";
    try {
      await api(`/players/${p.id}/availability`, { method: "PUT", body: { availability: av.value, availability_note: note.value || null } });
      await api(`/players/${p.id}/medical`, { method: "PUT", body: { current_health: health.value || null, injury_history: { ...inj, notes: notes.value || null } } });
      toast("Saved"); go("players");
    } catch (x) { err.textContent = x.message; }
  } }, h("h2", {}, "Medical & availability"), h("p", { class: "sub" }, "Physiotherapists only. Every access is logged; others see availability only."),
    h("div", { class: "grid" }, field("Availability", av), field("Note shown to coaches", note)),
    field("Current health", health), field("Injury history notes", notes), err, h("button", { type: "submit" }, "Save")));
}

// ───────────── calendar ─────────────
async function calendarTab() {
  const from = new Date(Date.now() - 7 * 864e5).toISOString();
  const events = await api(`/squads/${S.squad.id}/events?from=${encodeURIComponent(from)}`);
  const canEdit = can("coach", "sc_coach", "admin");
  const main = $("#main");
  main.replaceChildren(h("div", { class: "bar" }, h("h1", {}, "Calendar"), canEdit ? h("div", { class: "row" },
    h("button", { class: "small", onclick: () => eventForm() }, "+ Event"), h("button", { class: "small ghost", onclick: () => seasonForm() }, "+ Season")) : null));
  if (S.season) main.append(h("p", { class: "sub" }, `Season ${S.season.name}: ${S.season.start_date} to ${S.season.end_date}`));
  else main.append(h("div", { class: "card" }, "No season yet. " + (canEdit ? "Add one with “+ Season” – fitness tests belong to a season." : "")));
  if (!events.length) return main.append(h("div", { class: "empty" }, "No events scheduled."));
  let day = "";
  const list = h("div", { class: "list" });
  for (const ev of events) {
    const d = new Date(ev.start_at.endsWith("Z") || /[+-]\d\d:\d\d$/.test(ev.start_at) ? ev.start_at : ev.start_at + "Z");
    const dl = d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "short" });
    if (dl !== day) { day = dl; list.append(h("h3", {}, dl)); }
    list.append(h("div", { class: "item" }, h("span", {}, h("strong", {}, ev.title), h("br"),
      h("span", { class: "sub" }, d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) + (ev.venue ? " · " + ev.venue : "") + (ev.intensity_planned ? " · intensity " + ev.intensity_planned + "/10" : ""))),
      h("span", { class: "row" }, h("span", { class: "chip " + ev.event_type }, EVT[ev.event_type]),
        canEdit ? h("button", { class: "ghost small", "aria-label": "Delete " + ev.title, onclick: async () => { if (confirm("Delete this event?")) { await api("/events/" + ev.id, { method: "DELETE" }); go("calendar"); } } }, "✕") : null)));
  }
  main.append(list);
}

function eventForm() {
  const f = { type: h("select", {}, Object.entries(EVT).map(([k, v]) => h("option", { value: k }, v))), title: h("input", { required: true }),
    start: h("input", { type: "datetime-local", required: true }), end: h("input", { type: "datetime-local" }), venue: h("input"),
    inten: h("input", { type: "number", min: 1, max: 10, placeholder: "1-10" }), notes: h("textarea") };
  const err = h("div", { class: "err", role: "alert" });
  $("#main").replaceChildren(h("form", { class: "card", onsubmit: async (e) => {
    e.preventDefault(); err.textContent = "";
    try {
      await api(`/squads/${S.squad.id}/events`, { method: "POST", body: { event_type: f.type.value, title: f.title.value.trim(), start_at: new Date(f.start.value).toISOString(),
        end_at: f.end.value ? new Date(f.end.value).toISOString() : null, venue: f.venue.value || null, intensity_planned: f.inten.value ? +f.inten.value : null, notes: f.notes.value || null } });
      toast("Event added"); go("calendar");
    } catch (x) { err.textContent = x.message; }
  } }, h("h1", {}, "New event"), h("div", { class: "grid" }, field("Type", f.type), field("Title", f.title), field("Starts", f.start), field("Ends (optional)", f.end), field("Venue", f.venue), field("Planned intensity", f.inten)),
    field("Notes", f.notes), err, h("div", { class: "row" }, h("button", { type: "submit" }, "Save"), h("button", { type: "button", class: "ghost", onclick: () => go("calendar") }, "Cancel"))));
}

// ───────────── fitness ─────────────
const FIELDS = [["bodyweight_kg", "Bodyweight (kg)", "0.1"], ["height_cm", "Height (cm)", "0.1"], ["cmj_cm", "Countermovement jump (cm)", "0.1"], ["squat_jump_cm", "Squat jump (cm)", "0.1"],
  ["sprint_5m_s", "5 m sprint (s)", "0.01"], ["sprint_10m_s", "10 m sprint (s)", "0.01"], ["sprint_20m_s", "20 m sprint (s)", "0.01"], ["yoyo_level", "Yo-Yo IR1 level (e.g. 15.3)", null],
  ["yoyo_distance_m", "Yo-Yo distance (m)", "1"], ["prone_plank_s", "Prone plank (s)", "1"], ["side_plank_front_s", "Side plank, front (s)", "1"], ["side_plank_back_s", "Side plank, back (s)", "1"],
  ["calf_raises_front_leg", "Calf raises, front leg", "1"], ["calf_raises_back_leg", "Calf raises, back leg", "1"]];

async function fitnessTab() {
  const main = $("#main");
  if (!S.season) return main.replaceChildren(h("h1", {}, "Fitness"), h("div", { class: "card" }, "Create a season first (Admin tab → + Season)."));
  const phase = S.phase || "baseline";
  const rows = await api(`/squads/${S.squad.id}/fitness?season_id=${S.season.id}&phase=${phase}`);
  const cols = [["name", "Name"], ["bowling_arm", "Arm"], ["bodyweight_kg", "kg"], ["height_cm", "cm"], ["cmj_cm", "CMJ"], ["squat_jump_cm", "SJ"], ["sprint_5m_s", "5m"], ["sprint_10m_s", "10m"], ["sprint_20m_s", "20m"],
    ["yoyo_level", "Yo-Yo"], ["yoyo_distance_m", "Yo-Yo m"], ["prone_plank_s", "Plank"], ["side_plank_front_s", "Side F"], ["side_plank_back_s", "Side B"], ["calf_raises_front_leg", "Calf F"], ["calf_raises_back_leg", "Calf B"]];
  main.replaceChildren(h("div", { class: "bar" }, h("h1", {}, "Fitness report"), h("div", { class: "row" }, seasonPicker(fitnessTab),
    h("select", { "aria-label": "Test phase", onchange: (e) => { S.phase = e.target.value; fitnessTab(); } }, Object.entries(PHASE).map(([k, v]) => h("option", { value: k, selected: k === phase }, v))))),
    h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, cols.map(([, l]) => h("th", {}, l)))),
      h("tbody", {}, rows.map((r) => h("tr", { class: "click", tabindex: 0, onclick: () => fitnessForm({ id: r.player_id, full_name: r.name, role: r.role }, phase),
        onkeydown: (e) => e.key === "Enter" && fitnessForm({ id: r.player_id, full_name: r.name, role: r.role }, phase) }, cols.map(([k]) => h("td", {}, fmt(r[k])))))))),
    h("p", { class: "sub" }, "Select a row to enter results. Empty = not tested."),
    can("coach", "sc_coach", "admin") ? benchmarkCard() : null);
}

function benchmarkCard() {
  const fld = h("select", {}, FIELDS.filter(([k]) => !["bodyweight_kg", "height_cm", "yoyo_level"].includes(k)).map(([k, l]) => h("option", { value: k }, l)));
  const val = h("input", { type: "number", step: "any", required: true });
  const err = h("div", { class: "err", role: "alert" });
  return h("form", { class: "card", onsubmit: async (e) => {
    e.preventDefault(); err.textContent = "";
    try { await api(`/squads/${S.squad.id}/fitness-benchmarks`, { method: "PUT", body: { field_name: fld.value, target_value: +val.value } }); toast("Benchmark saved"); val.value = ""; } catch (x) { err.textContent = x.message; }
  } }, h("h3", {}, "Coach benchmark for this squad"), h("p", { class: "sub" }, "Your own provisional targets. No adult standards."),
    h("div", { class: "grid" }, field("Test", fld), field("Target value", val)), err, h("button", { class: "small", type: "submit" }, "Save benchmark"));
}

async function fitnessForm(p, phase) {
  if (!S.season) return toast("Create a season first");
  const existing = (await api(`/players/${p.id}/fitness?season_id=${S.season.id}`)).find((t) => t.phase === phase) || {};
  const kpis = p.role ? await api(`/meta/role-kpis/${p.role}`) : [];
  const kinputs = kpis.map((m) => [m.field, h("input", { type: "number", step: m.unit === "1-5 rating" ? "1" : "any", min: m.lo, max: m.hi, inputMode: "decimal", value: (existing.role_specific || {})[m.field] ?? "" }), `${m.label} (${m.unit})`]);
  const ph = h("select", { onchange: () => fitnessForm(p, ph.value) }, Object.entries(PHASE).map(([k, v]) => h("option", { value: k, selected: k === phase }, v)));
  const date = h("input", { type: "date", required: true, value: existing.test_date || new Date().toISOString().slice(0, 10) });
  const inputs = FIELDS.map(([k, l, step]) => [k, h("input", { type: step ? "number" : "text", step, value: typeof existing[k] === "number" ? +existing[k].toFixed(3) : existing[k] ?? "", inputMode: "decimal" }), l]);
  const err = h("div", { class: "err", role: "alert" });
  $("#main").replaceChildren(h("form", { class: "card", onsubmit: async (e) => {
    e.preventDefault(); err.textContent = "";
    const body = { test_date: date.value };
    for (const [k, el] of inputs) if (el.value !== "") body[k] = el.type === "number" ? +el.value : el.value; else if (existing[k] != null) body[k] = null;
    const rs = {};
    for (const [k, el] of kinputs) if (el.value !== "") rs[k] = +el.value; else if ((existing.role_specific || {})[k] != null) rs[k] = null;
    if (Object.keys(rs).length) body.role_specific = rs;
    try { await api(`/players/${p.id}/fitness/${S.season.id}/${ph.value}`, { method: "PUT", body }); toast("Results saved"); S.phase = ph.value; S.pid = p.id; go(S.tab === "fitness" ? "fitness" : "players"); }
    catch (x) { err.textContent = x.message; }
  } }, h("h1", {}, "Fitness results – " + p.full_name), h("div", { class: "grid" }, field("Season", h("input", { value: S.season.name, disabled: true })), field("Test phase", ph), field("Test date", date)),
    h("div", { class: "grid" }, inputs.map(([, el, l]) => field(l, el))),
    kinputs.length ? [h("h2", {}, "Role-specific measures"), h("div", { class: "grid" }, kinputs.map(([, el, l]) => field(l, el)))] : null, err,
    h("div", { class: "row" }, h("button", { type: "submit" }, "Save results"), h("button", { type: "button", class: "ghost", onclick: () => go(S.tab) }, "Cancel"))));
}

// ───────────── shared helpers (admin + plan) ─────────────
const STATUS = { not_started: "Not started", in_progress: "In progress", achieved: "Achieved", revised: "Revised", dropped: "Dropped" };
const PHASE_NAME = { pre_season: "Pre-season", pre_competition: "Pre-competition", in_season: "In-season", transition: "Transition / off-season" };
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const fdate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
const kv = (k, v) => h("div", { class: "kv" }, h("span", { class: "k" }, k), h("span", {}, v));
const roleLabel = (r) => r.replace(/_/g, " ");

async function refreshSquads(selectId) {
  S.squads = await api("/squads");
  $("#squad").replaceChildren(...S.squads.map((s) => h("option", { value: s.id }, s.name)));
  if (S.squads.length) return selectSquad(S.squads.some((s) => s.id === selectId) ? selectId : S.squads[0].id);
  S.squad = null; S.seasons = []; S.season = null; drawTabs(); go("admin");
}

function metricTable(rows) {
  return h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Measure", "Baseline", "Mid", "End", "Change", "Squad %", "Target"].map((c) => h("th", {}, c)))),
    h("tbody", {}, rows.map((m) => {
      const cls = m.improved === true ? "up" : m.improved === false ? "down" : "flat";
      const arrow = m.change_from_baseline == null ? "–" : (m.change_from_baseline > 0 ? "▲ +" : m.change_from_baseline < 0 ? "▼ " : "") + fmt(m.change_from_baseline) + (m.change_pct != null ? ` (${m.change_pct}%)` : "");
      const tgt = m.individual_target ?? m.coach_benchmark;
      const st = m.individual_target != null ? m.individual_target_status : m.coach_benchmark_status;
      return h("tr", {}, h("td", {}, `${m.label} (${m.unit})`), h("td", {}, fmt(m.baseline)), h("td", {}, fmt(m.mid_season)), h("td", {}, fmt(m.end_season)),
        h("td", { class: cls }, arrow), h("td", {}, m.squad_percentile == null ? "–" : Math.round(m.squad_percentile)),
        h("td", { class: st === "met" ? "up" : "" }, tgt == null ? "–" : fmt(tgt) + (st === "met" ? " ✓" : "")));
    }))));
}

async function drawProgress(p, host) {
  host.replaceChildren(h("div", { class: "bar" }, h("h2", {}, "Fitness progress"), seasonPicker(() => drawProgress(p, host))));
  if (!S.season) return host.append(h("div", { class: "sub" }, "No season set up for this squad yet (Admin tab)."));
  const rep = await api(`/players/${p.id}/fitness/progress?season_id=${S.season.id}`);
  const rows = rep.metrics.filter((m) => m.baseline != null || m.current != null);
  const roleRows = rep.role_metrics.filter((m) => m.baseline != null || m.current != null);
  if (!rows.length && !roleRows.length) host.append(h("div", { class: "sub" }, "No results entered for this season."));
  if (rows.length) host.append(metricTable(rows));
  if (roleRows.length) host.append(h("h3", {}, "Role-specific measures (" + roleLabel(rep.role) + ")"), metricTable(roleRows));
  host.append(h("p", { class: "sub" }, "Against the player's own baseline and targets. Squad % needs 5+ players tested."));
  if (can("coach", "sc_coach", "admin")) host.append(h("button", { class: "small", onclick: () => fitnessForm(p, "baseline") }, "Enter / edit results"));
}

// ───────────── phase editor ─────────────
function phaseEditor(initial) {
  const rows = [];
  const box = h("div", {});
  function addRow(p = {}) {
    const r = {
      type: h("select", {}, Object.entries(PHASE_NAME).map(([v, l]) => h("option", { value: v, selected: p.phase_type === v }, l))),
      s: h("input", { type: "date", value: p.start_date || "" }), e: h("input", { type: "date", value: p.end_date || "" }),
      focus: h("input", { value: p.focus || "", maxLength: 300 }),
    };
    r.el = h("div", { class: "card" }, h("div", { class: "grid" }, field("Phase", r.type), field("Starts", r.s), field("Ends", r.e)), field("Focus (optional)", r.focus),
      h("button", { type: "button", class: "ghost small", onclick: () => { rows.splice(rows.indexOf(r), 1); r.el.remove(); } }, "Remove phase"));
    rows.push(r); box.append(r.el);
  }
  (initial || []).forEach(addRow);
  return {
    el: box, add: () => addRow(),
    set: (list) => { rows.splice(0).forEach((r) => r.el.remove()); list.forEach(addRow); },
    get: () => rows.map((r) => ({ phase_type: r.type.value, start_date: r.s.value, end_date: r.e.value, focus: r.focus.value || null })),
  };
}

function seasonForm(back = "calendar") {
  const y = new Date().getFullYear();
  const f = { name: h("input", { required: true, value: `${y}/${String(y + 1).slice(2)}` }), s: h("input", { type: "date", required: true }), e: h("input", { type: "date", required: true }) };
  const ed = phaseEditor([]);
  const err = h("div", { class: "err", role: "alert" });
  const suggest = async () => {
    err.textContent = "";
    if (!f.s.value || !f.e.value) { err.textContent = "Enter the season start and end dates first."; return; }
    try { ed.set(await api(`/season-phase-suggestion?start_date=${f.s.value}&end_date=${f.e.value}`)); } catch (x) { err.textContent = x.message; }
  };
  $("#main").replaceChildren(h("form", { class: "card", onsubmit: async (ev) => {
    ev.preventDefault(); err.textContent = "";
    try {
      await api(`/squads/${S.squad.id}/seasons`, { method: "POST", body: { name: f.name.value.trim(), start_date: f.s.value, end_date: f.e.value, phases: ed.get() } });
      toast("Season added"); S.tab = back; await selectSquad(S.squad.id);
    } catch (x) { err.textContent = x.message; }
  } }, h("h1", {}, "New season"), h("div", { class: "grid" }, field("Name", f.name), field("Starts", f.s), field("Ends", f.e)),
    h("h2", {}, "Phases"), h("p", { class: "sub" }, "Optional. Leave empty to use a suggested split."), ed.el,
    h("div", { class: "row" }, h("button", { type: "button", class: "ghost small", onclick: () => ed.add() }, "+ Add phase"), h("button", { type: "button", class: "ghost small", onclick: suggest }, "Suggest a split")),
    err, h("div", { class: "row" }, h("button", { type: "submit" }, "Save season"), h("button", { type: "button", class: "ghost", onclick: () => go(back) }, "Cancel"))));
}

function editPhases(season) {
  const ed = phaseEditor(season.phases);
  const err = h("div", { class: "err", role: "alert" });
  const suggest = async () => {
    err.textContent = "";
    try { ed.set(await api(`/season-phase-suggestion?start_date=${season.start_date}&end_date=${season.end_date}`)); } catch (x) { err.textContent = x.message; }
  };
  $("#main").replaceChildren(h("form", { class: "card", onsubmit: async (ev) => {
    ev.preventDefault(); err.textContent = "";
    try { await api(`/seasons/${season.id}/phases`, { method: "PUT", body: ed.get() }); toast("Phases saved"); S.tab = "admin"; await selectSquad(S.squad.id); }
    catch (x) { err.textContent = x.message; }
  } }, h("h1", {}, "Phases – " + season.name), h("p", { class: "sub" }, `${fdate(season.start_date)} to ${fdate(season.end_date)}. Phases must fit inside the season without overlapping.`), ed.el,
    h("div", { class: "row" }, h("button", { type: "button", class: "ghost small", onclick: () => ed.add() }, "+ Add phase"), h("button", { type: "button", class: "ghost small", onclick: suggest }, "Replace with a suggested split")),
    err, h("div", { class: "row" }, h("button", { type: "submit" }, "Save phases"), h("button", { type: "button", class: "ghost", onclick: () => go("admin") }, "Cancel"))));
}

// ───────────── admin ─────────────
async function adminTab() {
  const [users, squads, requests] = await Promise.all([api("/admin/users"), api("/admin/squads"), api("/admin/signup-requests")]);
  const staffLists = await Promise.all(squads.map((s) => api(`/admin/squads/${s.id}/staff`)));
  $("#main").replaceChildren(h("h1", {}, "Admin"),
    h("p", { class: "sub" }, "Only administrators can sign in for now. Other staff can still be added for planning."),
    requests.length ? requestsCard(requests) : null, squadsCard(squads, staffLists, users), seasonsCard(), usersCard(users));
}

function requestsCard(requests) {
  const rows = requests.map((r) => {
    const role = h("select", { class: "small", "aria-label": "Role for " + r.full_name },
      ["coach", "sc_coach", "physio", "player", "admin"].map((x) => h("option", { value: x, selected: x === r.role }, SIGNUP_ROLE_LABEL[x])));
    const e2 = h("div", { class: "err", role: "alert" });
    const act = (path, body, msg) => async () => {
      e2.textContent = "";
      try { await api(`/admin/signup-requests/${r.id}/${path}`, { method: "POST", body }); toast(msg); S.tab = "admin"; go("admin"); }
      catch (x) { e2.textContent = x.message; }
    };
    return h("div", { class: "item request" },
      h("div", {}, h("strong", {}, r.full_name), " ", h("span", { class: "chip" }, "asked for " + SIGNUP_ROLE_LABEL[r.role]), h("br"),
        h("span", { class: "sub" }, `${r.email} · ${new Date(r.created_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}`),
        r.signup_note ? h("p", { class: "quote" }, r.signup_note) : null,
        r.role_can_sign_in ? null : h("p", { class: "hint warn" }, "This role cannot sign in yet (SLC_ENABLED_ROLES)."), e2),
      h("div", { class: "row" }, role,
        h("button", { class: "small", onclick: () => act("approve", { role: role.value }, `${r.full_name} approved`)() }, "Approve"),
        h("button", { class: "small ghost danger", onclick: () => confirm(`Reject the request from ${r.full_name}?`) && act("reject", null, "Request rejected")() }, "Reject")));
  });
  return h("div", { class: "card attention" }, h("h2", {}, `Access requests (${requests.length})`),
    h("p", { class: "sub" }, "Approve only people you know. You can change the role."), h("div", { class: "list" }, rows));
}

function squadsCard(squads, staffLists, users) {
  const candidates = users.filter((u) => u.role !== "player" && u.is_active && u.approval_status === "approved");
  const age = h("select", {}, [["U15", "Under 15"], ["U17", "Under 17"], ["U19", "Under 19"]].map(([v, t]) => h("option", { value: v }, t)));
  const name = h("input", { required: true, maxLength: 200 }), prov = h("input", { required: true, maxLength: 100 });
  const err = h("div", { class: "err", role: "alert" });
  const create = h("form", { onsubmit: async (e) => {
    e.preventDefault(); err.textContent = "";
    try { const s = await api("/admin/squads", { method: "POST", body: { name: name.value.trim(), province: prov.value.trim(), age_group: age.value } }); toast("Squad created"); S.tab = "admin"; await refreshSquads(s.id); }
    catch (x) { err.textContent = x.message; }
  } }, h("div", { class: "grid" }, field("Squad name", name), field("Province", prov), field("Age group", age)), err, h("button", { class: "small", type: "submit" }, "Create squad"));
  const list = squads.map((s, i) => {
    const current = new Set(staffLists[i].map((u) => u.id));
    const boxes = candidates.map((u) => ({ u, el: h("input", { type: "checkbox", checked: current.has(u.id) }) }));
    const e2 = h("div", { class: "err", role: "alert" });
    return h("details", { class: "card" }, h("summary", {}, `${s.name} · ${s.age_group} · ${s.province} · ${staffLists[i].length} staff`),
      boxes.length ? h("div", {}, boxes.map((b) => h("label", { class: "inline" }, b.el, `${b.u.full_name} (${roleLabel(b.u.role)})`))) : h("p", { class: "sub" }, "Create staff users first (Users, below)."),
      e2, boxes.length ? h("button", { class: "small", onclick: async () => {
        e2.textContent = "";
        try { await api(`/admin/squads/${s.id}/staff`, { method: "PUT", body: { user_ids: boxes.filter((b) => b.el.checked).map((b) => b.u.id) } }); toast("Staff saved"); S.tab = "admin"; go("admin"); }
        catch (x) { e2.textContent = x.message; }
      } }, "Save staff") : null);
  });
  return h("div", { class: "card" }, h("h2", {}, "Squads"), list.length ? h("div", { class: "list" }, list) : h("p", { class: "sub" }, "No squads yet. Create the first one below."),
    h("h3", {}, "New squad"), create);
}

function seasonsCard() {
  if (!S.squad) return h("div", { class: "card" }, h("h2", {}, "Seasons"), h("p", { class: "sub" }, "Create a squad first."));
  const list = S.seasons.map((s) => h("div", { class: "item" }, h("span", {}, h("strong", {}, s.name), h("br"),
    h("span", { class: "sub" }, `${fdate(s.start_date)} – ${fdate(s.end_date)} · ` + (s.phases.length ? s.phases.map((p) => PHASE_NAME[p.phase_type]).join(", ") : "no phases set (a suggested split is used)"))),
    h("button", { class: "small ghost", onclick: () => editPhases(s) }, "Edit phases")));
  return h("div", { class: "card" }, h("div", { class: "bar" }, h("h2", {}, "Seasons – " + S.squad.name), h("button", { class: "small", onclick: () => seasonForm("admin") }, "+ Season")),
    list.length ? h("div", { class: "list" }, list) : h("p", { class: "sub" }, "No seasons yet."));
}

function usersCard(users) {
  const f = { email: h("input", { type: "email", required: true }), name: h("input", { required: true, maxLength: 200 }),
    role: h("select", {}, ["coach", "sc_coach", "physio", "admin", "player"].map((r) => h("option", { value: r }, roleLabel(r)))),
    pw: h("input", { type: "password", required: true, minLength: 10, autocomplete: "new-password" }) };
  const err = h("div", { class: "err", role: "alert" });
  const create = h("form", { onsubmit: async (e) => {
    e.preventDefault(); err.textContent = "";
    try { await api("/admin/users", { method: "POST", body: { email: f.email.value.trim(), full_name: f.name.value.trim(), role: f.role.value, language: "en", temp_password: f.pw.value } }); toast("User created"); S.tab = "admin"; go("admin"); }
    catch (x) { err.textContent = x.message; }
  } }, h("div", { class: "grid" }, field("Email", f.email), field("Full name", f.name), field("Role", f.role), field("Temporary password", f.pw)),
    h("p", { class: "sub" }, "At least 10 characters with upper case, lower case and a digit."), err, h("button", { class: "small", type: "submit" }, "Create user"));
  const rows = users.map((u) => {
    const rejected = u.approval_status === "rejected";
    const action = u.id === S.user.id ? "" : rejected
      ? h("button", { class: "ghost small", onclick: async () => {
        try { await api(`/admin/signup-requests/${u.id}/approve`, { method: "POST", body: { role: null } }); toast("Approved"); S.tab = "admin"; go("admin"); } catch (x) { toast(x.message); }
      } }, "Approve")
      : h("button", { class: "ghost small", onclick: async () => {
        try { await api("/admin/users/" + u.id, { method: "PATCH", body: { is_active: !u.is_active } }); S.tab = "admin"; go("admin"); } catch (x) { toast(x.message); }
      } }, u.is_active ? "Deactivate" : "Activate");
    return h("tr", {}, h("td", {}, u.full_name), h("td", {}, u.email), h("td", {}, roleLabel(u.role)),
      h("td", { class: !rejected && u.is_active ? "up" : "down" }, rejected ? "Rejected" : u.is_active ? "Active" : "Inactive"), h("td", {}, action));
  });
  return h("div", { class: "card" }, h("h2", {}, "Users"), h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Name", "Email", "Role", "Status", ""].map((c) => h("th", {}, c)))), h("tbody", {}, rows))),
    h("h3", {}, "New user"), create);
}

// ───────────── seasonal plan ─────────────
function planRow(row) {
  const tracker = row.plan_item_id ? (() => {
    const st = h("select", { "aria-label": "Progress status" }, Object.entries(STATUS).map(([v, l]) => h("option", { value: v, selected: row.status === v }, l)));
    const rv = h("input", { value: row.coach_review || "", maxLength: 2000, placeholder: "Coach review comment", "aria-label": "Coach review" });
    return h("div", { class: "track" }, h("div", { class: "grid" }, field("Progress status", st), field("Coach review", rv)),
      h("button", { class: "small ghost", onclick: async () => {
        try { await api("/plan-items/" + row.plan_item_id, { method: "PATCH", body: { status: st.value, coach_review: rv.value } }); row.status = st.value; row.coach_review = rv.value; toast("Saved"); }
        catch (x) { toast(x.message); }
      } }, "Save status"));
  })() : h("p", { class: "sub" }, "Save the plan to track progress status and coach review.");
  return h("div", { class: "card prow" }, h("div", { class: "row" }, h("span", { class: "chip area " + row.development_area }, cap(row.development_area)), h("span", { class: "chip" }, row.applies_to_label),
    h("span", { class: "sub" }, `${fdate(row.start_date)} – ${fdate(row.end_date)}`)),
    h("p", { class: "goal" }, row.goal), kv("Planned activities", row.planned_activities), kv("Responsible", row.responsible), kv("Measurement", row.measurement_method), kv("Target", row.target_outcome), tracker);
}

async function downloadPlan(q, file = "seasonal-plan.xlsx") {
  const res = await fetch(`/squads/${S.squad.id}/seasons/${S.season.id}/${file}${q}`, { headers: { Authorization: "Bearer " + S.token } });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Download failed"); }
  const blob = await res.blob();
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") || "")?.[1] || "seasonal-plan.xlsx";
  const a = h("a", { href: URL.createObjectURL(blob), download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

async function planTab(rolesParam) {
  const main = $("#main");
  if (!S.season) return main.replaceChildren(h("h1", {}, "Seasonal plan"), h("div", { class: "card" }, "This squad has no season yet. Create one in Admin → Seasons."));
  const q = rolesParam ? "?roles=" + encodeURIComponent(rolesParam) : "";
  const plan = await api(`/squads/${S.squad.id}/seasons/${S.season.id}/seasonal-plan${q}`);
  const rq = "?roles=" + encodeURIComponent(plan.roles.join(","));
  const picked = new Set(plan.roles);
  const roleBoxes = Object.entries(ROLE).map(([k, v]) => ({ k, v, el: h("input", { type: "checkbox", checked: picked.has(k) }) }));

  const fArea = h("select", { "aria-label": "Filter by development area" }, h("option", { value: "" }, "All areas"), ["technical", "tactical", "physical", "mental", "nutrition", "recovery"].map((a) => h("option", { value: a }, cap(a))));
  const fGroup = h("select", { "aria-label": "Filter by player group" }, h("option", { value: "" }, "All groups"), h("option", { value: "all" }, "All players (squad-wide)"), plan.roles.map((r) => h("option", { value: r }, ROLE[r])));
  const rowsBox = h("div", {});
  const renderRows = () => {
    const keep = (r) => (!fArea.value || r.development_area === fArea.value) && (!fGroup.value || (fGroup.value === "all" ? r.applies_to === null : r.applies_to === fGroup.value));
    rowsBox.replaceChildren(plan.phases.map((p, i) => {
      const rs = plan.rows.filter((r) => r.phase === p.phase_type && keep(r));
      return h("details", { open: i === 0 }, h("summary", {}, `${p.label} · ${fdate(p.start_date)} – ${fdate(p.end_date)} · ${rs.length} rows`), rs.length ? rs.map(planRow) : h("p", { class: "sub" }, "No rows match the filter."));
    }));
  };
  fArea.onchange = renderRows; fGroup.onchange = renderRows;

  const err = h("div", { class: "err", role: "alert" });
  main.replaceChildren(
    h("div", { class: "bar" }, h("h1", {}, "Seasonal plan"), seasonPicker(() => planTab(rolesParam))),
    h("p", { class: "sub" }, `${plan.squad} · season ${plan.season.name} · ${fdate(plan.season.start_date)} – ${fdate(plan.season.end_date)}`),
    h("div", { class: "row" },
      can("coach", "admin") ? h("button", { onclick: async () => { err.textContent = ""; try { const r = await api(`/squads/${S.squad.id}/seasons/${S.season.id}/seasonal-plan/save${rq}`, { method: "POST" }); toast(`Plan saved (${r.new} new, ${r.updated} updated)`); planTab(rolesParam); } catch (x) { err.textContent = x.message; } } }, plan.saved ? "Re-save plan" : "Save plan") : null,
      h("button", { class: "ghost", onclick: async () => { err.textContent = ""; try { await downloadPlan(rq); } catch (x) { err.textContent = x.message; } } }, "Download Excel"),
      h("button", { class: "ghost", onclick: async () => { err.textContent = ""; try { await downloadPlan(rq, "seasonal-workbook.xlsx"); } catch (x) { err.textContent = x.message; } } }, "Download plan workbook")),
    err,
    h("div", { class: "card" }, h("h3", {}, "Notes"), h("ul", {}, plan.notes.map((n) => h("li", {}, n)))),
    h("div", { class: "card" }, h("h3", {}, "Player groups in this plan"), h("div", { class: "row" }, roleBoxes.map((b) => h("label", { class: "inline" }, b.el, b.v))),
      h("button", { class: "small ghost", onclick: () => { const sel = roleBoxes.filter((b) => b.el.checked).map((b) => b.k); sel.length ? planTab(sel.join(",")) : toast("Pick at least one group"); } }, "Update plan")),
    h("h2", {}, "Phases"), plan.phases.map((p) => h("div", { class: "card" }, h("div", { class: "bar" }, h("h3", {}, p.label), h("span", { class: "chip" }, p.intensity)),
      h("div", { class: "sub" }, `${fdate(p.start_date)} – ${fdate(p.end_date)} · ${p.weeks} weeks`), h("p", {}, p.focus), h("p", { class: "sub" }, p.workload),
      h("div", { class: "sub" }, `${p.matches} match(es) · ${p.training_sessions} training session(s) · ${p.rest_days} rest day(s)` + (p.fitness_tests.length ? " · tests: " + p.fitness_tests.map((t) => fdate(t.date)).join(", ") : "")))),
    h("div", { class: "card" }, h("h3", {}, "Fitness testing"), plan.testing.map((t) => kv(t.test, `${fdate(t.from)} – ${fdate(t.to)} (${t.source})`))),
    h("div", { class: "card" }, h("h3", {}, "Staff"), kv("Coach(es)", plan.staff.coach.join(", ") || "To be assigned"), kv("S&C coach(es)", plan.staff.sc_coach.join(", ") || "To be assigned"), kv("Physiotherapist(s)", plan.staff.physio.join(", ") || "To be assigned")),
    h("h2", {}, "Plan"), h("div", { class: "grid" }, field("Development area", fArea), field("Player group", fGroup)), rowsBox,
    h("h2", {}, "Role programmes"), h("p", { class: "sub" }, "Phase use is a proposal for coaches to confirm."),
    plan.roles.map((r) => h("details", {}, h("summary", {}, ROLE[r]), Object.keys(PHASE_NAME).filter((ph) => plan.phases.some((p) => p.phase_type === ph)).map((ph) => {
      const items = plan.programmes.filter((x) => x.role === r && x.phase === ph);
      return h("div", {}, h("h3", {}, PHASE_NAME[ph]), h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Exercise / activity", "Used for", "Areas improved"].map((c) => h("th", {}, c)))),
        h("tbody", {}, items.map((x) => h("tr", {}, h("td", {}, x.name), h("td", { class: "wrap" }, x.purpose), h("td", { class: "wrap" }, x.areas)))))));
    }))),
    h("h2", {}, "Workload rules"), h("div", { class: "card" }, h("p", { class: "sub" }, plan.workload_note), plan.workload_rules.map((w) => kv(w.applies_to, w.rule))),
    h("h2", {}, "Example session"), h("div", { class: "card" }, h("p", { class: "sub" }, plan.session_guidance.join(" ")), plan.session_template.map((s) => kv(`${s.part} (${s.minutes} min)`, s.what))));
  renderRows();
  main.querySelector("h2:nth-of-type(2)"); // keeps layout stable; rowsBox is already in place
}

// ───────────── workload (phase 3) ─────────────
const SEV = { stop: "Stop", warn: "Warning", info: "Note" };
const todayStr = () => new Date().toLocaleDateString("en-CA");
const sevChip = (s) => s ? h("span", { class: "chip " + s }, SEV[s]) : h("span", { class: "chip ok" }, "OK");
const BOWLS = ["fast_bowler", "spin_bowler", "all_rounder"], BATS = ["batter", "bat_wicketkeeper", "all_rounder"];

function alertList(alerts, onAck) {
  if (!alerts.length) return h("p", { class: "sub" }, "No open alerts.");
  return h("div", { class: "list" }, alerts.map((a) => h("div", { class: "item alert " + a.severity },
    h("span", {}, sevChip(a.severity), " ", a.player_name ? h("strong", {}, a.player_name + ": ") : null, a.message,
      a.acknowledged_at ? h("span", { class: "sub" }, " (seen)") : null),
    onAck && !a.acknowledged_at && a.id ? h("button", { class: "small ghost", onclick: () => onAck(a) }, "Mark seen") : null)));
}

async function workloadTab() {
  const [rows, alerts] = await Promise.all([api(`/squads/${S.squad.id}/workload/overview`), api(`/squads/${S.squad.id}/alerts`)]);
  const ack = async (a) => { try { await api(`/alerts/${a.id}/acknowledge`, { method: "POST" }); workloadTab(); } catch (x) { toast(x.message); } };
  const order = { stop: 0, warn: 1, info: 2 };
  rows.sort((a, b) => (order[a.worst_severity] ?? 3) - (order[b.worst_severity] ?? 3) || a.name.localeCompare(b.name));
  $("#main").replaceChildren(h("h1", {}, "Workload"),
    h("p", { class: "sub" }, "Alerts are prompts for the coach and physio, not a diagnosis. Fast-bowler limits are provisional."),
    h("div", { class: "card" }, h("h2", {}, "Open alerts"), alertList(alerts, ack)),
    h("div", { class: "card" }, h("h2", {}, "Squad overview"), h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {},
      ["Player", "Role", "Availability", "7-day load", "Load ratio", "Overs (7 d)", "Bowling days", "Status"].map((c) => h("th", {}, c)))),
      h("tbody", {}, rows.map((r) => h("tr", { class: "click", onclick: () => { S.pid = r.player_id; go("players"); } },
        h("td", {}, r.name), h("td", {}, ROLE[r.role]), h("td", {}, h("span", { class: "chip " + r.availability }, r.availability)),
        h("td", {}, r.acute_load_7d), h("td", {}, r.acwr == null ? "needs 3 weeks" : r.acwr),
        h("td", {}, BOWLS.includes(r.role) ? r.overs_7d : "–"), h("td", {}, BOWLS.includes(r.role) ? r.bowling_days_7d : "–"), h("td", {}, sevChip(r.worst_severity))))))),
      h("p", { class: "sub" }, "Load = RPE × minutes. Load ratio = 7-day ÷ 4-week average (needs 3 weeks of logs).")));
}

function weekBars(weeks, chronic) {
  const n = weeks.length;
  return Charts.columns({ ariaLabel: "Weekly load, oldest to newest",
    data: weeks.map((w, i) => ({ label: i === n - 1 ? "This wk" : `−${n - 1 - i}`, value: w,
      tip: [i === n - 1 ? "This week (last 7 days)" : `${n - 1 - i} week(s) ago`, `${(w || 0).toLocaleString()} units`] })),
    refs: chronic ? [{ value: chronic, label: "4-wk avg" }] : [] });
}

async function workloadCard(p, host) {
  host.replaceChildren(h("div", { class: "bar" }, h("h2", {}, "Workload")));
  const sum = await api(`/players/${p.id}/workload/summary`);
  const s = sum.summary, b = s.bowling, coach = sum.alerts !== null;
  const btns = h("div", { class: "row" },
    can("player", "coach", "sc_coach", "admin") ? h("button", { class: "small", onclick: () => sessionForm(p, "log") }, "Log session") : null,
    can("player", "coach", "sc_coach", "physio", "admin") ? h("button", { class: "small ghost", onclick: () => wellnessForm(p) }, "Daily wellness") : null,
    coach ? h("button", { class: "small ghost", onclick: () => sessionForm(p, "check") }, "Check a planned session") : null,
    can("coach", "sc_coach", "admin") ? h("button", { class: "small ghost", onclick: () => limitsForm(p, b.limits) }, "Bowling limits") : null);
  host.append(btns,
    h("div", { class: "kpis compact" },
      Charts.stat({ label: "Last 7 days", value: (s.acute_load_7d || 0).toLocaleString(), sub: "load units" }),
      Charts.stat({ label: "4-week weekly average", value: s.chronic_weekly_load_28d == null ? "–" : Math.round(s.chronic_weekly_load_28d).toLocaleString(), sub: "load units" }),
      (() => { const st = ACWR_STATE(s.acwr); return Charts.stat({ label: "Load ratio", value: s.acwr ?? "–", sub: st ? st[0] + " · cap 1.3" : "needs 3 weeks of logs",
        tone: st ? { "c-critical": "critical", "c-warning": "warning", "c-good": "good" }[st[1]] : null }); })(),
      Charts.stat({ label: "Vs last week", value: s.vs_last_week_pct == null ? "–" : (s.vs_last_week_pct > 0 ? "+" : "") + s.vs_last_week_pct + "%",
        sub: s.month_vs_last_month_pct == null ? "month: –" : `month ${s.month_vs_last_month_pct > 0 ? "+" : ""}${s.month_vs_last_month_pct}%` })),
    h("h3", {}, "Weekly load, last 8 weeks"),
    weekBars(s.weekly_loads_oldest_first, s.chronic_weekly_load_28d));
  if (BOWLS.includes(p.role)) host.append(h("h3", {}, "Bowling, last 7 days"), h("div", { class: "sub" },
    `${b.overs_7d} overs on ${b.days_bowled_7d.length} day(s).` + (b.limits ? ` Limits: ${b.limits.max_spell_overs ?? "–"} per spell, ${b.limits.max_match_day_overs ?? "–"} per day, ${b.limits.max_bowling_days_week ?? "–"} days a week.` : " No automatic limits for this player. A coach can set them.")));
  if (coach) {
    host.append(h("h3", {}, "Alerts"), alertList(sum.alerts.map((a) => ({ ...a, id: null }))));
    const g = sum.guidance;
    host.append(h("h3", {}, "Next week (guidance)"), h("div", { class: "card inner" }, h("p", {}, h("strong", {}, cap(g.action.replace("_", " ")) + (g.next_week_load ? `: about ${g.next_week_load[0]} to ${g.next_week_load[1]} load units` : "")),
      sum.season_phase ? h("span", { class: "sub" }, " · " + PHASE_NAME[sum.season_phase] + " phase") : null), h("p", {}, g.reason), h("p", { class: "sub" }, g.note)));
  }
  const logs = await api(`/players/${p.id}/workload`);
  if (logs.length) host.append(h("h3", {}, "Recent sessions"), h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Date", "Type", "Minutes", "RPE", "Load", "Overs"].map((c) => h("th", {}, c)))),
    h("tbody", {}, logs.slice(0, 10).map((l) => h("tr", {}, h("td", {}, fdate(l.log_date)), h("td", {}, l.attended ? cap(l.session_type.replace("_", " ")) : "Absent"), h("td", {}, l.duration_min ?? "–"),
      h("td", {}, l.rpe ?? l.session_intensity ?? "–"), h("td", {}, l.load == null ? "–" : l.load), h("td", {}, l.overs_bowled ?? "–")))))));
  else host.append(h("p", { class: "sub" }, "No sessions logged in the last 28 days."));
}

function sessionForm(p, mode) {
  const num = (min, max, step = "1") => h("input", { type: "number", min, max, step, inputMode: "decimal" });
  const f = { date: h("input", { type: "date", required: true, value: todayStr(), max: mode === "log" ? todayStr() : null }),
    type: h("select", {}, ["training", "match", "fitness_test", "camp", "review"].map((v) => h("option", { value: v }, cap(v.replace("_", " "))))),
    att: h("input", { type: "checkbox", checked: true }), dur: num(1, 480), rpe: num(1, 10), inten: num(1, 10),
    overs: num(0, 50, "0.1"), spells: h("input", { placeholder: "e.g. 4, 3", inputMode: "decimal" }), faced: num(0, 600), keep: num(0, 480), throws: num(0, 300) };
  const err = h("div", { class: "err", role: "alert" }), result = h("div", {});
  const body = () => {
    const b = { log_date: f.date.value, session_type: f.type.value, attended: f.att.checked };
    if (!b.attended) return b;
    const set = (k, el, conv = Number) => { if (el.value !== "") b[k] = conv(el.value); };
    set("duration_min", f.dur); set("rpe", f.rpe); set("session_intensity", f.inten); set("overs_bowled", f.overs);
    set("balls_faced", f.faced); set("keeping_minutes", f.keep); set("throws", f.throws);
    if (f.spells.value.trim()) b.spells = f.spells.value.split(",").map((x) => ({ overs: Number(x.trim()) }));
    return b;
  };
  const submit = async (ev) => {
    ev.preventDefault(); err.textContent = ""; result.replaceChildren();
    try {
      if (mode === "log") { await api(`/players/${p.id}/workload`, { method: "POST", body: body() }); toast("Session saved"); go("players"); }
      else {
        const r = await api(`/players/${p.id}/workload/check`, { method: "POST", body: body() });
        result.replaceChildren(r.ok ? h("p", { class: "up" }, "No new alerts for this session.") : h("div", {}, h("p", { class: "down" }, "This session would raise:"), alertList(r.new_alerts)),
          h("p", { class: "sub" }, "Nothing was saved."));
      }
    } catch (x) { err.textContent = x.message; }
  };
  $("#main").replaceChildren(h("form", { class: "card", onsubmit: submit },
    h("h1", {}, (mode === "log" ? "Log session – " : "Check a planned session – ") + p.full_name),
    h("div", { class: "grid" }, field("Date", f.date), field("Type", f.type), h("label", { class: "inline" }, f.att, "Attended")),
    h("div", { class: "grid" }, field("Minutes", f.dur), field("RPE (1-10, from the player)", f.rpe), field("Planned intensity (1-10)", f.inten)),
    BOWLS.includes(p.role) ? [h("h2", {}, "Bowling"), h("div", { class: "grid" }, field("Overs (3.2 = 3 overs 2 balls)", f.overs), field("Spells in overs, comma separated", f.spells))] : null,
    BATS.includes(p.role) ? [h("h2", {}, "Batting"), h("div", { class: "grid" }, field("Balls faced", f.faced))] : null,
    p.role === "bat_wicketkeeper" ? [h("h2", {}, "Keeping"), h("div", { class: "grid" }, field("Keeping minutes", f.keep), field("Throws", f.throws))] : null,
    err, result, h("div", { class: "row" }, h("button", { type: "submit" }, mode === "log" ? "Save session" : "Check"), h("button", { type: "button", class: "ghost", onclick: () => go("players") }, "Cancel"))));
}

function wellnessForm(p) {
  const n = (min, max, step = "1") => h("input", { type: "number", min, max, step, inputMode: "decimal" });
  const f = { date: h("input", { type: "date", required: true, value: todayStr(), max: todayStr() }), sore: n(1, 10), fat: n(1, 10), sq: n(1, 10), sh: n(0, 24, "0.5"), rec: n(1, 10), pain: h("input", { type: "checkbox" }) };
  const err = h("div", { class: "err", role: "alert" });
  $("#main").replaceChildren(h("form", { class: "card", onsubmit: async (ev) => {
    ev.preventDefault(); err.textContent = "";
    const b = { log_date: f.date.value, pain_flag: f.pain.checked };
    for (const [k, el] of [["soreness", f.sore], ["fatigue", f.fat], ["sleep_quality", f.sq], ["sleep_hours", f.sh], ["recovery", f.rec]]) if (el.value !== "") b[k] = Number(el.value);
    try { await api(`/players/${p.id}/wellness`, { method: "POST", body: b }); toast("Wellness saved"); go("players"); } catch (x) { err.textContent = x.message; }
  } }, h("h1", {}, "Daily wellness – " + p.full_name),
    h("p", { class: "sub" }, "Soreness and fatigue: 10 = worst. Sleep and recovery: 10 = best. Pain details go to the physio, not here."),
    h("div", { class: "grid" }, field("Date", f.date), field("Soreness (1-10)", f.sore), field("Fatigue (1-10)", f.fat), field("Sleep quality (1-10)", f.sq), field("Sleep (hours)", f.sh), field("Recovery (1-10)", f.rec)),
    h("label", { class: "inline" }, f.pain, "Pain reported (the physiotherapist will be alerted)"), err,
    h("div", { class: "row" }, h("button", { type: "submit" }, "Save"), h("button", { type: "button", class: "ghost", onclick: () => go("players") }, "Cancel"))));
}

function limitsForm(p, eff) {
  const cur = {}; // only coach-set values are editable; effective defaults are shown as hints
  const mk = (k, hint) => h("input", { type: "number", min: 1, max: 30, inputMode: "numeric", placeholder: hint });
  const f = { max_spell_overs: mk(), max_match_day_overs: mk(), max_bowling_days_week: mk() };
  const err = h("div", { class: "err", role: "alert" });
  $("#main").replaceChildren(h("form", { class: "card", onsubmit: async (ev) => {
    ev.preventDefault(); err.textContent = "";
    const b = {}; for (const [k, el] of Object.entries(f)) b[k] = el.value === "" ? null : Number(el.value);
    try { await api(`/players/${p.id}/workload-limits`, { method: "PUT", body: b }); toast("Limits saved"); go("players"); } catch (x) { err.textContent = x.message; }
  } }, h("h1", {}, "Bowling limits – " + p.full_name),
    h("p", { class: "sub" }, p.role === "fast_bowler" ? "Fast bowlers start with 5 overs a spell, 16 a day and 3 bowling days a week (provisional). Fill a box to use a stricter number for this player. Leave all boxes empty to use the defaults."
      : "Spin bowlers, all-rounders, batters and keepers have no automatic limits. Fill a box to start checking this player against your number. Leave all boxes empty to switch checks off."),
    eff ? h("p", { class: "sub" }, `Currently checked: ${eff.max_spell_overs ?? "–"} per spell, ${eff.max_match_day_overs ?? "–"} per day, ${eff.max_bowling_days_week ?? "–"} days a week.`) : null,
    h("div", { class: "grid" }, field("Most overs in a spell", f.max_spell_overs), field("Most overs in a day", f.max_match_day_overs), field("Most bowling days in 7 days", f.max_bowling_days_week)),
    err, h("div", { class: "row" }, h("button", { type: "submit" }, "Save limits"), h("button", { type: "button", class: "ghost", onclick: () => go("players") }, "Cancel"))));
}

// ───────────── SLC U15 physical tests: import, categories, individual plan ─────────────
const WINDOWS = [["baseline", "Baseline"], ["mid_season", "Mid-season"], ["end_season", "End of season"]];
const READY_CHIP = { ready: "ok", caution: "warn", hold: "stop" };
const readyChip = (r) => h("span", { class: "chip " + READY_CHIP[r.status], title: r.reason }, r.label);
const bandChip = (c) => c.band ? h("span", { class: "chip band" + c.band }, `Band ${c.band} · ${c.band_label}`) : h("span", { class: "chip" }, "No band yet");

async function downloadFile(url, fallback) {
  const res = await fetch(url, { headers: { Authorization: "Bearer " + S.token } });
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Download failed"); }
  const blob = await res.blob();
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") || "")?.[1] || fallback;
  const a = h("a", { href: URL.createObjectURL(blob), download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

function windowPicker(current, onchange) {
  return h("select", { "aria-label": "Test window", onchange: (e) => onchange(e.target.value) },
    WINDOWS.map(([k, v]) => h("option", { value: k, selected: k === current }, v)));
}

function ageNormsCard(n, ag) {
  return h("details", { class: "card" }, h("summary", {}, `Age references · ${ag}`),
    h("p", { class: "sub" }, "Provisional reference points for boys, from published youth data where it exists. Replace with SLC's own data over time."),
    h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Test", "Developing", "Expected", "Strong", "Source"].map((c) => h("th", {}, c)))),
      h("tbody", {}, n.tests.map((t) => { const a = t.ages[ag] || t.ages.U15;
        return h("tr", {}, h("td", {}, `${t.label} (${t.unit})`), h("td", {}, a.developing), h("td", {}, h("strong", {}, a.expected)), h("td", {}, a.strong),
          h("td", { class: "sub" }, t.quality)); })))));
}

function areaTable(cat) {
  if (!cat.areas.length) return null;
  return h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Area", "Test", "Trial 1", "Trial 2", "Trial 3", "Best", "Rank in level", "Area rank", "For age"].map((c) => h("th", {}, c)))),
    h("tbody", {}, cat.areas.flatMap((a) => a.tests.map((t, i) => h("tr", {},
      h("td", {}, i === 0 ? a.label : ""), h("td", {}, `${t.label} (${t.unit})`), ...t.trials_display.map((d) => h("td", {}, d ?? "–")), h("td", {}, h("strong", {}, t.display ?? "–")),
      h("td", {}, t.percentile == null ? "–" : t.percentile), h("td", {}, i === 0 && a.percentile != null ? a.percentile : ""),
      h("td", {}, t.age ? h("span", { class: "chip age-" + t.age.band, title: `${t.age.age_group}: developing ${t.age.developing} · expected ${t.age.expected} · strong ${t.age.strong} ${t.age.unit}` +
        (t.age.quality === "estimate" ? " (estimate)" : "") }, t.age.label) : "–")))))));
}

const AREA_STATUS = { priority: ["Priority", "warn", "c-s2"], solid: ["Solid", "info", "c-s1"], strength: ["Strength", "ok", "c-s3"], untested: ["Not tested", "", "c-muted"] };
const GOAL_KIND = { test: "Test target", maintain: "Keep", skill: "Cricket skill", role_skill: "Role skill", habit: "Daily habit", rating: "Coach rating" };
const PHASE_CLS = { pre_season: "c-s1", pre_competition: "c-s3", in_season: "c-s2", transition: "c-muted" };

const PROG_CHIP = { progressed: ["Progressed", "ok"], at_target: ["At target", "ok"], on_track: ["On track", "ok"], held: ["Hold", "warn"],
  held_readiness: ["Hold (readiness)", "warn"], stepped_back: ["Stepped back", "stop"], in_progress: ["In progress", "info"], not_started: ["Not started", ""] };

function planView(plan, ctx = {}) {
  const sm = plan.load_summary, pr = plan.profile, gr = pr.growth, ta = pr.training_age;
  const li = (...k) => h("li", {}, ...k);
  const ed = !!ctx.editing, edit = ctx.edit || (() => {});
  const progOf = (ph, a, e) => plan.progress && plan.progress.exercises[`${ph}|${a}|${e}`];
  const out = [h("p", { class: "sub" }, "Personal plan · a proposal for the coach to review.")];
  if (plan.coach_note || ed) out.push(ed
    ? h("label", {}, "Coach note (saved with the version)", h("textarea", { rows: 2, maxLength: 2000, value: plan.coach_note || "", onchange: (e) => edit({ type: "note", text: e.target.value }) }))
    : h("div", { class: "coach-note" }, h("strong", {}, "Coach note: "), plan.coach_note));

  // ── who this plan is for ──
  out.push(h("div", { class: "plan-profile" },
    h("div", { class: "pp-col good" }, h("h4", {}, "Strengths to build on"),
      plan.strengths.length ? h("ul", { class: "pp-list" }, plan.strengths.map((s) => li(h("strong", {}, s.label), h("span", { class: "sub" }, " · " + s.detail))))
        : h("p", { class: "sub" }, "No clear strength yet. Every area is still trained.")),
    h("div", { class: "pp-col warn" }, h("h4", {}, "Priorities"),
      plan.priorities.length ? h("ul", { class: "pp-list" }, plan.priorities.map((s) => li(h("strong", {}, s.label), h("span", { class: "sub" }, " · " + s.detail))))
        : h("p", { class: "sub" }, "Nothing is below the middle. All areas share the work.")),
    h("div", { class: "pp-col" }, h("h4", {}, "What shapes this plan"), h("ul", { class: "pp-facts" },
      li(h("span", { class: "k" }, "Readiness"), readyChip(plan.readiness)),
      li(h("span", { class: "k" }, "Growth"), `${gr.label}` + (gr.velocity_cm_yr != null ? ` · ${gr.velocity_cm_yr} cm a year` : "") + (gr.source !== "not known" ? ` (${gr.source})` : "")),
      li(h("span", { class: "k" }, "Experience"), ta.label),
      li(h("span", { class: "k" }, "Weighting"), pr.importance_source === "role default" ? "Role default (add a needs analysis in the screening)" : "From the screening needs analysis"),
      BOWLS.includes(plan.role) ? li(h("span", { class: "k" }, "Bowling limits"), `${plan.limits.max_spell_overs} overs a spell · ${plan.limits.max_bowling_days_week} bowling days in 7`) : null,
      pr.objective ? li(h("span", { class: "k" }, "Player's goal"), pr.objective) : null))));
  if (pr.missing.length) out.push(h("p", { class: "hint warn" }, "This plan would be more personal with: " + pr.missing.join("; ") + "."));
  if (pr.areas.some((a) => a.percentile != null)) out.push(Charts.hbars({ ariaLabel: "Area profile", max: 100, refs: [{ value: 50, label: "middle" }, { value: 70, label: "strength" }],
    data: pr.areas.map((a) => ({ label: a.label, sub: AREA_STATUS[a.status][0] + (a.trend ? ` · ${a.trend}` : "") + (a.source === "coach rating" ? " · coach rating" : a.source === "age reference" ? " · age reference" : a.age_label ? ` · ${a.age_label.toLowerCase()} for age` : ""),
      value: a.percentile, cls: AREA_STATUS[a.status][2], display: a.percentile == null ? "–" : Charts.num(a.percentile, 1),
      tip: [a.label, a.percentile == null ? "Not ranked" : `Rank ${a.percentile} of 100`, a.previous_percentile != null ? `Last window: ${a.previous_percentile}` : null,
        a.coach_rating ? `Coach rating ${a.coach_rating}/5` : null, a.importance !== 1 ? `Importance ×${a.importance}` : null, a.note] })) }));

  // ── goals ──
  if (plan.goals.length) out.push(h("h3", {}, "Goals"), h("div", { class: "scroll" }, h("table", { class: "goals" },
    h("thead", {}, h("tr", {}, ["Type", "Goal", "By", "Why"].map((c) => h("th", {}, c)))),
    h("tbody", {}, plan.goals.map((g, gi) => h("tr", {}, h("td", {}, h("span", { class: "chip goal-" + g.kind }, GOAL_KIND[g.kind] || g.kind), g.edited ? h("span", { class: "chip edited" }, "Coach edit") : null),
      h("td", { class: "wrap" }, h("strong", {}, g.label),
        ed && g.target_display ? h("label", { class: "inline" }, "Target ", h("input", { class: "tiny", value: g.target_display, maxLength: 20,
          onchange: (e) => edit({ type: "goal", index: gi, target_display: e.target.value }) })) : null),
      h("td", {}, ed ? h("input", { class: "tiny wide", value: g.by || "", maxLength: 60, "aria-label": "Goal date", onchange: (e) => edit({ type: "goal", index: gi, by: e.target.value }) }) : (g.by || "–")),
      h("td", { class: "wrap sub" }, g.why || "")))))));
  if (plan.progress) {
    const ad = plan.progress.adherence;
    out.push(h("h3", {}, "Progress against the plan"),
      h("p", { class: "sub" }, `Focus sessions, last 4 weeks: ${ad.done} of ${ad.planned}` + (ad.pct != null ? ` (${ad.pct}%)` : "") + ". Doses update automatically from logged sessions."),
      Charts.columns({ ariaLabel: "Focus sessions per week", highlight: -1, height: 90, capAll: true,
        data: ad.weeks.map((w) => ({ label: fdate(w.week_start), value: w.done, cls: w.done >= w.planned && w.planned ? "c-good" : "c-s1",
          tip: [`Week of ${fdate(w.week_start)}`, `${w.done} of ${w.planned} focus sessions`] })) }),
      ctx.onLog ? h("button", { class: "small", onclick: ctx.onLog }, "Log a focus session") : null);
  }

  // ── load ──
  const presentPhases = [...new Set(plan.weeks.map((w) => w.phase))];
  out.push(h("h3", {}, "Weekly load plan"),
    h("p", { class: "sub" }, `Start ${sm.start_load.toLocaleString()} units/week (${sm.from_logs ? "own logs" : "estimate"}) · max rise ${sm.max_rise_pct}% · max ratio ${sm.max_load_ratio ?? "–"} · ${sm.easy_weeks} easy week(s)`),
    Charts.legend(presentPhases.map((p) => ({ cls: PHASE_CLS[p], label: PHASE_NAME[p] || p }))),
    Charts.columns({ ariaLabel: "Planned load per week", highlight: -1, height: 160,
      data: plan.weeks.map((w) => ({ label: w.week % 4 === 1 ? "W" + w.week : "", value: w.planned_load, cls: PHASE_CLS[w.phase],
        tip: [`Week ${w.week} · ${fdate(w.start)} · ${w.phase_label}`, `${w.planned_load.toLocaleString()} units planned`,
          w.match_load ? `Matches ${w.match_load}` : null, w.bowl_days ? `Bowling ${w.bowl_days} × ${w.overs_per_day} overs (${w.spells})` : null,
          `Focus work ${w.focus_load} · general ${w.general_load}`, w.flags.length ? w.flags.join("; ") : null] })) }),
    h("p", {}, plan.load_violations.length ? h("strong", { class: "down" }, "Check needed: " + plan.load_violations.join("; ")) : "All weeks are within the limits.",
      sm.match_over_limit_weeks ? h("strong", { class: "down" }, ` ${sm.match_over_limit_weeks} week(s): match load alone is above the weekly limit. Review the match minutes.`) : null),
    h("details", {}, h("summary", {}, "Show the week-by-week load"), h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Week", "Starts", "Phase", "Load", "Matches", "Bowling", "Focus work", "General", "Change", "Ratio", "Notes"].map((c) => h("th", {}, c)))),
      h("tbody", {}, plan.weeks.map((w) => h("tr", {}, h("td", {}, w.week), h("td", {}, fdate(w.start)), h("td", {}, w.phase_label), h("td", {}, w.planned_load.toLocaleString()),
        h("td", {}, w.match_load || "–"), h("td", {}, w.bowl_days ? `${w.bowl_days} x ${w.overs_per_day} ov (${w.spells})` : "–"), h("td", {}, w.focus_load), h("td", {}, w.general_load),
        h("td", {}, w.rise_pct == null ? "–" : (w.rise_pct > 0 ? "+" : "") + w.rise_pct + "%"), h("td", {}, w.load_ratio ?? "–"), h("td", { class: "sub" }, w.flags.join("; ")))))))));
  // ── the programme, phase by phase ──
  out.push(h("h3", {}, "Programme by phase"),
    h("p", { class: "sub" }, "Start at the first number; progression is automatic from logged sessions."));
  plan.phases.forEach((ph, i) => {
    const body = [];
    for (const a of ph.areas) {
      const st = AREA_STATUS[a.status] || AREA_STATUS.solid;
      body.push(h("div", { class: "area-head" }, h("strong", {}, a.label), h("span", { class: "chip " + st[1] }, st[0]),
        a.trend ? h("span", { class: "chip" }, a.trend) : null, h("span", { class: "sub" }, `${a.exercises.length} exercise(s)`)));
      if (a.note) body.push(h("p", { class: "sub" }, a.note));
      const alts = a.alternatives || [];
      if (a.exercises.length) body.push(h("div", { class: "scroll" }, h("table", { class: "ex" }, h("tbody", {}, a.exercises.map((e, ei) => {
        const pg = progOf(ph.phase, a.area, e.name);
        const chip = pg && PROG_CHIP[pg.status];
        return h("tr", {}, h("td", { class: "wrap" }, h("strong", {}, e.name), e.edited ? h("span", { class: "chip edited" }, "Coach edit") : null,
            h("div", { class: "sub" }, e.purpose), e.why ? h("div", { class: "why" }, "Why: " + e.why) : null,
            ed && alts.length ? h("label", { class: "inline" }, "Swap for ", h("select", { class: "tiny", onchange: (ev) => ev.target.value && edit({ type: "swap", phase: ph.phase, area: a.area, index: ei, exercise: ev.target.value }) },
              h("option", { value: "" }, "choose…"), alts.map((x) => h("option", { value: x.name }, x.name)))) : null,
            ed ? h("button", { class: "small ghost danger", onclick: () => edit({ type: "remove", phase: ph.phase, area: a.area, index: ei }) }, "Remove") : null),
          h("td", { class: "wrap" },
            ed ? h("div", { class: "row" },
              h("label", { class: "inline" }, "Reps ", h("input", { class: "tiny", value: e.rep || "", maxLength: 40, onchange: (ev) => edit({ type: "dose", phase: ph.phase, area: a.area, index: ei, rep: ev.target.value }) })),
              h("label", { class: "inline" }, "Sets ", h("input", { class: "tiny", value: e.set || "", maxLength: 20, onchange: (ev) => edit({ type: "dose", phase: ph.phase, area: a.area, index: ei, set: ev.target.value }) })))
              : [e.time, e.rep && e.rep + " reps", e.set && e.set + " sets", e.rest].filter(Boolean).join(" · "),
            e.basis ? h("div", { class: "sub" }, e.basis) : null,
            pg && pg.status !== "not_started" ? h("div", { class: "prog" }, chip ? h("span", { class: "chip " + chip[1] }, chip[0]) : null,
              pg.current ? h("strong", {}, " Next: " + pg.current) : null, h("div", { class: "sub" }, pg.reason + (pg.next_review ? ` Next review ${fdate(pg.next_review)}.` : ""))) : null));
      })))));
      if (ed && alts.length) body.push(h("label", { class: "inline" }, `Add to ${a.label}: `, h("select", { class: "tiny", onchange: (ev) => ev.target.value && edit({ type: "add", phase: ph.phase, area: a.area, exercise: ev.target.value }) },
        h("option", { value: "" }, "choose…"), alts.map((x) => h("option", { value: x.name }, x.name)))));
    }
    if (ph.role_skills && ph.role_skills.length) {
      body.push(h("h4", {}, "Role skills to improve"));
      body.push(h("ul", { class: "skills" }, ph.role_skills.map((s) => h("li", {}, h("strong", {}, `${s.group} – ${s.skill}`), h("span", { class: "sub" }, ` (${s.status_label})`),
        s.drills.length ? h("div", {}, s.drills.map((d) => d.name + (d.added ? " (added drill)" : "")).join(" · ")) : h("div", { class: "sub" }, "No drill for this skill in this phase.")))));
    }
    if (ph.skills && ph.skills.length) {
      body.push(h("h4", {}, "Cricket skills to improve"));
      body.push(h("ul", { class: "skills" }, ph.skills.map((s) => h("li", {}, h("strong", {}, `${s.group} – ${s.skill}`), h("span", { class: "sub" }, ` (rated ${s.rating}/5)`),
        s.drills.length ? h("div", {}, s.drills.map((d) => d.name).join(" · ")) : null, s.note ? h("div", { class: "sub" }, s.note) : null))));
    }
    if (ph.typical_week) body.push(h("h4", {}, "A typical week"), h("div", { class: "week-grid" }, ph.typical_week.map((d) =>
      h("div", { class: "wk-day" + (d.items.some((x) => x.startsWith("Match")) ? " match" : d.items.some((x) => x.startsWith("Focus")) ? " focus" : "") },
        h("div", { class: "wk-name" }, d.day), d.items.map((x) => h("div", { class: "wk-item" }, x))))));
    out.push(h("details", { class: "phase", open: i === 0 }, h("summary", {}, `${ph.label} · ${ph.sessions_per_week} focus session(s) a week`), body));
  });

  // ── reviews and notes ──
  if (plan.reviews.length) out.push(h("h3", {}, "Review points"), h("ol", { class: "reviews" }, plan.reviews.slice(0, 12).map((r) =>
    h("li", {}, h("strong", {}, fdate(typeof r.date === "string" ? r.date.slice(0, 10) : r.date)), " · ", r.what))));
  out.push(h("details", {}, h("summary", {}, "How this plan was built (notes)"), plan.notes.map((n) => h("p", { class: "sub" }, n))));
  return out;
}

// ───────────── the plan in use: versions, coach edits, session logging ─────────────
async function planPanel(p, host, window) {
  const canEdit = can("coach", "sc_coach", "admin");
  const st = { plan: null, base: "saved", edits: [], editing: false, fresh: false, busy: false };
  const q = (extra = "") => `/players/${p.id}/individual-plan?window=${window}${extra}`;
  const msg = h("div", { class: "err", role: "alert" });
  const load = async (fresh) => {
    host.replaceChildren(h("div", { class: "sub loading" }, fresh ? "Building a fresh plan from the latest data…" : "Loading the plan…"));
    st.plan = await api(q(fresh ? "&fresh=true" : "")); st.fresh = !!fresh; st.base = fresh ? "fresh" : "saved"; st.edits = []; st.editing = false;
    render();
  };
  const preview = async (op) => {
    msg.textContent = "";
    const edits = [...st.edits, op];
    try { st.plan = await api(`/players/${p.id}/individual-plan/preview`, { method: "POST", body: { base: st.base, edits, season_id: st.plan.season.id, window } }); st.edits = edits; }
    catch (x) { msg.textContent = x.message; }
    render();
  };
  const save = async () => {
    msg.textContent = "";
    try {
      st.plan = await api(`/players/${p.id}/individual-plan/versions`, { method: "POST",
        body: { base: st.base, edits: st.edits, season_id: st.plan.season.id, window, note: st.plan.coach_note ?? null } });
      toast(`Saved as version ${st.plan.saved.version}`); st.edits = []; st.editing = false; st.base = "saved"; st.fresh = false; render();
    } catch (x) { msg.textContent = x.message; render(); }
  };
  const versions = async () => {
    const list = await api(`/players/${p.id}/individual-plan/versions?season_id=${st.plan.season.id}`);
    toast(list.length ? `${list.length} saved version(s)` : "No saved versions yet");
    st.versions = list; render();
  };
  function bar() {
    const pl = st.plan, sv = pl.saved, ls = pl.latest_saved;
    const status = sv ? h("span", {}, h("span", { class: "chip ok" }, `Saved version ${sv.version}`), ` by ${sv.saved_by || "–"} on ${new Date(sv.saved_at).toLocaleDateString()}`,
        sv.based_on ? h("span", { class: "sub" }, ` · from ${sv.based_on}`) : null)
      : h("span", {}, h("span", { class: "chip warn" }, st.edits.length ? `Unsaved: ${st.edits.length} change(s)` : "Generated, not saved"),
        ls ? h("span", { class: "sub" }, ` · version ${ls.version} is saved`) : h("span", { class: "sub" }, " · save it to make it the plan in use"));
    return h("div", { class: "plan-bar" }, status, h("div", { class: "row" },
      canEdit && !st.editing ? h("button", { class: "small", onclick: () => { st.editing = true; render(); } }, "Edit plan") : null,
      canEdit && (st.editing || !sv) ? h("button", { class: "small", onclick: save }, st.edits.length ? "Save as new version" : "Save this plan") : null,
      st.editing ? h("button", { class: "small ghost", onclick: () => load(st.fresh) }, "Discard changes") : null,
      ls ? h("button", { class: "small ghost", onclick: versions }, "Versions") : null,
      sv || ls ? h("button", { class: "small ghost", onclick: () => load(!st.fresh) }, st.fresh ? "Back to the saved version" : "Regenerate from latest data") : null,
      h("button", { class: "small ghost", onclick: () => downloadFile(`/players/${p.id}/individual-plan.xlsx?window=${window}${st.fresh ? "&fresh=true" : ""}`, "individual-plan.xlsx").catch((x) => toast(x.message)) }, "Excel")));
  }
  function render() {
    const vlist = st.versions && st.versions.length ? h("details", { open: true }, h("summary", {}, "Saved versions"), h("ul", { class: "reviews" },
      st.versions.map((v) => h("li", {}, h("strong", {}, `Version ${v.version}`), ` · ${new Date(v.saved_at).toLocaleString()} · ${v.saved_by || "–"} · from ${v.based_on}`,
        v.edits ? ` · ${v.edits} edit(s)` : "", v.note ? h("div", { class: "sub" }, v.note) : null)))) : null;
    host.replaceChildren(h("h3", {}, "Individual seasonal plan"), bar(), msg, vlist,
      st.editing ? h("p", { class: "hint" }, "Edit mode: changes preview instantly and are kept only when you save a version.") : null,
      ...planView(st.plan, { editing: st.editing, edit: preview, onLog: canEdit && !st.editing ? () => logForm(p, st.plan, () => load(false)) : null }));
  }
  try { await load(false); } catch (x) { host.replaceChildren(h("div", { class: "err" }, x.message)); }
}

function logForm(p, plan, done) {
  const phase = plan.progress.current_phase;
  const ph = plan.phases.find((x) => x.phase === phase) || plan.phases[0];
  const today = new Date().toISOString().slice(0, 10);
  const date = h("input", { type: "date", value: today, max: today });
  const minutes = h("input", { type: "number", min: 1, max: 300, placeholder: "e.g. 40" }), rpe = h("input", { type: "number", min: 1, max: 10, placeholder: "1-10" });
  const rows = [];
  for (const a of ph.areas) for (const e of a.exercises) {
    const pg = plan.progress.exercises[`${ph.phase}|${a.area}|${e.name}`] || {};
    const r = { a, e, done: h("input", { type: "checkbox", checked: true }), sets: h("input", { type: "number", class: "tiny", min: 0, max: 100, value: pg.current_sets ?? "" }),
      reps: h("input", { type: "number", class: "tiny", min: 0, max: 500, value: pg.current_reps ?? "" }), ok: h("input", { type: "checkbox", checked: true }), pain: h("input", { type: "checkbox" }) };
    rows.push(r);
  }
  const err = h("div", { class: "err", role: "alert" });
  $("#main").replaceChildren(h("div", { class: "card" }, h("h2", {}, `Log a focus session · ${p.full_name}`),
    h("p", { class: "sub" }, `${ph.label}. Untick anything not done. Tick pain if felt: the dose steps back and the physio should be told.`),
    h("div", { class: "grid" }, field("Date", date), field("Minutes (adds to workload)", minutes), field("Session RPE", rpe)),
    h("div", { class: "scroll" }, h("table", { class: "log" }, h("thead", {}, h("tr", {}, ["Done", "Exercise", "Sets", "Reps", "Technique good", "Pain"].map((c) => h("th", {}, c)))),
      h("tbody", {}, rows.map((r) => h("tr", {}, h("td", {}, r.done), h("td", { class: "wrap" }, h("strong", {}, r.e.name), h("div", { class: "sub" }, r.a.label)),
        h("td", {}, r.sets), h("td", {}, r.reps), h("td", {}, r.ok), h("td", {}, r.pain)))))),
    err, h("div", { class: "row" }, h("button", { onclick: async () => {
      err.textContent = "";
      const items = rows.filter((r) => r.done.checked).map((r) => ({ phase: ph.phase, area: r.a.area, exercise: r.e.name,
        sets_done: r.sets.value === "" ? null : +r.sets.value, reps_done: r.reps.value === "" ? null : +r.reps.value, technique_ok: r.ok.checked, pain: r.pain.checked }));
      if (!items.length) { err.textContent = "Tick at least one exercise."; return; }
      try {
        await api(`/players/${p.id}/plan-sessions`, { method: "POST", body: { log_date: date.value || today, minutes: minutes.value ? +minutes.value : null,
          rpe: rpe.value ? +rpe.value : null, season_id: plan.season.id, items } });
        toast("Session logged"); S.pid = p.id; go("players");
      } catch (x) { err.textContent = x.message; }
    } }, "Save session"), h("button", { class: "ghost", onclick: () => { S.pid = p.id; go("players"); } }, "Cancel"))));
}

// ───────────── role skill grids (Development / Adaptability / Progress Status) ─────────────
async function roleSkillsCard(p, host, kind = "development") {
  host.replaceChildren(h("h2", {}, "Role skills"), h("div", { class: "sub loading" }, "Loading…"));
  let d;
  try { d = await api(`/players/${p.id}/role-skills?kind=${kind}`); } catch (x) { return host.replaceChildren(h("h2", {}, "Role skills"), h("p", { class: "sub" }, x.message)); }
  const canEdit = can("coach", "sc_coach", "admin");
  const today = new Date().toISOString().slice(0, 10);
  const date = h("input", { type: "date", value: today, max: today, "aria-label": "Assessment date" });
  const rows = [];
  const opts = [["", "–"], ...Object.entries(d.legend)];
  const paint = (s) => { s.className = "rate st-" + (s.value || "none"); };
  const groups = d.groups.map((g) => h("div", { class: "pdp-group" }, h("h4", {}, g.group), g.items.map((it) => {
    const s = h("select", { "aria-label": `${g.group}: ${it.skill}`, disabled: !canEdit, onchange: (e) => paint(e.target) },
      opts.map(([v, t]) => h("option", { value: v, selected: (it.status ?? "") === v }, t)));
    paint(s);
    const note = h("input", { class: "tiny wide", value: it.coach_note || "", maxLength: 500, placeholder: "note", disabled: !canEdit, "aria-label": `Note for ${it.skill}` });
    rows.push({ it, s, note });
    return h("div", { class: "rs-item" }, h("span", {}, it.skill), s, note);
  })));
  const err = h("div", { class: "err", role: "alert" });
  host.replaceChildren(h("div", { class: "bar" }, h("h2", {}, "Role skills"),
      h("select", { class: "tiny", "aria-label": "Skill sheet", onchange: (e) => roleSkillsCard(p, host, e.target.value) }, d.kinds.map((k) => h("option", { value: k.kind, selected: k.kind === kind }, k.label)))),
    h("p", { class: "sub" }, (d.last_assessed ? `Last assessed ${fdate(d.last_assessed)}. ` : "Not assessed yet. ")),
    h("div", { class: "pdp-grid" }, groups),
    canEdit ? h("div", { class: "row" }, h("label", { class: "inline" }, "Assessed on ", date), h("button", { class: "small", onclick: async () => {
      err.textContent = "";
      const items = rows.filter((r) => r.s.value !== (r.it.status ?? "") || r.note.value !== (r.it.coach_note || ""))
        .map((r) => ({ template_id: r.it.id, status: r.s.value || null, coach_note: r.note.value || null }));
      if (!items.length) return toast("No changes to save");
      try { await api(`/players/${p.id}/role-skills?kind=${kind}`, { method: "PUT", body: { period_start: date.value || today, items } }); toast("Role skills saved"); roleSkillsCard(p, host, kind); }
      catch (x) { err.textContent = x.message; }
    } }, "Save")) : null, err);
}

// ───────────── PDP development ratings (coach 1-5; feeds the individual plan) ─────────────
async function pdpCard(p, host) {
  host.replaceChildren(h("h2", {}, "Development ratings (PDP)"), h("div", { class: "sub loading" }, "Loading…"));
  let d;
  try { d = await api(`/players/${p.id}/pdp`); } catch (x) { return host.replaceChildren(h("h2", {}, "Development ratings (PDP)"), h("p", { class: "sub" }, x.message)); }
  const canEdit = can("coach", "sc_coach", "admin");
  const today = new Date().toISOString().slice(0, 10);
  const date = h("input", { type: "date", value: today, max: today, "aria-label": "Rating date" });
  const sels = [];
  const paint = (s) => { s.className = "rate" + (s.value ? " r" + s.value : ""); };
  const groups = d.groups.map((g) => h("div", { class: "pdp-group" }, h("h4", {}, g.group), g.items.map((it) => {
    const s = h("select", { "aria-label": `${g.group}: ${it.skill}`, disabled: !canEdit, onchange: (e) => paint(e.target) },
      [["", "–"], ["1", "1"], ["2", "2"], ["3", "3"], ["4", "4"], ["5", "5"]].map(([v, t]) => h("option", { value: v, selected: String(it.rating ?? "") === v }, t)));
    paint(s);
    sels.push({ it, s });
    return h("label", { class: "pdp-item" }, h("span", {}, it.skill), s);
  })));
  const err = h("div", { class: "err", role: "alert" });
  host.replaceChildren(h("div", { class: "bar" }, h("h2", {}, "Development ratings (PDP)"),
      h("span", { class: "sub" }, d.last_rated_on ? "Last rated " + fdate(d.last_rated_on) : "Not rated yet")),
    h("p", { class: "sub" }, "1–2 improve · 3 average · 4–5 strength."),
    h("div", { class: "pdp-grid" }, groups),
    canEdit ? h("div", { class: "row" }, h("label", { class: "inline" }, "Rated on ", date), h("button", { class: "small", onclick: async () => {
      err.textContent = "";
      const ratings = {};
      for (const { it, s } of sels) if (s.value !== String(it.rating ?? "")) ratings[it.id] = s.value ? +s.value : null;
      if (!Object.keys(ratings).length) return toast("No changes to save");
      try { await api(`/players/${p.id}/pdp`, { method: "PUT", body: { rated_on: date.value || today, ratings } }); toast("Ratings saved"); pdpCard(p, host); }
      catch (x) { err.textContent = x.message; }
    } }, "Save ratings")) : null, err);
}

async function testingCard(p, host, window) {
  host.replaceChildren(h("h2", {}, "Physical tests (SLC SOP)"), h("div", { class: "sub loading" }, "Loading…"));
  let t;
  try { t = await api(`/players/${p.id}/testing` + (window ? `?window=${window}` : "")); }
  catch (x) { return host.replaceChildren(h("h2", {}, "Physical tests (SLC SOP)"), h("div", { class: "sub" }, x.message)); }
  const cat = t.category, w = t.window;
  const planHost = h("div"), progHost = h("div");
  const head = h("div", { class: "bar" }, h("h2", {}, "Physical tests (SLC SOP)"), windowPicker(w, (v) => testingCard(p, host, v)));
  host.replaceChildren(head);
  if (!t.sessions.some((s) => s.window === w)) {
    host.append(h("div", { class: "sub" }, "No results for this window yet. Import them in the Tests tab."));
  } else {
    const sess = t.sessions.find((s) => s.window === w);
    host.append(h("div", { class: "row" }, bandChip(cat), h("span", { class: "chip" }, sess.level_label), readyChip(t.readiness),
      h("span", { class: "sub" }, `Tested ${sess.test_date ? fdate(sess.test_date) : "–"} · height ${fmt(sess.height_cm)} cm · weight ${fmt(sess.weight_kg)} kg`)),
      cat.overall != null ? h("p", {}, `Overall ${cat.overall} of 100 against ${cat.cohort_size} ${sess.level_label} players. Not a pass or fail mark.`) : null,
      cat.note ? h("p", { class: "sub" }, cat.note) : null,
      cat.areas.some((a) => a.percentile != null) ? h("div", { class: "card inner" }, h("h3", {}, "Area profile"),
        h("p", { class: "sub" }, "Rank within the player's level (100 = best). Below the middle = focus area."),
        Charts.hbars({ ariaLabel: "Area rank inside level", max: 100, refs: [{ value: 50, label: "middle" }],
          data: cat.areas.map((a) => ({ label: a.label, value: a.percentile, cls: a.percentile == null ? "c-muted" : a.percentile < 50 ? "c-s2" : "c-s1",
            display: a.percentile == null ? "not ranked" : Charts.num(a.percentile, 1) + (a.percentile < 50 ? " · focus" : ""),
            tip: [a.label, a.percentile == null ? "Not ranked (missing result or small group)" : `Rank ${a.percentile} of 100`, ...a.tests.map((t) => `${t.label}: ${t.display ?? "–"}`)] })) })) : null,
      areaTable(cat),
      cat.focus_areas.length ? h("p", {}, h("strong", {}, "Focus areas (below the middle): "), cat.focus_areas.map((f) => f.label).join(", ")) : (cat.band ? h("p", {}, "No area is below the middle.") : null),
      h("div", { class: "row" },
        h("button", { class: "small", onclick: () => planPanel(p, planHost, w) }, "Show individual plan")),
      progHost, planHost, h("p", { class: "sub" }, "Confidential: squad coaches, S&C and admin only."));
    if (t.sessions.length >= 2) api(`/players/${p.id}/test-progress`).then((pr) => progHost.replaceChildren(progressView(pr))).catch(() => {});
  }
}

async function testingTab() {
  const main = $("#main");
  if (!S.season) return main.replaceChildren(h("h1", {}, "Tests"), h("div", { class: "card" }, "This squad has no season yet. Create one in Admin → Seasons."));
  let window = main.dataset.window || "baseline";
  const canImport = can("sc_coach", "admin");
  const table = h("div", { class: "card" });
  const importHost = h("div", { class: "card" });
  main.replaceChildren(h("div", { class: "bar" }, h("h1", {}, "Physical tests"), h("div", { class: "row" }, seasonPicker(() => testingTab()), windowPicker(window, (v) => { main.dataset.window = v; testingTab(); }))),
    canImport ? importHost : null, table);

  if (canImport) {
    const file = h("input", { type: "file", accept: ".xlsx", "aria-label": "Test results workbook" });
    const result = h("div");
    const send = async (confirm) => {
      if (!file.files[0]) return toast("Choose the filled .xlsx file first");
      const buf = await file.files[0].arrayBuffer();
      const res = await fetch(`/squads/${S.squad.id}/test-import?season_id=${S.season.id}&window=${window}&confirm=${confirm}&filename=${encodeURIComponent(file.files[0].name)}`,
        { method: "POST", headers: { Authorization: "Bearer " + S.token, "Content-Type": "application/octet-stream" }, body: buf });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) return result.replaceChildren(h("div", { class: "err" }, j.detail || "Upload failed"));
      result.replaceChildren(
        h("p", {}, j.saved ? h("strong", {}, `Saved ${j.accepted.length} player(s).`) : h("strong", {}, `${j.accepted.length} row(s) are valid. Nothing is saved yet.`),
          ` ${j.errors.length} problem(s), ${j.blank_rows} blank row(s) ignored.`),
        j.errors.length ? h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Sheet", "Row", "Column", "Problem"].map((c) => h("th", {}, c)))),
          h("tbody", {}, j.errors.map((e) => h("tr", {}, h("td", {}, e.sheet), h("td", {}, e.row), h("td", {}, e.column), h("td", { class: "down" }, e.message)))))) : null,
        !j.saved && j.accepted.length ? h("div", { class: "row" }, h("button", { onclick: async () => { await send(true); testingTab(); } }, `Save ${j.accepted.length} valid row(s)`),
          h("span", { class: "sub" }, "Rows with problems are not saved.")) : null);
    };
    importHost.replaceChildren(h("h2", {}, "Import test results"),
      h("ol", { class: "sub" }, h("li", {}, "Download the template."), h("li", {}, "Fill the trials (times as mm.ss, e.g. 8.25). Leave blanks if not tested."),
        h("li", {}, "Upload it, check the preview, then save.")),
      h("div", { class: "row" }, h("button", { class: "small", onclick: () => downloadFile(`/squads/${S.squad.id}/test-template.xlsx?season_id=${S.season.id}&window=${window}`, "test-template.xlsx").catch((x) => toast(x.message)) }, "Download template"),
        file, h("button", { class: "small", onclick: () => send(false).catch((x) => toast(x.message)) }, "Check file")), result);
  }

  const prog = h("div", { class: "card" });
  const c = await api(`/squads/${S.squad.id}/seasons/${S.season.id}/test-categories?window=${window}`);
  const tested = c.players.filter((r) => r.band);
  const bandCls = ["c-q1", "c-q2", "c-q3", "c-q4", "c-q5"];
  const focusCount = {};
  c.players.forEach((r) => r.focus_areas.forEach((f) => (focusCount[f] = (focusCount[f] || 0) + 1)));
  const focus = Object.entries(focusCount).sort((a, b) => b[1] - a[1]);
  const charts = h("div", { class: "dash-grid two" },
    card("Players per band", tested.length ? `${tested.length} of ${c.players.length} players have a band in this window.` : "No bands yet for this window.",
      tested.length ? Charts.columns({ ariaLabel: "Players per band", highlight: -1, capAll: true, height: 160, format: (v) => `${v} player${v === 1 ? "" : "s"}`,
        data: c.band_names.map((name, i) => { const v = tested.filter((r) => r.band === i + 1).length;
          return { label: `${i + 1} ${name}`, value: v, cls: bandCls[i], tip: [`Band ${i + 1} · ${name}`, `${v} player${v === 1 ? "" : "s"}`] }; }) })
        : h("p", { class: "sub" }, `A band needs at least ${c.min_cohort} players of the same level with results.`)),
    card("Most common focus areas", "Players below the middle, per area.",
      Charts.hbars({ ariaLabel: "Players per focus area", format: (v) => `${v} player${v === 1 ? "" : "s"}`,
        data: focus.map(([label, v]) => ({ label, value: v, cls: "c-s2" })), empty: "No focus areas yet." })));
  main.insertBefore(charts, table);
  api("/meta/age-norms").then((n) => main.append(ageNormsCard(n, S.squad.age_group || "U15"))).catch(() => {});
  table.replaceChildren(h("h2", {}, `Categories · ${c.window_label}`),
    h("p", { class: "sub" }, `Ranked within the same level only. A band needs ${c.min_cohort}+ players of a level.`),
    h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Player", "Level", "Band", "Score", "Focus areas", "Readiness"].map((x) => h("th", {}, x)))),
      h("tbody", {}, c.players.map((r) => h("tr", { class: "click", onclick: () => { S.pid = r.player_id; go("players"); } },
        h("td", {}, r.player), h("td", {}, r.level_label || "Not tested"), h("td", {}, r.band ? bandChip(r) : "–"), h("td", {}, r.overall ?? "–"),
        h("td", {}, r.focus_areas.join(", ") || "–"), h("td", {}, readyChip(r.readiness))))))));
  const sp = await api(`/squads/${S.squad.id}/seasons/${S.season.id}/test-progress`);
  if (sp.windows_with_results.length >= 2) {
    prog.replaceChildren(h("h2", {}, "Progress since the first test"),
      h("p", { class: "sub" }, "Each player against their own earlier results."),
      h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Player", "Band movement", "Tests improved", "Below middle before, not now", "Newly below middle"].map((x) => h("th", {}, x)))),
        h("tbody", {}, sp.players.map((r) => h("tr", { class: "click", onclick: () => { S.pid = r.player_id; go("players"); } },
          h("td", {}, r.player), h("td", {}, r.band_text ?? "–"), h("td", {}, r.tests_compared ? `${r.tests_improved} of ${r.tests_compared}` : "–"),
          h("td", {}, r.focus_resolved.join(", ") || "–"), h("td", {}, r.focus_new.join(", ") || "–")))))));
    main.append(prog);
  }
}

// ───────────── boot ─────────────
$("#logout").addEventListener("click", signOut);
S.token = store.get();
splash().then(() => (S.token ? start() : showLogin(location.hash === AUTH_HASH.signup ? "signup" : "signin")));
