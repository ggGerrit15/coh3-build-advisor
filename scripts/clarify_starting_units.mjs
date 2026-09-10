import fs from 'node:fs/promises';

const HTML_PATH = 'index.html';
const JSON_PATH = 'coh3_build_advisor_data.json';
const VERSION = 'v1.1.14';

function normalizeUnit(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[–—-]/g, ' ')
    .replace(/[^a-z0-9äöüß ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function starterFrom(step) {
  const match = /^(?:Start|Starting unit):\s*(.+)$/i.exec(String(step || '').trim());
  return match ? match[1].trim() : null;
}

function clarifyBuild(build) {
  if (!Array.isArray(build) || !build.length) return 0;
  const starter = starterFrom(build[0]);
  if (!starter) return 0;

  let changes = 0;
  const wantedStart = `Starting unit: ${starter}`;
  if (build[0] !== wantedStart) {
    build[0] = wantedStart;
    changes++;
  }

  const starterKey = normalizeUnit(starter);
  let copyNumber = 1;
  for (let i = 1; i < build.length; i++) {
    const raw = String(build[i] || '').trim();
    const key = normalizeUnit(raw);

    if (key === starterKey) {
      copyNumber++;
      const replacement = `${copyNumber === 2 ? '2nd' : copyNumber === 3 ? '3rd' : `${copyNumber}th`} ${starter}`;
      if (build[i] !== replacement) {
        build[i] = replacement;
        changes++;
      }
      continue;
    }

    const explicitCopy = /^(?:2nd|second|3rd|third|4th|fourth)\s+(.+)$/i.exec(raw);
    if (explicitCopy && normalizeUnit(explicitCopy[1]) === starterKey) {
      const ordinal = /^(?:2nd|second)/i.test(raw) ? '2nd' : /^(?:3rd|third)/i.test(raw) ? '3rd' : '4th';
      const number = ordinal === '2nd' ? 2 : ordinal === '3rd' ? 3 : 4;
      copyNumber = Math.max(copyNumber, number);
      const replacement = `${ordinal} ${starter}`;
      if (build[i] !== replacement) {
        build[i] = replacement;
        changes++;
      }
    }
  }

  return changes;
}

function clarifyProfile(profile) {
  if (!profile || typeof profile !== 'object' || !profile.profileType) return 0;
  let changes = clarifyBuild(profile.build);
  for (const variant of profile.variants || []) changes += clarifyBuild(variant?.build);
  return changes;
}

function walkProfiles(node) {
  let changes = 0;
  if (Array.isArray(node)) {
    for (const item of node) changes += walkProfiles(item);
    return changes;
  }
  if (!node || typeof node !== 'object') return 0;

  if (node.profileType && Array.isArray(node.build)) {
    changes += clarifyProfile(node);
    return changes; // Do not rewrite legacy/creator-derived nested source snapshots.
  }

  for (const value of Object.values(node)) changes += walkProfiles(value);
  return changes;
}

function extractProfiles(html) {
  const startToken = 'const PROFILES=';
  const endToken = ';\nconst MATCHUPS=';
  const start = html.indexOf(startToken);
  const end = html.indexOf(endToken, start);
  if (start < 0 || end < 0) throw new Error('Could not locate embedded PROFILES block.');
  const jsonStart = start + startToken.length;
  return {
    profiles: JSON.parse(html.slice(jsonStart, end)),
    before: html.slice(0, jsonStart),
    after: html.slice(end),
  };
}

let data = JSON.parse(await fs.readFile(JSON_PATH, 'utf8'));
const jsonChanges = walkProfiles(data);
data.verified = '10 Sep 2026 — v1.1.14 starting-unit clarity pass. Current Advisor build orders now label the unit already present at game start as “Starting unit: …”. If the same starting unit is intentionally produced again, subsequent copies are explicitly labelled “2nd …”, “3rd …”, etc. Creator-source data remains preserved; the live renderer applies the same display clarification without rewriting creator originals.';
await fs.writeFile(JSON_PATH, JSON.stringify(data, null, 2) + '\n');

let html = await fs.readFile(HTML_PATH, 'utf8');
const embedded = extractProfiles(html);
let embeddedChanges = 0;
for (const profile of embedded.profiles) embeddedChanges += clarifyProfile(profile);
html = embedded.before + JSON.stringify(embedded.profiles) + embedded.after;

const oldBuildHtml = 'function buildHtml(arr){return arr.map((x,i)=>`${i?\'<span class="arrow">→</span> \':\'\'}${x}`).join(" ")}';
const newBuildHtml = `function displayBuildSteps(arr){const out=[...(arr||[])];if(!out.length)return out;const starter=starterFromDisplay(out[0]);if(!starter)return out;out[0]=\`Starting unit: \${starter}\`;const key=normalizeDisplayUnit(starter);let n=1;for(let i=1;i<out.length;i++){const raw=String(out[i]||'').trim(),rawKey=normalizeDisplayUnit(raw);if(rawKey===key){n++;out[i]=\`\${n===2?'2nd':n===3?'3rd':n+'th'} \${starter}\`;continue}const m=/^(?:2nd|second|3rd|third|4th|fourth)\\s+(.+)$/i.exec(raw);if(m&&normalizeDisplayUnit(m[1])===key){const ord=/^(?:2nd|second)/i.test(raw)?'2nd':/^(?:3rd|third)/i.test(raw)?'3rd':'4th';n=Math.max(n,ord==='2nd'?2:ord==='3rd'?3:4);out[i]=\`\${ord} \${starter}\`}}return out}
function normalizeDisplayUnit(value){return String(value||'').toLowerCase().replace(/[–—-]/g,' ').replace(/[^a-z0-9äöüß ]+/g,' ').replace(/\\s+/g,' ').trim()}
function starterFromDisplay(step){const m=/^(?:Start|Starting unit):\\s*(.+)$/i.exec(String(step||'').trim());return m?m[1].trim():null}
function buildHtml(arr){return displayBuildSteps(arr).map((x,i)=>\`\${i?'<span class="arrow">→</span> ':''}\${x}\`).join(" ")}`;

if (html.includes(oldBuildHtml)) {
  html = html.replace(oldBuildHtml, newBuildHtml);
} else if (!html.includes('function displayBuildSteps(arr)')) {
  throw new Error('Could not locate buildHtml renderer for starting-unit display clarification.');
}

html = html.replace(/CoH3 Build Advisor v1\.1\.\d+/g, `CoH3 Build Advisor ${VERSION}`);
await fs.writeFile(HTML_PATH, html);

console.log(`Starting-unit clarity complete: ${jsonChanges} JSON edits, ${embeddedChanges} embedded-profile edits, ${VERSION}.`);
