import fs from 'node:fs/promises';

const HTML_PATH = 'index.html';
const JSON_PATH = 'coh3_build_advisor_data.json';
const VERSION = 'v1.1.13';

let html = await fs.readFile(HTML_PATH, 'utf8');

function clean(label, pattern, replacement = '') {
  const before = html;
  html = html.replace(pattern, replacement);
  if (html === before) console.warn(`No match for cleanup: ${label}`);
  else console.log(`Cleaned: ${label}`);
}

// Keep the public advisor focused on actionable game information. Longer methodology
// and provenance notes remain available in the dedicated Sources tab.
clean(
  'Smart recommendation explainer',
  /<div class="muted" style="margin-bottom:10px">Advisor Score combines profile confidence,[\s\S]*?adds a separate mode component\.<\/div>/g,
);

clean(
  'Build phase disclaimer',
  /<div class="small muted" style="margin-top:9px">The phase labels are a quick-reference grouping of the recommended sequence, not invented exact minute timings\.<\/div>/g,
);

clean(
  'Evidence layer card',
  /<div class="card"><h3>Evidence layer<\/h3>\$\{evidence\}<div class="small muted">Client patch \$\{PATCH\}\.[\s\S]*?measured team-composition win rate\.<\/div><\/div>/g,
);

clean(
  'Team composition weighting explainer',
  /<br><span class="small">Lane opponent: \$\{list\[0\]\}\.[\s\S]*?do not bypass tech prerequisites\.<\/span>/g,
);

clean(
  'Team composition methodology footer',
  /<div class="small muted" style="margin-top:8px">These are qualitative risk weights from the advisor's matchup layer, not measured team-composition win rates\.<\/div>/g,
);

clean(
  'Team-adjusted build disclaimer',
  /\$\{isTeam\?`<div class="small muted" style="margin-top:8px">The stored base build[\s\S]*?required structure\/tech\.<\/div>`:''\}/g,
);

clean(
  'ELO methodology footer',
  /<div class="small muted" style="margin-top:9px">Faction battlegroup average in this ELO table: \$\{avg\.toFixed\(1\)\}%\.[\s\S]*?not a map-filtered CoHDB result\.<\/div>/g,
);

clean(
  'Exact-mode archetype disclaimer',
  /<div class="small muted" style="margin-top:9px">This is a faction build\/tech archetype, not a battlegroup-specific win rate\. It is shown as exact-mode strategic context only\.<\/div>/g,
);

clean(
  'Archetype methodology footer',
  /<div class="small muted" style="margin-top:9px">Archetype WR is descriptive\. Late-tech categories can contain survivorship bias and are not battlegroup-specific\.<\/div>/g,
);

clean(
  'Creator comparison methodology sentence',
  /<div class="small muted">Green = similar step detected; amber = unique to that sequence\. Text matching is approximate because creators often use shorter unit names\.<\/div>/g,
  '<div class="small muted">Green = shared · Amber = unique</div>',
);

clean(
  'Ranking methodology paragraph',
  /<p class="muted">Smart ranking for \$\{rmap\.value\}, ELO \$\{relo\.value\}\.[\s\S]*?CoHDB metric\.<\/p>/g,
  () => '<p class="muted">${rmap.value} · ELO ${relo.value}</p>',
);

html = html.replace(/CoH3 Build Advisor v1\.1\.\d+/g, `CoH3 Build Advisor ${VERSION}`);
await fs.writeFile(HTML_PATH, html);

try {
  const data = JSON.parse(await fs.readFile(JSON_PATH, 'utf8'));
  data.verified = '10 Sep 2026 — v1.1.13 public-copy cleanup. Removed methodology-heavy explanatory text from the main advisor, phase view, evidence sidebar, team-composition cards, ELO/archetype panels and rankings. Detailed source and methodology information remains available in the dedicated Sources tab.';
  await fs.writeFile(JSON_PATH, JSON.stringify(data, null, 2) + '\n');
} catch (err) {
  console.warn('Could not update JSON verified metadata:', err.message);
}

console.log(`Public copy cleanup complete: ${VERSION}.`);
