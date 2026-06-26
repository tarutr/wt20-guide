/* ============================================================================
   COMPARE STATS  —  Stage A
   Skeleton + data table: discipline & range toggles, frozen panes,
   player cell (photo, flag, name in country colour, [X]), search-add,
   Reset Players (clears table). Sorting/filtering/columns come in later stages.

   Relies on globals from index.html: DATA, ASSETS, slug, TEAM_COLORS, track()
   ========================================================================== */
(function () {
  "use strict";

  // ---- Stat column definitions (aligned to index.html's canonical arrays) -
  // group: 'basic' | 'advanced' (drives the section sub-headers + default show)
  // lower: true if a lower value is better (for later sorting/colour)
  // src: 'stats' (pre_wc/wc) or 'graph' (graph_data) — top7 SR lives in graph_data
  const BAT_COLS = [
    { key: "innings_batted", label: "Inns", group: "basic", dp: 0 },
    { key: "runs", label: "Runs", group: "basic", dp: 0 },
    { key: "batting_average", label: "Avg", group: "basic", dp: 1 },
    { key: "batting_sr", label: "Bat SR", group: "basic", dp: 1 },
    { key: "fifties_plus", label: "50+", group: "basic", dp: 0 },
    { key: "highest_score", label: "HS", group: "basic", dp: 0 },
    { key: "first_10_ball_sr", label: "10Ball SR", group: "advanced", dp: 1 },
    { key: "powerplay_sr", label: "PP SR", group: "advanced", dp: 1 },
    { key: "sr_edge", label: "SR Edge", group: "advanced", dp: 2 },
    { key: "balls_per_boundary", label: "Balls/Bdry", group: "advanced", dp: 1, lower: true },
    { key: "dot_pct", label: "Dot %", group: "advanced", dp: 1, lower: true },
    { key: "non_boundary_sr", label: "NBSR", group: "advanced", dp: 1 },
  ];
  const BOWL_COLS = [
    { key: "innings_bowled", label: "Inns", group: "basic", dp: 0 },
    { key: "wickets", label: "Wkts", group: "basic", dp: 0 },
    { key: "economy", label: "Econ", group: "basic", dp: 2, lower: true },
    { key: "bowling_average", label: "Bowl Avg", group: "basic", dp: 1, lower: true },
    { key: "bowling_sr", label: "Bowl SR", group: "basic", dp: 1, lower: true },
    { key: "three_wicket_hauls", label: "3WI", group: "basic", dp: 0 },
    { key: "top7_wickets", label: "Top7 Wkt", group: "advanced", dp: 0 },
    { key: "top7_bowling_sr", label: "Top7 SR", group: "advanced", dp: 1, lower: true, src: "graph" },
    { key: "wicket_edge", label: "Wicket Edge", group: "advanced", dp: 2 },
    { key: "bowling_dot_pct", label: "Dot %", group: "advanced", dp: 1 },
    { key: "boundary_runs_per_over", label: "Bdry/Over", group: "advanced", dp: 2, lower: true },
    { key: "econ_edge", label: "Econ Edge", group: "advanced", dp: 2 },
  ];

  // ---- Filter option definitions -----------------------------------------
  const ROLE_GROUPS = {
    Batter: ["Top Order Bat", "Middle Order Bat", "Finisher", "Wicket Keeper"],
    Bowler: ["Pacer", "Spinner"],
    "All-Rounder": ["All-Rounder"],
  };
  const BAT_TYPES = ["Top Order Bat", "Middle Order Bat", "Finisher", "Wicket Keeper"];
  const BAT_TYPE_LABELS = { "Top Order Bat": "Top Order", "Middle Order Bat": "Middle Order", "Finisher": "Finisher", "Wicket Keeper": "Wicket Keeper" };
  const BOWL_TYPES = ["Pace", "Off-Spin", "Leg Spin", "Left-Arm Orthodox", "Left-Arm Unorthodox"];
  const COUNTRIES = ["Australia", "Bangladesh", "England", "India", "Ireland", "Netherlands", "New Zealand", "Pakistan", "Scotland", "Sri Lanka", "South Africa", "West Indies"];

  // ---- State --------------------------------------------------------------
  const cs = {
    discipline: "batting", // 'batting' | 'bowling'
    range: "pre_wc", // 'pre_wc' | 'wc'
    rows: [], // array of player objects currently shown
    filters: { role: "", type: "", hand: "", country: "" },
    sortKey: null, // column key or attribute key currently sorted
    sortDir: "desc", // 'asc' | 'desc'
    hidden: {}, // { batting: Set(keys hidden), bowling: Set(keys hidden) }
    order: {}, // { batting: [keys...], bowling: [keys...] } custom STAT column order
    attrOrder: {}, // { batting: [attr keys...], bowling: [...] } custom ATTR order
    attrCols: {}, // { batting: Set(attr keys shown), bowling: Set(...) } e.g. 'role','country'
    minInnings: { batting: 10, bowling: 10 }, // default for pre_wc; reset on range toggle
  };

  // Glossary tooltips by column key (text drawn from index.html's glossary)
  const GLOSS = {
    innings_batted: "Number of innings batted.",
    runs: "Total runs scored.",
    batting_average: "Runs per dismissal.",
    batting_sr: "Runs per 100 balls faced.",
    fifties_plus: "Scores of fifty or more (includes hundreds).",
    highest_score: "Highest individual score.",
    first_10_ball_sr: "Strike rate across the first 10 balls a batter faces — how quickly they get going.",
    powerplay_sr: "Strike rate in the powerplay (overs 1–6).",
    sr_edge: "How often a batter scored faster than their team's run rate while at the crease. Higher is better.",
    balls_per_boundary: "How many balls a batter faces, on average, between boundaries.",
    dot_pct: "Share of balls faced that are dots (no run scored). Lower is better.",
    non_boundary_sr: "Strike rate from runs other than boundaries — rotating strike and running hard.",
    innings_bowled: "Number of innings bowled.",
    wickets: "Total wickets taken.",
    economy: "Runs conceded per over, excluding byes and leg-byes. Lower is better.",
    bowling_average: "Runs conceded per wicket. Lower is better.",
    bowling_sr: "Balls bowled per wicket. Lower is better.",
    three_wicket_hauls: "Innings in which a bowler took three or more wickets.",
    top7_wickets: "Wickets of top-7 (specialist) batters.",
    top7_bowling_sr: "Balls per top-7 wicket. Lower is better.",
    wicket_edge: "How often a bowler struck more frequently than their team. Higher is better.",
    bowling_dot_pct: "Share of legal deliveries that are dots. Higher is better for a bowler.",
    boundary_runs_per_over: "Boundary runs conceded per over. Lower is better.",
    econ_edge: "How often a bowler was more economical than their team. Higher is better.",
  };

  // Attribute (non-stat) columns available via Show/Hide
  function groupedRole(p) {
    for (const g in ROLE_GROUPS) if (ROLE_GROUPS[g].includes(p.role)) return g;
    return p.role || "—";
  }
  const ATTR_COLS = [
    { key: "role", label: "Role", get: (p) => groupedRole(p) },
    { key: "type", label: "Type", get: (p) => (cs.discipline === "batting" ? p.role : p.bowling_type) },
    { key: "hand", label: cs.discipline === "batting" ? "Bat Hand" : "Bowl Hand", get: (p) => (cs.discipline === "batting" ? p.batting_hand : p.bowling_hand) },
    { key: "country", label: "Country", get: (p) => p.nationality },
  ];

  // ---- Helpers ------------------------------------------------------------
  function statsFor(player) {
    return cs.range === "wc" ? player.wc_stats : player.pre_wc_stats;
  }
  function colVal(player, col) {
    if (col.src === "graph") return (player.graph_data || {})[col.key];
    const s = statsFor(player) || {};
    return s[col.key];
  }
  function pal(player) {
    return TEAM_COLORS[slug(player.nationality)] || { p: "#E4324B", s: "#15233F" };
  }
  function activeCols() {
    return cs.discipline === "batting" ? BAT_COLS : BOWL_COLS;
  }
  // ensure per-discipline state containers exist
  function ensureColState() {
    const d = cs.discipline;
    if (!cs.hidden[d]) {
      // default: advanced stats hidden, basic shown
      cs.hidden[d] = new Set(activeCols().filter((c) => c.group === "advanced").map((c) => c.key));
    }
    if (!cs.order[d]) cs.order[d] = activeCols().map((c) => c.key);
    if (!cs.attrCols[d]) cs.attrCols[d] = new Set();
    if (!cs.attrOrder[d]) cs.attrOrder[d] = ATTR_COLS.map((a) => a.key);
  }
  // visible stat columns in custom order, minus hidden
  function visibleStatCols() {
    ensureColState();
    const d = cs.discipline;
    const byKey = {};
    activeCols().forEach((c) => (byKey[c.key] = c));
    return cs.order[d]
      .map((k) => byKey[k])
      .filter((c) => c && !cs.hidden[d].has(c.key));
  }
  function visibleAttrCols() {
    ensureColState();
    const d = cs.discipline;
    const byKey = {};
    ATTR_COLS.forEach((a) => (byKey[a.key] = a));
    return cs.attrOrder[d]
      .map((k) => byKey[k])
      .filter((a) => a && cs.attrCols[d].has(a.key));
  }
  function inningsKey() {
    return cs.discipline === "batting" ? "innings_batted" : "innings_bowled";
  }
  function maxInnings() {
    const k = inningsKey();
    let mx = 0;
    DATA.players.forEach((p) => {
      const v = (statsFor(p) || {})[k];
      if (typeof v === "number" && v > mx) mx = v;
    });
    return mx;
  }
  // Min Innings: default 1 for WC (1-step options), 10 for pre-WC (5-step options)
  function updateMinInningsDefault() {
    const def = cs.range === "wc" ? 1 : 10;
    cs.minInnings[cs.discipline] = def;
    const valEl = document.getElementById("cs-mininn-val");
    if (valEl) valEl.textContent = def;
  }
  function minInnOptions() {
    const mx = maxInnings();
    const opts = [];
    if (cs.range === "wc") {
      for (let i = 0; i <= mx; i++) opts.push(i);
    } else {
      for (let i = 0; i <= mx; i += 5) opts.push(i);
      if (opts[opts.length - 1] !== mx && mx > 0) {} // keep clean 5-steps
    }
    return opts.length ? opts : [0];
  }
  function openMinInnMenu() {
    closeAnyMenu();
    const anchor = document.getElementById("cs-mininnbtn");
    const menu = document.createElement("div");
    menu.className = "cs-fmenu cs-popmenu"; menu.id = "cs-popmenu";
    menu.style.bottom = "calc(100% + 5px)"; menu.style.top = "auto"; menu.style.right = "0"; menu.style.left = "auto";
    const cur = cs.minInnings[cs.discipline];
    menu.innerHTML = minInnOptions().map((n) =>
      `<div class="cs-fmenu-it ${n === cur ? "on" : ""}" data-n="${n}">${n}</div>`).join("");
    anchor.appendChild(menu);
    menu.querySelectorAll(".cs-fmenu-it").forEach((it) => {
      it.addEventListener("click", (e) => {
        e.stopPropagation();
        cs.minInnings[cs.discipline] = parseInt(it.dataset.n, 10);
        document.getElementById("cs-mininn-val").textContent = it.dataset.n;
        closeAnyMenu(); renderTable();
      });
    });
    armOutsideClose();
  }

  // ---- Sorting ------------------------------------------------------------
  function sortRows(rows) {
    if (!cs.sortKey) {
      // default: country, then player first name (alphabetical)
      return rows.slice().sort((a, b) => {
        const ca = a.nationality.toLowerCase(), cb = b.nationality.toLowerCase();
        if (ca < cb) return -1; if (ca > cb) return 1;
        const fa = a.name.split(/\s+/)[0].toLowerCase(), fb = b.name.split(/\s+/)[0].toLowerCase();
        return fa < fb ? -1 : fa > fb ? 1 : 0;
      });
    }
    const key = cs.sortKey;
    const dir = cs.sortDir === "asc" ? 1 : -1;
    const attr = ATTR_COLS.find((a) => a.key === key);
    const statCol = activeCols().find((c) => c.key === key);
    const val = (p) => {
      if (key === "name") return p.name.toLowerCase();
      if (attr) return (attr.get(p) || "").toString().toLowerCase();
      if (statCol) { const v = colVal(p, statCol); return v == null ? -Infinity : Number(v); }
      return 0;
    };
    return rows.slice().sort((a, b) => {
      const va = val(a), vb = val(b);
      if (va < vb) return -1 * dir;
      if (va > vb) return 1 * dir;
      return 0;
    });
  }
  function applySort(key) {
    if (cs.sortKey === key) {
      cs.sortDir = cs.sortDir === "asc" ? "desc" : "asc";
    } else {
      cs.sortKey = key; cs.sortDir = "desc";
    }
    renderTable();
  }
  window.csApplySort = applySort;

  // ---- Show / hide columns menu ------------------------------------------
  function openColMenu() {
    closeAnyMenu();
    ensureColState();
    const d = cs.discipline;
    const anchor = document.getElementById("cs-colbtn");
    const menu = document.createElement("div");
    menu.className = "cs-popmenu cs-colmenu"; menu.id = "cs-popmenu";
    const mkStat = (c) => {
      const shown = !cs.hidden[d].has(c.key);
      return `<div class="cs-colit ${shown ? "on" : ""}" data-kind="stat" data-key="${c.key}">
        <span class="cs-box"></span>${c.label}</div>`;
    };
    const basicItems = activeCols().filter((c) => c.group === "basic").map(mkStat).join("");
    const advItems = activeCols().filter((c) => c.group === "advanced").map(mkStat).join("");
    const attrItems = ATTR_COLS.map((a) => {
      const shown = cs.attrCols[d].has(a.key);
      return `<div class="cs-colit ${shown ? "on" : ""}" data-kind="attr" data-key="${a.key}">
        <span class="cs-box"></span>${a.label}</div>`;
    }).join("");
    menu.innerHTML =
      `<div class="cs-colmenu-h">Basic Stats</div><div class="cs-colgrid">${basicItems}</div>` +
      `<div class="cs-colmenu-h">Advanced Stats</div><div class="cs-colgrid">${advItems}</div>` +
      `<div class="cs-colmenu-h">Attributes</div><div class="cs-colgrid">${attrItems}</div>`;
    anchor.appendChild(menu);
    menu.querySelectorAll(".cs-colit").forEach((it) => {
      it.addEventListener("click", (e) => {
        e.stopPropagation();
        const key = it.dataset.key;
        if (it.dataset.kind === "stat") {
          if (cs.hidden[d].has(key)) cs.hidden[d].delete(key); else cs.hidden[d].add(key);
        } else {
          if (cs.attrCols[d].has(key)) cs.attrCols[d].delete(key); else cs.attrCols[d].add(key);
        }
        it.classList.toggle("on");
        renderTable();
      });
    });
    armOutsideClose();
  }

  // ---- Sort By menu -------------------------------------------------------
  function openSortMenu() {
    closeAnyMenu();
    const anchor = document.getElementById("cs-sortbtn");
    const menu = document.createElement("div");
    menu.className = "cs-popmenu"; menu.id = "cs-popmenu";
    const items = [
      { key: "name", label: "Player name" },
      ...ATTR_COLS.map((a) => ({ key: a.key, label: a.label })),
      ...activeCols().map((c) => ({ key: c.key, label: c.label })),
    ];
    menu.innerHTML = items.map((it) =>
      `<div class="cs-fmenu-it ${cs.sortKey === it.key ? "on" : ""}" data-key="${it.key}">${it.label}${cs.sortKey === it.key ? (cs.sortDir === "asc" ? " ▲" : " ▼") : ""}</div>`
    ).join("");
    anchor.appendChild(menu);
    menu.querySelectorAll(".cs-fmenu-it").forEach((it) => {
      it.addEventListener("click", (e) => {
        e.stopPropagation();
        applySort(it.dataset.key);
        closeAnyMenu();
      });
    });
    armOutsideClose();
  }

  function closeAnyMenu() {
    const m = document.getElementById("cs-popmenu");
    if (m) m.remove();
  }
  function armOutsideClose() {
    setTimeout(() => {
      document.addEventListener("click", function handler(e) {
        if (e.target.closest("#cs-popmenu") || e.target.closest("#cs-colbtn") ||
            e.target.closest("#cs-sortbtn") || e.target.closest("#cs-mininnbtn")) {
          document.addEventListener("click", handler, { once: true }); return;
        }
        closeAnyMenu();
      }, { once: true });
    }, 0);
  }
  function fmt(val, dp) {
    if (val === null || val === undefined || val === "" || Number.isNaN(val)) return "—";
    const n = Number(val);
    if (Number.isNaN(n)) return "—";
    if (dp === 0) return Math.round(n).toLocaleString();
    return n.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp });
  }
  function flagImg(player) {
    const sl = slug(player.nationality);
    return `<img class="cs-flag" src="${ASSETS}/wavy_flags/${sl}.png" onerror="this.style.visibility='hidden'">`;
  }

  // ---- Build the modal once ----------------------------------------------
  function buildModal() {
    if (document.getElementById("cs-backdrop")) return;
    const wrap = document.createElement("div");
    wrap.id = "cs-backdrop";
    wrap.className = "cs-backdrop";
    wrap.addEventListener("click", (e) => { if (e.target === wrap) closeCompareStats(); });
    wrap.innerHTML = `
      <div class="cs-modal">
        <div class="cs-head">
          <div>
            <div class="cs-title serif">Compare Stats</div>
          </div>
          <div class="cs-head-r">
            <button class="cs-rand" id="cs-rand" title="Surprise me with a random comparison">&#127922; Randomise</button>
            <button class="cs-x" onclick="closeCompareStats()" aria-label="Close">&#10005;</button>
          </div>
        </div>

        <div class="cs-toolbar">
          <div class="cs-toolrow cs-searchrow" id="cs-searchrow">
            <button class="cs-chev" id="cs-chev-search" title="Collapse / expand">&#9650;</button>
            <span class="cs-collabel">Search</span>
            <div class="cs-search">
              <input type="text" id="cs-search-input" placeholder="Search a player to add…" autocomplete="off">
              <div class="cs-results" id="cs-search-results"></div>
            </div>
            <div class="cs-seg" id="cs-discipline">
              <button data-v="batting" class="on">Batting</button>
              <button data-v="bowling">Bowling</button>
            </div>
            <div class="cs-seg" id="cs-range">
              <button data-v="wc">WC</button>
              <button data-v="pre_wc" class="on">Since Last WC</button>
            </div>
          </div>
          <div class="cs-toolrow cs-filterrow" id="cs-filterrow">
            <button class="cs-chev" id="cs-chev-filter" title="Collapse / expand">&#9650;</button>
            <span class="cs-collabel">Filters</span>
            <div class="cs-filtergroup">
              <span class="cs-filter-tag">Filters</span>
              <div class="cs-fdrop" id="cs-f-role"><span class="cs-fl">Role</span> <span class="cs-fv">All</span> <span class="cs-ca">&#9660;</span></div>
              <div class="cs-fdrop" id="cs-f-type"><span class="cs-fl">Type</span> <span class="cs-fv">All</span> <span class="cs-ca">&#9660;</span></div>
              <div class="cs-fdrop" id="cs-f-hand"><span class="cs-fl">Bat Hand</span> <span class="cs-fv">All</span> <span class="cs-ca">&#9660;</span></div>
              <div class="cs-fdrop" id="cs-f-country"><span class="cs-fl">Country</span> <span class="cs-fv">All</span> <span class="cs-ca">&#9660;</span></div>
            </div>
            <div class="cs-spacer"></div>
            <button class="cs-clear" onclick="csResetTable()">Clear</button>
            <button class="cs-run" id="cs-run">Search</button>
          </div>
        </div>

        <div class="cs-sentence" id="cs-sentence" style="display:none"></div>

        <div class="cs-twrap" id="cs-twrap">
          <table class="cs-table" id="cs-table"></table>
          <div class="cs-empty" id="cs-empty">
            <div class="cs-empty-in">
              <div class="cs-empty-h">No players yet</div>
              <div class="cs-empty-p">Search for a player above, or run a filter, to build your table.</div>
            </div>
          </div>
        </div>

        <div class="cs-foot">
          <div class="cs-foot-btn" id="cs-colbtn">&#9776; Show / hide columns</div>
          <div class="cs-foot-btn" id="cs-sortbtn">&#8645; Sort by</div>
          <div class="cs-foot-mininn">
            <span class="cs-mininn-lab">Min Innings</span>
            <div class="cs-foot-btn" id="cs-mininnbtn"><span id="cs-mininn-val">10</span> <span class="cs-ca">&#9660;</span></div>
          </div>
        </div>
      </div>`;
    document.body.appendChild(wrap);

    // discipline toggle
    wrap.querySelector("#cs-discipline").addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      setSeg("cs-discipline", b); cs.discipline = b.dataset.v;
      cs.filters.type = ""; cs.filters.hand = "";
      cs.sortKey = null;
      ensureColState();
      updateFilterLabels();
      updateMinInningsDefault();
      renderTable();
    });
    // range toggle
    wrap.querySelector("#cs-range").addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      setSeg("cs-range", b); cs.range = b.dataset.v;
      updateMinInningsDefault();
      renderTable();
    });
    // footer buttons
    wrap.querySelector("#cs-colbtn").addEventListener("click", (e) => { e.stopPropagation(); openColMenu(); });
    wrap.querySelector("#cs-sortbtn").addEventListener("click", (e) => { e.stopPropagation(); openSortMenu(); });
    wrap.querySelector("#cs-mininnbtn").addEventListener("click", (e) => { e.stopPropagation(); openMinInnMenu(); });
    // filter dropdowns
    wrap.querySelector("#cs-f-role").addEventListener("click", () => openFilterMenu("role"));
    wrap.querySelector("#cs-f-type").addEventListener("click", () => openFilterMenu("type"));
    wrap.querySelector("#cs-f-hand").addEventListener("click", () => openFilterMenu("hand"));
    wrap.querySelector("#cs-f-country").addEventListener("click", () => openFilterMenu("country"));
    // run button + randomise
    wrap.querySelector("#cs-run").addEventListener("click", runFilters);
    wrap.querySelector("#cs-rand").addEventListener("click", randomise);
    // row chevrons (collapse each row independently)
    wrap.querySelector("#cs-chev-search").addEventListener("click", () => toggleRow("search"));
    wrap.querySelector("#cs-chev-filter").addEventListener("click", () => toggleRow("filter"));
    // search
    const si = wrap.querySelector("#cs-search-input");
    si.addEventListener("input", onSearchInput);
    si.addEventListener("focus", onSearchInput);
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".cs-search")) hideResults();
    });
  }

  function setSeg(segId, btn) {
    document.querySelectorAll(`#${segId} button`).forEach((b) => b.classList.remove("on"));
    btn.classList.add("on");
  }

  function toggleRow(which) {
    const row = document.getElementById(which === "search" ? "cs-searchrow" : "cs-filterrow");
    const chev = document.getElementById(which === "search" ? "cs-chev-search" : "cs-chev-filter");
    if (!row) return;
    const collapsed = row.classList.toggle("collapsed");
    chev.innerHTML = collapsed ? "&#9660;" : "&#9650;";
  }

  // ---- Filters ------------------------------------------------------------
  function typeOptions() {
    return cs.discipline === "batting"
      ? BAT_TYPES.map((v) => ({ v, label: BAT_TYPE_LABELS[v] || v }))
      : BOWL_TYPES.map((v) => ({ v, label: v }));
  }
  function filterOptions(which) {
    if (which === "role") return Object.keys(ROLE_GROUPS).map((v) => ({ v, label: v }));
    if (which === "type") return typeOptions();
    if (which === "hand") return [{ v: "LHB", label: "Left" }, { v: "RHB", label: "Right" }];
    if (which === "country") return COUNTRIES.map((v) => ({ v, label: v }));
    return [];
  }
  function updateFilterLabels() {
    const handLabel = cs.discipline === "batting" ? "Bat Hand" : "Bowl Hand";
    setDropLabel("cs-f-hand", handLabel, cs.filters.hand, "hand");
    setDropLabel("cs-f-role", "Role", cs.filters.role, "role");
    setDropLabel("cs-f-type", "Type", cs.filters.type, "type");
    setDropLabel("cs-f-country", "Country", cs.filters.country, "country");
  }
  function setDropLabel(id, label, value, which) {
    const el = document.getElementById(id);
    if (!el) return;
    el.querySelector(".cs-fl").textContent = label;
    const opts = filterOptions(which);
    const match = opts.find((o) => o.v === value);
    el.querySelector(".cs-fv").textContent = value ? (match ? match.label : value) : "All";
    el.classList.toggle("active", !!value);
  }
  function openFilterMenu(which) {
    const existing = document.getElementById("cs-fmenu");
    const wasThisOpen = existing && existing.dataset.which === which;
    closeFilterMenu();
    if (wasThisOpen) return; // clicking the same dropdown again just closes it
    const anchor = document.getElementById("cs-f-" + which);
    const menu = document.createElement("div");
    menu.className = "cs-fmenu";
    menu.id = "cs-fmenu";
    menu.dataset.which = which;
    const opts = [{ v: "", label: "All" }, ...filterOptions(which)];
    menu.innerHTML = opts.map((o) =>
      `<div class="cs-fmenu-it ${cs.filters[which] === o.v ? "on" : ""}" data-v="${o.v}">${o.label}</div>`
    ).join("");
    anchor.appendChild(menu);
    menu.querySelectorAll(".cs-fmenu-it").forEach((it) => {
      it.addEventListener("click", (e) => {
        e.stopPropagation();
        cs.filters[which] = it.dataset.v;
        updateFilterLabels();
        closeFilterMenu();
      });
    });
  }
  function closeFilterMenu() {
    const m = document.getElementById("cs-fmenu");
    if (m) m.remove();
  }
  // Close any open filter menu when clicking outside the filter row.
  document.addEventListener("click", (e) => {
    const menu = document.getElementById("cs-fmenu");
    if (!menu) return;
    if (e.target.closest(".cs-fdrop")) return; // dropdown clicks handled by openFilterMenu
    if (e.target.closest(".cs-fmenu")) return; // option clicks handled above
    closeFilterMenu();
  });
  function roleMatch(player, roleGroup) {
    const granular = ROLE_GROUPS[roleGroup] || [];
    return granular.includes(player.role);
  }
  function playerMatchesFilters(p) {
    const f = cs.filters;
    if (f.role && !roleMatch(p, f.role)) return false;
    if (f.type) {
      if (cs.discipline === "batting") { if (p.role !== f.type) return false; }
      else { if (p.bowling_type !== f.type) return false; }
    }
    if (f.hand) {
      const h = cs.discipline === "batting" ? p.batting_hand : p.bowling_hand;
      if (h !== f.hand) return false;
    }
    if (f.country && p.nationality !== f.country) return false;
    return true;
  }
  function runFilters() {
    cs.rows = DATA.players.filter(playerMatchesFilters);
    renderTable();
    if (window.track) track("compare_stats_run_filters", {
      role: cs.filters.role || "all", type: cs.filters.type || "all",
      hand: cs.filters.hand || "all", country: cs.filters.country || "all",
      count: cs.rows.length,
    });
  }

  // ---- Randomiser ---------------------------------------------------------
  // Picks a sensible combo that yields >=10 players, biased toward the more
  // interesting categorical dimensions for variety.
  function randomise() {
    const MIN = 5;
    const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
    const shuffle = (arr) => arr.map((v) => [Math.random(), v]).sort((a, b) => a[0] - b[0]).map((x) => x[1]);
    // Randomiser always operates on Since-Last-WC data
    if (cs.range !== "pre_wc") {
      cs.range = "pre_wc";
      setSeg("cs-range", document.querySelector('#cs-range button[data-v="pre_wc"]'));
    }
    // Randomly choose a discipline and switch the toggle so the stats shown match
    const disc = pick(["batting", "bowling"]);
    if (cs.discipline !== disc) {
      cs.discipline = disc;
      setSeg("cs-discipline", document.querySelector(`#cs-discipline button[data-v="${disc}"]`));
      cs.sortKey = null;
      ensureColState();
    }
    updateFilterLabels();
    updateMinInningsDefault(); // reset min innings to the pre_wc default (10)
    cs.filters = { role: "", type: "", hand: "", country: "" };
    // Bias order toward interesting dimensions first, hand last.
    const dimsOrder = ["type", "role", "country", "hand"];
    let best = null;
    for (let attempt = 0; attempt < 80; attempt++) {
      // choose how many filters this attempt uses: 2, 3, or 4 (weighted toward 2-3)
      const nFilters = pick([2, 2, 2, 3, 3, 4]);
      const chosen = shuffle(dimsOrder).slice(0, nFilters);
      const trial = { role: "", type: "", hand: "", country: "" };
      let ok = true;
      for (const dim of chosen) {
        const opts = filterOptions(dim);
        if (!opts.length) { ok = false; break; }
        trial[dim] = pick(opts).v;
      }
      if (!ok) continue;
      const count = DATA.players.filter((p) => matchesTrial(p, trial)).length;
      if (count >= MIN && count <= 60) { best = trial; break; }
      if (count >= MIN && !best) best = trial; // fallback: any combo with >=5 and >=2 filters
    }
    if (!best) {
      // fallback that still uses two filters: a country + a common role
      best = { role: "Batter", type: "", hand: "", country: pick(COUNTRIES) };
    }
    cs.filters = best;
    updateFilterLabels();
    runFilters();
    if (window.track) track("compare_stats_randomise");
  }
  window.csRandomise = randomise;
  function matchesTrial(p, trial) {
    if (trial.role && !roleMatch(p, trial.role)) return false;
    if (trial.type) {
      if (cs.discipline === "batting") { if (p.role !== trial.type) return false; }
      else { if (p.bowling_type !== trial.type) return false; }
    }
    if (trial.hand) {
      const h = cs.discipline === "batting" ? p.batting_hand : p.bowling_hand;
      if (h !== trial.hand) return false;
    }
    if (trial.country && p.nationality !== trial.country) return false;
    return true;
  }

  // ---- Search -------------------------------------------------------------
  function onSearchInput() {
    const q = document.getElementById("cs-search-input").value.trim().toLowerCase();
    const box = document.getElementById("cs-search-results");
    if (!q) { box.style.display = "none"; box.innerHTML = ""; return; }
    const inTable = new Set(cs.rows.map((p) => p.id));
    const matches = DATA.players
      .filter((p) => p.name.toLowerCase().includes(q) && !inTable.has(p.id))
      .slice(0, 8);
    if (!matches.length) { box.style.display = "none"; box.innerHTML = ""; return; }
    box.innerHTML = matches.map((p) => {
      const c = pal(p).p;
      return `<div class="cs-res" data-id="${p.id}">
        <img class="cs-res-face" src="${p.photo_url}" onerror="this.style.visibility='hidden'">
        ${flagImg(p)}
        <span class="cs-res-nm" style="color:${c}">${p.name}</span>
        <span class="cs-res-meta">${p.nationality}</span>
      </div>`;
    }).join("");
    box.style.display = "block";
    box.querySelectorAll(".cs-res").forEach((el) => {
      el.addEventListener("click", () => {
        const p = DATA.players.find((x) => x.id === el.dataset.id);
        if (p) addPlayer(p);
        document.getElementById("cs-search-input").value = "";
        hideResults();
      });
    });
  }
  function hideResults() {
    const box = document.getElementById("cs-search-results");
    if (box) { box.style.display = "none"; box.innerHTML = ""; }
  }

  // ---- Add / remove rows --------------------------------------------------
  function addPlayer(p) {
    if (cs.rows.some((x) => x.id === p.id)) return;
    cs.rows.unshift(p); // add to the top
    renderTable();
    if (window.track) track("compare_stats_add_player", { player: p.name });
  }
  window.csRemovePlayer = function (id) {
    cs.rows = cs.rows.filter((p) => p.id !== id);
    renderTable();
  };
  window.csResetTable = function () {
    cs.rows = [];
    const d = cs.discipline;
    // reset filters
    cs.filters = { role: "", type: "", hand: "", country: "" };
    updateFilterLabels();
    // reset columns to default: basic shown, advanced hidden, default order, no attrs
    cs.hidden[d] = new Set(activeCols().filter((c) => c.group === "advanced").map((c) => c.key));
    cs.order[d] = activeCols().map((c) => c.key);
    cs.attrCols[d] = new Set();
    cs.attrOrder[d] = ATTR_COLS.map((a) => a.key);
    cs.sortKey = null; cs.sortDir = "desc";
    renderTable();
  };

  // ---- Render table -------------------------------------------------------
  // Build an italicised sentence describing the active filter set.
  function filterSentence() {
    const f = cs.filters;
    const subjects = [];
    if (f.role) subjects.push(f.role + "s");
    if (f.type) {
      const t = cs.discipline === "batting" ? (BAT_TYPE_LABELS[f.type] || f.type) : f.type;
      subjects.push(f.role ? `(${t})` : t + (cs.discipline === "batting" ? " batters" : " bowlers"));
    }
    if (f.hand) {
      const h = f.hand === "LHB" ? "left-hand" : "right-hand";
      subjects.push(cs.discipline === "batting" ? h + " bats" : h + " bowlers");
    }
    // If no role/type/hand, default subject is "players"
    let subject = subjects.length ? subjects.join(", ") : "players";
    if (f.country) subject += " from " + f.country;
    if (!subjects.length && !f.country) return "";
    const disc = cs.discipline === "batting" ? "Batting" : "Bowling";
    return `${disc} stats for ${subject}.`;
  }

  function renderTable() {
    const table = document.getElementById("cs-table");
    const empty = document.getElementById("cs-empty");
    const sent = document.getElementById("cs-sentence");
    if (!table) return;
    ensureColState();

    // active-filter sentence
    if (sent) {
      const txt = cs.rows.length ? filterSentence() : "";
      sent.textContent = txt;
      sent.style.display = txt ? "block" : "none";
    }

    // apply min-innings filter to the displayed rows
    const minInn = cs.minInnings[cs.discipline] || 0;
    const ik = inningsKey();
    let rows = cs.rows.filter((p) => {
      const v = (statsFor(p) || {})[ik];
      return typeof v === "number" ? v >= minInn : minInn === 0;
    });
    rows = sortRows(rows);

    if (!cs.rows.length) {
      table.innerHTML = ""; table.style.display = "none"; empty.style.display = "flex"; return;
    }
    empty.style.display = "none"; table.style.display = "";

    const statCols = visibleStatCols();
    const attrCols = visibleAttrCols();
    const basicCols = statCols.filter((c) => c.group === "basic");
    const advCols = statCols.filter((c) => c.group === "advanced");

    // group header row (hide a group if it has no visible columns)
    let groupRow = `<tr class="cs-grouprow"><th class="cs-col-player"></th>`;
    if (attrCols.length) groupRow += `<th class="cs-group cs-group-attr" colspan="${attrCols.length}"></th>`;
    if (basicCols.length) groupRow += `<th class="cs-group" colspan="${basicCols.length}">Basic Stats</th>`;
    if (advCols.length) groupRow += `<th class="cs-group cs-group-adv" colspan="${advCols.length}">Advanced Stats</th>`;
    groupRow += `</tr>`;

    // ordered list of all visible columns (attrs first, then stats in custom order)
    const allCols = [
      ...attrCols.map((a) => ({ kind: "attr", key: a.key, label: a.label, section: "attr" })),
      ...statCols.map((c) => ({ kind: "stat", key: c.key, label: c.label, col: c, section: c.group })),
    ];

    const sortInd = (key) => cs.sortKey === key ? `<span class="cs-sortind">${cs.sortDir === "asc" ? "▲" : "▼"}</span>` : "";
    const colRow = `<tr>
      <th class="cs-col-player cs-sortable" data-sortkey="name">Player ${sortInd("name")}</th>
      ${allCols.map((c) => {
        const tip = c.kind === "stat" && GLOSS[c.key] ? ` data-tip="${GLOSS[c.key].replace(/"/g, "&quot;")}"` : "";
        return `<th class="cs-sortable cs-draggable" draggable="true" data-sortkey="${c.key}" data-colkey="${c.key}" data-kind="${c.kind}" data-section="${c.section}"${tip}>${c.label} ${sortInd(c.key)}</th>`;
      }).join("")}
    </tr>`;

    const head = `<thead>${groupRow}${colRow}</thead>`;

    const body = `<tbody>${rows.map((p) => {
      const c = pal(p).p;
      const cells = allCols.map((cc) => {
        if (cc.kind === "attr") {
          const a = ATTR_COLS.find((x) => x.key === cc.key);
          return `<td>${a ? (a.get(p) || "—") : "—"}</td>`;
        }
        return `<td>${fmt(colVal(p, cc.col), cc.col.dp)}</td>`;
      }).join("");
      return `<tr>
        <td class="cs-col-player">
          <div class="cs-pl">
            <img class="cs-face" src="${p.photo_url}" onerror="this.style.visibility='hidden'">
            ${flagImg(p)}
            <span class="cs-nm" style="color:${c}">${p.name}</span>
            <span class="cs-pl-sp"></span>
            <button class="cs-rm" title="Remove" onclick="csRemovePlayer('${p.id}')">&#10005;</button>
          </div>
        </td>
        ${cells}
      </tr>`;
    }).join("")}</tbody>`;

    table.innerHTML = head + body;
    wireHeaderInteractions();
  }

  // Click-to-sort + drag-to-reorder (constrained within a section) on headers
  function wireHeaderInteractions() {
    const table = document.getElementById("cs-table");
    if (!table) return;
    let dragKey = null, dragSection = null;
    table.querySelectorAll("th.cs-sortable").forEach((th) => {
      th.addEventListener("click", () => {
        if (th._dragged) { th._dragged = false; return; }
        applySort(th.dataset.sortkey);
      });
    });
    table.querySelectorAll('th.cs-draggable[draggable="true"]').forEach((th) => {
      th.addEventListener("dragstart", (e) => {
        dragKey = th.dataset.colkey; dragSection = th.dataset.section; th._dragged = true;
        e.dataTransfer.effectAllowed = "move";
      });
      th.addEventListener("dragover", (e) => {
        // only allow dropping within the SAME section
        if (th.dataset.section === dragSection) {
          e.preventDefault();
          th.classList.add("cs-dragover");
        }
      });
      th.addEventListener("dragleave", () => th.classList.remove("cs-dragover"));
      th.addEventListener("drop", (e) => {
        e.preventDefault(); th.classList.remove("cs-dragover");
        const targetKey = th.dataset.colkey;
        if (dragKey && targetKey && dragKey !== targetKey && th.dataset.section === dragSection) {
          reorderCol(dragKey, targetKey, dragSection);
        }
        dragKey = null; dragSection = null;
      });
    });
  }
  function reorderCol(fromKey, toKey, section) {
    const d = cs.discipline;
    const arr = section === "attr" ? cs.attrOrder[d] : cs.order[d];
    const fi = arr.indexOf(fromKey), ti = arr.indexOf(toKey);
    if (fi < 0 || ti < 0) return;
    arr.splice(fi, 1);
    arr.splice(ti, 0, fromKey);
    renderTable();
  }

  // ---- Open / close -------------------------------------------------------
  window.openCompareStats = function () {
    buildModal();
    ensureColState();
    updateMinInningsDefault();
    renderTable();
    document.getElementById("cs-backdrop").classList.add("show");
    document.body.classList.add("ov-open");
    if (window.track) track("compare_stats_open");
  };
  window.closeCompareStats = function () {
    const bd = document.getElementById("cs-backdrop");
    if (bd) bd.classList.remove("show");
    document.body.classList.remove("ov-open");
    hideResults();
  };

  // ESC to close
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const bd = document.getElementById("cs-backdrop");
      if (bd && bd.classList.contains("show")) closeCompareStats();
    }
  });
})();
