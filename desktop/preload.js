const { contextBridge } = require('electron');

function getArgValue(name) {
  const prefix = `--${name}=`;
  const arg = process.argv.find((item) => item.startsWith(prefix));
  return arg ? arg.slice(prefix.length) : '';
}

contextBridge.exposeInMainWorld('geoDesktop', {
  apiBaseUrl: getArgValue('geo-api-base'),
  isDesktop: true,
});
