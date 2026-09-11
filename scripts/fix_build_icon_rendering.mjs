import fs from 'node:fs/promises';

const HTML_PATH = 'index.html';
const VERSION = 'v1.1.22';
const RENDER_MARKER = 'BUILD_ICON_RENDER_FIX_V1';
const BADGE_MARKER = 'BUILD_STEP_BADGE_INSIDE_V3';
const LEGACY_BADGE_MARKERS = ['BUILD_STEP_BADGE_OUTSIDE_V2', 'BUILD_STEP_BADGE_LAYOUT_V1'];

let html = await fs.readFile(HTML_PATH, 'utf8');
let changed = false;

// Keep the real CoH3 artwork fetchable while the symbol fallback remains visible.
if (!html.includes(RENDER_MARKER)) {
  const styleFix = `\n/* ${RENDER_MARKER}: keep CoH3 artwork fetchable while the fallback remains visible */\n.buildstepimg{display:block!important;opacity:0;visibility:hidden;transition:opacity .12s ease}\n.buildstepicon.loaded .buildstepimg{display:block!important;opacity:1;visibility:visible}\n.buildstepicon.failed .buildstepimg{display:none!important}\n`;
  if (!html.includes('</style>')) throw new Error('Could not find </style> in index.html');
  html = html.replace('</style>', `${styleFix}</style>`);
  changed = true;
}

// Put every step badge INSIDE the card, in its top-right corner. Both numbered
// badges and START use the same anchor. Reset the extra spacing from the old
// outside-badge layout so the cards return to their normal compact grid.
const badgeCss = `\n/* ${BADGE_MARKER}: all step badges sit inside the card's top-right corner */\n.buildstepgrid{column-gap:10px;row-gap:10px;padding-right:0}\n.buildstepcard{position:relative}\n.buildstepbadge:not(.start){top:8px;right:8px;left:auto;min-width:28px;width:28px;height:28px;padding:0;font-size:12px;line-height:1;z-index:3;box-shadow:0 2px 8px rgba(0,0,0,.25);transform:none}\n.buildstepbadge.start{top:8px;right:8px;left:auto;min-width:56px;width:auto;height:30px;padding:0 10px;font-size:12px;line-height:1;z-index:3;transform:none}\n`;

for (const marker of LEGACY_BADGE_MARKERS) {
  if (!html.includes(marker)) continue;
  const legacyBlock = new RegExp(`\\n/\\* ${marker}:[\\s\\S]*?(?=\\n/\\* BUILD_|\\n</style>)`, 'm');
  if (legacyBlock.test(html)) {
    html = html.replace(legacyBlock, '');
    changed = true;
  }
}

if (!html.includes(BADGE_MARKER)) {
  if (!html.includes('</style>')) throw new Error('Could not find </style> in index.html');
  html = html.replace('</style>', `${badgeCss}</style>`);
  changed = true;
}

// These tiny local assets are only hydrated for the visible build order and
// should load immediately rather than waiting on native lazy-loading.
const lazyPattern = /<img class="buildstepimg" alt="" loading="lazy">/g;
if (lazyPattern.test(html)) {
  html = html.replace(lazyPattern, '<img class="buildstepimg" alt="" decoding="async">');
  changed = true;
}

// Hydrate immediately after the advisor HTML has been inserted.
const timerPattern = /setTimeout\(\(\)=>\{try\{hydrateBuildIcons\(p,\$\((['"])advisorContent\1\)\)\}catch\(e\)\{console\.warn\((['"])Build icons could not be hydrated\.\2,e\)\}\},0\)/;
if (timerPattern.test(html)) {
  html = html.replace(timerPattern, "requestAnimationFrame(()=>{try{hydrateBuildIcons(p,$('advisorContent'))}catch(e){console.warn('Build icons could not be hydrated.',e)}})");
  changed = true;
}

// Improve the visible step category for common British/USF tech structures.
const oldTechTest = "if(/(kompanie|company|quarters|bunker|station|camp|support elements|armory|hq)/i.test(name))type='tech';";
const newTechTest = "if(/(kompanie|company|quarters|bunker|station|camp|support elements|armory|hq|command post|training center|support center|motor pool|tank depot|barracks|headquarters)/i.test(name))type='tech';";
if (html.includes(oldTechTest)) {
  html = html.replace(oldTechTest, newTechTest);
  changed = true;
}

const oldUpgradeTest = "if(/(upgrade|scoped rifles|mp40|flamethrower|conversion|panzerschreck|panzerbuechse|officer|package|refit|antenna)/i.test(src))type='upgrade';";
const newUpgradeTest = "if(/(upgrade|training|scoped rifles|mp40|flamethrower|conversion|panzerschreck|panzerbuechse|officer|package|refit|antenna)/i.test(src))type='upgrade';";
if (html.includes(oldUpgradeTest)) {
  html = html.replace(oldUpgradeTest, newUpgradeTest);
  changed = true;
}

const versioned = html.replace(/CoH3 Build Advisor v1\.1\.\d+/g, `CoH3 Build Advisor ${VERSION}`);
if (versioned !== html) {
  html = versioned;
  changed = true;
}

if (changed) {
  await fs.writeFile(HTML_PATH, html);
  console.log(`Fixed build-order CoH3 icon rendering and inside top-right badge layout; ${VERSION}.`);
} else {
  console.log(`Build-order icon rendering and inside top-right badge layout already present; ${VERSION}.`);
}
