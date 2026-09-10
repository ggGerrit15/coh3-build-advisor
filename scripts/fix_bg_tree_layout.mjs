import fs from 'node:fs/promises';

const HTML_PATH = 'index.html';
const OLD_RULE = '.bg-tier-row.count-1 .bg-node-shell{grid-column:2;width:100%}';
const NEW_RULE = '.bg-tier-row.count-1 .bg-node-shell{grid-column:1 / -1;width:min(220px,100%);justify-self:center}';

let html = await fs.readFile(HTML_PATH, 'utf8');

if (html.includes(OLD_RULE)) {
  html = html.replace(OLD_RULE, NEW_RULE);
} else if (!html.includes(NEW_RULE)) {
  throw new Error('Expected single-node battlegroup tree CSS rule was not found.');
}

html = html.replace(/CoH3 Build Advisor v1\.1\.7/g, 'CoH3 Build Advisor v1.1.8');

await fs.writeFile(HTML_PATH, html);
console.log('Fixed battlegroup tree layout: single-option tiers now span the full row and stay centered.');
