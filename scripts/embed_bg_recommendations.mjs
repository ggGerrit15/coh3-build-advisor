import fs from 'node:fs/promises';

const JSON_PATH = 'coh3_build_advisor_data.json';
const HTML_PATH = 'index.html';
const VERSION = 'v1.1.11';

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

data.verified = `10 Sep 2026 — ${VERSION} team-game recommendation embedding fix. The 28 battlegroups now expose explicit 3v3 and 4v4 numbered pick orders in the data file and the same recommendation object is embedded into index.html. This fixes the previous state where team-game orders existed in JSON but the live page still used the older small-game-only embedded recommendation constant.`;
await fs.writeFile(JSON_PATH, JSON.stringify(data, null, 2) + '\n');

console.log(`Embedded ${battlegroups} battlegroups and ${teamOrders} 3v3/4v4 orders into index.html.`);
