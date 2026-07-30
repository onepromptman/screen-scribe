// Offline behavioral test of the REAL Code-node jsCode from the generated
// workflows, run through a minimal n8n mock. Tests the deterministic logic
// (SOURCE parse, template render, ATS request builders). Does NOT test the live
// model call or Google/Slack/ATS HTTP I/O (those need the n8n UI + creds).
const fs = require('fs');

const path = require('path');
const PKG = path.resolve(__dirname, '..');
const A3 = JSON.parse(fs.readFileSync(`${PKG}/templates/A3-endtoend-ats.template.json`, 'utf8'));
const sampleEnriched = JSON.parse(fs.readFileSync(`${PKG}/tools/sample-enriched.json`, 'utf8'));

const codeOf = (wf, name) => {
  const n = wf.nodes.find(n => n.name === name);
  if (!n || !n.parameters.jsCode) throw new Error('no jsCode for ' + name);
  return n.parameters.jsCode;
};
const setConfigOut = (wf) => {
  const n = wf.nodes.find(n => n.name === 'Set Config');
  const out = {};
  for (const a of n.parameters.assignments.assignments) out[a.name] = a.value;
  return out;
};

const $now = { toISO: () => '2026-07-16T12:00:00.000Z', toISODate: () => '2026-07-16' };
function runCode(code, currentItem, store) {
  const $input = { first: () => ({ json: currentItem }), all: () => [{ json: currentItem }] };
  const $ = (name) => {
    if (!(name in store)) throw new Error('$(' + name + ') not in store');
    return { first: () => ({ json: store[name] }), item: { json: store[name] } };
  };
  const fn = new Function('$input', '$', '$now', code);
  return fn($input, $, $now).json;
}

let pass = 0, fail = 0;
const check = (cond, msg) => { if (cond) { pass++; } else { fail++; console.log('  FAIL:', msg); } };

function runPipeline(atsProvider) {
  const store = {};
  const cfg = setConfigOut(A3);
  cfg.ats_provider = atsProvider;                 // exercise both providers
  store['Set Config'] = cfg;
  store['Fetch Notes (SOURCE)'] = runCode(codeOf(A3, 'Fetch Notes (SOURCE)'), cfg, store);
  store['Resolve Context (RESOLVE)'] = runCode(codeOf(A3, 'Resolve Context (RESOLVE)'), store['Fetch Notes (SOURCE)'], store);
  // simulate the enrich stage output (Parse Enrich Output returns {...ctx, enriched})
  store['Parse Enrich Output'] = { ...store['Resolve Context (RESOLVE)'], enriched: sampleEnriched };
  store['Format Screen (FORMAT)'] = runCode(codeOf(A3, 'Format Screen (FORMAT)'), store['Parse Enrich Output'], store);
  store['Create Doc'] = { id: 'DOCTEST123' };     // simulate Google Docs create
  store['Build ATS Lookup'] = runCode(codeOf(A3, 'Build ATS Lookup'), store['Format Screen (FORMAT)'], store);
  const afterLookup = { ...store['Build ATS Lookup'], ats_candidate_id: 'CAND999' };
  store['Build ATS Note'] = runCode(codeOf(A3, 'Build ATS Note'), afterLookup, store);
  store['Dry Run Preview'] = runCode(codeOf(A3, 'Dry Run Preview'), store['Format Screen (FORMAT)'], store);
  return store;
}

// ---- ASHBY path ----
console.log('== A3 pipeline (ashby) ==');
let s = runPipeline('ashby');
const fmt = s['Format Screen (FORMAT)'];
check(typeof fmt.doc_title === 'string' && fmt.doc_title.includes('Jordan Rivera'), 'doc_title has candidate');
check(fmt.doc_body_markdown.includes('# Recruiter Screen: Jordan Rivera'), 'doc heading rendered');
check(fmt.doc_body_markdown.includes('## Standard screen questions'), 'standard questions section rendered');
const leftovers = fmt.doc_body_markdown.match(/\{\{[^}]+\}\}/g);
check(!leftovers, 'no unrendered {{ }} placeholders remain' + (leftovers ? ' -> ' + JSON.stringify([...new Set(leftovers)]) : ''));
check((fmt.doc_body_markdown.match(/### /g) || []).length >= 8, 'all 8 question subheads rendered');
check(fmt.doc_body_markdown.includes('advance'), 'recommendation rendered');
const lk = s['Build ATS Lookup'].ats_lookup;
check(lk.method === 'POST' && lk.url === 'https://api.ashbyhq.com/candidate.search', 'ashby lookup url/method');
check(lk.body && lk.body.email === 'jordan.rivera@example.com', 'ashby lookup email');
const nt = s['Build ATS Note'].ats_note;
check(nt.url === 'https://api.ashbyhq.com/candidate.createNote', 'ashby note url');
check(nt.body.candidateId === 'CAND999' && typeof nt.body.note === 'string' && nt.body.note.includes('DOCTEST123'), 'ashby note body has candidateId + doc link');
check(s['Dry Run Preview'].dry_run === true && !!s['Dry Run Preview'].would_ats_add_note, 'dry-run preview builds ats request');

// ---- LEVER path ----
console.log('== A3 pipeline (lever) ==');
s = runPipeline('lever');
const lk2 = s['Build ATS Lookup'].ats_lookup;
check(lk2.method === 'GET' && lk2.url.startsWith('https://api.lever.co/v1/opportunities?email='), 'lever lookup url/method');
check(lk2.url.includes('jordan.rivera%40example.com'), 'lever lookup email url-encoded');
const nt2 = s['Build ATS Note'].ats_note;
check(nt2.url === 'https://api.lever.co/v1/opportunities/CAND999/notes', 'lever note url has candidate id');
check(typeof nt2.body.value === 'string' && nt2.body.value.includes('DOCTEST123'), 'lever note body.value has doc link');

// ---- A1/A2 deterministic fallback (no enriched -> Format must still render) ----
console.log('== Format fallback (no model / A1 path) ==');
{
  const store = {};
  const cfg = setConfigOut(A3);
  store['Set Config'] = cfg;
  store['Fetch Notes (SOURCE)'] = runCode(codeOf(A3, 'Fetch Notes (SOURCE)'), cfg, store);
  // no 'enriched' key -> Format builds a deterministic object from notes
  const out = runCode(codeOf(A3, 'Format Screen (FORMAT)'), store['Fetch Notes (SOURCE)'], store);
  check(typeof out.doc_body_markdown === 'string' && out.doc_body_markdown.length > 20, 'fallback renders a body');
  check(out.screen_output && out.screen_output.recommendation === 'maybe', 'fallback default recommendation');
  check(out.doc_body_markdown.includes('Jordan Rivera'), 'fallback uses candidate from config');
}

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
