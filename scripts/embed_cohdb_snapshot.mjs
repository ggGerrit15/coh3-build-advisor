import fs from 'node:fs/promises';

const SNAPSHOT_PATH = 'data/cohdb/latest.json';
const HTML_PATH = 'index.html';

const snapshot = JSON.parse(await fs.readFile(SNAPSHOT_PATH, 'utf8'));
if (snapshot.schema_version !== 'cohdb.snapshot.v1') {
  throw new Error(`Unsupported CoHDB snapshot schema: ${snapshot.schema_version}`);
}
if (!snapshot.patch?.id || !snapshot.patch?.label) throw new Error('CoHDB snapshot has no patch provenance');
if (!Array.isArray(snapshot.battlegroups) || snapshot.battlegroups.length < 32) {
  throw new Error('CoHDB snapshot has fewer than 32 battlegroup rows');
}
if (!Array.isArray(snapshot.build_orders) || snapshot.build_orders.length < 4) {
  throw new Error('CoHDB snapshot has fewer than four build-order pages');
}

let html = await fs.readFile(HTML_PATH, 'utf8');
const embedded = `const COHDB_SNAPSHOT=${JSON.stringify(snapshot)};\n`;
if (/const COHDB_SNAPSHOT=.*?;\n/s.test(html)) {
  html = html.replace(/const COHDB_SNAPSHOT=.*?;\n/s, embedded);
} else if (html.includes('const PROFILES=')) {
  html = html.replace('const PROFILES=', `${embedded}const PROFILES=`);
} else {
  throw new Error('Could not find the PROFILES constant in index.html');
}
await fs.writeFile(HTML_PATH, html);

console.log(`Embedded CoHDB snapshot ${snapshot.patch.label} (${snapshot.patch.id}) into index.html.`);
