// Offline behavioral test of the analyst profile's Word renderer. Covers the
// two hard stops documented in docs/ANALYST-PROFILE.md ("it will not render a
// report whose flagged content was never withheld" / "it will not render a
// pre-filled recommendation"), the shape check, and the happy path.
//
// Needs `npm install` (the docx dependency). Everything here is offline.
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const PKG = path.resolve(__dirname, '..');
const RENDERER = path.join(PKG, 'tools', 'render_docx.js');
const SAMPLE = path.join(PKG, 'tools', 'sample-analyst-report.json');
const SCHEMA = JSON.parse(fs.readFileSync(`${PKG}/config/analyst-output-schema.json`, 'utf8'));
const LEGAL = JSON.parse(fs.readFileSync(`${PKG}/config/legal-reference.json`, 'utf8'));

const { refusalReason, REQUIRED_TOP_LEVEL } = require(RENDERER);
const sample = JSON.parse(fs.readFileSync(SAMPLE, 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));

let pass = 0, fail = 0;
const check = (cond, msg) => { if (cond) { pass++; } else { fail++; console.log('  FAIL:', msg); } };

/** Run the CLI with the given argv; return { code, out }. Never throws. */
function runArgs(args, cwd) {
  try {
    const out = execFileSync('node', [RENDERER, ...args], { encoding: 'utf8', stdio: 'pipe', cwd });
    return { code: 0, out };
  } catch (e) {
    return { code: e.status, out: `${e.stdout || ''}${e.stderr || ''}` };
  }
}

const runCli = (reportPath, outPath) => runArgs([reportPath, '-o', outPath]);

const tmp = fs.mkdtempSync(path.join(require('os').tmpdir(), 'screen-scribe-'));
const write = (name, obj) => {
  const p = path.join(tmp, name);
  fs.writeFileSync(p, JSON.stringify(obj));
  return p;
};

console.log('== hard stop 1: flagged content that was never withheld ==');
{
  const r = clone(sample);
  r.compliance.violations = [{ category: 'Age', question: 'How old are you?', analysis: 'ADEA exposure.' }];
  r.compliance.scrubbed_from_analysis = false;
  check(/scrubbed_from_analysis is not true/.test(refusalReason(r) || ''), 'refuses when scrubbed_from_analysis is false');

  delete r.compliance.scrubbed_from_analysis;
  check(refusalReason(r) !== null, 'refuses when scrubbed_from_analysis is absent entirely');

  r.compliance.scrubbed_from_analysis = 'true';
  check(refusalReason(r) !== null, 'refuses on the string "true" — must be a real boolean');

  r.compliance.scrubbed_from_analysis = true;
  check(refusalReason(r) === null, 'allows flagged content once it is confirmed withheld');

  const res = runCli(write('unscrubbed.json', (() => {
    const b = clone(sample);
    b.compliance.violations = [{ category: 'Age', question: 'q', analysis: 'a' }];
    b.compliance.scrubbed_from_analysis = false;
    return b;
  })()), path.join(tmp, 'nope.docx'));
  check(res.code === 1, 'CLI exits non-zero on unscrubbed violations');
  check(!fs.existsSync(path.join(tmp, 'nope.docx')), 'CLI writes no file when it refuses');
}

console.log('== hard stop 2: the recommendation stays a human decision ==');
{
  const r = clone(sample);
  r.recruiter_recommendation = 'Strong hire — advance.';
  check(/recruiter_recommendation must be null/.test(refusalReason(r) || ''), 'refuses a pre-filled recommendation');

  r.recruiter_recommendation = null;
  check(refusalReason(r) === null, 'allows a null recommendation');

  r.recruiter_recommendation = '';
  check(refusalReason(r) === null, 'treats an empty string as unfilled');

  const res = runCli(write('prefilled.json', { ...clone(sample), recruiter_recommendation: 'Hire.' }),
                     path.join(tmp, 'nope2.docx'));
  check(res.code === 1, 'CLI exits non-zero on a pre-filled recommendation');
  check(/must be null/.test(res.out), 'CLI explains why it refused');
}

console.log('== shape check: a malformed model response reports what is missing ==');
{
  for (const key of REQUIRED_TOP_LEVEL) {
    const r = clone(sample);
    delete r[key];
    check(new RegExp(`missing required key\\(s\\).*${key}`).test(refusalReason(r) || ''),
          `names the missing key '${key}' instead of throwing`);
  }
  check(refusalReason(clone(sample)) === null, 'the shipped sample passes every gate');
}

console.log('== contract: the sample matches the schema and the legal reference ==');
{
  check(SCHEMA.required.every((k) => k in sample), 'sample carries every schema-required top-level key');
  check(REQUIRED_TOP_LEVEL.join() === SCHEMA.required.join(),
        'renderer required keys match config/analyst-output-schema.json required');

  const labels = new Set(LEGAL.categories.map((c) => c.label));
  const used = sample.compliance.violations.map((v) => v.category);
  check(used.length > 0, 'sample exercises the violations path');
  check(used.every((c) => labels.has(c)),
        `every sample violation category is a legal-reference label (got: ${used.join(', ')})`);

  const info = sample.candidate_info;
  const sources = new Set(['transcript', 'ats', 'config', 'not_found']);
  check(Object.values(info).every((f) => sources.has(f.source)), 'every candidate_info field carries a known source');
  // `quote` is optional in the schema, but a quote on a field that did NOT come
  // from the transcript is false provenance — the one direction worth enforcing.
  check(Object.values(info).every((f) => !f.quote || f.source === 'transcript'),
        'no field claims a transcript quote it did not get from the transcript');
  check(Object.values(info).some((f) => f.source === 'transcript' && f.quote),
        'sample exercises the quoted-provenance path');
}

console.log('== happy path: the sample renders ==');
{
  const outPath = path.join(tmp, 'sample.docx');
  const res = runCli(SAMPLE, outPath);
  check(res.code === 0, 'CLI exits zero on the shipped sample');
  check(fs.existsSync(outPath) && fs.statSync(outPath).size > 5000, 'produces a non-trivial .docx');
  check(fs.readFileSync(outPath).slice(0, 2).toString() === 'PK', 'output is a real zip-backed .docx');

  // Argument handling: -o is optional and order-independent. Getting this wrong
  // silently breaks `npm run sample`, so pin all four forms.
  check(runArgs([SAMPLE, '-o', path.join(tmp, 'after.docx')]).code === 0, 'accepts -o after the report path');
  check(runArgs(['-o', path.join(tmp, 'before.docx'), SAMPLE]).code === 0, 'accepts -o before the report path');
  const dflt = runArgs([SAMPLE], tmp);
  check(dflt.code === 0 && fs.existsSync(path.join(tmp, 'report.docx')),
        'writes report.docx in the working directory when -o is omitted');
  check(runArgs([]).code === 2, 'exits 2 with usage when given no arguments');

  // Optional blocks must not take the renderer down when they are absent.
  const variants = {
    'no violations': (r) => { r.compliance.violations = []; },
    'null strategic_insights': (r) => { r.qualifications.strategic_insights = null; },
    'no research sources': (r) => { r.qualifications.strategic_insights.sources = []; },
    'no risks': (r) => { r.qualifications.risks = []; },
  };
  for (const [name, mutate] of Object.entries(variants)) {
    const r = clone(sample);
    mutate(r);
    const p = write(`${name.replace(/\W+/g, '_')}.json`, r);
    check(runCli(p, path.join(tmp, 'v.docx')).code === 0, `renders with ${name}`);
  }
}

fs.rmSync(tmp, { recursive: true, force: true });
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
