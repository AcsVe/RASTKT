// Writes capacitor.config.json for the target server. The app is a thin
// shell around the live site, so the only real setting is its URL — taken
// from the APP_URL env var (the workflow feeds it from a workflow input or
// the repository variable APP_URL), which means moving the site to a new
// domain later only needs a variable change + one APK rebuild.
const fs = require('fs');
const path = require('path');

const raw = (process.env.APP_URL || 'https://rastkt.onrender.com').trim().replace(/\/+$/, '');
let host;
try { host = new URL(raw).host; } catch (e) { console.error('APP_URL is not a valid URL:', raw); process.exit(1); }

const config = {
  appId: 'org.alraed.rastkt',
  appName: 'الدعم الفني',
  webDir: 'www',
  backgroundColor: '#1B3358',
  server: {
    url: raw + '/',
    cleartext: raw.startsWith('http://'),
    allowNavigation: [host],
    errorPath: 'offline.html',
  },
  android: { allowMixedContent: false },
};
fs.writeFileSync(path.join(__dirname, '..', 'capacitor.config.json'), JSON.stringify(config, null, 2));
console.log('capacitor.config.json written for', raw);
