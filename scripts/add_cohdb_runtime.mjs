import fs from 'node:fs/promises';

const HTML_PATH = 'index.html';
const RUNTIME_PATH = 'scripts/cohdb_runtime.js';
let html = await fs.readFile(HTML_PATH, 'utf8');

const runtime = await fs.readFile(RUNTIME_PATH, 'utf8');
const anchor = 'const $=id=>document.getElementById(id);';
if (!html.includes(anchor)) throw new Error('Could not find frontend helper anchor');
const runtimeStart = html.indexOf('const COHDB_MODE_KEYS');
if (runtimeStart >= 0) {
  const runtimeEnd = html.indexOf(anchor, runtimeStart);
  if (runtimeEnd < 0) throw new Error('Could not find end of embedded CoHDB runtime');
  html = html.slice(0, runtimeStart) + runtime + '\n' + html.slice(runtimeEnd);
} else {
  html = html.replace(anchor, `${runtime}\n${anchor}`);
}

function replaceFunction(name, nextName, replacement) {
  const startMarker = `function ${name}(`;
  const start = html.indexOf(startMarker);
  if (start < 0) throw new Error(`Could not find ${name}`);
  const end = html.indexOf(`\nfunction ${nextName}(`, start);
  if (end < 0) throw new Error(`Could not find end of ${name}`);
  html = html.slice(0, start) + replacement + html.slice(end);
}

replaceFunction(
  'scoreProfile',
  'recommendation',
  `function scoreProfile(p,o,m,band,list=null){const mu=teamMatchupComponent(p,o,list),r=mu.laneRank,ec=eloComponent(p,band),xc=exactModeComponent(p),mb=mapComponent(p,m),rc=recoveryComponent(p),cb=confidenceBonus(p.confidence),rb=mu.bonus,cc=cohdbComponent(p);const score=Math.round(clamp(55+cb+rb+mb+rc+ec.bonus+xc.bonus+cc.bonus,35,95));return {score,rank:r,confidence:cb,rankBonus:rb,map:mb,recovery:rc,elo:ec.bonus,eloInfo:ec,mode:xc.bonus,modeInfo:xc,cohdb:cc.bonus,cohdbInfo:cc}}\n`
);

replaceFunction(
  'smartReason',
  'smartSection',
  `function smartReason(x){const bits=[];if(x.rank===1)bits.push('#1 lane-matchup shell');if(x.teamMatchupInfo?.active)bits.push('enemy-team composition included');if(x.map>=4)bits.push('excellent map fit');else if(x.map<0)bits.push('map penalty');if(x.elo>=2)bits.push('positive ELO context');if(x.mode>=1.5)bits.push('strong exact-mode signal');if(x.cohdb>=1)bits.push('CoHDB evidence supports the shell');if(x.recovery>=3)bits.push('strong recovery path');return bits.join(' • ')||'Balanced current recommendation'}\n`
);

replaceFunction(
  'smartSection',
  'jsq',
  `function smartSection(){const team=teamOpponents(),rows=smartRows(fac.value,mode.value,opp.value,maptype.value,elo.value,team).slice(0,3),favs=getFavorites().filter(k=>k.startsWith(fac.value+'|'+mode.value+'|')),fmt=x=>Number.isInteger(x)?x:x.toFixed(1);return \`<div class="card" style="margin-top:14px"><h2>Smart recommendation</h2><div class="smartgrid">\${rows.map((x,i)=>\`<div class="smartcard \${i===0?'first':''}"><div class="tags"><span class="tag">#\${i+1}</span><span class="tag">\${x.p.confidence}</span></div><h3>\${x.p.battlegroup}</h3><div class="score">\${x.score}<span class="small muted">/100</span></div><div class="scorebar"><span style="width:\${x.score}%"></span></div><div class="smartreason">\${smartReason(x)}</div><div class="scoreparts"><div class="scorepart"><b>+\${x.confidence}</b>confidence</div><div class="scorepart"><b>+\${fmt(x.rankBonus)}</b>\${teamMode(mode.value)?'team matchup':'matchup'}</div><div class="scorepart"><b>\${x.map>=0?'+':''}\${x.map}</b>map</div><div class="scorepart"><b>\${x.elo>=0?'+':''}\${x.elo.toFixed(1)}</b>ELO</div><div class="scorepart"><b>\${x.mode>=0?'+':''}\${x.mode.toFixed(1)}</b>mode</div><div class="scorepart"><b>\${x.cohdb>=0?'+':''}\${x.cohdb.toFixed(1)}</b>CoHDB</div><div class="scorepart"><b>+\${x.recovery}</b>recovery</div></div><div class="small muted" style="margin-top:8px">\${x.eloInfo.label}\${x.p.mode==='4v4'?\` • \${x.modeInfo.label}\`:''}</div><div class="smartactions"><button onclick="selectBG('\${jsq(x.p.battlegroup)}')">Use build</button><button onclick="toggleFavoriteByName('\${jsq(x.p.battlegroup)}')">★</button></div></div>\`).join('')}</div>\${favs.length?\`<div class="favbar"><span class="muted small">Favorites:</span>\${favs.map(k=>\`<button class="favchip" onclick="selectBG('\${jsq(k.split('|')[2])}')">★ \${k.split('|')[2]}</button>\`).join('')}</div>\`:''}</div>\`}\n`
);

const oldStats = '${factionStatsSection(p)}<div class="card"><h3>${isTeam?\'Lane matchup decisions\':\'Matchup decisions\'}';
const newStats = '${factionStatsSection(p)}${cohdbStatsSection(p)}<div class="card"><h3>${isTeam?\'Lane matchup decisions\':\'Matchup decisions\'}';
if (html.includes(oldStats)) html = html.replace(oldStats, newStats);

await fs.writeFile(HTML_PATH, html);
console.log('Added CoHDB statistics and recommendation scoring to index.html.');
