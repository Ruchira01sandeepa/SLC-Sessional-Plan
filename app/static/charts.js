"use strict";
/* Small dependency-free charts for the SLC U15 UI.
   - CSP-safe: no inline <style>, colours come from CSS classes (.c-s1 … .c-good …) defined in app.css.
   - Text is always real DOM text (never painted into a canvas), so it scales, translates and is read by screen readers.
   - Every mark has a hover / keyboard-focus tooltip; values are also shown as labels, legends or tables. */
const Charts = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, cls, ...kids) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    for (const k of kids.flat()) if (k != null && k !== false) e.append(k.nodeType ? k : document.createTextNode(String(k)));
    return e;
  };
  const svg = (tag, attrs = {}) => {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) if (v != null) e.setAttribute(k, v);
    return e;
  };
  const num = (v, d = 0) => (v == null ? "–" : Number(v).toLocaleString(undefined, { maximumFractionDigits: d }));

  // ───────── tooltip (one shared element) ─────────
  let tipEl = null;
  function tip() {
    if (!tipEl) { tipEl = el("div", "viz-tip"); tipEl.setAttribute("role", "tooltip"); tipEl.hidden = true; document.body.append(tipEl); }
    return tipEl;
  }
  function place(x, y) {
    const t = tip(), r = t.getBoundingClientRect(), pad = 12;
    let left = x + pad, top = y + pad;
    if (left + r.width > window.innerWidth - 8) left = x - r.width - pad;
    if (top + r.height > window.innerHeight - 8) top = y - r.height - pad;
    t.style.left = Math.max(8, left) + "px"; t.style.top = Math.max(8, top) + "px";
  }
  function show(lines, x, y) {
    const t = tip();
    t.replaceChildren(...lines.filter(Boolean).map((l, i) => el("div", i === 0 ? "viz-tip-title" : null, l)));
    t.hidden = false; place(x, y);
  }
  const hide = () => { if (tipEl) tipEl.hidden = true; };
  /** Wire hover + focus tooltips onto a mark. lines: array of strings (first = title). */
  function hover(node, lines, label) {
    node.setAttribute("tabindex", "0");
    node.setAttribute("aria-label", label || lines.filter(Boolean).join(", "));
    node.addEventListener("mousemove", (e) => show(lines, e.clientX, e.clientY));
    node.addEventListener("mouseleave", hide);
    node.addEventListener("focus", () => { const r = node.getBoundingClientRect(); show(lines, r.left + r.width / 2, r.top); });
    node.addEventListener("blur", hide);
  }
  window.addEventListener("scroll", hide, { passive: true });

  /** Clean axis ticks: 0 … ≥max in 1/2/2.5/5 × 10^n steps. */
  function ticks(max, target = 4) {
    if (!(max > 0)) return [0, 1];
    const raw = max / target, p = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= raw);
    const out = [];
    for (let v = 0; v < max + step * 0.999; v += step) out.push(+v.toFixed(10));
    return out;
  }
  const compact = (v) => (Math.abs(v) >= 10000 ? (v / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 }) + "K" : v.toLocaleString());

  // ───────── stat tile ─────────
  /** {label, value, sub?, tone?: "good"|"warning"|"critical", icon?} */
  function stat({ label, value, sub, tone }) {
    return el("div", "stat" + (tone ? " tone-" + tone : ""), el("div", "stat-label", label), el("div", "stat-value", value), sub ? el("div", "stat-sub", sub) : null);
  }

  // ───────── legend ─────────
  function legend(items) {
    return el("ul", "viz-legend", items.map((i) => el("li", null, el("span", "swatch " + i.cls), el("span", "lg-label", i.label), i.value != null ? el("span", "lg-value", i.value) : null)));
  }

  // ───────── donut ─────────
  /** parts: [{label, value, cls}], center: {value, label}. Parts at zero draw nothing but stay in the legend. */
  function donut({ parts, center, title, size = 168, unit = "" }) {
    const total = parts.reduce((s, p) => s + (p.value || 0), 0);
    const R = 80, r = 54, C = 84;
    const g = svg("svg", { viewBox: "0 0 168 168", width: size, height: size, class: "donut", role: "img",
      "aria-label": `${title || "Breakdown"}: ` + parts.map((p) => `${p.label} ${p.value}`).join(", ") });
    g.append(svg("circle", { cx: C, cy: C, r: (R + r) / 2, class: "donut-track", "stroke-width": R - r, fill: "none" }));
    if (total > 0) {
      let a0 = -Math.PI / 2;
      const live = parts.filter((p) => p.value > 0);
      for (const p of live) {
        const a1 = a0 + (p.value / total) * Math.PI * 2;
        const share = Math.round((p.value / total) * 100);
        let path;
        if (live.length === 1) {
          path = svg("path", { d: `M${C} ${C - R}A${R} ${R} 0 1 1 ${C - 0.01} ${C - R}L${C - 0.01} ${C - r}A${r} ${r} 0 1 0 ${C} ${C - r}Z`, class: "donut-seg " + p.cls });
        } else {
          const large = a1 - a0 > Math.PI ? 1 : 0;
          const P = (rad, a) => `${(C + rad * Math.cos(a)).toFixed(2)} ${(C + rad * Math.sin(a)).toFixed(2)}`;
          path = svg("path", { d: `M${P(R, a0)}A${R} ${R} 0 ${large} 1 ${P(R, a1)}L${P(r, a1)}A${r} ${r} 0 ${large} 0 ${P(r, a0)}Z`, class: "donut-seg " + p.cls });
        }
        hover(path, [p.label, `${num(p.value)}${unit} · ${share}%`]);
        g.append(path);
        a0 = a1;
      }
    }
    const mid = el("div", "donut-center", el("div", "donut-value", center ? center.value : num(total)), el("div", "donut-label", center ? center.label : "total"));
    return el("div", "donut-wrap", el("div", "donut-box", g, mid),
      legend(parts.map((p) => ({ cls: p.cls, label: p.label, value: total ? `${num(p.value)} · ${Math.round(((p.value || 0) / total) * 100)}%` : num(p.value) }))));
  }

  // ───────── horizontal bars (one row per item; text stays real HTML) ─────────
  /** data: [{label, value|null, cls, display?, sub?, onClick?, tip?: string[]}]; refs: [{value, label}] drawn as hairlines. */
  function hbars({ data, max, refs = [], format = (v) => num(v), empty = "No data yet.", ariaLabel }) {
    if (!data.length) return el("p", "sub", empty);
    const top = Math.max(max || 0, ...data.map((d) => d.value || 0), ...refs.map((r) => r.value)) || 1;
    const wrap = el("div", "hbars");
    if (ariaLabel) { wrap.setAttribute("role", "group"); wrap.setAttribute("aria-label", ariaLabel); }
    if (refs.length) {
      const head = el("div", "hb-row hb-refs", el("span", "hb-label"), el("span", "hb-track"), el("span", "hb-value"));
      for (const r of refs) { const m = el("span", "hb-ref-label", r.label); m.style.left = (r.value / top) * 100 + "%"; head.children[1].append(m); }
      wrap.append(head);
    }
    for (const d of data) {
      const track = el("span", "hb-track");
      for (const r of refs) { const line = el("span", "hb-ref"); line.style.left = (r.value / top) * 100 + "%"; track.append(line); }
      if (d.value != null && d.value > 0) {
        const bar = el("span", "hb-bar " + (d.cls || "c-s1"));
        bar.style.width = Math.max(0.6, (d.value / top) * 100) + "%";
        track.append(bar);
      }
      const row = el(d.onClick ? "button" : "div", "hb-row" + (d.onClick ? " clickable" : ""),
        el("span", "hb-label", d.label, d.sub ? el("span", "hb-sub", d.sub) : null), track, el("span", "hb-value", d.display ?? format(d.value)));
      if (d.onClick) { row.type = "button"; row.addEventListener("click", d.onClick); }
      hover(row, d.tip || [d.label, d.display ?? format(d.value)]);
      if (d.onClick) row.removeAttribute("tabindex");             // buttons are focusable already
      wrap.append(row);
    }
    return wrap;
  }

  // ───────── vertical columns ─────────
  /** data: [{label, value, cls?, tip?: string[]}]; highlight: index to label on its cap (default: the last). */
  function columns({ data, height = 180, format = (v) => num(v), highlight = data.length - 1, ariaLabel, refs = [], capAll = false, capFormat = (v) => num(v) }) {
    const max = Math.max(...data.map((d) => d.value || 0), ...refs.map((r) => r.value), 0);
    const tk = ticks(max), top = tk[tk.length - 1] || 1;
    const plot = el("div", "cols-plot");
    plot.style.height = height + "px";
    for (const t of tk) {
      const line = el("div", "cols-grid" + (t === 0 ? " base" : ""), el("span", "cols-tick", compact(t)));
      line.style.bottom = (t / top) * 100 + "%";
      plot.append(line);
    }
    for (const r of refs) {
      const line = el("div", "cols-ref", el("span", "cols-ref-label", r.label));
      line.style.bottom = (r.value / top) * 100 + "%";
      plot.append(line);
    }
    const bars = el("div", "cols-bars");
    data.forEach((d, i) => {
      const col = el("div", "cols-col");
      const bar = el("div", "cols-bar " + (d.cls || (i === highlight ? "c-s1" : "c-muted")));
      bar.style.height = d.value > 0 ? Math.max(1, (d.value / top) * 100) + "%" : "0";
      if ((capAll || i === highlight) && d.value != null) bar.append(el("span", "cols-cap", capFormat(d.value)));
      col.append(bar);
      hover(col, d.tip || [d.label, format(d.value)]);
      bars.append(col);
    });
    plot.append(bars);
    const labels = el("div", "cols-labels", data.map((d) => el("span", null, d.label)));
    const wrap = el("div", "cols", plot, labels);
    wrap.setAttribute("role", "group");
    if (ariaLabel) wrap.setAttribute("aria-label", ariaLabel);
    return wrap;
  }

  return { stat, donut, hbars, columns, legend, num, hide };
})();
