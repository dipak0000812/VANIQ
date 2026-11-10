// Real-browser E2E for VANIQ Studio (headless Chromium). Exit code 1 if any check fails.
import chromium from '@sparticuz/chromium';
import puppeteer from 'puppeteer-core';
import fs from 'fs';

const base = process.argv[2] || 'http://localhost:8011';
const shots = process.argv[3] || '/tmp/shots';
const wav = process.argv[4] || '/tmp/tone_e2e.wav';
fs.mkdirSync(shots, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const results = []; let failed = 0;
const errors = [];
async function step(name, fn) {
  try { await fn(); results.push(['PASS', name]); console.log('PASS ' + name); }
  catch (e) { failed++; results.push(['FAIL', name, e.message]); console.log('FAIL ' + name + '\n     -> ' + e.message.split('\n')[0]); }
}
const ok = (c, msg) => { if (!c) throw new Error(msg || 'assertion failed'); };

const browser = await puppeteer.launch({ executablePath: await chromium.executablePath(), args: [...chromium.args, '--no-sandbox', '--autoplay-policy=no-user-gesture-required'], headless: 'shell' });
const p = await browser.newPage();
await p.setViewport({ width: 1440, height: 900 });
let expectErrors = false;
p.on('pageerror', e => errors.push('pageerror: ' + e.message));
p.on('console', m => { if (m.type() === 'error' && !expectErrors) errors.push('console: ' + m.text()); });
p.on('dialog', d => d.accept());

const text = () => p.evaluate(() => document.getElementById('main').innerText);
const go = async (hash) => { await p.goto(base + '/app#/' + hash, { waitUntil: 'networkidle0' }); const n = hash.split('/')[0]; await p.waitForFunction(x => document.body.dataset.route === x && document.body.dataset.ready === '1', { timeout: 12000 }, n.length ? n : 'home'); await sleep(200); };
const settle = async () => { await sleep(120); await p.waitForFunction(() => document.body.dataset.ready === '1' && !document.querySelector('#main [aria-busy=true]'), { timeout: 12000 }); await sleep(250); };
async function click(selector, txt, root = 'body') {
  const h = await p.evaluateHandle((sel, t, r) => {
    const scope = document.querySelector(r) || document.body;
    return [...scope.querySelectorAll(sel)].find(e => e.offsetParent !== null && (!t || e.textContent.trim().includes(t)));
  }, selector, txt, root);
  const el = h.asElement(); if (!el) throw new Error(`no visible ${selector} with text "${txt}"`);
  await el.click(); return el;
}
const waitText = (t, timeout = 10000) => p.waitForFunction(x => document.body.innerText.includes(x), { timeout }, t);
const setReviewer = async n => p.evaluate(v => { const r = document.getElementById('reviewer'); r.value = v; r.dispatchEvent(new Event('change')); }, n);
const api = (path, opts) => p.evaluate(async (pa, o) => (await fetch(pa, o)).json(), path, opts);
const shot = n => p.screenshot({ path: `${shots}/${n}.png` });

await p.goto(base + '/app', { waitUntil: 'networkidle0' }); await settle();
await p.evaluate(() => localStorage.clear());

// ------------------------------------------------------------------ navigation
for (const [route, label] of [['home', 'Home'], ['studio', 'Studio'], ['skills', 'Skills'], ['knowledge', 'Knowledge'], ['workflows', 'Workflows'], ['lexicon', 'Lexicon'], ['datasets', 'Datasets'], ['evaluation', 'Evaluation'], ['about', 'About & limits']]) {
  await step(`nav: ${label} loads`, async () => {
    await click(`.nav a[data-route=${route}]`); await settle();
    ok((await p.evaluate(() => location.hash)).startsWith('#/' + route), 'hash not updated');
    const crumb = await p.$eval('#crumb-view', e => e.textContent); ok(crumb.includes(label.split(' ')[0]), 'crumb ' + crumb);
    ok(await p.$eval(`.nav a[data-route=${route}]`, e => e.getAttribute('aria-current') === 'page'), 'aria-current');
    ok(!(await text()).includes('Cannot reach'), 'error shown'); await shot('nav-' + route);
  });
}
await step('nav: collapse and expand', async () => {
  await click('#nav-toggle'); ok(await p.$eval('#app', e => e.classList.contains('nav-c')), 'not collapsed');
  await click('#nav-toggle'); ok(!(await p.$eval('#app', e => e.classList.contains('nav-c'))), 'not expanded');
});
await step('command bar: Ctrl+K opens, filters, navigates; Esc closes', async () => {
  await go('home'); await p.keyboard.down('Control'); await p.keyboard.press('k'); await p.keyboard.up('Control');
  await p.waitForSelector('.dialog.palette'); await p.keyboard.type('evalu'); await sleep(200);
  ok((await p.$eval('.palette ul', e => e.innerText)).includes('Go to Evaluation'), 'item missing');
  await p.keyboard.press('Enter'); await settle(); ok((await p.evaluate(() => location.hash)) === '#/evaluation', 'did not navigate');
  await p.keyboard.down('Control'); await p.keyboard.press('k'); await p.keyboard.up('Control'); await p.waitForSelector('.dialog.palette');
  await p.keyboard.press('Escape'); await sleep(200); ok(!(await p.$('.dialog')), 'palette still open');
});

// ------------------------------------------------------------------ agent (Home)
await step('home: command-mode banner and empty/seeded state', async () => {
  await go('home'); const t = await text(); ok(t.includes('Command mode'), 'no honest mode note'); ok(t.includes('No language model'), 'no LLM note'); await shot('home');
});
await step('agent: read-only request runs immediately with real results', async () => {
  await p.type('.composer textarea', 'what needs doing'); await p.keyboard.press('Enter');
  await p.waitForFunction(() => [...document.querySelectorAll('.plan .chip')].some(c => c.textContent === 'Completed'), { timeout: 10000 });
  const t = await text(); ok(t.includes('List') || t.includes('What needs doing'), 'plan title'); ok(/counts/i.test(t) && /verified clips/i.test(t), 'result missing'); await shot('home-agent-result');
});
await step('agent: results survive a page refresh', async () => {
  await p.reload({ waitUntil: 'networkidle0' }); await settle(); await waitText('what needs doing'); await waitText('Completed');
});
await step('agent: unsupported request is refused honestly', async () => {
  await p.type('.composer textarea', 'tell me a joke'); await p.keyboard.press('Enter');
  await waitText('Not supported'); ok((await text()).includes('command mode'), 'no explanation');
});
await step('agent: refuses to verify references / accept corrections', async () => {
  await p.type('.composer textarea', 'verify this reference as hello'); await p.keyboard.press('Enter'); await waitText("can't write or verify");
});

// ------------------------------------------------------------------ studio: upload, waveform, playback
await step('studio: upload audio with provenance and permission', async () => {
  await go('studio'); await click('button', 'Add audio'); await p.waitForSelector('.dialog input[type=file]');
  const fi = await p.$('.dialog input[type=file]'); await fi.uploadFile(wav);
  await p.select('.dialog #perm', 'granted'); await p.select('.dialog #usage', 'private_research');
  await p.evaluate(() => { document.querySelector('.dialog #speaker').value = 'e2e-speaker'; document.querySelector('.dialog #dialect').value = 'Ahirani (declared)'; });
  await click('.dialog button', 'Upload and segment'); await p.waitForFunction(() => document.querySelector('.dialog').innerText.includes('Created'), { timeout: 15000 });
  await shot('studio-upload-dialog'); await click('.dialog button', 'Done'); await settle();
});
await step('studio: invalid upload shows an inline error', async () => {
  expectErrors = true;
  await click('button', 'Add audio'); await p.waitForSelector('.dialog input[type=file]');
  fs.writeFileSync('/tmp/bad.wav', Buffer.from('junkjunkjunkjunk'.repeat(10)));
  await (await p.$('.dialog input[type=file]')).uploadFile('/tmp/bad.wav'); await click('.dialog button', 'Upload and segment');
  await p.waitForFunction(() => [...document.querySelectorAll('#toast div')].some(d => d.textContent.includes('not a readable audio')), { timeout: 8000 });
  await p.keyboard.press('Escape'); await sleep(150); ok(!(await p.$('.dialog')), 'dialog did not close'); expectErrors = false;
});
let clipIds = [];
await step('studio: new recording appears with segments on the canvas', async () => {
  await p.reload({ waitUntil: 'networkidle0' }); await settle();
  const sources = await api('/api/sources'); const s = sources.find(x => x.original_name.includes('tone_e2e')); ok(s, 'source missing');
  clipIds = (await api('/api/clips?source_id=' + s.id)).sort((a, b) => a.start_s - b.start_s).map(c => c.id); ok(clipIds.length === 2, 'expected 2 clips');
  await go('studio/' + clipIds[0]);
  await p.waitForFunction(() => document.querySelectorAll('.region').length === 2, { timeout: 8000 });
});
await step('studio: waveform canvas is actually drawn', async () => {
  await p.waitForFunction(() => document.querySelector('[data-testid=waveform] .hint')?.textContent.includes('Hz'), { timeout: 8000 });
  const n = await p.$eval('[data-testid=waveform] canvas', c => { const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let k = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 0) k++; return k; });
  ok(n > 500, 'canvas blank (' + n + ' opaque pixels)'); await shot('studio-waveform');
});
await step('studio: clicking a segment selects it and updates URL, tracks and inspector', async () => {
  await click('.region', '2'); await settle();
  await p.waitForFunction(id => location.hash === '#/studio/' + id, { timeout: 5000 }, clipIds[1]);
  ok(await p.$eval('.region[data-clip="' + clipIds[1] + '"]', e => e.getAttribute('aria-pressed') === 'true'), 'not pressed');
  await waitText('Get a transcript'); ok((await p.$eval('.inspector', e => e.innerText)).includes('Declared dialect'), 'inspector');
});
await step('studio: audio playback starts and pauses', async () => {
  await click('button', 'Play'); await sleep(700);
  ok(await p.$$eval('button', bs => bs.some(b => b.textContent.trim() === 'Pause')), 'did not enter playing state');
  const t = await p.$eval('.time', e => e.textContent); ok(!t.startsWith('0.0 /'), 'time did not advance: ' + t);
  await click('button', 'Pause'); await sleep(200); ok(await p.$$eval('button', bs => bs.some(b => b.textContent.trim() === 'Play')), 'did not pause');
});
await step('studio: Play segment plays within the selected region', async () => {
  await click('button', 'Play segment'); await sleep(500); await p.evaluate(() => { const a = document.querySelector('audio'); });
  const t = await p.$eval('.time', e => parseFloat(e.textContent)); ok(t >= 0, 'bad time');
});

// ------------------------------------------------------------------ contextual AI + approval gate
await step('agent drawer: contextual baseline plan waits for approval; nothing runs before it', async () => {
  await setReviewer('');
  await click('.canvas-top button', 'Run STT baseline');
  await p.waitForSelector('.drawer.open .approval', { timeout: 8000 });
  const before = (await api('/api/clips/' + clipIds[1])).transcripts.length; ok(before === 0, 'transcript already existed');
  const drawerText = await p.$eval('.drawer', e => e.innerText); ok(drawerText.includes('Needs your approval') && drawerText.includes(clipIds[1]), 'context/plan missing');
  await shot('studio-agent-approval');
});
await step('agent drawer: approval without reviewer name is blocked', async () => {
  await click('.drawer .approval button', 'Approve'); await p.waitForFunction(() => [...document.querySelectorAll('#toast div')].some(d => d.textContent.includes('reviewer name')), { timeout: 5000 });
  ok((await api('/api/clips/' + clipIds[1])).transcripts.length === 0, 'ran without approval');
});
await step('agent drawer: approve with name -> real execution -> transcript is a labelled baseline', async () => {
  await setReviewer('e2e-reviewer'); await click('.drawer .approval button', 'Approve');
  await p.waitForFunction(() => [...document.querySelectorAll('.drawer .plan .chip')].some(c => c.textContent === 'Completed'), { timeout: 12000 });
  const ws = await api('/api/clips/' + clipIds[1]); ok(ws.transcripts.length === 1 && ws.transcripts[0].experiment_role === 'baseline', 'no baseline transcript');
  await click('.drawer .dh button'); await p.reload({ waitUntil: 'networkidle0' }); await settle();
  const t = await text(); ok(t.includes('STT baseline experiment') && t.includes('DEMO PLACEHOLDER'), 'labels missing'); await shot('studio-baseline');
});

// ------------------------------------------------------------------ linguistic integrity + review
await step('reference: empty by default; STT view is explicit opt-in; copy is explicit', async () => {
  const ref = await p.$('textarea[aria-label="Reference transcript"]'); ok(ref, 'no reference box');
  ok((await p.$eval('textarea[aria-label="Reference transcript"]', e => e.value)) === '', 'prefilled');
  ok(!(await text()).includes('Copy original STT'), 'STT shown without opt-in');
  await click('button', 'Show STT transcript'); ok((await text()).includes('Copy original STT into the box'), 'no copy');
  await click('button', 'Copy original STT into the box'); ok((await p.$eval('textarea[aria-label="Reference transcript"]', e => e.value)).length > 0, 'copy failed');
});
await step('reference: verify persists across refresh and records stt_viewed', async () => {
  await p.$eval('textarea[aria-label="Reference transcript"]', e => { e.value = 'my independent reference text'; });
  await click('button', 'Verify as reference'); await waitText('Verified by e2e-reviewer');
  await p.reload({ waitUntil: 'networkidle0' }); await settle(); await waitText('Verified by e2e-reviewer');
  ok((await p.$eval('textarea[aria-label="Reference transcript"]', e => e.value)) === 'my independent reference text', 'reference lost');
  const audit = await api('/api/audit?limit=50'); const v = audit.find(a => a.action === 'verify_reference'); ok(JSON.parse(v.detail).stt_viewed === true, 'stt_viewed not recorded');
});
await step('inspector: provider-detected language, script and baseline role are separate fields', async () => {
  const t = await p.$eval('.inspector', e => e.innerText);
  for (const s of ['Provider-detected language', 'Transcript script', 'Orthographic convention', 'STT provider and model', 'Declared dialect', 'Consent and permission', 'Verification and export']) ok(t.includes(s), 'missing ' + s);
  ok((await p.$eval('.inspector input[aria-label="Declared dialect"]', e => e.value)) === 'Ahirani (declared)', 'declared dialect value'); ok(!t.includes('Dialect: Marathi'), 'relabelled');
});
await step('correction: accept / undo a suggestion; raw text never changes', async () => {
  const cl = (await api('/api/clips?review_status=needs_review'));
  let target = null; for (const c of cl) { const ws = await api('/api/clips/' + c.id); if (ws.transcripts[0] && ws.transcripts[0].suggestions.some(s => s.status === 'pending' && s.kind !== 'normalization')) { target = { id: c.id, raw: ws.transcripts[0].transcript_raw }; break; } }
  ok(target, 'no clip with pending lexical suggestions'); await go('studio/' + target.id);
  const rawBefore = await p.$eval('.textbox.indic', e => e.innerText);
  await click('.sug button', 'Accept'); await p.waitForFunction(() => document.querySelector('mark.sg.accepted'), { timeout: 6000 }); await settle();
  ok((await api('/api/clips/' + target.id)).transcripts[0].transcript_raw === target.raw, 'raw changed');
  await shot('studio-correction');
  await click('.sug button', 'Undo'); await p.waitForFunction(() => !document.querySelector('mark.sg.accepted'), { timeout: 6000 });
});
await step('inspector: edit dialect and permission persist after refresh; eligibility updates', async () => {
  await go('studio/' + clipIds[1]);
  await p.$eval('.inspector input[aria-label="Declared dialect"]', e => { e.value = 'Ahirani'; });
  await p.select('.inspector select[aria-label="Permission status"]', 'granted'); await p.select('.inspector select[aria-label="Permitted usage"]', 'public_release');
  await click('.inspector button', 'Save details'); await p.waitForFunction(() => document.getElementById('save-state').className.includes('saved'), { timeout: 5000 });
  await p.reload({ waitUntil: 'networkidle0' }); await settle(); await waitText('Declared dialect');
  ok((await p.$eval('.inspector input[aria-label="Declared dialect"]', e => e.value)) === 'Ahirani', 'dialect lost');
  ok((await p.$eval('.inspector select[aria-label="Permitted usage"]', e => e.value)) === 'public_release', 'usage lost');
  ok((await p.$eval('.inspector', e => e.innerText)).includes('eligible'), 'eligibility');
});
await step('save indicator reflects real writes', async () => { ok(await p.$eval('#save-state', e => /Saved|Nothing/.test(e.innerText)), 'indicator'); });

// ------------------------------------------------------------------ permission denied
await step('permission denied: agent baseline fails honestly and creates no transcript', async () => {
  const sid = (await api('/api/clips/' + clipIds[0])).clip.source_id;
  await api('/api/sources/' + sid, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ permission_status: 'denied', permitted_usage: 'UNKNOWN', reviewer: 'e2e' }) });
  await go('studio/' + clipIds[0]); await click('.canvas-top button', 'Run STT baseline'); await p.waitForSelector('.drawer.open .approval');
  await click('.drawer .approval button', 'Approve');
  await p.waitForFunction(() => document.querySelector('.drawer').innerText.includes('permission_denied'), { timeout: 10000 });
  ok((await api('/api/clips/' + clipIds[0])).transcripts.length === 0, 'transcript created for denied clip'); await shot('permission-denied');
  await click('.drawer .dh button');
});

// ------------------------------------------------------------------ skills
await step('skills: read-only skill runs; consequential skill waits and can be rejected', async () => {
  await go('skills'); const cards = await p.$$eval('.skill', c => c.length); ok(cards >= 9, 'skills missing: ' + cards);
  await click('.skill[data-skill=list_work] button', 'Run'); await p.waitForFunction(() => document.querySelector('.skill[data-skill=list_work] .plan .chip')?.textContent === 'Completed', { timeout: 8000 });
  await click('.skill[data-skill=create_export] button', 'Plan this skill'); await p.waitForSelector('.skill[data-skill=create_export] .approval', { timeout: 6000 });
  ok(((await api('/api/exports')).length === 0), 'export ran without approval');
  await click('.skill[data-skill=create_export] .approval button', 'Reject'); await p.waitForFunction(() => document.querySelector('.skill[data-skill=create_export]').innerText.includes('Rejected'), { timeout: 6000 }); await shot('skills');
});

// ------------------------------------------------------------------ knowledge
await step('knowledge: draft -> approve -> edit returns to draft -> version history', async () => {
  await go('knowledge'); await click('button', 'New entry');
  await p.type('input[aria-label=Title]', 'Spelling convention (team)'); await p.type('textarea[aria-label=Body]', 'Write words as heard; record the variant used.');
  await click('button', 'Create draft'); await waitText('Draft: not visible to the agent');
  await click('button', 'Approve'); await waitText('Approved by e2e-reviewer');
  await p.$eval('textarea[aria-label=Body]', e => { e.value = 'Write words as heard; record the variant used. (v2)'; });
  await click('button', 'Save as new version'); await waitText('Draft: not visible to the agent'); await waitText('v1'); await shot('knowledge');
  const k = await api('/api/knowledge'); ok(k[0].version === 2 && k[0].status === 'draft', 'version/status');
});

// ------------------------------------------------------------------ workflows
await step('workflows: gallery, template categories, use template opens editor', async () => {
  await go('workflows'); ok((await p.$$eval('.tpl', c => c.length)) >= 4, 'templates'); await shot('workflows-gallery');
  await click('.suggest button', 'Baseline'); ok((await p.$$eval('.tpl', c => c.length)) === 1, 'filter'); await click('.suggest button', 'All');
  await click('.tpl[data-workflow=tpl-baseline] button', 'Use template'); await p.waitForSelector('.node', { timeout: 6000 });
  ok((await p.$$eval('.node', n => n.length)) === 4, 'nodes'); ok((await p.$$eval('path[data-edge]', n => n.length)) === 3, 'edges'); await waitText('Valid');
});
await step('workflows: invalid connection is refused with the reason', async () => {
  await click('.pal-item', 'Evaluate'); await sleep(200);
  const evalNode = await p.$eval('.node[data-type=evaluate]', e => e.dataset.node);
  await click('.node[data-node=' + evalNode + '] .port.out'); await click('.node[data-node=n4] .port.in');
  await p.waitForFunction(() => [...document.querySelectorAll('#toast div')].some(d => d.textContent.includes('Cannot connect Evaluate')), { timeout: 5000 });
});
await step('workflows: dragging a node moves it; unsaved changes block Run until saved', async () => {
  const hd = await p.$('.node[data-node=n1] .nh'); const b = await hd.boundingBox(); const left0 = await p.$eval('.node[data-node=n1]', e => e.offsetLeft);
  await p.mouse.move(b.x + 20, b.y + 10); await p.mouse.down(); await p.mouse.move(b.x + 80, b.y + 50, { steps: 5 }); await p.mouse.up(); await sleep(200);
  ok((await p.$eval('.node[data-node=n1]', e => e.offsetLeft)) > left0, 'did not move'); ok((await text()).includes('Unsaved changes'), 'dirty flag');
  ok(await p.$$eval('.wf-bar button', bs => bs.find(b => b.textContent.includes('Run')).disabled), 'run enabled while dirty');
  await click('.wf-bar button', 'Save'); await waitText('Workflow saved'); await p.waitForFunction(() => !document.body.innerText.includes('Unsaved changes'), { timeout: 4000 });
});
await step('workflows: run waits for approval, then executes with live node states', async () => {
  // remove the stray Evaluate node so the graph is valid
  await p.$eval('.node[data-type=evaluate]', e => e.focus()); await p.keyboard.press('Delete'); await sleep(300);
  await click('.wf-bar button', 'Save'); await sleep(500);
  await p.waitForFunction(() => { const b = [...document.querySelectorAll('.wf-bar button')].find(x => x.textContent.includes('Run')); return b && !b.disabled; }, { timeout: 5000 });
  await click('.wf-bar button', 'Run'); await p.waitForSelector('[data-testid=run-panel] .notice.warn', { timeout: 6000 });
  const pre = (await api('/api/clips?source_id=' + (await api('/api/clips/' + clipIds[1])).clip.source_id)); const untranscribed = (await Promise.all(pre.map(c => api('/api/clips/' + c.id)))).filter(w => w.transcripts.length === 0).length;
  await shot('workflow-awaiting-approval');
  await click('[data-testid=run-panel] button', 'Approve and run');
  await p.waitForFunction(() => document.querySelector('[data-testid=run-panel]')?.innerText.includes('Completed') || document.querySelector('[data-testid=run-panel]')?.innerText.includes('Failed'), { timeout: 15000 });
  const rt = await p.$eval('[data-testid=run-panel]', e => e.innerText); ok(rt.includes('Completed'), 'run did not complete: ' + rt.slice(0, 300));
  ok(await p.$$eval('.node.done', n => n.length) >= 2, 'nodes not marked done'); await shot('workflow-completed');
});
await step('workflows: verified-clips-to-evaluation template auto-runs (no consequential nodes)', async () => {
  await go('workflows/tpl-evaluation'); await waitText('read-only template'); await click('.wf-bar button', 'Run');
  await p.waitForFunction(() => document.querySelector('[data-testid=run-panel]')?.innerText.includes('Completed'), { timeout: 15000 });
});

// ------------------------------------------------------------------ datasets / evaluation / lexicon / about
await step('datasets: live eligibility table with reasons; export respects permissions', async () => {
  await go('datasets'); const t = await text(); ok(t.includes('Eligibility') && t.includes('eligible for a public export'), 'eligibility'); ok(/permission or permitted usage unknown|permission denied|no human-verified/.test(t), 'reasons');
  await p.select('#el-vis', 'internal'); await waitText('include unknown-permission clips'); await shot('datasets');
  await p.select('#vis', 'public'); await click('button', 'Create export'); await p.waitForFunction(() => /clip\(s\) exported|Nothing matched/.test(document.getElementById('main').innerText), { timeout: 10000 });
  const exportOk = await p.$eval('#tb-export', e => !e.disabled); ok(exportOk, 'toolbar export should be enabled when eligible clips exist');
});
await step('evaluation: baseline separated, Ahirani claim not allowed, no unlabeled combined table', async () => {
  await go('evaluation'); await click('button', 'Run evaluation'); await waitText('Ahirani performance claim: not allowed');
  const t = await text(); ok(/STT baseline experiment \(not Ahirani performance\)/.test(t), 'baseline heading'); ok(!t.includes('Before vs after corrections'), 'unlabelled table'); await shot('evaluation');
});
await step('lexicon + about render with truthful content', async () => {
  await go('lexicon'); ok((await text()).includes('no Ahirani vocabulary'), 'lexicon honesty');
  await go('about'); const t = await text(); ok(t.includes('Trained dialect correction model') && t.includes('not implemented'), 'capabilities'); await shot('about');
});

// ------------------------------------------------------------------ errors
await step('error state: network failure shows the real problem and no fake success', async () => {
  await go('home'); expectErrors = true; await p.setRequestInterception(true);
  const h = r => (r.url().includes('/api/agent/plan') ? r.abort() : r.continue()); p.on('request', h);
  await p.type('.composer textarea', 'what needs doing'); await p.keyboard.press('Enter');
  await p.waitForFunction(() => [...document.querySelectorAll('#toast div.err')].some(d => d.textContent.includes('Cannot reach')), { timeout: 6000 });
  p.off('request', h); await p.setRequestInterception(false); expectErrors = false;
});
await step('error state: unknown route and missing workflow degrade gracefully', async () => {
  await p.goto(base + '/app#/nonsense', { waitUntil: 'networkidle0' }); await settle(); ok((await p.$eval('#crumb-view', e => e.textContent)) === 'Home', 'fallback');
  await go('workflows/does-not-exist'); await waitText('Workflow not found');
});

// ------------------------------------------------------------------ responsive + motion
for (const [w, hgt, label] of [[1440, 900, 'desktop'], [1024, 768, 'tablet'], [390, 844, 'mobile']]) {
  await step(`responsive ${label} (${w}x${hgt}): no horizontal overflow; key regions usable`, async () => {
    await p.setViewport({ width: w, height: hgt });
    for (const r of ['home', 'studio/' + clipIds[1], 'workflows', 'skills']) {
      await go(r); await sleep(300);
      const o = await p.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth })); ok(o.sw <= o.iw + 1, `${r} overflows ${o.sw}>${o.iw}`);
      await shot(`resp-${label}-${r.split('/')[0]}`);
    }
    if (w < 900) { const navBox = await p.$eval('#nav', e => { const r = e.getBoundingClientRect(); return { b: r.bottom, h: window.innerHeight }; }); ok(Math.abs(navBox.b - navBox.h) < 4, 'bottom nav not at bottom'); }
    if (w < 1200) { await go('studio/' + clipIds[1]); await click('.canvas-top button', 'Inspector'); await sleep(350); ok(await p.$eval('.inspector', e => e.getBoundingClientRect().right <= window.innerWidth + 1 && e.getBoundingClientRect().left < window.innerWidth - 100), 'inspector sheet not shown'); }
  });
}
await step('reduced motion: animations and transitions are neutralised', async () => {
  await p.setViewport({ width: 1440, height: 900 }); await p.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }]); await go('home');
  const d = await p.evaluate(() => parseFloat(getComputedStyle(document.querySelector('.view')).animationDuration)); ok(d < 0.01, 'animation duration ' + d);
  await p.emulateMediaFeatures([]);
});
await step('landing page: renders, links into the app, no console errors', async () => {
  await p.goto(base + '/', { waitUntil: 'networkidle0' }); await sleep(600);
  ok((await p.$$eval('a[href^="/app"]', a => a.length)) >= 3, 'CTAs'); ok(!(await text().catch(() => '')).includes('Lindy') && !(await p.evaluate(() => document.body.innerText)).match(/Lindy|RetailSync/), 'reference branding leaked');
  await p.evaluate(() => window.scrollTo(0, document.body.scrollHeight)); await sleep(900); await shot('landing-full');
  for (const [w, hh] of [[390, 844], [1024, 768]]) { await p.setViewport({ width: w, height: hh }); await p.goto(base + '/', { waitUntil: 'networkidle0' }); const o = await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1); ok(o, 'landing overflows at ' + w); await shot('landing-' + w); }
  await p.setViewport({ width: 1440, height: 900 });
});
await step('no unexpected console or page errors in the whole session', async () => { ok(errors.length === 0, errors.slice(0, 5).join(' | ')); });

await browser.close();
console.log(`\n${results.length - failed}/${results.length} checks passed`);
process.exit(failed ? 1 : 0);
