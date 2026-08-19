#!/usr/bin/env node
/**
 * Render a Talent Intelligence Report (config/analyst-output-schema.json) into a
 * professionally templated Word document.
 *
 *   node tools/render_docx.js report.json -o out.docx
 *
 * Company-specific styling and wording come from config/company-profile.json —
 * nothing here hardcodes a company, a work policy, or a jurisdiction.
 */

const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, AlignmentType, Footer, PageNumber, convertInchesToTwip,
} = require('docx');

const ROOT = path.resolve(__dirname, '..');
const LETTER = { width: 12240, height: 15840 };
const INK = '1A1A2E';
const MUTED = '6B6B7B';
const RULE = 'D8D8E0';
const WASH = 'F4F4F8';
const FLAG = '9B1C1C';
const FLAG_WASH = 'FDF2F2';

const NO_BORDER = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
const NO_BORDERS = { top: NO_BORDER, bottom: NO_BORDER, left: NO_BORDER, right: NO_BORDER };

/* ---------- small builders ---------- */

const text = (t, o = {}) => new TextRun({ text: t, font: 'Calibri', color: INK, size: 21, ...o });

const para = (runs, o = {}) =>
  new Paragraph({ children: Array.isArray(runs) ? runs : [runs], spacing: { after: 120 }, ...o });

const body = (t) => para(text(t), { spacing: { after: 160, line: 288 } });

const spacer = (after = 160) => new Paragraph({ children: [], spacing: { after } });

/** Section heading: small-caps-ish label over a full-width rule. */
const sectionHeading = (label, accent) =>
  new Paragraph({
    children: [text(label.toUpperCase(), { bold: true, size: 20, color: accent, characterSpacing: 30 })],
    spacing: { before: 320, after: 140 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: accent, space: 6 } },
  });

/** Bold run-in heading followed by prose in the same paragraph. */
const runIn = (heading, prose) =>
  para([text(`${heading}  `, { bold: true }), text(prose)], { spacing: { after: 160, line: 288 } });

const cell = (children, o = {}) =>
  new TableCell({
    children,
    margins: { top: 100, bottom: 100, left: 140, right: 140 },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 4, color: RULE },
      bottom: { style: BorderStyle.SINGLE, size: 4, color: RULE },
      left: NO_BORDER,
      right: NO_BORDER,
    },
    ...o,
  });

/* ---------- provenance ---------- */

const SOURCE_LABEL = {
  transcript: 'from the screen',
  ats: 'from candidate record',
  config: 'supplied',
  not_found: 'not covered',
};

/** A candidate-info field: value plus a muted provenance note and optional quote. */
function fieldCell(field, width) {
  const f = field || { value: 'UNKNOWN', source: 'not_found' };
  const missing = !f.value || /^(UNKNOWN|INSUFFICIENT DATA)$/.test(f.value);
  const kids = [
    para(text(f.value || 'UNKNOWN', { italics: missing, color: missing ? MUTED : INK }), {
      spacing: { after: f.quote ? 60 : 0 },
    }),
  ];
  if (f.quote) {
    kids.push(para(text(`“${f.quote}”`, { italics: true, size: 18, color: MUTED }), { spacing: { after: 0 } }));
  }
  kids.push(
    para(text(SOURCE_LABEL[f.source] || 'unverified', { size: 16, color: MUTED, allCaps: true, characterSpacing: 20 }), {
      spacing: { before: 40, after: 0 },
    }),
  );
  return cell(kids, { width: { size: width, type: WidthType.DXA } });
}

function infoTable(info, profile) {
  const LABEL_W = 2900;
  const VALUE_W = 6460;
  const rows = [
    ['Name', info.name],
    ['Current location', info.current_location],
    [`Confirmation of ${profile.work_policy.label}`, info.work_policy_confirmation],
    ['Salary expectations', info.salary_expectations],
    ['Availability', info.availability],
  ];
  return new Table({
    columnWidths: [LABEL_W, VALUE_W],
    width: { size: LABEL_W + VALUE_W, type: WidthType.DXA },
    rows: rows.map(
      ([label, field]) =>
        new TableRow({
          children: [
            cell([para(text(label, { bold: true, size: 20 }))], {
              width: { size: LABEL_W, type: WidthType.DXA },
              shading: { type: ShadingType.CLEAR, fill: WASH, color: 'auto' },
            }),
            fieldCell(field, VALUE_W),
          ],
        }),
    ),
  });
}

/* ---------- blocks ---------- */

function recommendationCallout(profile) {
  // Never auto-filled. A human types the assessment here.
  return new Table({
    columnWidths: [9360],
    width: { size: 9360, type: WidthType.DXA },
    rows: [
      new TableRow({
        children: [
          new TableCell({
            width: { size: 9360, type: WidthType.DXA },
            shading: { type: ShadingType.CLEAR, fill: WASH, color: 'auto' },
            margins: { top: 160, bottom: 160, left: 180, right: 180 },
            borders: {
              ...NO_BORDERS,
              left: { style: BorderStyle.SINGLE, size: 18, color: profile.report.accent_color },
            },
            children: [
              para(
                text('RECRUITER RECOMMENDATION', {
                  bold: true, size: 16, color: MUTED, allCaps: true, characterSpacing: 30,
                }),
                { spacing: { after: 80 } },
              ),
              para(text(profile.report.recommendation_placeholder, { bold: true, color: MUTED }), {
                spacing: { after: 0 },
              }),
            ],
          }),
        ],
      }),
    ],
  });
}

function insightBlock(insights, accent) {
  const kids = [
    para(
      [
        text('[AI INSIGHT]  ', { bold: true, size: 18, color: accent, characterSpacing: 20 }),
        text('Strategic insights from employer research', { bold: true, size: 20 }),
      ],
      { spacing: { after: 100 } },
    ),
  ];

  if (!insights || !insights.sources || insights.sources.length === 0) {
    kids.push(
      para(
        text(
          'No credible sources were found for the candidate’s previous employers. No employer research is presented.',
          { italics: true, color: MUTED },
        ),
        { spacing: { after: 0 } },
      ),
    );
  } else {
    kids.push(para(text(insights.summary), { spacing: { after: 120, line: 288 } }));
    insights.sources.forEach((s) => {
      kids.push(
        para(
          [
            text(`${s.employer} — `, { bold: true, size: 18 }),
            text(s.claim, { size: 18 }),
            text(`  (${[s.publisher, s.date].filter(Boolean).join(', ') || 'source'}: ${s.url})`, {
              size: 16, color: MUTED,
            }),
          ],
          { spacing: { after: 60 }, indent: { left: convertInchesToTwip(0.2) } },
        ),
      );
    });
  }

  return new Table({
    columnWidths: [9360],
    width: { size: 9360, type: WidthType.DXA },
    rows: [
      new TableRow({
        children: [
          new TableCell({
            width: { size: 9360, type: WidthType.DXA },
            shading: { type: ShadingType.CLEAR, fill: WASH, color: 'auto' },
            margins: { top: 160, bottom: 160, left: 180, right: 180 },
            borders: NO_BORDERS,
            children: kids,
          }),
        ],
      }),
    ],
  });
}

function violationBlock(v) {
  const kids = [
    para(
      [
        text(`${v.category}`, { bold: true, color: FLAG }),
        v.framework && v.framework.length
          ? text(`   ${v.framework.join(' · ')}`, { size: 16, color: MUTED, allCaps: true, characterSpacing: 20 })
          : text(''),
      ],
      { spacing: { after: 80 } },
    ),
    para(
      [
        text(`${v.speaker === 'candidate' ? 'Candidate' : 'Interviewer'}: `, { bold: true, size: 19 }),
        text(`“${v.question}”`, { italics: true, size: 19 }),
      ],
      { spacing: { after: 80 }, indent: { left: convertInchesToTwip(0.2) } },
    ),
    para([text('Analysis:  ', { bold: true, size: 19 }), text(v.analysis, { size: 19 })], {
      spacing: { after: 0, line: 276 },
    }),
  ];

  return new Table({
    columnWidths: [9360],
    width: { size: 9360, type: WidthType.DXA },
    rows: [
      new TableRow({
        children: [
          new TableCell({
            width: { size: 9360, type: WidthType.DXA },
            shading: { type: ShadingType.CLEAR, fill: FLAG_WASH, color: 'auto' },
            margins: { top: 150, bottom: 150, left: 180, right: 180 },
            borders: { ...NO_BORDERS, left: { style: BorderStyle.SINGLE, size: 18, color: FLAG } },
            children: kids,
          }),
        ],
      }),
    ],
  });
}

/* ---------- document ---------- */

function build(report, profile) {
  const accent = profile.report.accent_color;
  const info = report.candidate_info;
  const q = report.qualifications;
  const name = (info.name && info.name.value) || 'Candidate';
  const role = (info.role && info.role.value) || null;
  const screenDate = (info.screen_date && info.screen_date.value) || null;

  const children = [];

  /* Masthead */
  children.push(
    new Paragraph({
      children: [
        text(`${profile.company.short_name} · ${profile.report.title}`.toUpperCase(), {
          bold: true, size: 16, color: accent, characterSpacing: 40,
        }),
      ],
      spacing: { after: 60 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: accent, space: 8 } },
    }),
    para(text(name, { bold: true, size: 40 }), { spacing: { before: 200, after: 40 } }),
    para(
      text([role, screenDate ? `Screened ${screenDate}` : null].filter(Boolean).join('  ·  '), {
        size: 20, color: MUTED,
      }),
      { spacing: { after: 240 } },
    ),
  );

  /* Section 1 */
  children.push(sectionHeading('Section 1 · Quick Summary', accent));
  children.push(recommendationCallout(profile), spacer(200));
  children.push(
    para(text('Candidate Information', { bold: true, size: 22 }), { spacing: { after: 120 } }),
    infoTable(info, profile),
    spacer(80),
  );

  /* Section 2 */
  children.push(sectionHeading('Section 2 · Qualifications & Experience', accent));
  q.topics.forEach((t) => {
    children.push(para(text(t.heading, { bold: true, size: 22 }), { spacing: { before: 160, after: 80 } }));
    children.push(body(t.body));
  });

  const rb = q.recruiting_background;
  children.push(para(text('Recruiting Background', { bold: true, size: 22 }), { spacing: { before: 240, after: 120 } }));
  children.push(
    runIn('Current situation in job search.', rb.job_search_situation),
    runIn('Motivation.', rb.motivation),
    runIn('Current and past work experience.', rb.work_experience),
    runIn('Projects requiring ownership.', rb.ownership_projects),
    runIn('Experience relevant to the role.', rb.role_relevant_experience),
  );

  children.push(spacer(80), insightBlock(q.strategic_insights, accent), spacer(200));

  children.push(para(text('Interview Highlights', { bold: true, size: 22 }), { spacing: { before: 160, after: 100 } }));
  children.push(body(q.interview_highlights));

  // Omitted entirely when there are no risks — never printed as "none".
  if (q.risks && q.risks.length) {
    children.push(
      para(text('Potential Risks / Red Flags', { bold: true, size: 22 }), { spacing: { before: 240, after: 100 } }),
    );
    q.risks.forEach((r) => children.push(runIn(`${r.heading}.`, r.detail)));
  }

  /* Section 3 */
  children.push(sectionHeading('Section 3 · Legal Compliance Scrub', accent));
  const violations = report.compliance.violations || [];
  if (violations.length === 0) {
    children.push(
      body(
        `No violations of ${[profile.jurisdiction.country === 'US' ? 'U.S.' : profile.jurisdiction.country, profile.jurisdiction.state]
          .filter(Boolean)
          .join(' or ')} employment law were identified in the interview transcript.`,
      ),
    );
  } else {
    children.push(
      body(
        `${violations.length} item${violations.length === 1 ? '' : 's'} flagged and withheld from Sections 1 and 2.`,
      ),
    );
    violations.forEach((v) => children.push(violationBlock(v), spacer(120)));
  }

  return new Document({
    creator: `${profile.company.short_name} ${profile.report.analyst_persona}`,
    title: `${profile.report.title} — ${name}`,
    styles: { default: { document: { run: { font: 'Calibri', size: 21, color: INK } } } },
    sections: [
      {
        properties: {
          page: { size: LETTER, margin: { top: 1080, bottom: 1080, left: 1080, right: 1080 } },
        },
        footers: {
          default: new Footer({
            children: [
              new Paragraph({
                alignment: AlignmentType.RIGHT,
                border: { top: { style: BorderStyle.SINGLE, size: 4, color: RULE, space: 8 } },
                children: [
                  text(
                    profile.report.confidential_footer
                      ? `Confidential · ${name} · `
                      : `${name} · `,
                    { size: 16, color: MUTED },
                  ),
                  new TextRun({ children: [PageNumber.CURRENT], size: 16, color: MUTED, font: 'Calibri' }),
                ],
              }),
            ],
          }),
        },
        children,
      },
    ],
  });
}

/* ---------- cli ---------- */

const REQUIRED_TOP_LEVEL = ['candidate_info', 'qualifications', 'compliance'];

function fail(msg) {
  console.error(msg);
  process.exit(1);
}

function readJson(file, label) {
  let raw;
  try {
    raw = fs.readFileSync(file, 'utf8');
  } catch (e) {
    fail(`cannot read ${label} (${file}): ${e.code === 'ENOENT' ? 'no such file' : e.message}`);
  }
  try {
    return JSON.parse(raw);
  } catch (e) {
    fail(`${label} (${file}) is not valid JSON: ${e.message}`);
  }
}

/**
 * The two hard stops, plus a shape check so a malformed model response reports
 * what is missing instead of throwing from deep inside the layout code.
 * Returns an error string, or null when the report is safe to render.
 */
function refusalReason(report) {
  const absent = REQUIRED_TOP_LEVEL.filter((k) => !report[k]);
  if (absent.length) {
    return `refusing to render: report is missing required key(s): ${absent.join(', ')} ` +
      '(see config/analyst-output-schema.json)';
  }
  const v = (report.compliance && report.compliance.violations) || [];
  if (v.length > 0 && report.compliance.scrubbed_from_analysis !== true) {
    return `refusing to render: ${v.length} compliance violation(s) flagged but ` +
      'compliance.scrubbed_from_analysis is not true';
  }
  if (report.recruiter_recommendation) {
    return 'refusing to render: recruiter_recommendation must be null (a human fills it in)';
  }
  return null;
}

function main() {
  const argv = process.argv.slice(2);
  const outIdx = argv.indexOf('-o');
  const out = outIdx > -1 ? argv[outIdx + 1] : 'report.docx';
  // skip the -o value so `-o out.docx report.json` works in either order
  const src = argv.find((a, i) => !a.startsWith('-') && !(outIdx > -1 && i === outIdx + 1));
  if (!src) {
    console.error('usage: node tools/render_docx.js <report.json> [-o out.docx]');
    process.exit(2);
  }

  const report = readJson(src, 'report');
  const profile = readJson(path.join(ROOT, 'config', 'company-profile.json'), 'company profile');

  const refusal = refusalReason(report);
  if (refusal) fail(refusal);

  Packer.toBuffer(build(report, profile))
    .then((buf) => {
      fs.writeFileSync(out, buf);
      console.log(`wrote ${out} (${(buf.length / 1024).toFixed(1)} KB)`);
    })
    .catch((e) => fail(`failed to render: ${e.message}`));
}

if (require.main === module) main();
module.exports = { build, refusalReason, REQUIRED_TOP_LEVEL };
