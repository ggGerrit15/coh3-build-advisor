import fs from 'node:fs/promises';
import path from 'node:path';

const HTML_PATH = 'index.html';
const MANIFEST_PATH = 'assets/build-icons.json';
const REPORT_PATH = 'assets/build-icons-report.json';
const OUT_DIR = 'assets/build-icons';
const CDN_TREE = 'https://api.github.com/repos/cohstats/coh3-cdn/git/trees/master?recursive=1';
const CDN_RAW = 'https://raw.githubusercontent.com/cohstats/coh3-cdn/master/public';
const CDN = 'https://cdn.coh3stats.com';
const VERSION = 'v1.1.18';

const CDN_RACES = { Wehrmacht: 'german', DAK: 'afrika_corps', USF: 'american', British: 'british' };
const GENERIC = new Set(['squad','team','section','medium','heavy','light','unit','gun','tank','vehicle','the','production','unlock','upgrade','upgrades','call','in','anti','support']);
const BAD_MODIFIERS = ['command','king','flak','medical','mortar','bunker','emplacement','recon','flame','artillery','repair','fuel','scout'];
const BLOCKLIST = new Set(['Wehrmacht|support elements']);

const EXACT = {
  'Wehrmacht|mg42': 'export/icons/races/german/team_weapons/hmg_mg42_ger.webp',
  'Wehrmacht|mortar': 'export/icons/races/german/team_weapons/mortar_81mm_ger.webp',
  'Wehrmacht|pak 40': 'export/icons/races/german/team_weapons/at_gun_75mm_ger.webp',
  'Wehrmacht|pak': 'export/icons/races/german/team_weapons/at_gun_75mm_ger.webp',
  'Wehrmacht|panzer iv': 'export/icons/races/german/vehicles/panzer_iv_german.webp',
  'Wehrmacht|panzer iv command tank': 'export/icons/races/german/vehicles/panzer_iv_cmd_german.webp',
  'Wehrmacht|tiger': 'export/icons/races/german/vehicles/tiger_german.webp',
  'Wehrmacht|251 half track': 'export/icons/races/german/vehicles/halftrack_german.webp',
  'Wehrmacht|stummel': 'export/icons/races/german/vehicles/halftrack_stummel_german.webp',
  'Wehrmacht|stummel conversion': 'export/icons/races/german/vehicles/halftrack_stummel_german.webp',
  'Wehrmacht|kettenkrad': 'export/icons/races/german/vehicles/kettenkrad_german.webp',
  'Wehrmacht|brummbar': 'export/icons/races/german/vehicles/brummbar_german.webp',
  'Wehrmacht|sturmtiger': 'export/icons/races/german/vehicles/sturmtiger_german.webp',
  'Wehrmacht|panther': 'export/icons/races/german/vehicles/panther_german.webp',
  'Wehrmacht|wirbelwind': 'export/icons/races/german/vehicles/wirbelwind_german.webp',
  'Wehrmacht|stug iii': 'export/icons/races/german/vehicles/stug_iii_german.webp',
  'Wehrmacht|stug iii g': 'export/icons/races/german/vehicles/stug_iii_german.webp',
  'Wehrmacht|obice': 'export/icons/races/german/team_weapons/tw_howitzer_obice_210_ger.webp',
  'Wehrmacht|officer quarters': 'export/icons/races/german/upgrades/officer_quarters_for_wehrmacht.webp',
  'Wehrmacht|convert pioneer to sturmpioneer': 'export/icons/races/german/infantry/sturmpioneer_ger.webp',
  'Wehrmacht|sturmpioneer upgrade': 'export/icons/races/german/infantry/sturmpioneer_ger.webp',
  'DAK|mg34': 'export/icons/races/afrika_corps/team_weapons/hmg_mg34_ak.webp',
  'DAK|panzerpioneer': 'export/icons/races/afrika_corps/infantry/panzerpioneer_ak.webp',
  'DAK|assault grenadier': 'export/icons/races/afrika_corps/infantry/assault_panzergrenadier_ak.webp',
  'DAK|assault grenadiers': 'export/icons/races/afrika_corps/infantry/assault_panzergrenadier_ak.webp',
  'DAK|bersaglieri': 'export/icons/races/afrika_corps/infantry/bersaglieri_ak.webp',
  'DAK|guastatori': 'export/icons/races/afrika_corps/infantry/guastatori_ak.webp',
  'DAK|2 5t medical truck': 'export/icons/races/afrika_corps/vehicles/2_5_truck_medical_ak.webp'
};

function norm(value = '') { return String(value).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/ß/g,'ss').replace(/[^a-z0-9]+/g,' ').replace(/\s+/g,' ').trim(); }
function tokens(value = '') { return norm(value).split(' ').filter(Boolean); }
function simple(value = '') { return tokens(value).filter(x => !GENERIC.has(x)).join(' '); }
function slug(value = '') { return norm(value).replaceAll(' ','-').replace(/^-+|-+$/g,'') || 'icon'; }
function expectedCategory(step = '') {
  const q = norm(step);
  if (/(kompanie|company|quarters|bunker|station|camp|command post|support center|motor pool|tank depot|armory|hq|elements|training center|headquarters)/.test(q)) return 'buildings';
  if (/(mg\d*|hmg|pak\b|mortar|howitzer|pounder|at gun|anti tank gun|flak 36|flak 38|recoilless)/.test(q)) return 'team_weapons';
  if (/(upgrade|package|training|conversion|refit|bars?\b|grenade package|officer quarters)/.test(q)) return 'upgrades';
  if (/(half ?track|kettenkrad|\b\d+ rad\b|greyhound|chaffee|sherman|hellcat|stuart|dingo|humber|grant|centaur|churchill|panzer|tiger|stug|stummel|marder|wirbelwind|brummbar|tractor|truck|carro|semovente|flakvierling|weasel|bishop)/.test(q)) return 'vehicles';
  return 'infantry';
}
async function getJson(url){const r=await fetch(url,{headers:{'user-agent':'coh3-build-advisor-icon-qa',accept:'application/vnd.github+json'}});if(!r.ok)throw new Error(`${r.status} ${r.statusText}: ${url}`);return r.json()}
async function getBinary(url){const r=await fetch(url,{headers:{'user-agent':'coh3-build-advisor-icon-qa'}});if(!r.ok)return null;const b=Buffer.from(await r.arrayBuffer());return b.length>=250?b:null}
async function fetchRel(rel){const clean=String(rel).replace(/^public\//,'');for(const url of [`${CDN_RAW}/${clean}`,`${CDN}/${clean}`]){const buf=await getBinary(url);if(buf)return{buf,rel:clean,url}}return null}
function assetBase(pathName){const file=pathName.split('/').pop().replace(/\.webp$/i,'').replace(/_portrait$/i,'');return norm(file.replace(/_(?:german|ger|british|uk|american|us|afrika_corps|afrika|ak|dak)$/i,''))}
function categoryFromPath(pathName){const m=/\/icons\/races\/[^/]+\/([^/]+)\//.exec(pathName);return m?m[1]:''}
function assetIndex(tree,faction){const race=CDN_RACES[faction],prefix=`public/export/icons/races/${race}/`;return(tree.tree||[]).filter(x=>x.type==='blob'&&x.path.startsWith(prefix)&&x.path.endsWith('.webp')&&!x.path.endsWith('_portrait.webp')).map(x=>({path:x.path,rel:x.path.replace(/^public\//,''),base:assetBase(x.path),category:categoryFromPath(x.path)}))}
function scoreAsset(step,asset){const q=norm(step),qs=simple(q),a=asset.base,as=simple(a);if(!q||!a)return-999;let score=0;if(a===q)score+=1000;if(as&&as===qs)score+=700;if(a.includes(q)||q.includes(a))score+=160;const qt=tokens(q).filter(x=>!GENERIC.has(x)),at=new Set(tokens(a));for(const t of qt){if(at.has(t))score+=/^\d+$/.test(t)?65:36;else if([...at].some(h=>h.length>=4&&t.length>=4&&(h.startsWith(t)||t.startsWith(h))))score+=8;else score-= /^\d+$/.test(t)?150:22}for(const mod of BAD_MODIFIERS)if(!q.includes(mod)&&a.includes(mod))score-=200;const expected=expectedCategory(q);if(asset.category===expected)score+=100;else if(expected==='infantry'&&asset.category==='symbols')score+=20;else if(['infantry','vehicles','team_weapons','buildings','upgrades'].includes(asset.category))score-=40;return score}
function exactFor(faction,search){const q=norm(search),direct=EXACT[`${faction}|${q}`];if(direct)return direct;const rows=Object.entries(EXACT).filter(([k])=>k.startsWith(`${faction}|`)).map(([k,v])=>[k.split('|').slice(1).join('|'),v]).sort((a,b)=>b[0].length-a[0].length);for(const[k,v]of rows)if(q===k||q.startsWith(`${k} `))return v;return null}
function isSameFactionSource(faction,source=''){const race=CDN_RACES[faction];return String(source).includes(`/races/${race}/`)}
function patchManifest(html,manifest){const block=`const BUILD_ORDER_ICON_PATHS=${JSON.stringify(manifest)};\n`;if(/const BUILD_ORDER_ICON_PATHS=.*?;\n/.test(html))html=html.replace(/const BUILD_ORDER_ICON_PATHS=.*?;\n/,block);else throw new Error('BUILD_ORDER_ICON_PATHS not found in index.html');return html.replace(/CoH3 Build Advisor v1\.1\.\d+/g,`CoH3 Build Advisor ${VERSION}`)}

const [tree,report]=await Promise.all([getJson(CDN_TREE),JSON.parse(await fs.readFile(REPORT_PATH,'utf8'))]);
const manifest=JSON.parse(await fs.readFile(MANIFEST_PATH,'utf8'));
const all=[...(report.resolved||[]),...(report.unresolved||[])];
const unique=[...new Map(all.map(x=>[`${x.faction}|${x.lookup}`,x])).values()];
const indexes=Object.fromEntries(Object.keys(CDN_RACES).map(f=>[f,assetIndex(tree,f)]));
const previousByKey=new Map((report.resolved||[]).map(x=>[`${x.faction}|${x.lookup}`,x]));
const fixes=[],removed=[];

for(const item of unique){
  const key=`${item.faction}|${item.lookup}`;
  const search=item.search||item.step||item.lookup;
  if(BLOCKLIST.has(`${item.faction}|${norm(search)}`)||BLOCKLIST.has(key)){
    if(manifest[key]){delete manifest[key];removed.push({key,reason:'ambiguous tech label; keep symbol fallback'})}
    continue;
  }
  let selected=null,method='';
  const exact=exactFor(item.faction,search);
  if(exact){selected=await fetchRel(exact);method='exact'}
  if(!selected){
    const ranked=indexes[item.faction].map(a=>({a,score:scoreAsset(search,a)})).sort((x,y)=>y.score-x.score);
    const best=ranked[0],second=ranked[1],margin=best?best.score-(second?.score??-999):0;
    if(best&&(best.score>=260||(best.score>=190&&margin>=55))){selected=await fetchRel(best.a.rel);method=`cdn:${best.score}/${margin}`}
  }
  if(selected){
    const fileName=`${slug(item.faction)}--${slug(item.lookup)}.webp`,outPath=path.join(OUT_DIR,fileName);await fs.writeFile(outPath,selected.buf);manifest[key]=outPath.replaceAll('\\','/');fixes.push({key,search,source:selected.rel,method});continue;
  }
  const previous=previousByKey.get(key);
  if(previous&&manifest[key]&&!isSameFactionSource(item.faction,previous.sourceIcon)){
    delete manifest[key];removed.push({key,reason:`removed non-faction/ambiguous source ${previous.sourceIcon||'unknown'}`});
  }
}

await fs.writeFile(MANIFEST_PATH,JSON.stringify(manifest,null,2)+'\n');
report.iconQa={version:VERSION,generatedAt:new Date().toISOString(),sameFactionCdnFixes:fixes.length,removedAmbiguous:removed.length,fixes,removed};
await fs.writeFile(REPORT_PATH,JSON.stringify(report,null,2)+'\n');
let html=await fs.readFile(HTML_PATH,'utf8');html=patchManifest(html,manifest);await fs.writeFile(HTML_PATH,html);
console.log(`Build icon QA complete: ${fixes.length} same-faction CDN mappings applied; ${removed.length} ambiguous mappings removed.`);
