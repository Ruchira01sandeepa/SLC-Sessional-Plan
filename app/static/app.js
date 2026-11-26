"use strict";
/* SLC junior (U15 / U17) web UI. No build step, no dependencies.
   Security rule: API data is only ever inserted as text (textContent / createTextNode), never as HTML. */

// ───────────── tiny helpers ─────────────
// DOM append()/replaceChildren() turn a null/false child into the text "null"/"false". Conditional children
// (`cond ? node : null`) are used everywhere here, so make both calls skip empty values (and unwrap arrays).
for (const name of ["append", "replaceChildren"]) {
  const native = Element.prototype[name];
  Element.prototype[name] = function (...kids) { return native.apply(this, kids.flat(Infinity).filter((k) => k != null && k !== false)); };
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
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
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
    throw new Error(Array.isArray(d) ? d.map((e) => (e.msg || "").replace(/^Value error, /, "")).join("; ")
      : d && typeof d === "object" ? [d.message, ...(d.errors || []).map((e) => e.message)].filter(Boolean).join(" · ") : d || "Something went wrong");
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
    const admin = role.value === "admin";
    roleHint.hidden = !off && !admin;
    roleHint.textContent = off ? `${SIGNUP_ROLE_LABEL[role.value]} sign-in is not open yet.`
      : admin ? "Administrator requests are checked by the current administrator. Say who you are in the note below." : "";
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
  if (S.squad && can("coach", "sc_coach", "admin")) tabs.push(["physical", "Physical"], ["tests", "Tests"]);
  if (S.squad && can("coach", "admin")) tabs.push(["plan", "Seasonal plan"]);
  if (can("admin")) tabs.push(["admin", "Admin"]);
  const nav = $("#tabs"); nav.hidden = false;
  nav.replaceChildren(...tabs.map(([k, label]) => h("button", { "aria-current": S.tab === k ? "page" : null, onclick: () => { S.pid = null; S.from = null; go(k); } }, label)));
}

function go(tab) {
  if (tab !== "physical") S.athletePid = null;
  S.tab = tab; drawTabs();
  Charts.hide();
  document.body.classList.toggle("wide", tab === "overview" || tab === "fitness");
  const view = { overview: overviewTab, players: S.pid ? () => playerView(S.pid) : playersTab, calendar: calendarTab, fitness: fitnessTab, workload: workloadTab, physical: physicalTab, tests: testingTab, plan: () => planTab(), admin: adminTab }[tab];
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
  const openPlayer = (id) => () => { S.pid = id; S.from = "overview"; go("players"); };
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

  // bowling, split into fast and spin; each fast bowler is checked against the spell / day / days-in-7 limits
  const overLimit = (r) => {
    const L = r.bowling_limits; if (!L) return [];
    return [L.max_spell_overs && r.max_spell_7d > L.max_spell_overs ? `longest spell ${Charts.num(r.max_spell_7d, 1)} > ${L.max_spell_overs}` : null,
      L.max_match_day_overs && r.max_day_overs_7d > L.max_match_day_overs ? `${Charts.num(r.max_day_overs_7d, 1)} overs in a day > ${L.max_match_day_overs}` : null,
      L.max_bowling_days_week && r.bowling_days_7d > L.max_bowling_days_week ? `${r.bowling_days_7d} bowling days > ${L.max_bowling_days_week}` : null].filter(Boolean);
  };
  const oversBars = (list, label, empty) => Charts.hbars({ ariaLabel: label, format: (v) => Charts.num(v, 1),
    data: [...list].sort((a, b) => (b.overs_7d || 0) - (a.overs_7d || 0)).map((r) => {
      const over = overLimit(r);
      return { label: r.name, value: r.overs_7d || 0, cls: over.length ? "c-critical" : ROLE_CLS[r.role], onClick: openPlayer(r.player_id),
        sub: [`${r.bowling_days_7d} day(s)`, r.max_day_overs_7d ? `max ${Charts.num(r.max_day_overs_7d, 1)} in a day` : null,
          r.max_spell_7d ? `spell ${Charts.num(r.max_spell_7d, 1)}` : null, r.role === "all_rounder" ? "all-rounder" : null].filter(Boolean).join(" · "),
        display: Charts.num(r.overs_7d || 0, 1) + (over.length ? " ⚠" : ""),
        tip: [r.name, `${Charts.num(r.overs_7d || 0, 1)} overs in 7 days`, `${r.bowling_days_7d} bowling day(s)`, ROLE[r.role], ...over] };
    }), empty });
  const fast = rows.filter((r) => r.role === "fast_bowler");
  const spin = rows.filter((r) => r.role === "spin_bowler" || r.role === "all_rounder");
  const fastOver = fast.filter((r) => overLimit(r).length).length;
  const fastSub = (lim ? `${S.squad.age_group} fast-bowler limits: ${lim.max_spell_overs} a spell · ${lim.max_match_day_overs} a day · ${lim.max_bowling_days_week} days in 7` : "")
    + (fastOver ? ` · ${fastOver} over a limit` : fast.length ? " · all within limits" : "");

  // batting: balls faced, batting days and keeping minutes in the same 7 days
  const batters = rows.filter((r) => BATS.includes(r.role));
  const battingChart = Charts.hbars({ ariaLabel: "Balls faced in the last 7 days",
    data: [...batters].sort((a, b) => (b.balls_faced_7d || 0) - (a.balls_faced_7d || 0)).map((r) => ({ label: r.name, value: r.balls_faced_7d || 0,
      cls: ROLE_CLS[r.role], onClick: openPlayer(r.player_id), display: (r.balls_faced_7d || 0).toLocaleString(),
      sub: [`${r.batting_days_7d} batting day(s)`, r.keeping_minutes_7d ? `${r.keeping_minutes_7d} min keeping` : null, r.role !== "batter" ? ROLE[r.role] : null].filter(Boolean).join(" · "),
      tip: [r.name, `${r.balls_faced_7d || 0} balls faced in 7 days`, `${r.batting_days_7d} batting day(s)`, r.keeping_minutes_7d ? `${r.keeping_minutes_7d} min keeping` : null, ROLE[r.role]] })),
    empty: "No batters in this squad." });
  const totalBalls = batters.reduce((a, r) => a + (r.balls_faced_7d || 0), 0);
  const batSub = `Balls faced (net and match). ${totalBalls.toLocaleString()} in total` + (batters.length ? ` · ${batters.filter((r) => !r.balls_faced_7d).length} with none logged` : "");

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
    fast.length || spin.length ? h("div", { class: "dash-grid two" },
      card("Fast bowling, last 7 days", fastSub, oversBars(fast, "Overs by fast bowlers in the last 7 days", "No fast bowlers in this squad.")),
      card("Spin bowling, last 7 days", "Spinners and all-rounders. No automatic limit; the coach sets one per player if needed.",
        oversBars(spin, "Overs by spin bowlers and all-rounders in the last 7 days", "No spin bowlers or all-rounders in this squad."))) : null,
    batters.length ? card("Batting, last 7 days", batSub, battingChart) : null);
}
const fixTz = (s) => (s.endsWith("Z") || /[+-]\d\d:\d\d$/.test(s) ? s : s + "Z");

// ───────────── players ─────────────
async function playersTab() {
  const players = await api(`/players?squad_id=${S.squad.id}`);
  const main = $("#main");
  main.replaceChildren(
    h("div", { class: "bar" }, h("h1", {}, S.squad.name), can("coach", "admin") ? h("button", { onclick: () => addPlayerForm() }, "+ Add player") : null),
    players.length ? h("div", { class: "list" }, players.map((p) => h("button", { class: "item", onclick: () => { S.pid = p.id; go("players"); } },
      h("span", {}, h("strong", {}, (p.squad_no ? "#" + p.squad_no + "  " : "") + p.full_name), h("br"), h("span", { class: "sub" }, ROLE[p.role] + " · age " + p.age), p.captaincy ? h("span", { class: "chip" }, CAPT[p.captaincy]) : null, p.standby ? h("span", { class: "chip" }, "Stand-by") : null),
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

const FROM_LABEL = { players: "Players", physical: "Physical", tests: "Tests", workload: "Workload", overview: "Overview", fitness: "Fitness" };
// Close an opened plan and return to the plan buttons above it.
const planBack = (host) => h("button", { class: "ghost small", onclick: () => {
  let top = host.previousElementSibling;
  while (top && !top.querySelector("button")) top = top.previousElementSibling;      // the row with the plan buttons
  host.replaceChildren();
  (top || host).scrollIntoView({ behavior: "smooth", block: "center" });
} }, "← Back");

async function playerView(id) {
  const [p, screenings] = await Promise.all([api("/players/" + id), api(`/players/${id}/screenings`)]);
  const main = $("#main");
  const from = S.from && S.from !== "players" ? S.from : "players";
  const back = h("button", { class: "ghost small", onclick: () => { S.pid = null; S.from = null; go(from); } }, "← " + (FROM_LABEL[from] || "Players"));
  const head = h("div", { class: "card" }, h("div", { class: "bar" }, h("h1", {}, p.full_name), h("span", { class: "chip " + p.availability }, p.availability)),
    h("div", { class: "sub" }, `${ROLE[p.role]} · age ${p.age} · ${p.gender}` + (p.school_or_club ? " · " + p.school_or_club : "")),
    p.availability_note ? h("p", {}, "Note: " + p.availability_note) : null,
    h("div", { class: "sub" }, [p.captaincy && CAPT[p.captaincy], p.standby && "Stand-by", p.batting_hand && "Bats " + p.batting_hand, p.style ? "Bowls " + p.style : p.bowling_arm && "Bowls " + p.bowling_arm, p.school_or_club, p.district, p.guardian_name && "Guardian: " + p.guardian_name].filter(Boolean).join(" · ")));
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
  // (the Development ratings (PDP) and Role skills cards are not shown on the player page; pdpCard / roleSkillsCard are kept)
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
  main.replaceChildren(h("div", { class: "empty loading" }, "Loading the test report…"));
  const [d, cats, brand] = await Promise.all([
    api(`/squads/${S.squad.id}/seasons/${S.season.id}/test-results?window=${phase}`).catch((x) => ({ error: x.message })),
    api(`/squads/${S.squad.id}/seasons/${S.season.id}/test-categories?window=${phase}`).catch(() => null), branding()]);
  const controls = h("div", { class: "row no-print" }, seasonPicker(fitnessTab),
    h("select", { "aria-label": "Test window", onchange: (e) => { S.phase = e.target.value; fitnessTab(); } },
      Object.entries(PHASE).map(([k, v]) => h("option", { value: k, selected: k === phase }, v))),
    d.error ? null : h("button", { class: "small", onclick: () => downloadFile(`/squads/${S.squad.id}/seasons/${S.season.id}/test-summary.pdf?window=${phase}`,
      "Test-results-summary.pdf").catch((x) => toast(x.message)) }, "Download summary (PDF)"),
    d.error ? null : h("button", { class: "small ghost", onclick: () => window.print() }, "Print page"),
    d.error ? null : h("button", { class: "small ghost", onclick: () => downloadFile(`/squads/${S.squad.id}/seasons/${S.season.id}/physical-report.xlsx?window=${phase}`,
      "physical-report.xlsx").catch((x) => toast(x.message)) }, "Download Excel"));
  if (d.error) return main.replaceChildren(h("div", { class: "bar" }, h("h1", {}, "Fitness report"), controls),
    h("div", { class: "card" }, "The physical test report is for the coaches and S&C staff. ", h("span", { class: "sub" }, d.error)));
  main.replaceChildren(fitnessReport(d, cats, brand, phase, controls));
}

// Professional squad test report: header with the logo, key numbers, squad vs U15, one ranked chart per test, body composition,
// past tests and the full results table. Prints cleanly (Print / save PDF).
const AGE_CLS = { strong: "c-good", on_track: "c-s1", developing: "c-warning", below: "c-critical" };
const AGE_TXT = { strong: "Strong for age", on_track: "On track", developing: "Developing", below: "Below reference" };

function fitnessReport(d, cats, brand, phase, controls) {
  const used = d.tests.filter((t) => d.players.some((r) => r.values[t.key] != null));
  const tested = d.players.filter((r) => r.level);
  const catBy = Object.fromEntries(((cats && cats.players) || []).map((c) => [c.player_id, c]));
  const open = (r) => () => fitnessForm({ id: r.player_id, full_name: r.name, role: r.role }, phase);
  const mean = (vals) => { const x = vals.filter((v) => v != null && !isNaN(v)); return x.length ? x.reduce((a, b) => a + b, 0) / x.length : null; };
  const f1 = (v) => (v == null ? "–" : (+v).toFixed(1));
  const mmss = (s) => `${Math.floor(s / 60)}.${String(Math.round(s % 60)).padStart(2, "0")}`;
  const show = (t, v) => (v == null ? "–" : t.kind === "mmss" ? mmss(v) : t.kind === "count" ? String(Math.round(v)) : (+v).toFixed(2));
  const better = (t, a, b) => (t.higher_is_better ? a > b : a < b);
  const dates = [...new Set(tested.map((r) => r.test_date).filter(Boolean))].sort();
  const levels = [...new Set(tested.map((r) => r.level_label))];
  const short = (n) => { const p = n.split(" "); return p.length > 1 ? `${p[0]} ${p[p.length - 1][0]}.` : n; };

  // ── header ──
  const head = h("header", { class: "rep-head" },
    h("div", { class: "rep-brand" }, brand.logo ? h("img", { src: brand.logo, alt: brand.name || "Sri Lanka Cricket", class: "rep-logo" }) : null,
      h("div", {}, h("div", { class: "rep-org" }, "Sri Lanka Cricket · Strength and conditioning"), h("h1", {}, "Physical Test Report"),
        h("div", { class: "rep-meta" }, [d.squad, d.season.name, d.window_label,
          dates.length ? (dates.length === 1 ? `Tested ${fdate(dates[0])}` : `Tested ${fdate(dates[0])} to ${fdate(dates[dates.length - 1])}`) : "Not tested yet",
          levels.length === 1 ? levels[0] : null].filter(Boolean).join("  ·  ")))),
    controls);
  if (!tested.length) {
    return h("div", { class: "report" }, head, h("div", { class: "card" }, h("h2", {}, `No ${d.window_label.toLowerCase()} results yet`),
      h("p", { class: "sub" }, "Import the test template on the Tests page, or select a player below to enter results."),
      h("div", { class: "row" }, d.players.map((r) => h("button", { class: "small ghost", onclick: open(r) }, r.name)))),
      pastTestsCard(d, used));
  }

  // ── key numbers ──
  const ageVals = tested.flatMap((r) => Object.values(r.age).filter(Boolean));
  const meets = ageVals.filter((b) => b === "on_track" || b === "strong").length;
  const pts = tested.map((r) => catBy[r.player_id] && catBy[r.player_id].benchmark).filter(Boolean);
  const pct = ageVals.length ? Math.round((meets / ageVals.length) * 100) : null;
  const kpis = h("div", { class: "kpis" },
    Charts.stat({ label: "Players tested", value: `${tested.length} / ${d.players.length}`, sub: `${used.length} tests · best of 3 trials` }),
    Charts.stat({ label: `Results at or above ${d.age_group} expected`, value: pct == null ? "–" : `${pct}%`, sub: `${meets} of ${ageVals.length} results`,
      tone: pct == null ? null : pct >= 60 ? "good" : pct >= 40 ? "warning" : "critical" }),
    Charts.stat({ label: `Average ${d.age_group} points`, value: pts.length ? f1(mean(pts.map((b) => b.total))) : "–",
      sub: pts.length ? `out of ${pts[0].max} · SLC benchmark` : "needs a full test set" }),
    Charts.stat({ label: "Squad average", value: `${f1(mean(tested.map((r) => r.height_cm)))} cm`,
      sub: `${f1(mean(tested.map((r) => r.weight_kg)))} kg · sum of 8 skinfolds ${f1(mean(tested.map((r) => r.skinfold_sum)))} mm` }));

  // ── squad vs age reference ──
  const vsRef = used.filter((t) => t.reference).map((t) => {
    const have = tested.filter((r) => r.age[t.key]);
    const ok = have.filter((r) => ["on_track", "strong"].includes(r.age[t.key])).length;
    const p = have.length ? Math.round((ok / have.length) * 100) : 0;
    const avg = mean(tested.map((r) => r.values[t.key]));
    return { label: t.label, value: p, display: `${ok}/${have.length} · ${p}%`, cls: p >= 60 ? "c-good" : p >= 40 ? "c-warning" : "c-critical",
      sub: `avg ${show(t, avg)} · ${d.age_group} expected ${t.reference.expected_display} ${t.unit}`,
      tip: [t.label, `${ok} of ${have.length} players at or above ${d.age_group} expected`, `Squad average ${show(t, avg)} ${t.unit}`,
        `Expected ${t.reference.expected_display} · strong ${t.reference.strong_display}`] };
  });
  const bandCount = [1, 2, 3, 4, 5].map((b) => tested.filter((r) => (catBy[r.player_id] || {}).band === b).length);
  const bandCls = ["c-critical", "c-warning", "c-s1", "c-good", "c-q5"];
  const bandNames = (cats && cats.band_names) || ["Band 1", "Band 2", "Band 3", "Band 4", "Band 5"];
  const overview = h("div", { class: "dash-grid wide-left" },
    card(`Squad against the ${d.age_group} reference`, `Share of players at or above the ${d.age_group} expected value, test by test.`,
      Charts.hbars({ data: vsRef, max: 100, refs: [{ value: 50, label: "50%" }], ariaLabel: "Players at or above expected, by test" })),
    card("Squad bands", "Each player's band from the full test set (Band 5 = best in the level group).",
      bandCount.some(Boolean)
        ? Charts.donut({ title: "Bands", parts: bandCount.map((n, i) => ({ label: `Band ${i + 1} · ${bandNames[i] || ""}`.replace(/ · $/, ""), value: n, cls: bandCls[i] })),
          center: { value: String(bandCount.reduce((a, b) => a + b, 0)), label: "players" } })
        : h("p", { class: "sub" }, `Bands need at least ${(cats && cats.min_cohort) || 4} players at the same level.`)));

  // ── one ranked chart per test ──
  const ageLegend = Charts.legend(Object.entries(AGE_TXT).map(([k, v]) => ({ cls: AGE_CLS[k], label: v })));
  const testCards = used.map((t) => {
    const rows = tested.filter((r) => r.values[t.key] != null).sort((a, b) => (better(t, a.values[t.key], b.values[t.key]) ? -1 : 1));
    const avg = mean(rows.map((r) => r.values[t.key]));
    const ref = t.reference;
    const all = [...rows.map((r) => r.values[t.key]), avg, ref ? ref.expected : null].filter((v) => v != null);
    const base = Math.max(0, Math.floor(Math.min(...all) * 0.85));                 // bars start near the lowest value so differences show
    const best = rows[0];
    const refs = [{ value: avg - base, label: `avg ${show(t, avg)}` }];
    if (ref) refs.push({ value: ref.expected - base, label: `${d.age_group} ${ref.expected_display}` });
    const top = Math.max(...all.map((v) => v - base));
    if (refs.length === 2 && Math.abs(refs[0].value - refs[1].value) < top * 0.14) {     // labels would overlap: one label, both lines kept
      const [lo, hi] = refs[0].value <= refs[1].value ? [refs[0], refs[1]] : [refs[1], refs[0]];
      lo.label = `${lo.label} · ${hi.label}`; hi.label = "";
    }
    return card(`${t.label}`, `${t.unit} · ${t.higher_is_better ? "higher" : "lower"} is better · best ${best.name} ${best.results[t.key]}` +
        (base ? ` · axis starts at ${show(t, base)}` : ""),
      Charts.hbars({ ariaLabel: `${t.label} by player`, refs,
        data: rows.map((r) => {
          const ch = r.change && r.change.tests[t.key];
          return { label: short(r.name), sub: r.squad_no != null ? `#${r.squad_no}` : null, value: r.values[t.key] - base,
            display: r.results[t.key] + (ch && ch.state !== "same" ? (ch.state === "improved" ? " ▲" : " ▼") : ""),
            cls: AGE_CLS[r.age[t.key]] || "c-s1", onClick: open(r),
            tip: [r.name, `${r.results[t.key]} ${t.unit}`, r.age[t.key] ? `${AGE_TXT[r.age[t.key]]} for ${d.age_group}` : null,
              ch ? `${ch.text} since ${r.change.label} (was ${ch.from})` : null] };
        }) }));
  });

  // ── body composition ──
  const sf = tested.filter((r) => r.skinfold_sum != null).sort((a, b) => a.skinfold_sum - b.skinfold_sum);
  const sfAvg = mean(sf.map((r) => r.skinfold_sum));
  const ht = tested.filter((r) => r.height_cm != null).sort((a, b) => b.height_cm - a.height_cm);
  const htAvg = mean(ht.map((r) => r.height_cm));
  const htBase = ht.length ? Math.floor(Math.min(...ht.map((r) => r.height_cm)) * 0.85) : 0;
  const body = h("div", { class: "dash-grid two" },
    card("Sum of 8 skinfolds", "mm · ISAK 8 sites · lower = leaner. Track each player's own trend rather than comparing players.",
      Charts.hbars({ ariaLabel: "Sum of 8 skinfolds by player", refs: sfAvg ? [{ value: sfAvg, label: `avg ${f1(sfAvg)}` }] : [],
        empty: "No skinfolds recorded yet.",
        data: sf.map((r) => ({ label: short(r.name) + (r.copied.length ? " *" : ""), value: r.skinfold_sum, display: f1(r.skinfold_sum),
          cls: r.copied.length ? "c-muted" : "c-s3", onClick: open(r), tip: [r.name, `${f1(r.skinfold_sum)} mm`, r.copied.join(". ") || null] })) }),
      sf.some((r) => r.copied.length) ? h("p", { class: "hint warn" }, "* Grey bars were not measured: copied from a comparison player. Measure these players at the next test.") : null),
    card("Height, weight and BMI", `cm · axis starts at ${htBase} cm. BMI is a rough guide only for growing players.`,
      Charts.hbars({ ariaLabel: "Height by player", refs: htAvg ? [{ value: htAvg - htBase, label: `avg ${f1(htAvg)}` }] : [], empty: "No heights recorded yet.",
        data: ht.map((r) => ({ label: short(r.name), sub: `${f1(r.weight_kg)} kg · BMI ${f1(r.bmi)}`, value: r.height_cm - htBase, display: `${f1(r.height_cm)} cm`,
          cls: "c-s1", onClick: open(r), tip: [r.name, `${f1(r.height_cm)} cm`, `${f1(r.weight_kg)} kg`, `BMI ${f1(r.bmi)}`] })) })));

  return h("div", { class: "report" }, head, kpis, overview,
    h("h2", { class: "rep-section" }, "Results by test"), h("div", { class: "rep-legend" }, ageLegend, h("span", { class: "sub" }, "▲ better / ▼ worse than the player's previous test. Select a player to edit.")),
    h("div", { class: "dash-grid two" }, testCards),
    sitReachSection(d, tested, open, short),
    h("h2", { class: "rep-section" }, "Body composition"), body,
    pastTestsCard(d, used),
    h("h2", { class: "rep-section" }, "Full results"), resultsTable(d, used, tested, catBy, open, { mean, f1, show, dates, levels }),
    h("footer", { class: "rep-foot" }, brand.logo ? h("img", { src: brand.logo, alt: "", class: "rep-foot-logo" }) : null,
      h("div", {}, h("strong", {}, `Sri Lanka Cricket · ${d.squad}`), h("div", { class: "sub" },
        `${d.age_group} physical test report · ${d.season.name} · ${d.window_label} · prepared ${fdate(new Date().toISOString().slice(0, 10))}. ` +
        `Reference values: ${d.age_group} youth norms (published where available, otherwise SLC estimates). Best of 3 trials; times in mm.ss.`))));
}

// sit and reach: cm past (+) or short of (-) the toes. Recorded, not ranked; short of the toes = a flexibility focus in the plan.
const srTxt = (v) => (v == null ? "–" : `${v > 0 ? "+" : ""}${(+v).toFixed(1)}`);
const srCls = (v) => (v >= 10 ? "c-good" : v >= 0 ? "c-s1" : "c-warning");
function sitReachSection(d, tested, open, short) {
  const rows = tested.filter((r) => r.sit_reach != null).sort((a, b) => b.sit_reach - a.sit_reach);
  const missing = d.players.filter((r) => r.sit_reach == null);
  if (!rows.length) return h("div", {}, h("h2", { class: "rep-section" }, "Flexibility · sit and reach"),
    h("div", { class: "card" }, h("p", { class: "sub" }, "No sit-and-reach results yet. Select a player to enter one (cm past + or short − of the toes).")));
  const vals = rows.map((r) => r.sit_reach);
  const base = Math.floor(Math.min(0, ...vals)) - 3;                   // bars start below the lowest score, so every player shows
  const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
  const past = rows.filter((r) => r.sit_reach >= 0), shortOf = rows.filter((r) => r.sit_reach < 0), strong = rows.filter((r) => r.sit_reach >= 10);
  const legend = Charts.legend([{ cls: "c-good", label: "10 cm or more past the toes" }, { cls: "c-s1", label: "Reaches the toes" },
    { cls: "c-warning", label: "Short of the toes: flexibility focus" }]);
  return h("div", {}, h("h2", { class: "rep-section" }, "Flexibility · sit and reach"),
    h("div", { class: "dash-grid wide-left" },
      card("Sit and reach", `cm from the toes: + past them, − short of them · axis starts at ${base} cm`,
        Charts.hbars({ ariaLabel: "Sit and reach by player", refs: Math.abs(avg) < (Math.max(...vals) - base) * 0.14
            ? [{ value: Math.min(0, avg) - base, label: `toes · avg ${srTxt(avg)}` }, { value: Math.max(0, avg) - base, label: "" }]
            : [{ value: -base, label: "toes" }, { value: avg - base, label: `avg ${srTxt(avg)}` }],
          data: rows.map((r) => ({ label: short(r.name), sub: r.squad_no != null ? `#${r.squad_no}` : null, value: r.sit_reach - base,
            display: `${srTxt(r.sit_reach)} cm`, cls: srCls(r.sit_reach), onClick: open(r),
            tip: [r.name, `${srTxt(r.sit_reach)} cm`, r.sit_reach < 0 ? "Short of the toes: flexibility is a focus in the plan" : "Reaches the toes"] })) }),
        legend),
      card("Squad flexibility", "Recorded, not ranked. Players short of the toes get daily hamstring and lower-back work in their plan.",
        h("div", { class: "kpis" },
          Charts.stat({ label: "Reach the toes", value: `${past.length} / ${rows.length}`, tone: past.length >= shortOf.length ? "good" : "warning" }),
          Charts.stat({ label: "Squad average", value: `${srTxt(avg)} cm`, sub: avg >= 0 ? "past the toes" : "short of the toes" })),
        shortOf.length ? h("div", {}, h("strong", {}, `Flexibility focus (${shortOf.length})`),
          h("p", { class: "sub" }, shortOf.slice().sort((a, b) => a.sit_reach - b.sit_reach).map((r) => `${r.name} ${srTxt(r.sit_reach)}`).join(" · "))) : null,
        strong.length ? h("div", {}, h("strong", {}, `Strength (${strong.length})`), h("p", { class: "sub" }, strong.map((r) => `${r.name} ${srTxt(r.sit_reach)}`).join(" · "))) : null,
        missing.length ? h("p", { class: "hint warn" }, `Not tested yet: ${missing.map((r) => r.name).join(", ")}.`) : null)));
}

// every test window on record for the squad, with the squad averages and the change from the window before
function pastTestsCard(d, used) {
  const hist = d.history || [];
  if (!hist.length) return null;
  const tests = used.length ? used : d.tests.filter((t) => hist.some((w) => w.means[t.key]));
  const f1 = (v) => (v == null ? "–" : (+v).toFixed(1));
  const trend = (t, w, i) => {
    const prev = hist.slice(0, i).reverse().find((x) => x.means[t.key]);
    if (!prev || !w.means[t.key]) return null;
    const a = prev.means[t.key].value, b = w.means[t.key].value;
    if (Math.abs(b - a) < Math.abs(a) * 0.005) return h("span", { class: "trend same" }, " =");
    const good = t.higher_is_better ? b > a : b < a;
    return h("span", { class: "trend " + (good ? "up" : "down") }, good ? " ▲" : " ▼");
  };
  return h("div", {}, h("h2", { class: "rep-section" }, "Past tests"),
    card("Squad averages, every test on record", hist.length < 2
      ? "This is the first test on record for the squad. The mid-season and end-of-season tests will appear here with the change for each test."
      : "▲ the squad average improved / ▼ got worse since the test before.",
      h("div", { class: "scroll" }, h("table", { class: "rep-table" },
        h("thead", {}, h("tr", {}, [["Test"], ["Date"], ["Players"], ["Height", "cm"], ["Weight", "kg"], ...tests.map((t) => [t.label, t.unit]), ["Sit and reach", "cm from toes"], ["Sum of 8 skinfolds", "mm"]]
          .map(([l, un]) => h("th", {}, l, un ? h("span", { class: "unit" }, un) : null)))),
        h("tbody", {}, hist.map((w, i) => h("tr", { class: w.current ? "current" : "" },
          h("td", {}, h("strong", {}, `${w.window_label}`), h("span", { class: "sub" }, ` · ${w.season}`), w.current ? h("span", { class: "chip" }, " This report") : null),
          h("td", {}, w.date ? fdate(w.date) : "–"), h("td", {}, w.tested), h("td", {}, f1(w.height_cm)), h("td", {}, f1(w.weight_kg)),
          tests.map((t) => h("td", {}, w.means[t.key] ? w.means[t.key].display : "–", trend(t, w, i))),
          h("td", {}, srTxt(w.sit_reach)), h("td", {}, f1(w.skinfold_sum)))))))));
}

// the full table: best results (or all trials), age colour, change since the previous test, skinfold sites on request
function resultsTable(d, used, tested, catBy, open, u) {
  const host = h("div", { class: "card" });
  let showTrials = S.fitTrials === true, showSites = S.fitSites === true;
  const anySR = d.players.some((r) => r.sit_reach != null);
  const anySf = d.players.some((r) => Object.values(r.skinfolds).some((v) => v != null));
  const withLevel = u.levels.length > 1, withDate = u.dates.length > 1;
  const trialsOf = (t) => showTrials && t.kind !== "mmss" && t.kind !== "count";
  const draw = () => {
    const th = (label, unit) => h("th", {}, label, unit ? h("span", { class: "unit" }, unit) : null);
    const head = [th("No."), th("Player"), withLevel ? th("Level") : null, withDate ? th("Date") : null, th("Height", "cm"), th("Weight", "kg"), th("BMI"),
      ...used.flatMap((t) => (trialsOf(t) ? [th(t.label, "trial 1"), th("", "trial 2"), th("", "trial 3"), th("Best", t.unit)] : [th(t.label, t.unit)])),
      anySR ? th("Sit and reach", "cm from toes") : null, ...(showSites ? d.sites.map((x) => th(x.label, "mm")) : []), th("Sum of 8 skinfolds", "mm"), th("Band"), th(`${d.age_group} points`)].filter(Boolean);
    const cell = (r, t) => {
      const ch = r.change && r.change.tests[t.key];
      return h("td", { class: "res" }, r.age[t.key] ? h("span", { class: "dot " + AGE_CLS[r.age[t.key]], title: AGE_TXT[r.age[t.key]] }) : null,
        h("strong", {}, r.results[t.key] ?? "–"),
        ch && ch.state !== "same" ? h("div", { class: "trend " + (ch.state === "improved" ? "up" : "down"), title: `since ${r.change.label} (was ${ch.from})` }, ch.text) : null);
    };
    const avg = (t) => u.show(t, u.mean(tested.map((r) => r.values[t.key])));
    const foot = (label, fn, extra) => h("tr", {}, h("td"), h("td", {}, h("strong", {}, label)), withLevel ? h("td") : null, withDate ? h("td") : null,
      h("td", {}, extra[0]), h("td", {}, extra[1]), h("td", {}, extra[2]), used.flatMap((t) => (trialsOf(t) ? [h("td"), h("td"), h("td"), h("td", {}, fn(t))] : [h("td", {}, fn(t))])),
      anySR ? h("td", {}, extra[3]) : null, showSites ? d.sites.map((x) => h("td", {}, extra[4] ? u.f1(u.mean(d.players.map((r) => r.skinfolds[x.key]))) : "")) : null,
      h("td", {}, h("strong", {}, extra[5])), h("td"), h("td"));
    host.replaceChildren(
      h("div", { class: "bar no-print" }, h("p", { class: "sub" }, `${tested.length} of ${d.players.length} players tested. Best of 3 trials; times in mm.ss (8.25 = 8 min 25 s). ` +
        "The dot shows the result against the age reference; the line under it is the change since the player's previous test."),
        h("div", { class: "row rep-toggles" },
          h("label", {}, h("input", { type: "checkbox", checked: showTrials, onchange: (e) => { showTrials = S.fitTrials = e.target.checked; draw(); } }), " Show all 3 trials"),
          anySf ? h("label", {}, h("input", { type: "checkbox", checked: showSites, onchange: (e) => { showSites = S.fitSites = e.target.checked; draw(); } }), " Show the 8 skinfold sites") : null)),
      h("div", { class: "scroll" }, h("table", { class: "skinfolds rep-table" }, h("thead", {}, h("tr", {}, head)),
        h("tbody", {}, d.players.map((r, i) => {
          const out = [], c = catBy[r.player_id];
          if (r.standby && !(d.players[i - 1] || {}).standby) out.push(h("tr", { class: "group" }, h("td", { colspan: head.length }, "Stand-by players")));
          out.push(h("tr", { class: "click", tabindex: 0, onclick: open(r), onkeydown: (e) => e.key === "Enter" && open(r)(), title: r.copied.join(". ") || null },
            h("td", {}, r.squad_no ?? "–"), h("td", {}, r.name + (r.copied.length ? " *" : "")), withLevel ? h("td", {}, r.level_label || "Not tested") : null,
            withDate ? h("td", {}, r.test_date ? fdate(r.test_date) : "–") : null,
            h("td", {}, fmt(r.height_cm, 1)), h("td", {}, u.f1(r.weight_kg)), h("td", {}, u.f1(r.bmi)),
            used.flatMap((t) => (trialsOf(t)
              ? [...(r.trials[t.key] || [null, null, null]).map((v) => h("td", { class: "sub" }, v ?? "–")), cell(r, t)] : [cell(r, t)])),
            anySR ? h("td", { class: r.sit_reach < 0 ? "down" : "" }, srTxt(r.sit_reach)) : null,
            showSites ? d.sites.map((x) => h("td", {}, u.f1(r.skinfolds[x.key]))) : null,
            h("td", { class: r.third_needed ? "down" : "" }, h("strong", {}, u.f1(r.skinfold_sum))),
            h("td", {}, c && c.band ? bandChip(c) : "–"), h("td", {}, c ? benchChip(c.benchmark) : "–")));
          return out;
        })),
        h("tfoot", {},
          foot("Squad average", avg, [u.f1(u.mean(tested.map((r) => r.height_cm))), u.f1(u.mean(tested.map((r) => r.weight_kg))), u.f1(u.mean(tested.map((r) => r.bmi))),
            srTxt(u.mean(tested.map((r) => r.sit_reach))), true, u.f1(u.mean(tested.map((r) => r.skinfold_sum)))]),
          foot(`${d.age_group} expected`, (t) => (t.reference ? t.reference.expected_display : "–"), ["", "", "", "", false, ""])))),
      d.players.some((r) => r.copied.length) ? h("p", { class: "hint warn" }, "* Skinfolds not measured: copied from the comparison player the coach chose (hover the row). Replace them with real measurements when possible.") : null,
      anySR ? null : h("p", { class: "sub" }, "Sit and reach: no results yet. The column appears once a result is entered."));
  };
  draw();
  return host;
}

// SLC U15 SOP tests (Testing levels table), plus sit and reach and the ISAK 8-site skinfolds (recorded, not ranked)
const SOP_TESTS = [["bronco", "Bronco (1,200 m)", "mm.ss", "provincial"], ["run_2km", "2 km run", "mm.ss", "super_provincial"],
  ["broad_jump", "Standing broad jump", "cm", "super_provincial"], ["pushups", "Push-ups", "valid reps", "super_provincial"],
  ["inverted_row", "Inverted row", "valid reps", "super_provincial"], ["sprint_20m", "20 m sprint", "s", "super_provincial"],
  ["shuttle_5_10_5", "5-10-5 test", "s", "super_provincial"], ["plank", "Standard plank", "s", "super_provincial"]];
const SKINFOLDS = [["sf_triceps", "Triceps"], ["sf_subscapular", "Subscapular"], ["sf_biceps", "Biceps"], ["sf_iliac_crest", "Iliac crest"],
  ["sf_supraspinale", "Supraspinale"], ["sf_abdominal", "Abdominal"], ["sf_front_thigh", "Front thigh"], ["sf_medial_calf", "Medial calf"]];
// ISAK: mean of two within 5%, else a third and the median; one measure counts on its own
const skinfoldFinal = (vals) => {
  const t = vals.filter((v) => v != null && !isNaN(v));
  if (!t.length) return [null, false];
  if (t.length === 1) return [t[0], false];
  if (t.length >= 3) return [[...t].sort((a, b) => a - b)[1], false];
  return [(t[0] + t[1]) / 2, Math.abs(t[0] - t[1]) / Math.min(t[0], t[1]) > 0.05];
};

async function fitnessForm(p, phase) {
  if (!S.season) return toast("Create a season first");
  const canTest = can("sc_coach", "admin");
  const [list, kpis, tst] = await Promise.all([api(`/players/${p.id}/fitness?season_id=${S.season.id}`), p.role ? api(`/meta/role-kpis/${p.role}`) : [],
    api(`/players/${p.id}/testing?season_id=${S.season.id}&window=${phase}`).catch(() => null)]);
  const existing = list.find((t) => t.phase === phase) || {};
  const sess = tst ? tst.sessions.find((x) => x.window === phase) : null;
  const kinputs = kpis.map((m) => [m.field, h("input", { type: "number", step: m.unit === "1-5 rating" ? "1" : "any", min: m.lo, max: m.hi, inputMode: "decimal", value: (existing.role_specific || {})[m.field] ?? "" }), `${m.label} (${m.unit})`]);
  const ph = h("select", { onchange: () => fitnessForm(p, ph.value) }, Object.entries(PHASE).map(([k, v]) => h("option", { value: k, selected: k === phase }, v)));
  const date = h("input", { type: "date", required: true, value: (sess && sess.test_date) || existing.test_date || new Date().toISOString().slice(0, 10) });
  const inputs = FIELDS.map(([k, l, step]) => [k, h("input", { type: step ? "number" : "text", step, value: typeof existing[k] === "number" ? +existing[k].toFixed(3) : existing[k] ?? "", inputMode: "decimal" }), l]);
  const err = h("div", { class: "err", role: "alert" });

  // ── SOP section: one row per test, three trials; the best valid trial counts
  const level = h("select", { "aria-label": "Testing level" }, [["super_provincial", "Super Provincial"], ["provincial", "Provincial"]]
    .map(([v, l]) => h("option", { value: v, selected: (sess ? sess.level : "super_provincial") === v }, l)));
  const height = h("input", { type: "number", step: "0.1", min: 120, max: 200, value: sess && sess.height_cm != null ? sess.height_cm : "" });
  const weight = h("input", { type: "number", step: "0.1", min: 25, max: 120, value: sess && sess.weight_kg != null ? sess.weight_kg : "" });
  const trialRow = (key, label, unit, shown, extra) => {
    const els = [0, 1, 2].map((i) => h("input", { type: "text", inputMode: "decimal", size: 6, "aria-label": `${label} trial ${i + 1}`, value: shown[i] ?? "" }));
    els.forEach((el) => (el.dataset.initial = el.value));
    return { key, els, tr: h("tr", { "data-level": extra || "" }, h("td", {}, label, h("span", { class: "sub" }, ` (${unit})`)), els.map((el) => h("td", {}, el))) };
  };
  const sopRows = SOP_TESTS.map(([k, l, u, lv]) => trialRow(k, l, u, sess && sess.results[k] ? sess.results[k].trials : [], lv));
  const showLevel = () => sopRows.forEach((r) => (r.tr.hidden = r.tr.dataset.level !== level.value));
  level.addEventListener("change", showLevel); showLevel();
  const ex = sess ? sess.extras : null;
  const srShown = ex && ex.sit_reach ? (ex.sit_reach.trials.some((v) => v != null) ? ex.sit_reach.trials : [ex.sit_reach.final]) : [];
  const srRow = trialRow("sit_reach", "Sit and reach", "cm", srShown.map((v) => (v == null ? "" : String(v))));
  const sfTotal = h("strong"), sfNote = h("span", { class: "sub" });
  const sfRows = SKINFOLDS.map(([k, l]) => {
    const site = ex ? ex.skinfolds.find((x) => x.key === k) : null;
    const shown = site ? (site.trials.some((v) => v != null) ? site.trials : [site.final]) : [];
    const r = trialRow(k, l, "mm", shown.map((v) => (v == null ? "" : String(v))));
    r.final = h("td", { class: "num" }); r.tr.append(r.final, h("td", { class: "sub" }, site && site.note ? site.note : ""));
    return r;
  });
  const recalc = () => {
    let sum = 0, all = true, third = 0;
    for (const r of sfRows) {
      const [f, need] = skinfoldFinal(r.els.map((el) => (el.value.trim() === "" ? null : +el.value)));
      r.final.textContent = f == null ? "–" : f.toFixed(1) + (need ? " · take a 3rd" : "");
      r.final.className = need ? "num down" : "num";
      if (f == null) all = false; else sum += f;
      if (need) third++;
    }
    sfTotal.textContent = all ? sum.toFixed(1) + " mm" : "–";
    sfNote.textContent = (all ? "" : " (needs all 8 sites)") + (third ? ` · 3rd measure needed at ${third} site(s)` : "");
  };
  sfRows.forEach((r) => r.els.forEach((el) => el.addEventListener("input", recalc))); recalc();
  const trialTable = (rows, cols) => h("div", { class: "scroll" }, h("table", { class: "trials" }, h("thead", {}, h("tr", {}, cols.map((c) => h("th", {}, c)))),
    h("tbody", {}, rows.map((r) => r.tr))));
  const sopSection = canTest ? h("div", {},
    h("h2", {}, "SLC U15 physical tests (SOP)"),
    h("p", { class: "sub" }, "3 trials; the best valid trial is the result. Times in minutes as mm.ss (8.25 = 8 min 25 s). Leave a trial blank if not done: nothing is estimated."),
    h("div", { class: "grid" }, field("Testing level", level), field("Height (cm)", height), field("Body weight (kg)", weight)),
    trialTable(sopRows, ["Test", "Trial 1", "Trial 2", "Trial 3"]),
    h("h2", {}, "Sit and reach"),
    h("p", { class: "sub" }, "Hamstring and lower-back flexibility. cm with 0 at the toes (past the toes +, short of them −). Best of 3. Not ranked."),
    trialTable([srRow], ["Test", "Trial 1", "Trial 2", "Trial 3"]),
    h("h2", {}, "Skinfolds (mm, right side)"),
    h("p", { class: "sub" }, "ISAK 8 sites. Two measures per site; if they differ by more than 5% take a third. Final = mean of two, or median of three."),
    trialTable(sfRows, ["Site", "T1", "T2", "T3", "Final", ""]),
    h("p", {}, "Total of 8 skinfolds: ", sfTotal, sfNote)) : null;

  const sopBody = () => {
    const results = {};
    for (const r of [...sopRows.filter((x) => !x.tr.hidden), srRow, ...sfRows])
      if (r.els.some((el) => el.value !== el.dataset.initial)) results[r.key] = r.els.map((el) => el.value.trim() || null);
    const body = { level: level.value, test_date: date.value, results };
    if (height.value !== "") body.height_cm = +height.value;
    if (weight.value !== "") body.weight_kg = +weight.value;
    return body;
  };
  $("#main").replaceChildren(h("form", { class: "card", onsubmit: async (e) => {
    e.preventDefault(); err.textContent = "";
    try {
      if (canTest) await api(`/players/${p.id}/tests/${S.season.id}/${ph.value}`, { method: "PUT", body: sopBody() });
      const body = { test_date: date.value };
      let any = !!existing.id;
      for (const [k, el] of inputs) if (el.value !== "") { body[k] = el.type === "number" ? +el.value : el.value; any = true; } else if (existing[k] != null) body[k] = null;
      const rs = {};
      for (const [k, el] of kinputs) if (el.value !== "") { rs[k] = +el.value; any = true; } else if ((existing.role_specific || {})[k] != null) rs[k] = null;
      if (Object.keys(rs).length) body.role_specific = rs;
      if (any || !canTest) await api(`/players/${p.id}/fitness/${S.season.id}/${ph.value}`, { method: "PUT", body });
      toast("Results saved"); S.phase = ph.value; S.pid = p.id; go(S.tab === "fitness" ? "fitness" : "players");
    } catch (x) { err.textContent = x.message; }
  } }, h("h1", {}, "Fitness results – " + p.full_name), h("div", { class: "grid" }, field("Season", h("input", { value: S.season.name, disabled: true })), field("Test phase", ph), field("Test date", date)),
    sopSection,
    canTest ? null : h("div", { class: "grid" }, inputs.map(([, el, l]) => field(l, el))),
    kinputs.length ? h("details", { open: !canTest }, h("summary", {}, "Role-specific measures"),
      h("div", { class: "grid" }, kinputs.map(([, el, l]) => field(l, el)))) : null, err,
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
    AUTH_CFG && AUTH_CFG.enabled_roles && AUTH_CFG.enabled_roles.length < 5
      ? h("p", { class: "sub" }, "Only some roles can sign in at the moment (SLC_ENABLED_ROLES). Other staff can still be added for planning.") : null,
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
        h("button", { class: "small", onclick: () => (role.value !== "admin" || confirm(`Make ${r.full_name} an ADMINISTRATOR? They will have full access, including approving other people.`))
          && act("approve", { role: role.value }, `${r.full_name} approved`)() }, "Approve"),
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
    h("h3", {}, "New squad"), create, squadImport());
}

const CAPT = { captain: "Captain", vice_captain: "Vice-captain" };

function squadImport() {
  const file = h("input", { type: "file", accept: ".xlsx", "aria-label": "Squad sheet (.xlsx)" });
  const age = h("select", { "aria-label": "Age group" }, [["", "Age group: from the sheet title"], ["U15", "Under 15"], ["U17", "Under 17"], ["U19", "Under 19"]].map(([v, t]) => h("option", { value: v }, t)));
  const result = h("div");
  const send = async (confirm, extra = {}) => {
    if (!file.files[0]) { toast("Choose the squad .xlsx file first"); return null; }
    const q = new URLSearchParams({ confirm, filename: file.files[0].name, ...(age.value ? { age_group: age.value } : {}), ...extra });
    const res = await fetch(`/admin/squads/import?${q}`, { method: "POST", headers: { Authorization: "Bearer " + S.token, "Content-Type": "application/octet-stream" },
      body: await file.files[0].arrayBuffer() });
    const j = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof j.detail === "string" ? j.detail : "Upload failed");
    return j;
  };
  const problems = (title, list, cls) => list.length ? h("div", {}, h("h4", {}, `${title} (${list.length})`), h("div", { class: "scroll" }, h("table", {},
    h("thead", {}, h("tr", {}, ["Row", "Column", "Problem"].map((c) => h("th", {}, c)))),
    h("tbody", {}, list.map((e) => h("tr", {}, h("td", {}, e.row), h("td", {}, e.column || "–"), h("td", { class: cls }, e.message))))))) : null;
  const preview = (j) => {
    const name = h("input", { required: true, maxLength: 200, value: j.suggested.name || "" });
    const prov = h("input", { required: true, maxLength: 100, value: j.suggested.province || "" });
    const err = h("div", { class: "err", role: "alert" });
    const ok = !j.errors.length && j.rows.length;
    const create = h("button", { disabled: !ok, onclick: async () => {
      err.textContent = "";
      if (!name.value.trim() || !prov.value.trim()) { err.textContent = "Give the squad a name and a province."; return; }
      create.disabled = true;
      try {
        const r = await send(true, { name: name.value.trim(), province: prov.value.trim() });
        toast(`Squad "${r.squad.name}" created with ${r.rows.length} players`); S.tab = "admin"; await refreshSquads(r.squad.id);
      } catch (x) { err.textContent = x.message; create.disabled = false; }
    } }, `Create squad with ${j.rows.length} player${j.rows.length === 1 ? "" : "s"}`);
    const standby = j.rows.filter((r) => r.standby).length;
    result.replaceChildren(
      h("p", {}, h("strong", {}, `${j.rows.length} player${j.rows.length === 1 ? "" : "s"} read`), ` from sheet "${j.sheet}" (${j.age_group})` +
        (standby ? `, ${standby} on stand-by` : "") + `. ${j.errors.length} problem(s), ${j.warnings.length} warning(s). Nothing is saved yet.`),
      problems("Problems – fix these in Excel and upload again", j.errors, "down"), problems("Warnings – check these", j.warnings, ""),
      j.rows.length ? h("div", { class: "scroll" }, h("table", {},
        h("thead", {}, h("tr", {}, ["No", "Name", "Role", "", "Born", "Age", "School", "District", "Bat", "Bowl"].map((c) => h("th", {}, c)))),
        h("tbody", {}, j.rows.map((r) => h("tr", {}, h("td", {}, r.squad_no ?? "–"), h("td", {}, r.full_name), h("td", {}, ROLE[r.role]),
          h("td", {}, [r.captaincy && h("span", { class: "chip" }, CAPT[r.captaincy]), r.standby && h("span", { class: "chip" }, "Stand-by")].filter(Boolean)),
          h("td", {}, fdate(r.date_of_birth)), h("td", {}, r.age), h("td", {}, r.school_or_club || "–"), h("td", {}, r.district || "–"),
          h("td", {}, r.batting_hand || "–"), h("td", {}, r.bowl_code || "–")))))) : null,
      ok ? h("div", { class: "grid" }, field("New squad name", name), field("Province", prov)) : null, err,
      ok ? create : h("p", { class: "hint warn" }, "The squad can be created once the sheet has no problems."));
  };
  return h("div", {}, h("h3", {}, "Import squad from Excel"),
    h("p", { class: "sub" }, "Upload the squad list (Ranking, Player Name, DOB, School, District, Province, Bat, Bowl, with group headings such as " +
      "Batting group, Spin group, Pace group and Stand By). Check the preview, then create the squad with all its players."),
    h("div", { class: "row" }, file, age, h("button", { class: "small", onclick: async () => {
      try { const j = await send(false); if (j) preview(j); } catch (x) { result.replaceChildren(h("div", { class: "err" }, x.message)); }
    } }, "Check file")), result);
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

/** A player's seasonal plan (Annual plan · Load · Components · Session), built from their own test results. */
function playerPlanButton(squadId, pid, cls = "small") {
  return h("span", { class: "row", style: "display:inline-flex;gap:8px" },
    h("button", { class: cls, onclick: () => (S.season ? downloadFile(`/squads/${squadId}/seasons/${S.season.id}/player-plans/${pid}.xlsx`, "Seasonal-plan.xlsx")
      : Promise.reject(new Error("Choose a season first"))).catch((x) => toast(x.message)) }, "Download seasonal plan (Excel)"),
    playerPdfButton(squadId, pid, "annual", "Annual plan (PDF)"), playerPdfButton(squadId, pid, "weeks", "Week plans (PDF)"),
    playerPeriodizedButton(squadId, pid));
}
/** The player's own plan as a PDF: part = annual (52 weeks at a glance) | weeks (Monday to Friday sessions of every week). */
function playerPdfButton(squadId, pid, part, label) {
  return h("button", { class: "small ghost", title: part === "annual" ? "The Annual plan sheet (as in the Excel) and this player's test results"
      : "Every week's Monday to Friday sessions: exercises, times, sets and reps",
    onclick: (e) => { const b = e.target; if (!S.season) return toast("Choose a season first");
      b.disabled = true; b.textContent = "Building PDF…";
      downloadFile(`/squads/${squadId}/seasons/${S.season.id}/player-plans/${pid}.pdf?part=${part}`, `${part === "annual" ? "Annual-plan" : "Week-plans"}.pdf`)
        .catch((x) => toast(x.message)).finally(() => { b.disabled = false; b.textContent = label; }); } }, label);
}
/** The player's own periodized annual plan (NSCA · Zatsiorsky), built from their test ranks. */
function playerPeriodizedButton(squadId, pid) {
  const label = "Periodized plan (NSCA · Zatsiorsky)";
  return h("button", { class: "small ghost", title: "This player's own year → mesocycle → microcycle → session plan, with formula checks",
    onclick: (e) => { const b = e.target; if (!S.season) return toast("Choose a season first");
      b.disabled = true; b.textContent = "Building…";
      downloadFile(`/squads/${squadId}/seasons/${S.season.id}/periodized-plan/${pid}.xlsx`, "Periodized-plan.xlsx").catch((x) => toast(x.message))
        .finally(() => { b.disabled = false; b.textContent = label; }); } }, label);
}
/** Every player's Annual plan (as the Excel sheet, from their own tests) and test results, in one PDF. */
function allPlayersPdfButton(cls = "small") {
  const label = "All players' annual plans + test results (PDF)";
  return h("button", { class: cls, onclick: (e) => { const b = e.target; b.disabled = true; b.textContent = "Building every player's annual plan…";
    downloadFile(`/squads/${S.squad.id}/seasons/${S.season.id}/player-plans.pdf`, "Annual-plans-all-players.pdf").catch((x) => toast(x.message))
      .finally(() => { b.disabled = false; b.textContent = label; }); } }, label);
}
function allPlayersButton(cls = "small") {
  return h("button", { class: cls, onclick: (e) => { const b = e.target; b.disabled = true; b.textContent = "Preparing every player's plan…";
    downloadFile(`/squads/${S.squad.id}/seasons/${S.season.id}/player-plans.xlsx`, "Seasonal-plans-all-players.xlsx").catch((x) => toast(x.message))
      .finally(() => { b.disabled = false; b.textContent = "All players' plans (one Excel)"; }); } }, "All players' plans (one Excel)");
}

/** The periodized annual plan (Zatsiorsky & Kraemer + NSCA): year → mesocycles → microcycles → sessions, with formula checks.
 *  A separate plan beside the seasonal plan; neither replaces the other. */
function periodizedButton(err) {
  const label = "Periodized annual plan (NSCA · Zatsiorsky)";
  return h("button", { class: "ghost", title: "Year → mesocycles → microcycles → sessions, with a Checks sheet (every rule by formula)",
    onclick: async (e) => { const b = e.target; b.disabled = true; b.textContent = "Building the periodized plan…"; if (err) err.textContent = "";
      try { await downloadPlan("", "periodized-plan.xlsx"); } catch (x) { if (err) err.textContent = x.message; else toast(x.message); }
      finally { b.disabled = false; b.textContent = label; } } }, label);
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

const PLAN_CATS = [["", "Main plan (all areas)"], ["physical", "Physical – Strength & Conditioning"]];

async function planTab(rolesParam) {
  const main = $("#main");
  if (!S.season) return main.replaceChildren(h("h1", {}, "Seasonal plan"), h("div", { class: "card" }, "This squad has no season yet. Create one in Admin → Seasons."));
  const cat = S.planCat || "";
  const cq = cat ? "category=" + cat : "";
  const q = rolesParam ? "?roles=" + encodeURIComponent(rolesParam) + (cq ? "&" + cq : "") : (cq ? "?" + cq : "");
  const plan = await api(`/squads/${S.squad.id}/seasons/${S.season.id}/seasonal-plan${q}`);
  const rq = "?roles=" + encodeURIComponent(plan.roles.join(",")) + (cq ? "&" + cq : "");
  const catPick = h("select", { "aria-label": "Plan", onchange: (e) => { S.planCat = e.target.value; planTab(rolesParam); } },
    PLAN_CATS.map(([v, t]) => h("option", { value: v, selected: v === cat }, t)));
  const picked = new Set(plan.roles);
  const roleBoxes = Object.entries(ROLE).map(([k, v]) => ({ k, v, el: h("input", { type: "checkbox", checked: picked.has(k) }) }));

  const fArea = h("select", { "aria-label": "Filter by development area" }, h("option", { value: "" }, "All areas"), (plan.category ? plan.category.areas : ["technical", "tactical", "physical", "mental", "nutrition", "recovery"]).map((a) => h("option", { value: a }, cap(a))));
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
    h("div", { class: "bar" }, h("h1", {}, plan.category ? "Seasonal plan – " + plan.category.label : "Seasonal plan"), h("div", { class: "row" }, catPick, seasonPicker(() => planTab(rolesParam)))),
    h("p", { class: "sub" }, `${plan.squad} · season ${plan.season.name} · ${fdate(plan.season.start_date)} – ${fdate(plan.season.end_date)}`),
    h("div", { class: "row" },
      can("coach", "admin") ? h("button", { onclick: async () => { err.textContent = ""; try { const r = await api(`/squads/${S.squad.id}/seasons/${S.season.id}/seasonal-plan/save${rq}`, { method: "POST" }); toast(`Plan saved (${r.new} new, ${r.updated} updated)`); planTab(rolesParam); } catch (x) { err.textContent = x.message; } } }, (plan.saved ? "Re-save " : "Save ") + (plan.category ? "S&C rows" : "plan")) : null,
      h("button", { onclick: async () => { err.textContent = ""; try { await downloadPlan(rq, "seasonal-workbook.xlsx"); } catch (x) { err.textContent = x.message; } } }, "Download seasonal plan (Annual plan · Load · Components · Session)"),
      allPlayersButton("ghost"), allPlayersPdfButton("ghost"),
      periodizedButton(err)),
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
    squadWeekCard(),
    can("coach", "sc_coach", "admin") ? earlierCard() : null,
    h("div", { class: "card" }, h("h2", {}, "Squad overview"), h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {},
      ["Player", "Role", "Availability", "7-day load", "Load ratio", "Overs (7 d)", "Bowling days", "Status"].map((c) => h("th", {}, c)))),
      h("tbody", {}, rows.map((r) => h("tr", { class: "click", onclick: () => { S.pid = r.player_id; S.from = S.tab; go("players"); } },
        h("td", {}, r.name), h("td", {}, ROLE[r.role]), h("td", {}, h("span", { class: "chip " + r.availability }, r.availability)),
        h("td", {}, r.acute_load_7d), h("td", {}, r.acwr == null ? "needs 3 weeks" : r.acwr),
        h("td", {}, BOWLS.includes(r.role) ? r.overs_7d : "–"), h("td", {}, BOWLS.includes(r.role) ? r.bowling_days_7d : "–"), h("td", {}, sevChip(r.worst_severity))))))),
      h("p", { class: "sub" }, "Load = RPE × minutes. Load ratio = 7-day ÷ 4-week average (needs 3 weeks of logs).")));
}

// ───────────── earlier workload (weeks before the app was used) ─────────────
const mondayOf = (d) => { const x = new Date(d + "T00:00:00"); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x.toLocaleDateString("en-CA"); };
const addDays = (iso, n) => { const x = new Date(iso + "T00:00:00"); x.setDate(x.getDate() + n); return x.toLocaleDateString("en-CA"); };

function earlierCard() {
  const host = h("div", { class: "card" });
  const lastWeek = addDays(mondayOf(todayStr()), -7);
  const weeks = Array.from({ length: 8 }, (_, i) => addDays(lastWeek, -7 * i));
  const pick = h("select", { "aria-label": "Week" }, weeks.map((w) => h("option", { value: w }, `Week of ${fdate(w)} – ${fdate(addDays(w, 6))}`)));
  const body = h("div");
  const msg = h("div", { class: "err", role: "alert" });
  let current = null;
  const num = (v, min, max, step = "1", ph = "") => h("input", { type: "number", min, max, step, inputMode: "decimal", value: v ?? "", placeholder: ph, class: "tiny" });
  const load = async () => {
    msg.textContent = "";
    current = await api(`/squads/${S.squad.id}/workload/earlier?week_start=${pick.value}`);
    current.inputs = current.players.map((r) => ({ r, s: num(r.entry?.sessions, 0, 7), m: num(r.entry?.minutes, 10, 300, "5"), e: num(r.entry?.rpe, 1, 10),
      o: r.bowls ? num(r.entry?.overs, 0, 100, "0.1") : null, b: r.bowls ? num(r.entry?.bowling_days, 0, 7) : null }));
    body.replaceChildren(h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {},
      ["No", "Player", "Sessions", "Avg minutes", "Avg RPE (1-10)", "Overs", "Bowling days", "Week load", ""].map((x) => h("th", {}, x)))),
      h("tbody", {}, current.inputs.map(({ r, s, m, e, o, b }) => {
        const out = h("td", {}, r.entry ? r.entry.load : "–");
        const upd = () => { out.textContent = s.value && m.value && e.value ? Number(s.value) * Number(m.value) * Number(e.value) : "–"; };
        [s, m, e].forEach((x) => (x.oninput = upd));
        const locked = r.logged_sessions > 0;
        if (locked) [s, m, e, o, b].forEach((x) => x && (x.disabled = true));
        return h("tr", {}, h("td", {}, r.squad_no ?? "–"), h("td", {}, r.name), h("td", {}, s), h("td", {}, m), h("td", {}, e), h("td", {}, o || "–"), h("td", {}, b || "–"), out,
          h("td", {}, locked ? h("span", { class: "chip", title: "Sessions are already logged in this week" }, "Logged") : r.entry ? h("span", { class: "chip ok" }, "Entered") : null));
      })))));
  };
  const copyPrev = async () => {
    try {
      const prev = await api(`/squads/${S.squad.id}/workload/earlier?week_start=${addDays(pick.value, -7)}`);
      const by = Object.fromEntries(prev.players.map((r) => [r.player_id, r.entry]));
      current.inputs.forEach(({ r, s, m, e, o, b }) => { const x = by[r.player_id]; if (!x || s.disabled) return;
        s.value = x.sessions; m.value = x.minutes; e.value = x.rpe; if (o) o.value = x.overs ?? ""; if (b) b.value = x.bowling_days ?? ""; s.oninput(); });
    } catch (x) { msg.textContent = x.message; }
  };
  const save = async () => {
    msg.textContent = "";
    const rows = current.inputs.filter(({ s }) => !s.disabled && s.value !== "").map(({ r, s, m, e, o, b }) => ({ player_id: r.player_id, sessions: Number(s.value),
      minutes: m.value ? Number(m.value) : null, rpe: e.value ? Number(e.value) : null, overs: o && o.value ? Number(o.value) : null, bowling_days: b && b.value ? Number(b.value) : null }));
    if (!rows.length) return toast("Fill at least one player's sessions");
    try { const x = await api(`/squads/${S.squad.id}/workload/earlier`, { method: "PUT", body: { week_start: pick.value, rows } });
      toast(`Week saved: ${x.saved} player(s)` + (x.cleared ? `, ${x.cleared} cleared` : "")); await load(); } catch (e) { msg.textContent = e.message; }
  };
  pick.onchange = () => load().catch((x) => (msg.textContent = x.message));
  host.append(h("h2", {}, "Earlier workload"),
    h("p", { class: "sub" }, "Training from before the app was used, one line per player and week (sessions, average minutes and RPE; overs and bowling days for bowlers). " +
      "It lets the load ratio and the fast-bowler checks work from the start. Weeks with sessions already logged are locked. Sessions 0 clears a week."),
    h("div", { class: "row" }, pick, h("button", { class: "small ghost", onclick: copyPrev }, "Copy previous week"), h("button", { class: "small", onclick: save }, "Save week")),
    msg, body);
  load().catch((x) => (msg.textContent = x.message));
  return host;
}

// ───────────── the week (McGawley workshop): Mon-Sun loads, monotony, strain, change, ACWR, TRIMP, external load ─────────────
const fmtN = (v, d = 0) => (v == null ? "–" : Number(v).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }));
async function playerWeek(p, host, monday, coach) {
  const w = await api(`/players/${p.id}/workload/week?week_start=${monday}`);
  const pick = h("input", { type: "date", value: monday, onchange: (e) => playerWeek(p, host, mondayOf(e.target.value), coach) });
  const rows = w.days.flatMap((d) => (d.sessions.length ? d.sessions : [null]).map((x, i) => h("tr", {},
    h("td", {}, i === 0 ? d.day : ""), h("td", {}, i === 0 ? fdate(d.date) : ""), h("td", {}, x ? (x.attended === false ? "Absent" : cap(x.type.replace("_", " "))) : "Rest"),
    h("td", {}, x ? x.minutes ?? "–" : 0), h("td", {}, x ? x.rpe ?? x.intensity ?? "–" : 0), h("td", {}, h("strong", {}, x ? fmtN(x.load) : 0)),
    h("td", {}, x ? fmtN(x.edwards) : ""), h("td", {}, x ? fmtN(x.banister) : ""), h("td", {}, x ? fmtN(x.hit, 1) : ""), h("td", {}, x ? fmtN(x.sprint_m) : ""),
    h("td", {}, x ? fmtN(x.volume_load_kg) : ""), h("td", {}, x ? fmtN(x.foot_contacts) : ""))));
  const hrBox = coach && can("coach", "sc_coach", "admin") ? (() => {
    const mx = h("input", { type: "number", min: 150, max: 230, value: w.player.hr_max ?? "", class: "tiny", "aria-label": "Max heart rate" });
    const rs = h("input", { type: "number", min: 30, max: 110, value: w.player.hr_rest ?? "", class: "tiny", "aria-label": "Resting heart rate" });
    return h("div", { class: "row" }, h("span", { class: "sub" }, "Heart rate for TRIMP:"), "max", mx, "resting", rs,
      h("button", { class: "small ghost", onclick: async () => { try { await api(`/players/${p.id}/heart-rate`, { method: "PUT",
        body: { hr_max: mx.value ? Number(mx.value) : null, hr_rest: rs.value ? Number(rs.value) : null } }); toast("Heart rate saved"); playerWeek(p, host, monday, coach); }
        catch (x) { toast(x.message); } } }, "Save"),
      w.player.hr_max_estimated ? h("span", { class: "sub" }, `(using ${w.player.hr_max_used} bpm, estimated 208 − 0.7 × age)`) : null);
  })() : null;
  host.replaceChildren(h("div", { class: "bar" }, h("h3", {}, `This week: ${fdate(w.monday)} – ${fdate(w.sunday)}`), pick),
    h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Day", "Date", "Session", "Minutes", "RPE", "Load (AU)", "Edwards TRIMP",
      "Banister TRIMP", "Min ≥90% HRmax", "Sprint m", "Volume load kg", "Foot contacts"].map((c) => h("th", {}, c)))), h("tbody", {}, rows))),
    h("div", { class: "kpis compact" },
      Charts.stat({ label: "Weekly load", value: fmtN(w.total), sub: `mean ${fmtN(w.mean_daily)} · SD ${fmtN(w.sd_daily)} AU` }),
      Charts.stat({ label: "Monotony", value: fmtN(w.monotony, 2), sub: `strain ${fmtN(w.strain)} AU`, tone: w.monotony > 2 ? "warning" : null }),
      Charts.stat({ label: "Vs last week", value: w.change_pct == null ? "–" : (w.change_pct > 0 ? "+" : "") + fmtN(w.change_pct, 0) + "%",
        sub: `last week ${fmtN(w.previous_week)} AU · keep under ~10%`, tone: w.change_pct > 10 ? "warning" : null }),
      Charts.stat({ label: "Acute:chronic", value: fmtN(w.acwr, 2), sub: w.acwr_band, tone: w.acwr > 1.5 ? "critical" : null }),
      Charts.stat({ label: "Weekly load %", value: w.load_pct == null ? "–" : w.load_pct + "%", sub: `of the heaviest week (${fmtN(w.heaviest_week)} AU)` })),
    w.flags.length ? h("div", { class: "card inner" }, h("strong", {}, "Flags (a conversation, not a diagnosis)"), h("ul", {}, w.flags.map((f) => h("li", {}, f)))) : null,
    hrBox,
    h("p", { class: "sub" }, "Load = RPE (0-10) × minutes. Monotony = mean ÷ SD of the daily load (rest days 0); strain = weekly load × monotony. " +
      "Acute:chronic = this week ÷ the 4-week average (a flag only)." + (w.sdec != null ? ` Repeated sprints: performance decrement ${fmtN(w.sdec, 1)}%.` : "")));
}

function squadWeekCard() {
  const host = h("div", { class: "card" });
  const pick = h("input", { type: "date", value: mondayOf(todayStr()) });
  const body = h("div");
  const load = async () => {
    const m = mondayOf(pick.value);
    const r = await api(`/squads/${S.squad.id}/workload/week?week_start=${m}`);
    body.replaceChildren(h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Player", "Sessions", "Weekly load", "Mean", "SD", "Monotony",
      "Strain", "Vs last wk", "ACWR", "Load % (measured)", "Load % (planned)", "Edwards", "Banister", "Min ≥90%", "Sprint m", "Vol. load kg", "Contacts", "Sdec %", "Flags"].map((c) => h("th", {}, c)))),
      h("tbody", {}, r.players.map((x) => h("tr", { class: "click", onclick: () => { S.pid = x.player_id; S.from = S.tab; go("players"); } },
        h("td", {}, x.name), h("td", {}, x.sessions), h("td", {}, h("strong", {}, fmtN(x.total))), h("td", {}, fmtN(x.mean_daily)), h("td", {}, fmtN(x.sd_daily)),
        h("td", { class: x.monotony > 2 ? "down" : "" }, fmtN(x.monotony, 2)), h("td", {}, fmtN(x.strain)),
        h("td", { class: x.change_pct > 10 ? "down" : "" }, x.change_pct == null ? "–" : (x.change_pct > 0 ? "+" : "") + fmtN(x.change_pct) + "%"),
        h("td", { class: x.acwr > 1.5 ? "down" : "", title: x.acwr_band }, fmtN(x.acwr, 2)), h("td", {}, x.load_pct == null ? "–" : x.load_pct + "%"),
        h("td", {}, r.planned_pct == null ? "–" : r.planned_pct + "%"), h("td", {}, fmtN(x.edwards_trimp)), h("td", {}, fmtN(x.banister_trimp)),
        h("td", {}, fmtN(x.hit_minutes, 1)), h("td", {}, fmtN(x.sprint_m)), h("td", {}, fmtN(x.volume_load_kg)), h("td", {}, fmtN(x.foot_contacts)),
        h("td", {}, fmtN(x.sdec, 1)), h("td", { class: "sub" }, x.flags.length ? "⚑ " + x.flags.length : "–")))))));
  };
  pick.onchange = () => load().catch((x) => body.replaceChildren(h("p", { class: "err" }, x.message)));
  host.append(h("div", { class: "bar" }, h("h2", {}, "Weekly workload report"), h("div", { class: "row" }, pick,
      h("button", { class: "small", onclick: () => downloadFile(`/squads/${S.squad.id}/workload/report.xlsx?week_start=${mondayOf(pick.value)}`, "Workload-report.xlsx")
        .catch((x) => toast(x.message)) }, "Download report (Excel)"))),
    h("p", { class: "sub" }, "Monday to Sunday. Load = RPE × minutes; monotony, strain, change on last week (flag above 10%), acute:chronic (flag above 1.5), " +
      "weekly load % measured against the annual plan's planned %, TRIMP and external load. The Excel has each player's week, the 8-week trend, the test change, the formulas and the process."),
    body);
  load().catch((x) => body.replaceChildren(h("p", { class: "err" }, x.message)));
  return host;
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
  const weekHost = h("div");
  host.append(weekHost);
  playerWeek(p, weekHost, mondayOf(todayStr()), coach).catch((x) => weekHost.replaceChildren(h("p", { class: "sub" }, x.message)));
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
    overs: num(0, 50, "0.1"), spells: h("input", { placeholder: "e.g. 4, 3", inputMode: "decimal" }), faced: num(0, 600), keep: num(0, 480), throws: num(0, 300),
    hr: num(40, 230), zones: [0, 1, 2, 3, 4].map(() => num(0, 480, "0.5")), hit: num(0, 480, "0.5"), sprint: num(0, 20000), vload: num(0, 200000, "0.5"),
    contacts: num(0, 3000), stimes: h("input", { placeholder: "e.g. 7.1, 7.3, 7.4", inputMode: "decimal" }) };
  const err = h("div", { class: "err", role: "alert" }), result = h("div", {});
  const body = () => {
    const b = { log_date: f.date.value, session_type: f.type.value, attended: f.att.checked };
    if (!b.attended) return b;
    const set = (k, el, conv = Number) => { if (el.value !== "") b[k] = conv(el.value); };
    set("duration_min", f.dur); set("rpe", f.rpe); set("session_intensity", f.inten); set("overs_bowled", f.overs);
    set("balls_faced", f.faced); set("keeping_minutes", f.keep); set("throws", f.throws);
    if (f.spells.value.trim()) b.spells = f.spells.value.split(",").map((x) => ({ overs: Number(x.trim()) }));
    set("hr_avg", f.hr); set("hit_minutes", f.hit); set("sprint_m", f.sprint); set("volume_load_kg", f.vload); set("foot_contacts", f.contacts);
    if (f.zones.some((z) => z.value !== "")) b.zone_minutes = f.zones.map((z) => Number(z.value || 0));
    if (f.stimes.value.trim()) b.sprint_times = f.stimes.value.split(",").map((x) => Number(x.trim())).filter((x) => x > 0);
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
    h("details", {}, h("summary", {}, "Heart rate and external load (optional)"),
      h("p", { class: "sub" }, "Internal load: average heart rate and minutes in each heart-rate zone (Edwards / Banister TRIMP). External load: " +
        "minutes at 90% HRmax or more, sprint metres, volume load (sets × reps × %1RM × 1RM, kg), foot contacts. Repeated-sprint times give the performance decrement."),
      h("div", { class: "grid" }, field("Average heart rate (bpm)", f.hr), field("Minutes at ≥ 90% HRmax", f.hit), field("Sprint metres", f.sprint)),
      h("div", { class: "grid" }, ...["50-60%", "60-70%", "70-80%", "80-90%", "90-100%"].map((z, i) => field(`Minutes at ${z} HRmax`, f.zones[i]))),
      h("div", { class: "grid" }, field("Volume load (kg)", f.vload), field("Foot contacts", f.contacts), field("Repeated-sprint times (s), comma separated", f.stimes))),
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
  const by = cat.areas.flatMap((a) => a.tests).map((t) => t.goal && t.goal.by).find(Boolean);
  return h("div", {}, h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Area", "Test", "Trial 1", "Trial 2", "Trial 3", "Best", "For age", "Goal" + (by ? ` (${by})` : ""), "Why"].map((c) => h("th", {}, c)))),
    h("tbody", {}, cat.areas.flatMap((a) => a.tests.map((t, i) => h("tr", {},
      h("td", {}, i === 0 ? a.label : ""), h("td", {}, `${t.label} (${t.unit})`), ...t.trials_display.map((d) => h("td", {}, d ?? "–")), h("td", {}, h("strong", {}, t.display ?? "–")),
      h("td", {}, t.age ? h("span", { class: "chip age-" + t.age.band, title: `${t.age.age_group}: developing ${t.age.developing} · expected ${t.age.expected} · strong ${t.age.strong} ${t.age.unit}` +
        (t.age.quality === "estimate" ? " (estimate)" : "") }, t.age.label) : "–"),
      h("td", {}, t.goal ? h("span", { class: "chip " + GOAL_CHIP[t.goal.kind] }, `${t.goal.display} ${t.goal.unit}`) : "–"),
      h("td", { class: "sub" }, t.goal ? t.goal.why : "No result yet: test first."))))))),
    h("p", { class: "sub" }, "Goal = the result to reach at the next test. Focus tests aim for the middle of the group (at least the age group's expected value); " +
      "never more than 8% better in one window, so the goal stays reachable."));
}
const GOAL_CHIP = { focus: "warn", improve: "info", keep: "ok" };

// ───────────── SLC U15 points benchmark (app/benchmark.py) ─────────────
const BENCH_CLS = { green: "bm-green", light_green: "bm-light", amber: "bm-amber", red: "bm-red" };
function benchChip(b) {
  if (!b) return "–";
  return h("span", { class: "chip " + BENCH_CLS[b.band], title: `${b.band_label}: ${b.total} of ${b.max} points (${b.percent}%)` }, `${b.total} / ${b.max} · ${b.band_label}`);
}

function benchmarkCard(b) {
  if (!b) return null;
  const byArea = (a) => b.tests.filter((t) => t.area === a);
  return h("div", { class: "card inner" }, h("h3", {}, "SLC U15 benchmark (points)"),
    h("p", { class: "sub" }, "A fixed standard, the same for every U15 player: the SLC men's / U19 points system adapted to the U15 tests. " +
      "The ranks above compare with this squad; these points do not."),
    h("div", { class: "row" }, benchChip(b), b.note ? h("span", { class: "sub" }, b.note) : null),
    h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Quality", "Test", "Best", "Test points", "Quality points", "Next point at"].map((c) => h("th", {}, c)))),
      h("tbody", {}, b.areas.flatMap((a) => byArea(a.area).map((t, i) => h("tr", {},
        h("td", {}, i === 0 ? a.label : ""), h("td", {}, t.label), h("td", {}, t.display ?? "–"),
        h("td", {}, t.points == null ? "–" : `${t.points} / ${t.max}`),
        h("td", {}, i === 0 ? h("strong", {}, a.points == null ? "–" : `${a.points} / ${a.max}`) : ""),
        h("td", {}, t.points == null ? "–" : t.next ? `${t.next.display} ${t.next.unit} → ${t.next.points}` : "Maximum"))))))),
    h("p", { class: "sub" }, "Strength = the average of push-ups and inverted row. Skinfolds are not used for U15. Bands: green from 31, light green from 26, amber from 20 of 34."));
}

function benchmarkRefCard(t) {
  const lim = Math.max(...t.tests.map((x) => x.max));
  return h("details", { class: "card" }, h("summary", {}, `SLC U15 benchmark · points per test (max ${t.max})`),
    h("p", { class: "sub" }, `From the SLC men's / U19 points system: shared tests (2 km, 20 m, 5-10-5) use the U19 cut-offs × ${t.age_factor}; ` +
      "CMJ → broad jump, IMTP → push-ups and inverted row, skinfolds → plank. A proposal: replace with SLC's own U15 data."),
    h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Test", ...Array.from({ length: lim }, (_, i) => `${lim - i} pts`)].map((c) => h("th", {}, c)))),
      h("tbody", {}, t.tests.map((x) => h("tr", {}, h("td", {}, `${x.label} (${x.unit}, ${x.better} is better)`),
        ...Array.from({ length: lim }, (_, i) => { const c = x.cuts.find((k) => k.points === lim - i);
          return h("td", {}, c ? (x.better === "lower" ? "≤ " : "≥ ") + c.value : ""); })))))),
    h("p", { class: "sub" }, t.bands.map((b) => `${b.label} from ${b.from}`).join(" · ") + ` of ${t.max} points.`));
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

// ───────────── separate plans per category (Physical = Strength & Conditioning) ─────────────
const CAT_STATUS = { priority: "Priority", strength: "Strength", solid: "Solid", not_rated: "Not rated yet" };
const catTable = (cols, rows) => h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, cols.map((c) => h("th", {}, c)))),
  h("tbody", {}, rows.map((r) => h("tr", {}, r.map((v) => h("td", {}, v ?? "–")))))));

async function categoryPanel(p, host, window) {
  host.replaceChildren(h("div", { class: "sub loading" }, "Building the category plans…"));
  const [d, main] = await Promise.all([api(`/players/${p.id}/category-plans?window=${window}`), api(`/players/${p.id}/individual-plan?window=${window}`)]);
  const body = h("div");
  const tabs = h("div", { class: "row cat-tabs", role: "tablist", "aria-label": "Plan category" });
  const show = (key) => {
    tabs.querySelectorAll("button").forEach((b) => { b.classList.toggle("on", b.dataset.key === key); b.setAttribute("aria-selected", b.dataset.key === key); });
    const c = d.categories.find((x) => x.key === key);
    body.replaceChildren(...(c.key === "physical" ? scView(c, p, window, main) : skillCatView(c)));
  };
  d.categories.forEach((c) => tabs.append(h("button", { class: "small ghost" + (c.relevant ? "" : " off"), role: "tab", "data-key": c.key,
    title: c.relevant ? c.title : `${c.title} · for ${c.for.toLowerCase()}`, onclick: () => show(c.key) },
    c.group + (c.priorities ? ` (${c.priorities})` : ""))));
  host.replaceChildren(planBack(host), h("div", { class: "card inner" }, h("div", { class: "bar" }, h("h2", {}, "Plans by category"), h("span", { class: "chip" }, d.season ? d.season.name : "")),
    h("p", { class: "sub" }, d.note + " Greyed categories are not part of this player's role."), tabs, body), planBack(host));
  show("physical");
}

// The individual plan limited to its physical part: same layout as "Show individual plan".
function physicalOnly(plan) {
  const phys = (s) => !/ - /.test(s.label) || s.label.startsWith("Physical - ");          // cricket-skill entries are "Group - skill"
  return { ...plan, strengths: plan.strengths.filter(phys), priorities: plan.priorities.filter(phys),
    goals: plan.goals.filter((g) => ["test", "maintain", "rating"].includes(g.kind)), habits: [],
    phases: plan.phases.map((ph) => ({ ...ph, skills: [], role_skills: [] })) };
}

function scView(c, p, window, main) {
  const out = [h("div", { class: "bar" }, h("h3", {}, "Physical – Strength & Conditioning plan"),
    h("div", { class: "row" }, playerPlanButton(p.squad_id, p.id),
      S.season ? h("button", { class: "small ghost", onclick: () => { S.pid = null; openAthletePlan(p.id); } }, "16-step seasonal plan") : null)),
    h("p", { class: "sub" }, "The seasonal S&C plan in the same layout as the individual plan (its physical part), followed by the focus sessions and the week-by-week plan."),
    ...planView(physicalOnly(main)),
    h("h3", {}, "S&C sessions"),
    h("p", { class: "sub" }, "PDP – Physical: " + c.pdp.map((x) => `${x.skill} ${x.rating ?? "not rated"}`).join(" · "))];
  for (const ph of c.phases) {
    out.push(h("h3", {}, `${ph.label} · ${ph.sessions_per_week} focus session${ph.sessions_per_week === 1 ? "" : "s"} a week`),
      h("div", { class: "scroll" }, h("table", { class: "week" }, h("tbody", {}, h("tr", {}, ph.typical_week.map((x) => h("td", {}, h("strong", {}, x.day), h("br"), x.items.join(", "))))))));
    if (!ph.sessions.length) out.push(h("p", { class: "sub" }, "No focus sessions in this phase."));
    for (const s of ph.sessions) {
      const rows = [];
      s.parts.forEach((pt) => pt.items.forEach((it, i) => rows.push([i === 0 ? `${pt.part}${pt.minutes ? ` (${pt.minutes} min)` : ""}` : "", it.name, it.area_label, it.set, it.rep || it.time, it.rest, it.why])));
      out.push(h("div", { class: "card inner" }, h("div", { class: "bar" }, h("h4", {}, `${s.name}${s.day ? " · " + s.day : ""}`), h("span", { class: "chip" }, `about ${s.minutes} min · ${s.when}`)),
        s.note ? h("p", { class: "hint warn" }, s.note) : null,
        catTable(["Part", "Exercise", "Area", "Sets", "Reps / time", "Rest", "Why"], rows)));
    }
  }
  out.push(h("h3", {}, "Week by week"), catTable(["Week", "Starts", "Phase", "Sessions", "Focus load", "Week load", "Dose this week"],
    c.weeks.map((w) => [w.week, fdate(String(w.start).slice(0, 10)), w.phase_label, w.sessions.join(", ") || "–", w.focus_load, w.planned_load, w.dose_step])));
  out.push(h("h4", {}, "Rules"), h("ul", {}, c.rules.map((r) => h("li", {}, r))));
  return out;
}

function skillCatView(c) {
  const out = [h("h3", {}, `${c.group} – ${c.title}`), h("p", { class: "sub" }, (c.relevant ? "" : `Not part of this player's role (for ${c.for.toLowerCase()}). `) + c.notes.join(" "))];
  out.push(catTable(["Skill", "Coach rating (1-5)", "Status"], c.skills.map((s) => [s.skill, s.rating, CAT_STATUS[s.status] || s.status])));
  if (c.goals.length) out.push(h("h4", {}, "Goals"), h("ul", {}, c.goals.map((g) => h("li", {}, g.label))));
  for (const ph of c.phases) {
    out.push(h("h4", {}, ph.label));
    if (ph.general.length) out.push(h("ul", {}, ph.general.map((t) => h("li", {}, t))));
    out.push(catTable(c.key === "nutrition" ? ["Item", "Rating", "What to do"] : ["Skill", "Rating", "Drills"],
      ph.items.map((it) => [it.skill, it.rating, c.key === "nutrition" ? it.action
        : (it.drills.length ? it.drills.map((x) => `${x.name} – ${x.purpose}`).join(" · ") : it.note)])));
  }
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
      playerPlanButton(p.squad_id, p.id, "small ghost")));
  }
  function render() {
    const vlist = st.versions && st.versions.length ? h("details", { open: true }, h("summary", {}, "Saved versions"), h("ul", { class: "reviews" },
      st.versions.map((v) => h("li", {}, h("strong", {}, `Version ${v.version}`), ` · ${new Date(v.saved_at).toLocaleString()} · ${v.saved_by || "–"} · from ${v.based_on}`,
        v.edits ? ` · ${v.edits} edit(s)` : "", v.note ? h("div", { class: "sub" }, v.note) : null)))) : null;
    host.replaceChildren(planBack(host), h("h3", {}, "Individual seasonal plan"), bar(), msg, vlist,
      st.editing ? h("p", { class: "hint" }, "Edit mode: changes preview instantly and are kept only when you save a version.") : null,
      ...planView(st.plan, { editing: st.editing, edit: preview, onLog: canEdit && !st.editing ? () => logForm(p, st.plan, () => load(false)) : null }),
      planBack(host));
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
    host.append(h("div", { class: "sub" }, "No results for this window yet. Import them in the Tests tab, or enter them here."),
      can("sc_coach", "admin") ? h("button", { class: "small", onclick: () => fitnessForm(p, w) }, "Enter test results") : null);
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
      benchmarkCard(cat.benchmark),
      bodyExtrasCard(sess.extras),
      can("sc_coach", "admin") ? h("button", { class: "small ghost", onclick: () => fitnessForm(p, w) }, "Enter / edit test results") : null,
      cat.focus_areas.length ? h("p", {}, h("strong", {}, "Focus areas (below the middle): "), cat.focus_areas.map((f) => f.label).join(", ")) : (cat.band ? h("p", {}, "No area is below the middle.") : null),
      h("div", { class: "row" },
        h("button", { class: "small", onclick: () => planPanel(p, planHost, w) }, "Show individual plan"),
        h("button", { class: "small ghost", onclick: () => categoryPanel(p, planHost, w).catch((x) => planHost.replaceChildren(h("div", { class: "err" }, x.message))) }, "Plans by category")),
      progHost, planHost, h("p", { class: "sub" }, "Confidential: squad coaches, S&C and admin only."));
    if (t.sessions.length >= 2) api(`/players/${p.id}/test-progress`).then((pr) => progHost.replaceChildren(progressView(pr))).catch(() => {});
  }
}

// ───────────── Physical (S&C) page: dashboard, groups, re-test and progress, growth ─────────────
const MATURITY = { unknown: "Not known", pre_phv: "Before the growth spurt", circa_phv: "In the growth spurt", post_phv: "After the growth spurt" };
const rankCell = (v) => v == null ? h("td", { class: "heat na" }, "–")
  : h("td", { class: "heat " + (v < 50 ? "lo" : v >= 70 ? "hi" : "mid"), title: v < 50 ? "Priority" : v >= 70 ? "Strength" : "Solid" }, Charts.num(v, 0));
const openP = (id) => () => { S.pid = id; S.from = "physical"; go("players"); };

async function physicalTab() {
  const main = $("#main");
  if (!S.season) return main.replaceChildren(h("h1", {}, "Physical"), h("div", { class: "card" }, "This squad has no season yet. Create one in Admin → Seasons."));
  if (S.athletePid) return athletePlanView(S.athletePid);
  const sec = S.physSec || "today";
  const d = await api(`/squads/${S.squad.id}/seasons/${S.season.id}/physical${S.physWin ? "?window=" + S.physWin : ""}`);
  const tabs = h("div", { class: "row cat-tabs", role: "tablist" }, [["today", "Today"], ["season", "Season plan"], ["dashboard", "Dashboard"], ["groups", "S&C groups"], ["targets", "Targets"], ["progress", "Re-test & progress"], ["growth", "Growth & body"]]
    .map(([k, t]) => h("button", { class: "small ghost" + (k === sec ? " on" : ""), role: "tab", "aria-selected": k === sec, onclick: () => { S.physSec = k; physicalTab(); } }, t)));
  const winPick = d.windows_with_results.length > 1 ? h("select", { "aria-label": "Test window", onchange: (e) => { S.physWin = e.target.value; physicalTab(); } },
    d.windows_with_results.map((w) => h("option", { value: w, selected: w === d.window }, WINDOWS.find((x) => x[0] === w)[1]))) : null;
  const body = { today: physToday, season: physSeason, dashboard: physDashboard, groups: physGroups, targets: physTargets, progress: physProgress, growth: physGrowth }[sec](d);
  const report = h("button", { class: "small ghost", onclick: () => downloadFile(`/squads/${S.squad.id}/seasons/${S.season.id}/physical-report.xlsx?window=${d.window}`, "physical-report.xlsx").catch((x) => toast(x.message)) }, "Download report (Excel)");
  main.replaceChildren(h("div", { class: "bar" }, h("h1", {}, "Physical – Strength & Conditioning"), h("div", { class: "row" }, report, winPick, seasonPicker(() => physicalTab()))),
    h("p", { class: "sub" }, `${S.squad.name} · ${d.season.name} · test window: ${d.window_label}` + (d.phase_label ? ` · current phase: ${d.phase_label}` : "")),
    tabs, ...[].concat(body), h("details", { class: "card" }, h("summary", {}, "Notes"), d.notes.map((n) => h("p", { class: "sub" }, n))));
}

const canCoach = () => can("coach", "sc_coach", "admin");

function physToday(d) {
  const t = d.today;
  const order = ["full", "upper", "reduced", "light", "recovery", "none"];
  const tiles = h("div", { class: "row tiles" }, order.filter((k) => t.counts[k]).map((k) =>
    h("div", { class: "card tile" }, h("div", { class: "sub" }, t.labels[k]), h("div", { class: "big act " + k }, String(t.counts[k])))));
  return [h("p", { class: "sub" }, `S&C decision for ${fdate(String(t.date).slice(0, 10))}` + (t.match_today ? " · match today" : t.match_tomorrow ? " · match tomorrow" : "") +
      ". From availability, open workload alerts, the latest wellness check, matches and recent bowling. The strictest rule decides."),
    tiles,
    t.no_wellness.length ? h("p", { class: "hint warn" }, `No wellness check today or yesterday for ${t.no_wellness.length} player(s). Log wellness (player page → Wellness) so soreness, fatigue, sleep and pain count.`) : null,
    h("div", { class: "card" }, h("h2", {}, "Players"), h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Player", "Today", "Why", "Notes", "Wellness"].map((c) => h("th", {}, c)))),
      h("tbody", {}, t.players.map((p) => h("tr", { class: "click", onclick: openP(p.player_id) }, h("td", {}, p.name), h("td", { class: "act " + p.action }, p.label),
        h("td", { class: "wrap" }, p.reasons.join(" ")), h("td", { class: "wrap sub" }, p.notes.join(" ") || "–"),
        h("td", {}, p.wellness ? `sore ${p.wellness.soreness ?? "–"} · fatigue ${p.wellness.fatigue ?? "–"}` : "–")))))))];
}

function groupPick(d, g, p) {
  const sel = h("select", { "aria-label": "Group for " + p.name, onchange: async (e) => {
    try {
      await api(`/squads/${S.squad.id}/seasons/${S.season.id}/sc-groups/${p.player_id}`, { method: "PUT", body: { area: e.target.value || null } });
      toast(e.target.value ? `${p.name} moved` : `${p.name} back to the automatic group`); physicalTab();
    } catch (x) { toast(x.message); }
  } }, h("option", { value: "" }, p.moved ? "Automatic group" : g.label + " (automatic)"),
    d.group_options.map((o) => h("option", { value: o.key, selected: p.moved && o.key === g.key }, o.label + " group")));
  return h("span", {}, sel, p.moved ? h("span", { class: "chip" }, "moved") : null);
}

function scLogForm(host, g, s) {
  if (host.childNodes.length) return host.replaceChildren();
  const date = h("input", { type: "date", value: todayStr(), max: todayStr() });
  const mins = h("input", { type: "number", min: 10, max: 180, value: s ? s.minutes : 45, class: "tiny" });
  const rpe = h("input", { type: "number", min: 1, max: 10, value: 6, class: "tiny" });
  const rows = g.players.map((p) => ({ p, here: h("input", { type: "checkbox", checked: true }), rpe: h("input", { type: "number", min: 1, max: 10, class: "tiny", placeholder: "same" }) }));
  const err = h("div", { class: "err", role: "alert" });
  host.replaceChildren(h("div", { class: "card inner" }, h("h3", {}, `Log ${g.label.toLowerCase()} session`),
    h("p", { class: "sub" }, "Untick anyone who was absent. Leave a player's RPE empty to use the session RPE. Logging the same group and date again replaces it."),
    h("div", { class: "grid" }, field("Date", date), field("Minutes", mins), field("Session RPE (1-10)", rpe)),
    h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Present", "Player", "Own RPE"].map((c) => h("th", {}, c)))),
      h("tbody", {}, rows.map((r) => h("tr", {}, h("td", {}, r.here), h("td", {}, r.p.name), h("td", {}, r.rpe)))))),
    err, h("div", { class: "row" }, h("button", { class: "small", onclick: async () => {
      err.textContent = "";
      try {
        const x = await api(`/squads/${S.squad.id}/sc-sessions`, { method: "POST", body: { log_date: date.value, group: g.key, minutes: Number(mins.value), rpe: Number(rpe.value),
          players: rows.map((r) => ({ player_id: r.p.player_id, attended: r.here.checked, rpe: r.rpe.value ? Number(r.rpe.value) : null })) } });
        toast(`Session logged: ${x.present} present, ${x.absent} absent`); physicalTab();
      } catch (e) { err.textContent = e.message; }
    } }, "Save session"), h("button", { class: "small ghost", onclick: () => host.replaceChildren() }, "Cancel"))));
}

function attendanceCard(a) {
  return h("div", { class: "card" }, h("h2", {}, `Group sessions, last ${a.days} days`),
    a.sessions.length ? [catTable(["Date", "Group", "Present", "Absent", "Load (all present)"], a.sessions.map((x) => [fdate(String(x.date).slice(0, 10)), x.group, x.present, x.absent, x.load])),
      h("h3", {}, "Attendance by player (lowest first)"),
      catTable(["Player", "Attended", "%"], a.players.map((x) => [x.name, `${x.attended} of ${x.of}`, Math.round(100 * x.attended / x.of) + "%"]))]
      : h("p", { class: "sub" }, "No group sessions logged yet. Use \"Log this session\" on a group after you run it: present players get the load in their workload."));
}

function physTargets(d) {
  const rows = d.targets.filter((p) => p.targets.length);
  const none = d.targets.filter((p) => !p.targets.length).map((p) => p.name);
  return h("div", { class: "card" }, h("h2", {}, `Targets for the ${d.retest.label ? d.retest.label.toLowerCase() : "next"} test`),
    h("p", { class: "sub" }, "Each priority area's weakest test: the result that would lift the player about 15 rank points (never more than 8% in one window), " +
      "or the age-group expected value when that is higher. " + (d.later_window ? "Reached / not yet is checked against the later window." : "Checked automatically after the next test.")),
    h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Player", "Area (rank)", "Test", "Now", "Target", "Latest", "Result"].map((c) => h("th", {}, c)))),
      h("tbody", {}, rows.flatMap((p) => p.targets.map((t, i) => h("tr", {}, h("td", {}, i === 0 ? h("a", { href: "#", onclick: (e) => { e.preventDefault(); openP(p.player_id)(); } }, p.name) : ""),
        h("td", {}, `${t.area} (${Charts.num(t.rank, 0)})`), h("td", {}, `${t.test} (${t.unit})`), h("td", {}, t.current), h("td", {}, h("strong", {}, t.target)), h("td", {}, t.latest ?? "–"),
        h("td", {}, t.reached == null ? "–" : h("span", { class: "chip " + (t.reached ? "ok" : "warn") }, t.reached ? "Reached" : "Not yet")))))))),
    none.length ? h("p", { class: "sub" }, "No priority area (nothing below the middle): " + none.join(", ") + ".") : null);
}

function playerPlanList() {
  const host = h("div", {}, h("p", { class: "sub" }, "Loading players…"));
  api(`/players?squad_id=${S.squad.id}`).then((ps) => host.replaceChildren(...ps.filter((p) => p.is_active)
    .sort((a, b) => (a.squad_no ?? 999) - (b.squad_no ?? 999) || a.full_name.localeCompare(b.full_name))
    .map((p) => h("div", { class: "item" }, h("span", {}, (p.squad_no ? `#${p.squad_no}  ` : "") + p.full_name, h("span", { class: "sub" }, " · " + ROLE[p.role])),
      h("div", { class: "row" }, h("button", { class: "small", onclick: () => openAthletePlan(p.id) }, "Open 16-step seasonal plan"),
        playerPlanButton(S.squad.id, p.id, "small ghost"))))))
    .catch((x) => host.replaceChildren(h("div", { class: "err" }, x.message)));
  return host;
}

const MESO_CLS = { accumulation: "c-s3", transmutation: "c-s1", realization: "c-s2", competition: "c-good", transition: "c-muted" };

function physSeason() {
  const host = h("div", {}, h("div", { class: "sub loading" }, "Building the periodized season plan…"));
  api(`/squads/${S.squad.id}/seasons/${S.season.id}/sc-season-plan`).then((p) => {
    const wk = p.weeks;
    const grid = h("div", { class: "scroll" }, h("table", { class: "macro" }, h("tbody", {},
      [["Week", (w) => w.week], ["Starts", (w) => fdate(String(w.start).slice(0, 10))], ["Period", (w) => w.period], ["Mesocycle", (w) => `${w.mesocycle} · ${w.meso_label}`],
       ["Microcycle", (w) => w.microcycle], ["Volume %", (w) => w.volume], ["S&C sessions", (w) => w.sessions], ["Matches", (w) => w.matches || ""], ["Targets", (w) => w.targets.join(" + ")]]
        .map(([k, fn]) => h("tr", {}, h("th", {}, k), wk.map((w) => h("td", { class: ["Period", "Mesocycle", "Microcycle"].includes(k) ? "m-" + w.meso_type : "" }, String(fn(w)))))))));
    const chart = Charts.columns({ ariaLabel: "Planned S&C volume per week", height: 140, highlight: -1, capAll: true, format: (v) => `${v}%`,
      data: wk.map((w) => ({ label: `W${w.week}`, value: w.volume, cls: MESO_CLS[w.meso_type], tip: [`Week ${w.week} · ${fdate(String(w.start).slice(0, 10))}`, `${w.meso_label} · ${w.microcycle}`, `Volume ${w.volume}% · ${w.sessions} session(s)`, w.targets.length ? "Targets: " + w.targets.join(", ") : ""] })) });
    host.replaceChildren(
      h("div", { class: "card" }, h("div", { class: "bar" }, h("h2", {}, "Periodized S&C season plan"),
          h("div", { class: "row" },
            h("button", { class: "small ghost", onclick: () => downloadPlan("", "seasonal-workbook.xlsx").catch((x) => toast(x.message)) }, "Squad seasonal plan (Excel)"),
            allPlayersButton(), allPlayersPdfButton("ghost"))),
        h("p", { class: "sub" }, `${p.source}. Targets from ${p.based_on}; order of need: ${p.target_order.join(" → ")}.`),
        h("div", { class: "row legend" }, Object.entries({ accumulation: "Accumulation", transmutation: "Transmutation", realization: "Realization", competition: "Competition", transition: "Transition" })
          .map(([k, t]) => h("span", { class: "chip m-" + k }, t))),
        chart, grid),
      h("details", { class: "card", open: true }, h("summary", {}, "Player-by-player plans – the 16-step seasonal plan (STEP 0 answers first) and the periodized Excel"),
        h("div", { class: "list" }, playerPlanList())),
      ...p.mesocycles.map((m) => h("details", { class: "card", open: m.number === 1 },
        h("summary", {}, h("strong", {}, m.label), ` · ${fdate(String(m.start).slice(0, 10))} – ${fdate(String(m.end).slice(0, 10))} · ${m.weeks} week${m.weeks === 1 ? "" : "s"}` +
          (m.targets.length ? " · targets: " + m.targets.map((t) => t.label).join(" + ") : "")),
        h("div", { class: "row" }, m.methods.map((x) => h("span", { class: "chip" }, x)), h("span", { class: "chip " + (m.new_complex ? "warn" : "ok") }, m.new_complex ? "New exercise complex" : "Same complex as the last mesocycle")),
        catTable(["", ""], [["Targets", m.targets.map((t) => `${t.label} (${t.share})`).join(", ") || "–"], ["Retained", m.retained.join(", ") || "–"],
          ["Method", m.method], ["Dose", m.dose], ["Rest", m.rest], ["Frequency", m.frequency], ["Session length", m.minutes + " min"], ["Workout load", m.intensity]]),
        h("h4", {}, "Exercise complex (kept the whole mesocycle, in session order)"),
        catTable(["#", "Exercise", "Area", "Role", "Sets", "Reps / time"], m.complex.map((e, i) => [i + 1, e.name, e.area_label, e.role, e.set || "", e.rep || e.time || ""])),
        h("h4", {}, "Microcycle (week)"), catTable(["Day", "Session"], m.microcycle.map((d) => [d.day, d.session])))),
      h("div", { class: "card" }, h("h3", {}, "Session order"), h("ol", {}, p.session_order.map((t) => h("li", {}, t))),
        h("h3", {}, "Rules"), h("ul", {}, p.rules.map((t) => h("li", {}, t))),
        h("h3", {}, "Notes"), p.notes.map((n) => h("p", { class: "sub" }, n))));
  }).catch((x) => host.replaceChildren(h("div", { class: "err" }, x.message)));
  return host;
}

// ───────────── athlete seasonal plan in 16 steps (Zatsiorsky & Kraemer ch. 1, 5) ─────────────
const openAthletePlan = (pid) => { S.athletePid = pid; S.athleteEdit = false; go("physical"); };
const fd = (d) => (d ? fdate(String(d).slice(0, 10)) : "–");

async function athletePlanView(pid) {
  const main = $("#main");
  const base = `/squads/${S.squad.id}/seasons/${S.season.id}/athlete-plans/${pid}`;
  const s0 = await api(`${base}/step0`);
  const back = h("button", { class: "ghost small", onclick: () => { S.athletePid = null; physicalTab(); } }, "← Physical");
  const head = (extra) => h("div", { class: "bar" }, h("div", { class: "row" }, back, h("h1", {}, `Seasonal plan (16 steps) – ${s0.player.name}`)), h("div", { class: "row" }, extra));
  const sub = h("p", { class: "sub" }, `${S.squad.name} · ${s0.season.name} · Zatsiorsky & Kraemer, Science and Practice of Strength Training, ch. 1 and 5 (ch. 10 for young athletes)`);
  if (!s0.answers || S.athleteEdit) {
    main.replaceChildren(head(null), sub, step0Form(s0, base, () => { S.athleteEdit = false; athletePlanView(pid); }));
    return;
  }
  const p = await api(base);
  const dl = playerPlanButton(S.squad.id, pid);
  const edit = canCoach() ? h("button", { class: "small ghost", onclick: () => { S.athleteEdit = true; athletePlanView(pid); } }, "Edit STEP 0 answers") : null;
  main.replaceChildren(head([edit, dl]), sub, ...athletePlanBody(p));
}

function step0Form(s0, base, done) {
  const v = { ...s0.prefill, ...(s0.answers || {}) };
  const keep = (k) => (s0.answers && s0.answers[k] != null && s0.answers[k] !== "" ? s0.answers[k] : s0.prefill[k]);
  const inp = (k, type = "text", attrs = {}) => h("input", { type, value: keep(k) ?? "", ...attrs });
  const sel = (k, opts, def) => h("select", {}, opts.map(([val, t]) => h("option", { value: val, selected: (keep(k) ?? def) === val }, t)));
  const f = {
    position: inp("position"), age: inp("age", "number", { min: 8, max: 60 }), sex: sel("sex", [["male", "Male"], ["female", "Female"]], "male"),
    bw: inp("body_weight_kg", "number", { step: "0.1", min: 20, max: 150 }), tage: inp("training_age_years", "number", { step: "0.5", min: 0, max: 30 }),
    level: sel("level", [["", "– not sure (assume from age) –"], ...Object.entries(s0.levels)], ""),
    start: inp("plan_start", "date"), end: inp("plan_end", "date"),
    days: sel("training_days", [["", "– choose –"], ...[1, 2, 3, 4, 5, 6, 7].map((n) => [n, `${n} day${n > 1 ? "s" : ""} a week`])], ""),
    spd: sel("sessions_per_day", [["", "– choose –"], [1, "1 session a day"], [2, "2 sessions a day"], [3, "3 sessions a day"]], ""),
    result: inp("sport_result", "text", { placeholder: "e.g. 312 runs at 28, or 14 wickets at 18" }),
    injuries: inp("injuries", "text", { placeholder: "coach-safe wording only" }), recovery: inp("recovery"),
    equipment: inp("equipment", "text", { placeholder: "e.g. bands, medicine balls, light dumbbells" }),
    peak: sel("last_season_peak", [["", "– not stated –"], ["yes", "Yes, peaked on time"], ["early", "Peaked too early"], ["late", "Peaked too late"], ["no", "Did not peak"], ["first season", "First season"]], ""),
    loads: inp("last_season_loads", "text", { placeholder: "e.g. 2 S&C sessions a week, body weight only" }),
    inc: sel("load_increase", [["", "– not sure –"], ...Object.entries(s0.increase).map(([k, t]) => [k, `${t} (realization ${k === "mild" ? "≈2" : k === "normal" ? "≈4" : "≈6-7"} weeks)`])], ""),
  };
  // keep the selected value types for numbers
  [f.days, f.spd].forEach((s) => [...s.options].forEach((o) => { if (String(keep(s === f.days ? "training_days" : "sessions_per_day")) === o.value) o.selected = true; }));
  const lim = new Set(keep("limiting") || []);
  const limBox = h("div", { class: "row" }, Object.entries(s0.abilities).map(([k, t]) =>
    h("label", { class: "chip" }, h("input", { type: "checkbox", checked: lim.has(k), onchange: (e) => (e.target.checked ? lim.add(k) : lim.delete(k)) }), " " + t)));
  const comps = (keep("competitions") || []).map((c) => ({ ...c }));
  const compHost = h("div");
  const drawComps = () => compHost.replaceChildren(h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Competition", "Starts", "Days", "Importance", ""].map((c) => h("th", {}, c)))),
    h("tbody", {}, comps.map((c, i) => h("tr", {},
      h("td", {}, h("input", { value: c.name || "", oninput: (e) => (c.name = e.target.value) })),
      h("td", {}, h("input", { type: "date", value: String(c.start || "").slice(0, 10), onchange: (e) => (c.start = e.target.value) })),
      h("td", {}, h("input", { type: "number", min: 1, max: 60, value: c.days || 1, style: "width:5em", oninput: (e) => (c.days = +e.target.value) })),
      h("td", {}, h("select", { onchange: (e) => (c.importance = e.target.value) }, [["main", "MAIN (must peak)"], ["secondary", "Secondary (test)"]].map(([k, t]) => h("option", { value: k, selected: c.importance === k }, t)))),
      h("td", {}, h("button", { class: "small ghost", onclick: () => { comps.splice(i, 1); drawComps(); } }, "Remove"))))))),
    h("button", { class: "small ghost", onclick: () => { comps.push({ name: "", start: "", days: 1, importance: "secondary" }); drawComps(); } }, "+ Add competition"));
  drawComps();
  const exams = (keep("school_periods") || []).map((x) => ({ ...x }));
  const examHost = h("div");
  const drawExams = () => examHost.replaceChildren(...exams.map((x, i) => h("div", { class: "row" },
    h("input", { value: x.name || "", placeholder: "e.g. Term exams", oninput: (e) => (x.name = e.target.value) }),
    h("input", { type: "date", value: String(x.start || "").slice(0, 10), onchange: (e) => (x.start = e.target.value) }),
    h("input", { type: "date", value: String(x.end || "").slice(0, 10), onchange: (e) => (x.end = e.target.value) }),
    h("button", { class: "small ghost", onclick: () => { exams.splice(i, 1); drawExams(); } }, "Remove"))),
    h("button", { class: "small ghost", onclick: () => { exams.push({ name: "Exams", start: "", end: "" }); drawExams(); } }, "+ Add school / exam period"));
  drawExams();
  const num = (el) => (el.value === "" ? null : +el.value);
  const txt = (el) => el.value.trim() || null;
  const err = h("div", { class: "err", hidden: true });
  const save = h("button", { onclick: async () => {
    err.hidden = true;
    const body = { position: txt(f.position), age: num(f.age), sex: f.sex.value, body_weight_kg: num(f.bw), training_age_years: num(f.tage),
      level: f.level.value || null, plan_start: f.start.value || null, plan_end: f.end.value || null, training_days: num(f.days), sessions_per_day: num(f.spd),
      sport_result: txt(f.result), limiting: [...lim], injuries: txt(f.injuries), recovery: txt(f.recovery), equipment: txt(f.equipment),
      last_season_peak: f.peak.value || null, last_season_loads: txt(f.loads), load_increase: f.inc.value || null,
      competitions: comps.filter((c) => c.start).map((c) => ({ name: c.name || "Competition", start: String(c.start).slice(0, 10), days: c.days || 1, importance: c.importance || "secondary" })),
      school_periods: exams.filter((x) => x.start && x.end).map((x) => ({ name: x.name || "Exams", start: String(x.start).slice(0, 10), end: String(x.end).slice(0, 10) })) };
    save.disabled = true;
    try { await api(`${base}/step0`, { method: "PUT", body }); toast("STEP 0 saved – building the plan"); done(); }
    catch (x) { err.textContent = x.message; err.hidden = false; save.disabled = false; }
  } }, "Save STEP 0 and build the plan");
  const q = (n) => s0.questions.find((x) => x.n === n).text;
  const block = (n, ...kids) => h("div", { class: "card" }, h("h3", {}, `${n}. ${q(n)}`), ...kids);
  return h("div", {},
    h("p", { class: "hint" }, "STEP 0 – the plan is not built until these are answered. Fields are filled from the app where it knows the answer; anything left empty becomes a stated assumption."),
    block(1, h("div", { class: "grid" }, field("Sport", h("input", { value: "Cricket", disabled: true })), field("Position / event", f.position))),
    block(2, h("div", { class: "grid" }, field("Age", f.age), field("Sex", f.sex), field("Body weight (kg)", f.bw), field("Training age (years)", f.tage), field("Level", f.level))),
    block(3, compHost),
    block(4, h("div", { class: "grid" }, field("Plan starts", f.start), field("Plan ends (optional)", f.end)), h("p", { class: "sub" }, "Weeks available are counted from the start to the end of the last competition, plus at least 3 transition weeks.")),
    block(5, h("div", { class: "grid" }, field("Training days a week", f.days), field("Sessions a day", f.spd))),
    block(6, s0.tests.length ? catTable(["Test", "Result", "Area", "Rank (100 = best)"], s0.tests.map((t) => [t.test, t.value, t.area, t.rank == null ? "–" : Charts.num(t.rank, 0)]))
      : h("p", { class: "sub" }, "No test results in this season yet."), s0.test_window ? h("p", { class: "sub" }, `From the ${s0.test_window} tests.`) : null,
      field("Competition result in the main sport exercise", f.result)),
    block(7, h("p", { class: "sub" }, "Ticked from the test ranks below 50 where available – change as needed."), limBox),
    block(8, h("div", { class: "grid" }, field("Injuries", f.injuries), field("Recovery problems", f.recovery), field("Equipment limits", f.equipment)), examHost),
    block(9, h("div", { class: "grid" }, field("Did the athlete peak on time last season?", f.peak), field("Loads used last season", f.loads), field("Load increase this season", f.inc))),
    err, h("div", { class: "row" }, save));
}

const OKCLS = { true: "ok", false: "stop", null: "warn" };
const OKTXT = { true: "OK", false: "FIX", null: "Limited by the calendar" };

function athletePlanBody(p) {
  const chk = p.self_check;
  const fails = chk.filter((c) => c.ok === false).length;
  const out = [];
  out.push(h("div", { class: "card" }, h("div", { class: "bar" }, h("h2", {}, "STEP 16 – Self-check"),
      h("span", { class: "chip " + (fails ? "stop" : "ok") }, fails ? `${fails} to fix` : `All ${chk.length} checks pass`)),
    catTable(["", "Check", "Detail"], chk.map((c) => [h("span", { class: "chip " + OKCLS[c.ok] }, OKTXT[c.ok]), c.item, c.detail]))));
  out.push(h("div", { class: "card" }, h("h2", {}, "1. Summary of inputs + assumptions"),
    catTable(["#", "STEP 0", "Answer"], p.inputs.map((x) => [x.n, x.q, x.a])),
    p.assumptions.length ? [h("h4", {}, "Assumptions"), h("ul", {}, p.assumptions.map((a) => h("li", {}, a)))] : h("p", { class: "sub" }, "No assumptions – every question was answered.")));
  const wk = p.weeks;
  const chart = Charts.columns({ ariaLabel: "Relative volume per week", height: 140, highlight: -1, capAll: true, format: (v) => `${v}%`,
    data: wk.map((w) => ({ label: `W${w.week}`, value: w.volume, cls: MESO_CLS[w.meso_type], tip: [`Week ${w.week} · ${fd(w.start)}`, `${p.mesocycles[w.mesocycle - 1].label}`, `Volume ${w.volume}% · ${w.sessions} session(s)`, w.targets.join(" + ")] })) });
  out.push(h("div", { class: "card" }, h("h2", {}, "2. Season overview"),
    h("p", { class: "sub" }, `Model: ${p.model.model} · ${p.macrocycles.length} macrocycle(s) · peak: ${p.macrocycles.map((m) => `${m.peak} (${fd(m.start)})`).join(", ")}`),
    h("div", { class: "row legend" }, Object.entries({ accumulation: "Accumulation", transmutation: "Transmutation", realization: "Realization", competition: "Competition", transition: "Transition" })
      .map(([k, t]) => h("span", { class: "chip m-" + k }, t))),
    chart,
    h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Weeks", "Dates", "Period", "Mesocycle", "Targets", "Methods", "Load %", "Tests / competitions"].map((c) => h("th", {}, c)))),
      h("tbody", {}, p.mesocycles.map((m) => h("tr", {}, h("td", {}, m.weeks), h("td", {}, `${fd(m.start)} – ${fd(m.end)}`), h("td", {}, m.period),
        h("td", { class: "m-" + m.type }, m.label), h("td", {}, m.targets.join(" + ") + (m.halves.length ? h("div", { class: "sub" }, m.halves.map((x) => `${fd(x.from)}: ${x.targets.join(" + ")}`).join(" · ")) : "")),
        h("td", {}, m.methods.join(", ")), h("td", {}, m.relative_load),
        h("td", {}, p.testing.filter((t) => t.date >= m.start && t.date <= m.end).map((t) => `${fd(t.date)}: ${t.kind}`).join("; ") || "–"))))))));
  out.push(h("div", { class: "card" }, h("h2", {}, "3. Load curve"), h("ul", {}, p.load_curve.map((t) => h("li", {}, t)))));
  out.push(h("div", { class: "card" }, h("h2", {}, "4. Exercise complexes (with change dates)"),
    ...p.blocks.map((b) => h("p", {}, h("strong", {}, `Complex ${b.number} from ${fd(b.from)}: `), b.exercises.join(", ")))));
  out.push(h("h2", {}, "5. Mesocycles and sample microcycles"));
  for (const m of p.mesocycles) {
    out.push(h("details", { class: "card", open: m.number === 1 },
      h("summary", {}, h("strong", {}, m.label), ` · ${fd(m.start)} – ${fd(m.end)} · ${m.weeks} wk · ` + (m.targets.join(" + ") || "–")),
      h("div", { class: "row" }, m.methods.map((x) => h("span", { class: "chip" }, x)), h("span", { class: "chip " + (m.new_complex ? "warn" : "ok") }, m.new_complex ? "New complex" : "Same complex"),
        m.type === "accumulation" || m.type === "transmutation" ? h("span", { class: "chip info" }, `${Math.round(m.target_share * 100)}% of the sets on the targets`) : null),
      h("p", { class: "sub" }, `Technique: ${m.technique}. Retained: ${m.retained.join(", ") || "–"}.`),
      catTable(["#", "Exercise", "Ability", "Role", "Sets x reps / load", "Rest"], m.complex.map((e, i) => [i + 1, e.name, e.ability_label, e.role, e.dose, e.rest])),
      m.microcycle.length ? [h("h4", {}, "Sample week"), catTable(["Day", "When", "Load", "Exercises", "Restoration"], m.microcycle.map((d) => [d.day, d.when || d.note || "", d.load ? d.load + "%" : "",
        d.items.length ? h("ul", {}, d.items.map((x) => h("li", {}, `${x.name}${x.dose ? ": " + x.dose : ""}${x.rest ? " · rest " + x.rest : ""}`))) : "", d.restoration || ""]))] : null,
      m.competition_microcycle.length ? [h("h4", {}, `Competition microcycle (${m.competition_microcycle.length} days)`),
        catTable(["Date", "Day", "Session", "Restoration"], m.competition_microcycle.map((d) => [fd(d.date), d.day, d.match ? h("strong", {}, d.session) : d.session, d.restoration])),
        m.competition_note ? h("p", { class: "hint warn" }, m.competition_note) : null] : null));
  }
  for (const t of p.tapers) {
    out.push(h("div", { class: "card" }, h("h2", {}, `6. Taper – last 14 days before ${t.competition} (${fd(t.start)})`),
      catTable(["Date", "Days out", "Session", "Exercises", "Load", "Restoration"], t.rows.map((d) => [fd(d.date) + (d.past ? " (past)" : ""), d.days_out, d.session,
        d.exercises.map((e) => `${e.name} ${e.dose}`).join(", ") || "–", d.load + "%", d.restoration]))));
  }
  const tr = p.transition;
  out.push(h("div", { class: "card" }, h("h2", {}, "7. Competition period and transition"),
    h("ul", {}, p.steps.find((s) => s.n === 10).lines.map((t) => h("li", {}, t))),
    h("h4", {}, `Transition: ${tr.weeks} week(s)` + (tr.from ? ` from ${fd(tr.from)}` : "")), h("ul", {}, [...tr.guidelines, tr.body_weight].map((t) => h("li", {}, t)))));
  out.push(h("div", { class: "card" }, h("h2", {}, "8. Monitoring and adjustment"),
    catTable(["Date", "Mesocycle", "Test / competition", "What", "If below expectation"], p.testing.map((t) => [fd(t.date), t.mesocycle, t.kind, t.what, t.if_below]))));
  out.push(h("details", { class: "card" }, h("summary", {}, h("strong", {}, "STEPS 1-14 – the work behind the plan")),
    ...p.steps.map((s) => h("div", {}, h("h3", {}, `STEP ${s.n} – ${s.title}`), h("ul", {}, s.lines.map((t) => h("li", {}, t))),
      s.table ? catTable(["Weeks", "Period", "Mesocycle", "Main goal"], s.table.map((r) => [r.weeks, r.period, r.mesocycle, r.goal])) : null))));
  if (p.notes.length) out.push(h("div", { class: "card" }, h("h3", {}, "Notes"), p.notes.map((n) => h("p", { class: "sub" }, n))));
  return out;
}

function physDashboard(d) {
  const x = d.dashboard;
  const tiles = h("div", { class: "row tiles" },
    [["Tested", `${x.tested} of ${x.squad_size}`], ["Priority areas (below 50)", x.summary.reduce((a, s) => a + s.priority, 0)],
     ["Strengths (70+)", x.summary.reduce((a, s) => a + s.strength, 0)], ["Pace bowlers to watch", x.pace.filter((p) => p.watch.length).length]]
      .map(([k, v]) => h("div", { class: "card tile" }, h("div", { class: "sub" }, k), h("div", { class: "big" }, String(v)))));
  return [tiles,
    x.untested.length ? h("p", { class: "hint warn" }, "Not tested in this window: " + x.untested.join(", ")) : null,
    h("div", { class: "card" }, h("h2", {}, "Player × area (rank in level, 100 = best)"),
      h("p", { class: "sub" }, "Red = priority (below 50) · plain = solid · green = strength (70+). Click a player for their plans."),
      h("div", { class: "scroll" }, h("table", { class: "heatmap" }, h("thead", {}, h("tr", {}, ["Player", "Role", "Band", ...x.areas.map((a) => a.label), "Priorities"].map((c) => h("th", {}, c)))),
        h("tbody", {}, x.rows.map((r) => h("tr", { class: "click", onclick: openP(r.player_id) }, h("td", {}, r.name), h("td", {}, ROLE[r.role]),
          h("td", {}, r.band ? `${r.band} · ${r.band_label}` : "–"), ...x.areas.map((a) => rankCell(r.areas[a.area])), h("td", {}, r.priorities.join(", ") || "–"))))))),
    h("div", { class: "card" }, h("h2", {}, "Squad by area"), catTable(["Area", "Tested", "Priority", "Strength", "Weakest area for"],
      x.summary.map((s) => [s.label, s.tested, s.priority, s.strength, `${s.weakest_first} player(s)`]))),
    x.pace.length ? h("div", { class: "card" }, h("h2", {}, "Fast-bowler fitness"),
      h("p", { class: "sub" }, "Endurance and core protect a bowler late in a spell. Below 50 = watch (see Tests → Workload from testing for suggested limits)."),
      h("div", { class: "scroll" }, h("table", { class: "heatmap" }, h("thead", {}, h("tr", {}, ["Player", "Endurance", "Core", "Leg power", "Speed", "Watch"].map((c) => h("th", {}, c)))),
        h("tbody", {}, x.pace.map((p) => h("tr", {}, h("td", {}, p.name), rankCell(p.endurance), rankCell(p.core), rankCell(p.power), rankCell(p.speed),
          h("td", {}, p.watch.length ? h("span", { class: "chip warn" }, p.watch.join(", ")) : h("span", { class: "chip ok" }, "OK")))))))) : null];
}

function physGroups(d) {
  if (!d.groups.length) return h("div", { class: "card" }, "No test results in this window yet, so there are no groups.");
  return [h("p", { class: "sub" }, `${d.groups.length} groups for ${d.groups.reduce((a, g) => a + g.players.length, 0)} players, by each player's weakest area. Sessions are for the current phase (${d.phase_label || "–"}).`),
    ...d.groups.map((g) => {
      const s = g.session, rows = [];
      if (s) s.parts.forEach((pt) => pt.items.forEach((it, i) => rows.push([i === 0 ? `${pt.part}${pt.minutes ? ` (${pt.minutes} min)` : ""}` : "", it.name, it.area_label || "", it.set || "", it.rep || it.time || "", it.rest || ""])));
      const logHost = h("div");
      return h("div", { class: "card" }, h("div", { class: "bar" }, h("h2", {}, `${g.label} (${g.players.length})`),
          h("div", { class: "row" }, s ? h("span", { class: "chip" }, `${s.phase_label} · about ${s.minutes} min`) : null,
            canCoach() ? h("button", { class: "small", onclick: () => scLogForm(logHost, g, s) }, "Log this session") : null)),
        logHost,
        h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Player", "Rank", "Also below the middle", "Group"].map((c) => h("th", {}, c)))),
          h("tbody", {}, g.players.map((p) => h("tr", {}, h("td", {}, h("a", { href: "#", onclick: (e) => { e.preventDefault(); openP(p.player_id)(); } }, p.name)),
            h("td", {}, p.rank != null ? Charts.num(p.rank, 0) : "–"), h("td", {}, p.also.join(", ") || "–"),
            h("td", {}, canCoach() ? groupPick(d, g, p) : g.label)))))),
        s ? [s.second_focus ? h("p", { class: "sub" }, `Also covers: ${s.second_focus}, the group's next most common need.`) : null,
          catTable(["Part", "Exercise", "Area", "Sets", "Reps / time", "Rest"], rows), h("p", { class: "sub" }, s.note)] : null);
    }), attendanceCard(d.attendance)];
}

function physProgress(d) {
  const r = d.retest, p = d.progress;
  const plan = h("div", { class: "card" }, h("h2", {}, "Next test"), h("p", {}, r.text),
    r.next_window && !(r.scheduled || []).length && can("coach", "sc_coach", "admin") ? h("button", { class: "small", onclick: async () => {
      try {
        await api(`/squads/${S.squad.id}/events`, { method: "POST", body: { event_type: "fitness_test", title: `${r.label} physical testing`, start_at: `${r.suggested_date}T08:00:00+05:30` } });
        toast("Test added to the calendar"); physicalTab();
      } catch (x) { toast(x.message); }
    } }, `Add ${r.label.toLowerCase()} test on ${fdate(r.suggested_date)} to the calendar`) : null);
  const cls = { improved: "up", declined: "down", same: "flat", single: "" };
  const table = h("div", { class: "card" }, h("h2", {}, p.any_compared ? "Change since the first test" : "Results so far"),
    h("p", { class: "sub" }, p.any_compared ? "Green = better, red = worse, grey = no clear change. Each player against their own earlier result."
      : "Only one test window so far: these are the first results. After the next test this shows each player's change."),
    h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Player", ...p.tests.map((t) => `${t.label} (${t.unit})`), "Improved", "Band"].map((c) => h("th", {}, c)))),
      h("tbody", {}, p.rows.map((x) => h("tr", { class: "click", onclick: openP(x.player_id) }, h("td", {}, x.name),
        ...p.tests.map((t) => h("td", { class: cls[x.cells[t.key].state] }, x.cells[t.key].text)),
        h("td", {}, x.compared ? `${x.improved} of ${x.compared}` : "–"), h("td", {}, x.band || "–")))))));
  return [plan, table];
}

function physGrowth(d) {
  const canSet = can("coach", "sc_coach", "admin");
  const noData = d.growth.every((g) => !g.measures.length);
  return h("div", { class: "card" }, h("h2", {}, "Growth & body data"),
    noData ? h("p", { class: "hint warn" }, "No height or mass has been recorded yet. Fill Height (cm) and Body weight (kg) in the test template at every test; the growth rate appears after two heights at least 3 months apart.") : null,
    h("p", { class: "sub" }, "Growth stage changes the plans: in the growth spurt, jump and sprint volume is kept low and fast bowlers bowl one over fewer per day."),
    h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Player", "Height (cm)", "Mass (kg)", "BMI", "Growth (cm/yr)", "Stage", "Set stage"].map((c) => h("th", {}, c)))),
      h("tbody", {}, d.growth.map((g) => h("tr", {}, h("td", {}, h("a", { href: "#", onclick: (e) => { e.preventDefault(); openP(g.player_id)(); } }, g.name)),
        h("td", {}, g.height_cm ?? "–"), h("td", {}, g.weight_kg ?? "–"), h("td", {}, g.bmi ?? "–"),
        h("td", {}, g.velocity_cm_yr != null ? h("span", { class: g.in_spurt ? "chip warn" : "" }, String(g.velocity_cm_yr)) : (g.measures.length === 1 ? "needs a 2nd height" : "–")),
        h("td", {}, h("span", { class: g.in_spurt ? "chip warn" : "chip" }, g.stage_label), g.stage_source !== "not known" ? h("span", { class: "sub" }, ` (${g.stage_source})`) : null),
        h("td", {}, canSet ? h("select", { "aria-label": "Growth stage for " + g.name, onchange: async (e) => {
          try { await api(`/players/${g.player_id}`, { method: "PATCH", body: { maturity_status: e.target.value } }); toast("Growth stage saved"); physicalTab(); } catch (x) { toast(x.message); }
        } }, Object.entries(MATURITY).map(([k, t]) => h("option", { value: k, selected: k === g.maturity_status }, t))) : MATURITY[g.maturity_status])))))));
}

// ───────────── workload from the testing record ─────────────
const LIMIT_TXT = (l) => `${l.max_spell_overs ?? "–"} a spell · ${l.max_match_day_overs ?? "–"} a day · ${l.max_bowling_days_week ?? "–"} days/wk`;

async function testWorkloadCard(host, window) {
  const d = await api(`/squads/${S.squad.id}/seasons/${S.season.id}/test-workload?window=${window}`);
  const canLog = can("coach", "sc_coach", "admin");
  if (!d.players.length) return host.replaceChildren(h("h2", {}, "Workload from testing"), h("p", { class: "sub" }, "No test results in this window yet."));
  const logged = (r) => r.logged === "system" ? h("span", { class: "chip ok" }, `In workload (${r.logged_load})`)
    : r.logged === "coach" ? h("span", { class: "chip" }, "Logged by a coach") : h("span", { class: "chip warn" }, "Not in workload");
  const detail = h("div");
  const show = (r) => {
    const parts = r.day_load.parts;
    detail.replaceChildren(h("div", { class: "card inner" },
      h("div", { class: "bar" }, h("h3", {}, r.player), h("button", { class: "small ghost", onclick: () => detail.replaceChildren() }, "← Back")),
      h("h4", {}, `Test-day load · ${fdate(String(r.test_date).slice(0, 10))} · ${r.day_load.minutes} min · session RPE ${r.day_load.rpe} · ${r.day_load.load} units`),
      catTable(["Part", "Minutes", "RPE", "Load", "Based on"], parts.map((x) => [x.label, x.minutes, x.rpe, x.load, x.basis])),
      h("h4", {}, "Training loads from the tests"),
      catTable(["Quality", "Test result", "Training dose", "Why"], r.targets.map((t) => [t.quality, `${t.test}: ${t.result}`, t.prescription, t.why])),
      r.bowling ? [h("h4", {}, "Fast-bowling workload"),
        catTable(["", "Overs a spell", "Overs a day", "Bowling days a week"], [
          ["Limits now", r.bowling.limits.max_spell_overs, r.bowling.limits.max_match_day_overs, r.bowling.limits.max_bowling_days_week],
          ["Suggested from the tests", r.bowling.suggested.max_spell_overs, r.bowling.suggested.max_match_day_overs, r.bowling.suggested.max_bowling_days_week]]),
        h("ul", {}, r.bowling.reasons.map((x) => h("li", {}, x))),
        h("p", { class: "sub" }, `Last 7 days: ${r.bowling.current.overs_7d ?? 0} overs on ${r.bowling.current.bowling_days_7d} day(s). ` +
          `Load 7 days: ${r.load_7d ?? "–"} · load ratio: ${r.acwr ?? "needs 3 weeks of logs"}.`)] : null));
    detail.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const pace = d.players.filter((r) => r.bowling);
  const msg = h("div", { class: "err", role: "alert" });
  host.replaceChildren(h("div", { class: "bar" }, h("h2", {}, `Workload from testing · ${d.window_label}`),
      canLog ? h("button", { class: "small", onclick: async () => {
        msg.textContent = "";
        try { const x = await api(`/squads/${S.squad.id}/seasons/${S.season.id}/test-workload/log?window=${window}`, { method: "POST" });
          toast(`Test-day load: ${x.logged} added, ${x.updated} updated` + (x.coach_logged ? `, ${x.coach_logged} kept (logged by a coach)` : ""));
          testWorkloadCard(host, window); } catch (e) { msg.textContent = e.message; }
      } }, "Add test-day load to workload") : null),
    h("p", { class: "sub" }, "Click a player for the test-day load, training doses from their results and (pace bowlers) bowling workload."), msg,
    h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["No", "Player", "Role", "Test-day load", "Workload", "Training doses", "Bowling limit"].map((x) => h("th", {}, x)))),
      h("tbody", {}, d.players.map((r) => h("tr", { class: "click", onclick: () => show(r) },
        h("td", {}, r.squad_no ?? "–"), h("td", {}, r.player), h("td", {}, ROLE[r.role]),
        h("td", {}, `${r.day_load.minutes} min · RPE ${r.day_load.rpe} · ${r.day_load.load}`), h("td", {}, logged(r)), h("td", {}, `${r.targets.length} doses`),
        h("td", {}, r.bowling ? (r.bowling.stricter ? h("span", { class: "chip warn" }, "Stricter suggested") : h("span", { class: "chip ok" }, "Normal")) : "–")))))),
    pace.length ? [h("h3", {}, "Fast bowlers and pace all-rounders"), catTable(["Player", "Limits now", "Suggested from the tests", "Overs (7 d)", "Days (7 d)", "Why"],
      pace.map((r) => [r.player, LIMIT_TXT(r.bowling.limits), LIMIT_TXT(r.bowling.suggested), r.bowling.current.overs_7d ?? 0, r.bowling.current.bowling_days_7d, r.bowling.reasons.join(" ")]))] : null,
    detail, h("details", {}, h("summary", {}, "How these are worked out"), d.notes.map((n) => h("p", { class: "sub" }, n))));
}

// sit and reach + the 8 skinfolds of one session (player page)
function bodyExtrasCard(ex) {
  if (!ex || (!ex.sit_reach && !ex.skinfolds.some((x) => x.final != null))) return null;
  const sf = ex.skinfolds.filter((x) => x.final != null);
  return h("div", { class: "card inner" }, h("h3", {}, "Body composition and flexibility"),
    h("p", { class: "sub" }, "Recorded and tracked over the season; not ranked and not part of the band."),
    h("div", { class: "row" },
      Charts.stat({ label: "Sum of 8 skinfolds", value: ex.skinfold_sum == null ? "–" : ex.skinfold_sum.toFixed(1) + " mm",
        sub: ex.skinfold_sum == null ? `${sf.length} of 8 sites measured` : ex.third_needed ? `3rd measure needed at ${ex.third_needed} site(s)` : "lower = leaner" }),
      Charts.stat({ label: "Sit and reach", value: ex.sit_reach ? fmt(ex.sit_reach.final, 1) + " cm" : "–", sub: ex.sit_reach ? "best of 3" : "not tested" })),
    sf.length ? h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Site", "T1", "T2", "T3", "Final (mm)"].map((c) => h("th", {}, c)))),
      h("tbody", {}, ex.skinfolds.map((x) => h("tr", {}, h("td", {}, x.label), x.trials.map((v) => h("td", {}, fmt(v, 1))),
        h("td", { class: x.third_needed ? "down" : "" }, x.final == null ? "–" : x.final.toFixed(1) + (x.third_needed ? " · take a 3rd" : ""))))))) : null,
    ex.copied.length ? h("p", { class: "hint warn" }, ex.copied.join(". ") + ". Measure this player and enter the real values when possible.") : null);
}

// the squad's skinfold record and sit and reach (Tests page), in the layout of the skinfold sheet
async function bodyTestsCard(host, window, canEdit) {
  const d = await api(`/squads/${S.squad.id}/seasons/${S.season.id}/body-tests?window=${window}`);
  const anyData = d.players.some((r) => r.skinfold_sum != null || r.sit_reach || r.skinfolds.some((x) => x.final != null));
  const edit = (r) => () => canEdit ? fitnessForm({ id: r.player_id, full_name: r.name }, window) : (S.pid = r.player_id, S.from = S.tab, go("players"));
  const withSum = d.players.filter((r) => r.skinfold_sum != null).sort((a, b) => a.skinfold_sum - b.skinfold_sum);
  const chart = withSum.length ? Charts.hbars({ ariaLabel: "Sum of 8 skinfolds by player", format: (v) => Charts.num(v, 1),
    data: withSum.map((r) => ({ label: r.name, value: r.skinfold_sum, display: r.skinfold_sum.toFixed(1) + (r.copied.length ? " *" : ""),
      cls: r.copied.length ? "c-muted" : "c-s3", onClick: edit(r), tip: [r.name, `${r.skinfold_sum.toFixed(1)} mm (sum of 8)`, ...r.copied] })),
    refs: d.squad_mean_sum ? [{ value: d.squad_mean_sum, label: "mean " + d.squad_mean_sum }] : [] }) : null;
  host.replaceChildren(h("h2", {}, `Skinfolds and sit and reach · ${d.window_label}`),
    h("p", { class: "sub" }, "Readings in mm, right side (ISAK 8 sites). Two measures per site, a third if they differ by more than 5%. " +
      "Sit and reach in cm, best of 3. Recorded and tracked, not ranked." + (canEdit ? " Select a player to enter or edit." : "")),
    !anyData ? h("p", { class: "sub" }, "Nothing recorded for this window yet. Add the columns in the test template, or select a player to enter them.") : null,
    h("div", { class: "scroll" }, h("table", { class: "skinfolds" },
      h("thead", {}, h("tr", {}, ["No.", "Player", "Weight (kg)", ...d.sites.map((x) => x.label), "Total of 8", "3rd measure needed (sites)", "Sit and reach (cm)"].map((c) => h("th", {}, c)))),
      h("tbody", {}, d.players.map((r, i) => {
        const prev = d.players[i - 1];
        const rows = [];
        if (r.standby && (!prev || !prev.standby)) rows.push(h("tr", {}, h("td", { colspan: 14, class: "sub" }, h("strong", {}, "Stand-by"))));
        rows.push(h("tr", { class: "click", tabindex: 0, onclick: edit(r), onkeydown: (e) => e.key === "Enter" && edit(r)(), title: r.copied.join(". ") || null },
          h("td", {}, r.squad_no ?? "–"), h("td", {}, r.name + (r.copied.length ? " *" : "")), h("td", {}, fmt(r.weight_kg, 1)),
          r.skinfolds.map((x) => h("td", { class: x.third_needed ? "down" : "" }, x.final == null ? "" : x.final.toFixed(1))),
          h("td", {}, h("strong", {}, r.skinfold_sum == null ? "–" : r.skinfold_sum.toFixed(1))), h("td", {}, r.third_needed),
          h("td", {}, r.sit_reach ? fmt(r.sit_reach.final, 1) : "–")));
        return rows;
      })))),
    d.players.some((r) => r.copied.length) ? h("p", { class: "hint warn" }, "* Not measured: values copied from the comparison player the coach chose (hover the row to see who). Measure and replace them when possible.") : null,
    h("p", { class: "sub" }, `Squad mean: total of 8 ${d.squad_mean_sum ?? "–"} mm · sit and reach ${d.squad_mean_sit_reach ?? "–"} cm.`),
    chart ? h("div", { class: "card inner" }, h("h3", {}, "Sum of 8 skinfolds (lower = leaner)"), chart) : null);
}

// SLC National U15 Physical Testing: standard operating procedures (summary of the approved SOP)
const SOP_STEPS = [
  ["Testing levels", "Provincial: height + body weight, Bronco. Super Provincial: height + body weight, 2 km run, standing broad jump, push-ups + inverted row, 20 m sprint, 5-10-5, standard plank.", []],
  ["Before any test", "Confirm identity, age group, school/province, date, venue and assessor. Medical clearance first. Check surface, weather, equipment and run-out areas. Explain and demonstrate every test; same instructions, equipment, timing, order and scoring for all. Progressive warm-up. Stop if a player reports pain, dizziness, chest discomfort, unusual breathlessness or looks unwell.", []],
  ["Height + body mass", "Stadiometer on a level surface, barefoot, heels down, head neutral, record cm. Calibrated scale, no shoes, light clothing, record kg. Repeat an inconsistent reading.", []],
  ["Bronco (Provincial)", "Lines at 0, 20, 40 and 60 m. One cycle = 20 m out and back, 40 m out and back, 60 m out and back (240 m). Five cycles = 1,200 m. Record total time in minutes and seconds.", [["How to set up", "https://www.youtube.com/watch?v=R4cBuW3TrD0"], ["The Bronco test", "https://www.youtube.com/watch?v=EfuPPV_A9V4"]]],
  ["2 km run (Super Provincial)", "Measured 2,000 m course (5 laps of a 400 m track, anti-clockwise). Start on the signal, stop when the player crosses the finish. Never compare with Bronco.", []],
  ["Standing broad jump", "Non-slip level surface, take-off line, tape along the jump. Two-foot take-off and landing. Measure to the nearest landing mark (back of the nearest heel). Same arm-swing rule for all. Record every valid distance in cm and the best.", [["Video 1", "https://www.youtube.com/watch?v=EH4FuJF7_ok"], ["Video 2", "https://www.youtube.com/watch?v=GTjndpflm_I"]]],
  ["Push-ups", "Hands slightly wider than shoulders, body straight head to heels, elbows about 45°, lower until the chest is just above the ground, push to full extension. Count only reps that meet every point. Record the set-up.", [["Video 1", "https://www.youtube.com/watch?v=WDIpL0pjun0"], ["Video 2", "https://www.youtube.com/watch?v=rSjzEE-eoVM"]]],
  ["Inverted row", "Fixed bar, overhand grip just outside shoulder width, heels on the ground, body straight. Pull the chest to the bar, squeeze the shoulder blades, lower under control to straight arms. Same bar height, grip and foot position for all; record the set-up.", [["Video", "https://www.youtube.com/watch?v=EXTVaQudfj8"]]],
  ["20 m sprint", "Straight measured 20 m lane with a safe run-out. Same start position and command. Sprint through the finish. Timing gates if available. Record each valid time in seconds; fastest counts.", [["Video 1", "https://www.youtube.com/watch?v=mCvGvsOW_ew"], ["Video 2", "https://www.youtube.com/watch?v=XF3jb4b0jWo"]]],
  ["5-10-5 test", "Cones at 5 m left, middle (0 m), 5 m right. Start 30 cm from the middle, feet shoulder-width. Sprint 5 m right and touch the cone, 10 m left and touch, 5 m back through the middle. No touch = no try.", [["Video", "https://www.youtube.com/watch?v=XSc-g5o2qhY"]]],
  ["Standard plank", "Forearm plank, elbows under shoulders, straight line head to heels, hips level. Start timing once aligned; stop when alignment is lost and not corrected after the agreed cue. Record seconds.", [["Video", "https://www.youtube.com/watch?v=XuprZeJa7G0"]]],
  ["Sit and reach (added)", "Shoes off, legs straight, feet flat against the box. Reach forward slowly with both hands together and hold 2 s. Record cm (0 at the toes). Best of 3. Warm up first.", []],
  ["Skinfolds (added)", "Trained measurer, calibrated caliper, right side, ISAK landmarks: triceps, subscapular, biceps, iliac crest, supraspinale, abdominal, front thigh, medial calf. Two measures per site, a third if they differ by more than 5%. Report the sum of 8.", []],
  ["Results and reporting", "3 trials; the best counts. Record raw scores with units, test version, surface, timing method, trial number and notes, to two decimals (e.g. 8.25 min in the 2 km). Never estimate a missing result. Keep results confidential.", []]];
const sopCard = () => h("details", { class: "card" }, h("summary", {}, h("strong", {}, "Testing procedures (SLC U15 SOP)")),
  h("p", { class: "sub" }, "Summary of the Sri Lanka Cricket National Under-15 Physical Testing SOP, plus sit and reach and skinfolds."),
  h("dl", { class: "sop" }, SOP_STEPS.map(([t, d, links]) => [h("dt", {}, t), h("dd", {}, d, links.length ? h("span", { class: "sub" }, " · ",
    links.map(([l, u], i) => [i ? " · " : null, h("a", { href: u, target: "_blank", rel: "noopener noreferrer" }, l)])) : null)])));

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
  api("/meta/benchmark").then((b) => main.append(benchmarkRefCard(b))).catch(() => {});
  api("/meta/age-norms").then((n) => main.append(ageNormsCard(n, S.squad.age_group || "U15"))).catch(() => {});
  table.replaceChildren(h("h2", {}, `Categories · ${c.window_label}`),
    h("p", { class: "sub" }, `Ranked within the same level only. A band needs ${c.min_cohort}+ players of a level.`),
    h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Player", "Level", "Band", "Score", "U15 points", "Focus areas", "Readiness"].map((x) => h("th", {}, x)))),
      h("tbody", {}, c.players.map((r) => h("tr", { class: "click", onclick: () => { S.pid = r.player_id; S.from = S.tab; go("players"); } },
        h("td", {}, r.player), h("td", {}, r.level_label || "Not tested"), h("td", {}, r.band ? bandChip(r) : "–"), h("td", {}, r.overall ?? "–"),
        h("td", {}, benchChip(r.benchmark)),
        h("td", {}, r.focus_areas.join(", ") || "–"), h("td", {}, readyChip(r.readiness))))))));
  const twHost = h("div", { class: "card" });
  main.insertBefore(twHost, table.nextSibling);
  const bodyHost = h("div", { class: "card" });
  main.insertBefore(bodyHost, twHost);
  bodyTestsCard(bodyHost, window, canImport).catch((x) => bodyHost.replaceChildren(h("div", { class: "err" }, x.message)));
  main.append(sopCard());
  testWorkloadCard(twHost, window).catch((x) => twHost.replaceChildren(h("div", { class: "err" }, x.message)));
  const sp = await api(`/squads/${S.squad.id}/seasons/${S.season.id}/test-progress`);
  if (sp.windows_with_results.length >= 2) {
    prog.replaceChildren(h("h2", {}, "Progress since the first test"),
      h("p", { class: "sub" }, "Each player against their own earlier results."),
      h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, ["Player", "Band movement", "Tests improved", "Below middle before, not now", "Newly below middle"].map((x) => h("th", {}, x)))),
        h("tbody", {}, sp.players.map((r) => h("tr", { class: "click", onclick: () => { S.pid = r.player_id; S.from = S.tab; go("players"); } },
          h("td", {}, r.player), h("td", {}, r.band_text ?? "–"), h("td", {}, r.tests_compared ? `${r.tests_improved} of ${r.tests_compared}` : "–"),
          h("td", {}, r.focus_resolved.join(", ") || "–"), h("td", {}, r.focus_new.join(", ") || "–")))))));
    main.append(prog);
  }
}

// ───────────── boot ─────────────
$("#logout").addEventListener("click", signOut);
S.token = store.get();
splash().then(() => (S.token ? start() : showLogin(location.hash === AUTH_HASH.signup ? "signup" : "signin")));
