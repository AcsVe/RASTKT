// Writes capacitor.config.json for the staff app. The app opens the server's /admin/m/ (the staff mobile app,
// served and updated by the server — a new look or feature needs no new APK). APP_URL comes from the workflow
// input or the repository variable APP_URL, so moving the site only needs a variable change and one rebuild.
const fs = require('fs');
const path = require('path');

const raw = (process.env.APP_URL || 'https://1.iajaward.org').trim().replace(/\/+$/, '');
let host;
try { host = new URL(raw).host; } catch (e) { console.error('APP_URL is not a valid URL:', raw); process.exit(1); }

const config = {
  appId: 'org.alraed.rastkt.admin',
  appName: 'فريق الدعم الفني',
  webDir: 'www',
  backgroundColor: '#0847B0',
  server: {
    url: raw + '/admin/m/',
    cleartext: raw.startsWith('http://'),
    allowNavigation: [host],
    errorPath: 'offline.html',
  },
  android: { allowMixedContent: false },
  plugins: {
    LocalNotifications: { smallIcon: 'ic_stat_icon', iconColor: '#0C67EC' },
    StatusBar: { backgroundColor: '#0a3a8a', style: 'DARK', overlaysWebView: false },
  },
};
fs.writeFileSync(path.join(__dirname, '..', 'capacitor.config.json'), JSON.stringify(config, null, 2));
console.log('capacitor.config.json written for', raw + '/admin/m/');
