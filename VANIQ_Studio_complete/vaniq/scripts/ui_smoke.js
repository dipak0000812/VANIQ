// UI smoke test for the P0 linguistic-integrity behaviour. Needs: node 18+, `npm i jsdom`, server running in demo mode with demo data.
//   VANIQ_MODE=demo python -m src.cli serve &  curl -XPOST localhost:8000/api/demo/seed
//   NODE_PATH=/path/to/node_modules node scripts/ui_smoke.js [http://localhost:8000]
const { JSDOM } = require("jsdom");
const base = process.argv[2] || "http://localhost:8000";
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failed = 0;
const check = (name, ok, extra) => { console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : "  -> " + extra)); if (!ok) failed++; };

(async () => {
  const html = await (await fetch(base + "/")).text();
  const js = await (await fetch(base + "/app.js")).text();
  const dom = new JSDOM(html.replace('<script src="app.js"></script>', ""), { runScripts: "outside-only", url: base + "/", pretendToBeVisual: true });
  const w = dom.window; const errs = [];
  w.fetch = (u, o) => fetch(new URL(u, base), o); w.FormData = FormData; w.confirm = () => true;
  w.addEventListener("error", e => errs.push(e.message));
  w.HTMLElement.prototype.scrollIntoView = () => {};
  w.eval(js); await sleep(600);
  const doc = w.document, main = () => doc.getElementById("main");
  doc.getElementById("reviewer").value = "smoke-tester";

  const clips = await (await fetch(base + "/api/clips")).json();
  const open = clips.find(c => c.review_status === "needs_review" && c.transcript_count > 0);
  w.location.hash = "#/workspace/" + open.id; await sleep(1000);

  // 1. no hardcoded lang on transcript boxes
  check("no lang attribute on transcript boxes", ![...main().querySelectorAll(".textbox")].some(e => e.hasAttribute("lang")), "found lang attr");
  // 2. reference empty by default, STT opt-in
  const refTa = main().querySelector('textarea[aria-label="Reference transcript"]');
  check("reference box is empty by default", refTa && refTa.value === "", refTa && refTa.value);
  const showBtn = [...main().querySelectorAll("button")].find(b => b.textContent.startsWith("Show STT transcript"));
  check("STT opt-in button present", !!showBtn);
  const preOpt = main().textContent.includes("Copy original STT into the box");
  showBtn.click(); await sleep(100);
  check("STT hidden until opt-in, shown after", !preOpt && main().textContent.includes("Copy original STT into the box"));
  [...main().querySelectorAll("button")].find(b => b.textContent === "Copy original STT into the box").click();
  check("explicit copy fills the reference box", refTa.value.length > 0);
  // 3. provider-detected language + raw response visible, declared dialect shown separately
  const txt = main().textContent;
  check("provider-detected language shown", txt.includes("Provider-detected language:"));
  check("declared dialect shown separately", txt.includes("Declared dialect of this recording:"));
  check("raw provider response panel present", txt.includes("Provider response (raw JSON"));
  check("provider response JSON rendered", /"demo": true/.test(main().querySelector("details pre").textContent));
  // 5/6. baseline labelling
  check("transcript labelled STT baseline experiment", txt.includes("STT baseline experiment"));
  check("language-code control labelled as baseline setting", txt.includes("STT baseline experiment setting (language code sent to the provider)"));
  check("baseline-not-Ahirani notice", txt.includes("baseline experiment settings, not Ahirani"));
  const opts = [...doc.querySelectorAll("#langs option")].map(o => o.value);
  check("only indic-auto and mr-IN offered", JSON.stringify(opts.sort()) === JSON.stringify(["indic-auto", "mr-IN"]), opts);
  check("button says baseline", [...main().querySelectorAll("button")].some(b => /baseline|demo placeholder/i.test(b.textContent)));
  // reference verify sends stt_viewed
  let sent = null; const realFetch = w.fetch;
  w.fetch = (u, o) => { if (String(u).endsWith("/verify")) sent = JSON.parse(o.body); return realFetch(u, o); };
  refTa.value = "smoke reference";
  [...main().querySelectorAll("button")].find(b => b.textContent === "Verify as reference").click(); await sleep(800);
  check("verify payload carries stt_viewed=true after opt-in", sent && sent.stt_viewed === true, JSON.stringify(sent));

  // evaluation: per-role groups and claim notice
  w.fetch = realFetch;
  w.location.hash = "#/evaluation"; await sleep(500);
  [...main().querySelectorAll("button")].find(b => b.textContent === "Run evaluation").click(); await sleep(1200);
  const ev = main().textContent;
  check("evaluation: Ahirani claim notice", ev.includes("Ahirani performance claim: not allowed"));
  check("evaluation: baseline group heading", /STT baseline experiment \(not Ahirani performance\) \(n = \d+\)/.test(ev));
  check("evaluation: no unlabeled 'Before vs after' table", !ev.includes("Before vs after corrections"));
  check("no JS errors", errs.length === 0, errs.join("; "));
  console.log(failed ? `\n${failed} check(s) FAILED` : "\nAll UI checks passed");
  process.exit(failed ? 1 : 0);
})();
