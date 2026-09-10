import fs from 'node:fs';

const htmlPath = 'index.html';
const dataPath = 'coh3_build_advisor_data.json';

let html = fs.readFileSync(htmlPath, 'utf8');

function replaceBetween(source, start, end, replacement) {
  const a = source.indexOf(start);
  if (a < 0) throw new Error(`Start marker not found: ${start}`);
  const b = source.indexOf(end, a + start.length);
  if (b < 0) throw new Error(`End marker not found: ${end}`);
  return source.slice(0, a) + replacement + '\n' + source.slice(b);
}

html = html.replaceAll('v1.1.14', 'v1.1.15');

html = replaceBetween(
  html,
  'function smartSection(){',
  'function jsq(s){',
  `function smartSection(){const team=teamOpponents(),rows=smartRows(fac.value,mode.value,opp.value,maptype.value,elo.value,team).slice(0,3);return \`<div class="card" style="margin-top:14px"><h2>Top picks</h2><div class="smartgrid">\${rows.map((x,i)=>\`<div class="smartcard \${i===0?'first':''}"><div class="tags"><span class="tag">#\${i+1}</span><span class="tag conf \${cclass(x.p.confidence)}">\${x.p.confidence}</span></div><h3>\${x.p.battlegroup}</h3><div class="small muted">\${BG_META?.[x.p.faction]?.[x.p.battlegroup]?.style||''}</div><div class="smartactions"><button onclick="selectBG('\${jsq(x.p.battlegroup)}')">Use build</button><button onclick="toggleFavoriteByName('\${jsq(x.p.battlegroup)}')">★</button></div></div>\`).join("")}</div></div>\`}`
);

html = replaceBetween(
  html,
  'function renderAdvisor(){',
  'function findDecision',
  `function renderAdvisor(){const p=currentProfile();if(!p)return;const team=teamOpponents(),isTeam=teamMode(p.mode),displayBuild=effectiveBuild(p,team),enemyTags=isTeam?\`<span class="tag">Lane: \${opp.value}</span><span class="tag">Enemy team: \${teamCompLabel(team)}</span>\`:\`<span class="tag">vs \${opp.value}</span>\`,buildTitle=isTeam?'Team-adjusted build order':'Recommended build order';$("advisorContent").innerHTML=\`\${smartSection()}<div class="layout"><main><div class="card"><div class="tags"><span class="tag">\${p.faction}</span><span class="tag">\${p.mode}</span>\${enemyTags}<span class="tag">\${maptype.value}</span><span class="tag">ELO \${elo.value}</span></div><h2>\${p.battlegroup}</h2><p class="small muted">\${BG_META?.[p.faction]?.[p.battlegroup]?.style||'Combined arms'} · <span class="conf \${cclass(p.confidence)}">\${p.confidence} confidence</span></p><div class="smartactions"><button onclick="toggleFavorite()">\${isFavorite()?'★ Favorite':'☆ Add favorite'}</button><button onclick="switchView('match')">Match Mode</button></div></div><div class="card"><h3>\${buildTitle}</h3><div class="build">\${buildHtml(displayBuild)}</div></div></main><aside>\${battlegroupUnlockCard(p,"Battlegroup unlocks")}</aside></div>\`;}`
);

html = replaceBetween(
  html,
  'function renderMatch(){',
  'function useRecommended',
  `function renderMatch(){const p=currentProfile();if(!p)return;const team=teamOpponents(),isTeam=teamMode(p.mode),displayBuild=effectiveBuild(p,team),enemyTags=isTeam?\`<span class="tag">Lane: \${opp.value}</span><span class="tag">Enemy team: \${teamCompLabel(team)}</span>\`:\`<span class="tag">vs \${opp.value}</span>\`;$("matchContent").innerHTML=\`<div class="matchwrap"><div class="card"><div class="tags"><span class="tag">\${p.faction}</span><span class="tag">\${p.mode}</span>\${enemyTags}<span class="tag">\${maptype.value}</span></div><h2>\${p.battlegroup}</h2><h3>Build order</h3><div class="matchbuild">\${buildHtml(displayBuild)}</div><button class="action" style="margin-top:12px" onclick="switchView('advisor')">Back to Advisor</button></div>\${battlegroupUnlockCard(p,"Battlegroup unlocks")}</div>\`;}`
);

html = replaceBetween(
  html,
  'function creatorMiniCard(c){',
  'function creatorInline',
  `function creatorMiniCard(c){return \`<div class="creatorcard"><div class="creatorname">\${c.creator}</div><h3>\${c.title}</h3><div class="tags"><span class="tag">\${c.faction}</span><span class="tag">\${c.battlegroup}</span><span class="tag">\${(c.modes||[]).join(' / ')}</span></div><div class="build">\${buildHtml(c.build)}</div>\${c.path?.length?\`<div class="pathbox"><strong>\${c.pathLabel||'Battlegroup path'}</strong><ol>\${c.path.map(x=>\`<li>\${String(x).replace(/^\\d+\\.\\s*/, '')}</li>\`).join("")}</ol></div>\`:""}\${c.notes?.length?\`<details style="margin-top:10px"><summary>Notes</summary><ul>\${c.notes.map(x=>\`<li>\${x}</li>\`).join("")}</ul></details>\`:""}<div class="small muted" style="margin-top:10px">\${c.sourceLabel||''}</div></div>\`}`
);

html = replaceBetween(
  html,
  'function renderCreators(){',
  'function refreshRankControls',
  `function renderCreators(){let rows=CREATOR_BUILDS;if(cname.value!=='All')rows=rows.filter(c=>c.creator===cname.value);if(cfac.value!=='All')rows=rows.filter(c=>c.faction===cfac.value);if(cmode.value!=='All')rows=rows.filter(c=>(c.modes||[]).includes(cmode.value));if(cbg.value!=='All')rows=rows.filter(c=>c.battlegroup===cbg.value);$("creatorContent").innerHTML=\`<div class="card" style="margin-top:14px"><h2>Creator Builds <span class="countbadge">\${rows.length} shown / \${CREATOR_BUILDS.length} saved</span></h2><p class="small muted">Archived from the supplied creator material.</p></div><div class="creatorgrid">\${rows.map(creatorMiniCard).join("")}</div>\`}`
);

html = replaceBetween(
  html,
  'function renderRank(){',
  'function wilsonLB',
  `function renderRank(){const team=rankTeamOpponents(),rows=smartRows(rfac.value,rmode.value,ropp.value,rmap.value,relo.value,team),label=teamMode(rmode.value)?\`Lane \${ropp.value} · Enemy team \${teamCompLabel(team)}\`:\`vs \${ropp.value}\`;$("rankContent").innerHTML=\`<div class="card" style="margin-top:14px"><h2>\${rfac.value} \${rmode.value} — \${label}</h2><p class="small muted">\${rmap.value} · ELO \${relo.value} · WR is the selected all-mode CoHDB ELO snapshot.</p>\${rows.map((x,i)=>{const st=eloStat(x.p,relo.value);return \`<div class="rankrow"><div class="rank">\${i+1}</div><div><strong>\${x.p.battlegroup}</strong><div class="small muted">\${BG_META?.[x.p.faction]?.[x.p.battlegroup]?.style||''}</div></div><div class="conf \${cclass(x.p.confidence)}">\${x.p.confidence}</div><div><strong>\${st?st.wr.toFixed(1)+'%':'—'}</strong></div><div class="muted">\${st?'n='+st.n.toLocaleString():'No ELO sample'}</div></div>\`}).join("")}</div>\`}`
);

html = replaceBetween(
  html,
  'function renderSources(){',
  'function switchView',
  `function renderSources(){$("sourcesView").innerHTML=\`<div class="card"><h2>Sources</h2><div class="notice"><strong>Patch:</strong> current client 2.5.5. CoHDB statistical snapshots collected on 2.5.3 stay labelled as 2.5.3.</div><p class="small muted">Unofficial community project. Creator builds are archived separately and do not imply creator endorsement. Win rates are descriptive snapshots, not proof that a specific build causes the result.</p><div style="margin-top:14px">\${SOURCES.map(x=>\`<div class="source"><div><strong>\${x.name}</strong><div class="muted small">\${x.note}</div></div><a href="\${x.url}" target="_blank" rel="noopener noreferrer">Open ↗</a></div>\`).join("")}</div></div>\`}`
);

const methodStart = ' const method=`';
const methodEnd = " $('teamStatsContent').innerHTML=";
if (html.includes(methodStart) && html.includes(methodEnd)) {
  html = replaceBetween(html, methodStart, methodEnd, " const method='';");
}

const singleRule = '.bg-tier-row.count-1 .bg-node-shell{grid-column:1 / -1;width:min(220px,100%);justify-self:center}';
while (html.includes(singleRule + singleRule)) {
  html = html.replaceAll(singleRule + singleRule, singleRule);
}

fs.writeFileSync(htmlPath, html);

const data = JSON.parse(fs.readFileSync(dataPath, 'utf8'));
data.verified = '10 Sep 2026 — v1.1.15 public UI cleanup. The live advisor now focuses on top picks, the recommended build order and battlegroup unlock path. QA diagnostics, score breakdowns, phase summaries, inline creator comparisons, matchup explanation tables, composition targets, play tips, map-fit scores and note boxes were removed from the public advisor view; underlying research data remains preserved.';
fs.writeFileSync(dataPath, JSON.stringify(data, null, 2) + '\n');

console.log('Trimmed public advisor UI and bumped site to v1.1.15.');
