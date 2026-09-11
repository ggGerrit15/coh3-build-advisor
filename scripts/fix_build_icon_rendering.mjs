import fs from 'node:fs/promises';

const HTML_PATH = 'index.html';
const VERSION = 'v1.1.20';
const MARKER = 'BUILD_ICON_RENDER_FIX_V1';

let html = await fs.readFile(HTML_PATH, 'utf8');
let changed = false;

// The build-order images were present and correctly mapped, but the CSS hid
// them with display:none until the image load event fired. Together with
// native lazy-loading this can create a deadlock: a hidden lazy image is not
// fetched, so the load event never fires, so the image never becomes visible.
// Keep the image in the layout/fetch pipeline and reveal it only after load.
if (!html.includes(MARKER)) {
  const styleFix = `\n/* ${MARKER}: keep CoH3 artwork fetchable while the fallback remains visible */\n.buildstepimg{display:block!important;opacity:0;visibility:hidden;transition:opacity .12s ease}\n.buildstepicon.loaded .buildstepimg{display:block!important;opacity:1;visibility:visible}\n.buildstepicon.failed .buildstepimg{display:none!important}\n`;
  if (!html.includes('</style>')) throw new Error('Could not find </style> in index.html');
  html = html.replace('</style>', `${styleFix}</style>`);
  changed = true;
}

// These tiny local assets should not use native lazy-loading. They are only
// hydrated for the currently visible build order and should load immediately.
const lazyPattern = /<img class="buildstepimg" alt="" loading="lazy">/g;
if (lazyPattern.test(html)) {
  html = html.replace(lazyPattern, '<img class="buildstepimg" alt="" decoding="async">');
  changed = true;
}

// Make the post-render hydration timing explicit. requestAnimationFrame runs
// after the advisor HTML has been inserted and before the next paint.
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
  console.log(`Fixed build-order CoH3 icon rendering; ${VERSION}.`);
} else {
  console.log(`Build-order icon rendering fix already present; ${VERSION}.`);
}
