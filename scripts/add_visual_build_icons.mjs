import fs from 'node:fs/promises';

const HTML_PATH = 'index.html';
const VERSION = 'v1.1.15';

let html = await fs.readFile(HTML_PATH, 'utf8');

const CSS_MARKER = '/* VISUAL_BUILD_CARDS_V1 */';
if (!html.includes(CSS_MARKER)) {
  const css = `${CSS_MARKER}
.buildviz{display:flex;flex-direction:column;gap:14px}.buildlegend{display:flex;flex-wrap:wrap;gap:8px}.buildlegend .legenditem{display:inline-flex;align-items:center;gap:7px;padding:6px 10px;border-radius:999px;background:var(--panel2);border:1px solid var(--line);font-size:12px;color:var(--muted)}.buildlegend .legendicon{width:24px;height:24px;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;background:#101823;border:1px solid var(--line);font-size:13px}.buildphase{background:#0d131a;border:1px solid var(--line);border-radius:12px;padding:12px}.buildphasehead{display:flex;align-items:flex-end;justify-content:space-between;gap:10px;margin-bottom:10px}.buildphasekicker{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}.buildphase h4{margin:0;color:var(--accent2)}.buildstepgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:10px}.buildstepcard{position:relative;background:linear-gradient(180deg,#111a25,#0f1620);border:1px solid #2b3748;border-radius:14px;padding:12px;min-height:104px;box-shadow:0 8px 20px rgba(0,0,0,.18)}.buildstepcard.conditional{border-style:dashed}.buildstepcard.startcard{border-color:#35506d;background:linear-gradient(180deg,#12202c,#0f1720)}.buildstepbadge{position:absolute;top:-8px;left:12px;min-width:34px;height:34px;padding:0 10px;border-radius:999px;background:var(--accent2);color:#20160a;font-weight:900;font-size:12px;display:inline-flex;align-items:center;justify-content:center;box-shadow:0 3px 10px rgba(0,0,0,.28)}.buildstepbadge.start{background:#79c7ff;color:#082033;min-width:56px}.buildsteptype{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin-top:10px}.buildstepbody{display:flex;gap:10px;align-items:flex-start;margin-top:8px}.buildstepicon{width:48px;height:48px;border-radius:12px;display:flex;align-items:center;justify-content:center;background:#0c131b;border:1px solid #334155;font-size:22px;flex:0 0 48px;position:relative;overflow:hidden}.buildstepimg{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;display:none;padding:4px;background:#0c131b}.buildstepicon.loaded .buildstepimg{display:block}.buildstepicon.loaded .buildstepemoji{display:none}.buildstepemoji{display:inline-flex;align-items:center;justify-content:center;width:100%;height:100%}.buildsteptext{min-width:0}.buildstepname{font-size:15px;font-weight:800;line-height:1.25;color:#f4f7fb}.buildstepnote{margin-top:6px;font-size:12px;line-height:1.35;color:var(--muted)}.buildtexttoggle{margin-top:4px}.buildtexttoggle summary{cursor:pointer;color:var(--muted);font-size:12px}.buildtexttoggle .build{margin-top:10px}.buildcallout{margin:0 0 12px;font-size:12px;color:var(--muted)}
`;
  html = html.replace('@media(max-width:1050px){', css + '@media(max-width:1050px){');
}

const MAP_MARKER = 'const BUILD_STEP_ICON_OVERRIDES=';
if (!html.includes(MAP_MARKER)) {
  const mapBlock = `const BUILD_STEP_ICON_OVERRIDES={
  Wehrmacht:{
    'pioneer':['icons/races/german/symbols/pioneers_ger'],
    'kettenkrad':['icons/races/german/vehicles/kettenkrad_ger','icons/races/german/symbols/kettenkrad_ger'],
    'grenadier':['icons/races/german/symbols/grenadiers_ger'],
    'mg42':['icons/races/german/team_weapons/mg42_hmg_ger','icons/races/german/symbols/mg42_hmg_ger'],
    'panzergrenadier':['icons/races/german/symbols/panzergrenadiers_ger'],
    'fallschirmjager':['icons/races/german/symbols/fallshirmjagers_ger'],
    'fallschirmpioneer':['icons/races/german/symbols/fallshirmpioneers_ger'],
    'pak 40':['icons/races/german/team_weapons/pak_40_anti-tank_gun_ger','icons/races/german/symbols/pak_40_anti-tank_gun_ger'],
    '251 half track':['icons/races/german/vehicles/sdkfz_251_ger','icons/races/german/vehicles/251_half-track_ger'],
    'stummel':['icons/races/german/vehicles/sdkfz_251_9_ger','icons/races/german/vehicles/251_9_stummel_ger'],
    '221':['icons/races/german/vehicles/sdkfz_221_ger','icons/races/german/vehicles/221_scout_car_ger'],
    'panzer iv':['icons/races/german/vehicles/panzer_iv_ger'],
    'brummbar':['icons/races/german/vehicles/sturmpanzer_iv_brummbar_ger','icons/races/german/vehicles/brummbar_ger'],
    'panther':['icons/races/german/vehicles/panther_ger'],
    'wirbelwind':['icons/races/german/vehicles/wirbelwind_ger'],
    'tiger':['icons/races/german/vehicles/tiger_ger','icons/races/german/vehicles/tiger_heavy_tank_ger'],
    'infanterie kompanie':['icons/races/german/buildings/infanterie_kompanie_ger'],
    'panzergrenadier kompanie':['icons/races/german/buildings/panzergrenadier_kompanie_ger'],
    'luftwaffe kompanie':['icons/races/german/buildings/luftwaffe_kompanie_ger'],
    'panzer kompanie':['icons/races/german/buildings/panzer_kompanie_ger'],
    'medical bunker':['icons/races/german/buildings/medical_bunker_ger','icons/races/german/buildings/medic_station_ger'],
    'medical station':['icons/races/german/buildings/medic_station_ger','icons/races/german/buildings/medical_bunker_ger'],
    'siege camp':['icons/races/german/buildings/siege_camp_ger']
  },
  DAK:{
    'panzerpioneer':['icons/races/afrika_korps/symbols/panzerpioneers_ak'],
    'assault grenadier':['icons/races/afrika_korps/symbols/assault_grenadiers_ak'],
    'panzerjager':['icons/races/afrika_korps/symbols/panzerjagers_ak'],
    'kriegsmariner':['icons/races/afrika_korps/symbols/kriegsmariners_ak'],
    'mg34':['icons/races/afrika_korps/team_weapons/mg34_hmg_ak'],
    'bersaglieri':['icons/races/afrika_korps/symbols/bersaglieri_ak'],
    'guastatori':['icons/races/afrika_korps/symbols/guastatori_ak'],
    'panzergrenadier':['icons/races/afrika_korps/symbols/panzergrenadiers_ak'],
    '250':['icons/races/afrika_korps/vehicles/sdkfz_250_ak'],
    '8 rad':['icons/races/afrika_korps/vehicles/8_rad_ak'],
    'flakvierling':['icons/races/afrika_korps/vehicles/flakvierling_ak'],
    'pak 38':['icons/races/afrika_korps/team_weapons/pak_38_anti-tank_gun_ak'],
    'marder':['icons/races/afrika_korps/vehicles/marder_iii_ak'],
    'stug':['icons/races/afrika_korps/vehicles/stug_iii_ak'],
    'panzer iii':['icons/races/afrika_korps/vehicles/panzer_iii_ak'],
    'semovente':['icons/races/afrika_korps/vehicles/semovente_75_18_ak'],
    'carro armato':['icons/races/afrika_korps/vehicles/carro_armato_ak'],
    'light support kompanie':['icons/races/afrika_korps/buildings/light_support_kompanie_ak'],
    'panzerarmee kommand':['icons/races/afrika_korps/buildings/panzerarmee_kommand_ak'],
    'fire support elements':['icons/races/afrika_korps/buildings/fire_support_elements_ak']
  },
  USF:{
    'engineer':['icons/races/american/symbols/engineers_us'],
    'scout':['icons/races/american/symbols/scouts_us'],
    'rifleman':['icons/races/american/symbols/riflemen_us'],
    'captain':['icons/races/american/symbols/captain_us'],
    'ssf commandos':['icons/races/american/symbols/ssf_commandos_us'],
    'ranger':['icons/races/american/symbols/rangers_us'],
    'm29 weasel':['icons/races/american/vehicles/m29_weasel_us'],
    'm1 at gun':['icons/races/american/team_weapons/m1_57mm_at_gun_us'],
    'm8 greyhound':['icons/races/american/vehicles/m8_greyhound_us'],
    'chaffee':['icons/races/american/vehicles/m24_chaffee_us'],
    'sherman':['icons/races/american/vehicles/m4a1_sherman_us'],
    'hellcat':['icons/races/american/vehicles/m18_hellcat_us'],
    'barracks':['icons/races/american/buildings/barracks_us'],
    'weapons support center':['icons/races/american/buildings/weapons_support_center_us'],
    'infantry support center':['icons/races/american/buildings/infantry_support_center_us'],
    'mechanized support center':['icons/races/american/buildings/mechanized_support_center_us'],
    'motor pool':['icons/races/american/buildings/motor_pool_us'],
    'tank depot':['icons/races/american/buildings/tank_depot_us']
  },
  British:{
    'royal engineer section':['icons/races/british/symbols/royal_engineers_uk'],
    'infantry section':['icons/races/british/symbols/infantry_sections_uk'],
    'vickers machine gun team':['icons/races/british/team_weapons/vickers_hmg_uk'],
    '6 pounder':['icons/races/british/team_weapons/6_pounder_at_gun_uk'],
    'commando section':['icons/races/british/symbols/commando_section_uk'],
    'dingo light scout car':['icons/races/british/vehicles/dingo_uk'],
    'grant':['icons/races/british/vehicles/m3_grant_uk'],
    'centaur':['icons/races/british/vehicles/centaur_uk'],
    'churchill iv':['icons/races/british/vehicles/churchill_iv_uk'],
    'section command post':['icons/races/british/buildings/section_command_post_uk'],
    'platoon command post':['icons/races/british/buildings/platoon_command_post_uk'],
    'company command post':['icons/races/british/buildings/company_command_post_uk']
  }
};
`;
  const anchor = 'const BG_ICON_CACHE=new Map();';
  if (!html.includes(anchor)) throw new Error('Could not locate icon-cache insertion point.');
  html = html.replace(anchor, mapBlock + anchor);
}

const HELPERS_MARKER = 'function renderBuildVisualizer(arr,p)';
if (!html.includes(HELPERS_MARKER)) {
  const helperBlock = `
function buildStepInfo(step,num){const raw=String(step||'').trim();let name=raw,note='',type='infantry',isStart=false,badge=String(num);const start=raw.match(/^(?:Start|Starting unit)\\s*:\\s*(.+)$/i);if(start){isStart=true;name=start[1].trim();badge='START'}const ifMatch=!isStart?raw.match(/^(If [^:]+):\\s*(.+)$/i):null;if(ifMatch){note=ifMatch[1].trim();name=ifMatch[2].trim()}if(!note&&!isStart){const lower=raw.toLowerCase(),markers=[' only vs ',' if ',' when ',' after ',' vs '];let pick=null;markers.forEach(m=>{const idx=lower.indexOf(m);if(idx>0&&(!pick||idx<pick.idx))pick={idx,m}});if(pick){name=raw.slice(0,pick.idx).trim();note=raw.slice(pick.idx).trim()}}const src=(name+' '+note).toLowerCase();if(/(kompanie|company|quarters|bunker|station|camp|support elements|armory|hq)/i.test(name))type='tech';if(/(upgrade|scoped rifles|mp40|flamethrower|conversion|panzerschreck|panzerbuechse|officer|package|refit|antenna)/i.test(src))type='upgrade';if(/(paradrop|bombing run|loiter|reconnaissance|barrage|reserves|doctrine|firestorm|stuka|call[- ]?in)/i.test(src))type='battlegroup';if(/(kettenkrad|krad|221|250|251|8 rad|8-rad|half-track|halftrack|truck|tank|stug|stummel|marder|wirbelwind|panther|panzer iv|brummb[aä]r|tiger|crusader|matilda|bishop|dingo|humber|weasel|greyhound|chaffee|sherman|hellcat|stuart|tractor)/i.test(src))type='vehicle';const iconMap={infantry:'⚔',tech:'▦',vehicle:'◆',upgrade:'⚙',battlegroup:'★'},labelMap={infantry:'Unit',tech:'Tech',vehicle:'Vehicle',upgrade:'Upgrade',battlegroup:'BG choice'};return {raw,name,note,type,isStart,badge,icon:iconMap[type]||'•',label:labelMap[type]||'Step'}}
function normalizeBuildStepLookup(s=''){return normalizeBgToken(String(s).replace(/\\[[^\\]]*\\]/g,' ').replace(/[()]/g,' ').replace(/\\bproduction unlock\\b/ig,' ').replace(/\\bunlock\\b/ig,' ').replace(/\\bupgrades?\\b/ig,' ').replace(/\\bcall[- ]?in\\b/ig,' ').replace(/\\/[\\s\\S]*$/,' ').trim())}
function buildStepIconUrls(p,stepName){const factionMap=BUILD_STEP_ICON_OVERRIDES[p?.faction]||{},lookup=normalizeBuildStepLookup(stepName);const keys=Object.keys(factionMap).sort((a,b)=>b.length-a.length);for(const key of keys){if(lookup===key||lookup.includes(key))return factionMap[key].flatMap(coh3IconUrls)}return []}
function hydrateBuildIcons(p,root=document){const nodes=[...root.querySelectorAll('.buildstepicon[data-build-icon-name]')];nodes.forEach(node=>{const img=node.querySelector('.buildstepimg');if(!img)return;const urls=buildStepIconUrls(p,node.dataset.buildIconName||'');if(urls.length)loadImageCandidates(img,node,urls);else node.classList.add('failed')})}
function renderBuildVisualizer(arr,p){const steps=displayBuildSteps(arr||[]),phases=phaseBuild(steps);let stepNo=1;const legend='<div class="buildlegend"><span class="legenditem"><span class="legendicon">⚔</span> Units</span><span class="legenditem"><span class="legendicon">▦</span> Tech</span><span class="legenditem"><span class="legendicon">◆</span> Vehicles</span><span class="legenditem"><span class="legendicon">⚙</span> Upgrades</span><span class="legenditem"><span class="legendicon">★</span> Battlegroup</span><span class="legenditem"><span class="legendicon">S</span> Starting unit</span></div>';const blocks=phases.map((ph,i)=>{const cards=ph.steps.map(step=>{const info=buildStepInfo(step,stepNo);if(!info.isStart)stepNo++;return '<div class="buildstepcard type-'+info.type+' '+(info.note?'conditional ':'')+(info.isStart?'startcard':'')+'"><div class="buildstepbadge '+(info.isStart?'start':'')+'">'+info.badge+'</div><div class="buildsteptype">'+info.label+'</div><div class="buildstepbody"><div class="buildstepicon loading" data-build-icon-name="'+escapeHtml(info.name)+'"><span class="buildstepemoji">'+info.icon+'</span><img class="buildstepimg" alt="" loading="lazy"></div><div class="buildsteptext"><div class="buildstepname">'+escapeHtml(info.name)+'</div>'+(info.note?'<div class="buildstepnote">'+escapeHtml(info.note)+'</div>':'')+'</div></div></div>'}).join('');return '<div class="buildphase"><div class="buildphasehead"><div><div class="buildphasekicker">Phase '+(i+1)+'</div><h4>'+escapeHtml(ph.name)+'</h4></div></div><div class="buildstepgrid">'+cards+'</div></div>'}).join('');return '<div class="buildviz">'+legend+blocks+'<details class="buildtexttoggle"><summary>Show compact text version</summary><div class="build">'+buildHtml(steps)+'</div></details></div>'}
`;
  const anchor = 'function branchRows(rows){';
  if (!html.includes(anchor)) throw new Error('Could not locate build-helper insertion point.');
  html = html.replace(anchor, helperBlock + anchor);
}

if (!html.includes('${renderBuildVisualizer(displayBuild,p)}')) {
  const oldBuild = '<div class="card"><h3>${buildTitle}</h3><div class="build">${buildHtml(displayBuild)}</div>';
  const newBuild = '<div class="card"><h3>${buildTitle}</h3><div class="buildcallout">Quick-scan build order</div>${renderBuildVisualizer(displayBuild,p)}';
  if (!html.includes(oldBuild)) throw new Error('Could not locate main build-order card.');
  html = html.replace(oldBuild, newBuild);
  html = html.replace('${phaseSection(p,displayBuild)}', '');
}

if (!html.includes('hydrateBuildIcons(p,$("advisorContent"))')) {
  const oldHydrate = 'hydrateBattlegroupIcons(p,$("advisorContent"));';
  if (!html.includes(oldHydrate)) throw new Error('Could not locate advisor icon hydration call.');
  html = html.replace(oldHydrate, oldHydrate + 'hydrateBuildIcons(p,$("advisorContent"));');
}

html = html.replace(/CoH3 Build Advisor v1\.1\.\d+/g, `CoH3 Build Advisor ${VERSION}`);
await fs.writeFile(HTML_PATH, html);
console.log(`Visual build cards with CoH3 icon loading applied: ${VERSION}.`);
