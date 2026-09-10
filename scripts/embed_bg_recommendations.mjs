import fs from 'node:fs/promises';

const JSON_PATH = 'coh3_build_advisor_data.json';
const HTML_PATH = 'index.html';
const VERSION = 'v1.1.12';

const data = JSON.parse(await fs.readFile(JSON_PATH, 'utf8'));
const recs = data.battlegroupRecommendations || {};

let battlegroups = 0;
let teamOrders = 0;
for (const [faction, bgs] of Object.entries(recs)) {
  for (const [bg, bucket] of Object.entries(bgs)) {
    battlegroups += 1;
    for (const mode of ['3v3', '4v4']) {
      const rec = bucket?.[mode];
      if (!rec?.sequence?.length) throw new Error(`${faction} / ${bg}: missing ${mode} recommendation`);
      if (rec.sequence.length !== 6) throw new Error(`${faction} / ${bg}: ${mode} has ${rec.sequence.length} picks instead of 6`);
      teamOrders += 1;
    }
  }
}

if (battlegroups !== 28) throw new Error(`Expected 28 battlegroups, found ${battlegroups}`);
if (teamOrders !== 56) throw new Error(`Expected 56 team-game orders, found ${teamOrders}`);

let html = await fs.readFile(HTML_PATH, 'utf8');
const replacement = `const BATTLEGROUP_RECOMMENDATIONS=${JSON.stringify(recs)};\n`;

if (!/const BATTLEGROUP_RECOMMENDATIONS=.*?;\n/.test(html)) {
  throw new Error('Could not find embedded BATTLEGROUP_RECOMMENDATIONS constant in index.html');
}

html = html.replace(/const BATTLEGROUP_RECOMMENDATIONS=.*?;\n/, replacement);
html = html.replace(/CoH3 Build Advisor v1\.1\.\d+/g, `CoH3 Build Advisor ${VERSION}`);

await fs.writeFile(HTML_PATH, html);

data.verified = `10 Sep 2026 — ${VERSION} battlegroup icon QA update. The confirmed Wehrmacht Breakthrough / Mechanized Assault Group icon cross-swap is corrected during the asset workflow, and the generated icon report now performs an additional branch-level semantic cross-swap audit for all battlegroups. The 28 battlegroups also continue to expose explicit 3v3 and 4v4 numbered pick orders in both JSON and index.html.`;
await fs.writeFile(JSON_PATH, JSON.stringify(data, null, 2) + '\n');

console.log(`Embedded ${battlegroups} battlegroups and ${teamOrders} 3v3/4v4 orders into index.html (${VERSION}).`);
