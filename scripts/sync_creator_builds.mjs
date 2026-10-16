import fs from 'node:fs/promises';

// The standalone page carries its own copy of the creator library.
const data = JSON.parse(await fs.readFile('coh3_build_advisor_data.json', 'utf8'));
const html = await fs.readFile('index.html', 'utf8');
const marker = /const CREATOR_BUILDS=.*?;\nconst BG_META=/;
if (!Array.isArray(data.creatorBuilds) || !marker.test(html)) {
  throw new Error('Creator library or embedded CREATOR_BUILDS block is missing.');
}
await fs.writeFile(
  'index.html',
  html.replace(marker, () => `const CREATOR_BUILDS=${JSON.stringify(data.creatorBuilds)};\nconst BG_META=`)
);
console.log(`Synchronized ${data.creatorBuilds.length} creator builds.`);
