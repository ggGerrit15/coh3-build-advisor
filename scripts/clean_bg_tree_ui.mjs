import fs from 'node:fs/promises';

const HTML_PATH = 'index.html';
const JSON_PATH = 'coh3_build_advisor_data.json';
const VERSION = 'v1.1.9';

let html = await fs.readFile(HTML_PATH, 'utf8');

const start = html.indexOf('function renderBattlegroupTree(p){');
const end = html.indexOf('const $=id=>document.getElementById(id);', start);
if (start < 0 || end < 0) throw new Error('Could not locate battlegroup recommendation/tree render block.');

const replacement = `function renderBattlegroupTree(p){const tree=battlegroupTreeFor(p),schema=validateBattlegroupTree(tree);if(!schema.ok)return \`<div class="notice"><strong>Tree data error:</strong> \${schema.errors.join(' ')}</div>\`;const selectionMap=recommendationSelectionMap(p),hasSelected=Object.keys(selectionMap).length>0;return \`\${hasSelected?'<div class="bg-tree-key"><span class="bg-tree-pill"><span class="bg-tree-dot numbered"></span>Yellow badge = pick order</span></div>':''}<div class="bg-tree-wrap" style="margin-top:12px">\${tree.branches.map(branch=>renderBranchTree(p,branch,selectionMap)).join('')}</div>\`}\nfunction renderUnlockRecommendation(p){const check=validateUnlockRecommendation(p);if(!check.rec)return '';if(!check.ok)return \`<div class="notice"><strong>Recommendation blocked by validator.</strong><ul>\${check.errors.map(x=>\`<li>\${escapeHtml(x)}</li>\`).join('')}</ul></div>\`;const rec=check.rec;let body='';if(Array.isArray(rec.sequence)&&rec.sequence.length){body=\`<div class="pathbox"><strong>Numbered pick order</strong><div class="stepchips" style="margin-top:10px">\${rec.sequence.map((s,i)=>\`<span class="stepchip"><b style="color:var(--accent2)">\${i+1}.</b> \${escapeHtml(s.choice)}</span>\`).join('')}</div></div>\`}else{body=(rec.paths||[]).map(x=>\`<div class="pathbox"><strong>\${escapeHtml(x.branch)}</strong><div style="margin-top:6px">\${x.path.map(escapeHtml).join(' <span class="arrow">→</span> ')}</div></div>\`).join('')}return \`<div class="goodnotice"><strong>Recommendation</strong></div>\${body}\`}\nfunction battlegroupUnlockCard(p,heading='Battlegroup unlocks'){return \`<div class="card"><h3>\${heading}</h3>\${renderUnlockRecommendation(p)}\${renderBattlegroupTree(p)}</div>\`}\n`;

html = html.slice(0, start) + replacement + html.slice(end);
html = html.replace(/CoH3 Build Advisor v1\.1\.\d+/g, `CoH3 Build Advisor ${VERSION}`);

await fs.writeFile(HTML_PATH, html);

try {
  const data = JSON.parse(await fs.readFile(JSON_PATH, 'utf8'));
  data.verified = '10 Sep 2026 — v1.1.9 battlegroup recommendation UI cleanup. Removed explanatory recommendation notes, scope/confidence chips, branch/tier annotations in numbered picks, the Visual battlegroup tree heading/intro, and the Legal/Recommended legend. The visual tree, local icons, highlighted recommended nodes, and yellow pick-order badges remain unchanged.';
  await fs.writeFile(JSON_PATH, JSON.stringify(data, null, 2));
} catch (err) {
  console.warn('Could not update JSON verified metadata:', err.message);
}

console.log('Cleaned battlegroup recommendation UI and bumped to v1.1.9.');
