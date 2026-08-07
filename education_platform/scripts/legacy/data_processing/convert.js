// Read raw data and convert to JSON
const fs = require('fs');
const html = fs.readFileSync('数控操作工_完整数据展示平台.html', 'utf8');
const match = html.match(/var J=\[([\s\S]*?)\];/);
if (!match) { console.log('No data found'); process.exit(1); }
const raw = match[1];
// Split into individual objects
const objs = [];
let depth = 0, start = -1;
for (let i = 0; i < raw.length; i++) {
  if (raw[i] === '{') { if (depth === 0) start = i; depth++; }
  else if (raw[i] === '}') { depth--; if (depth === 0 && start >= 0) { objs.push(raw.substring(start, i+1)); start = -1; } }
}
console.log('Found ' + objs.length + ' objects');

// Convert each JS object to proper JSON
const results = [];
objs.forEach((str, idx) => {
  try {
    // Quote unquoted keys
    let json = str.replace(/([{,]\s*)([a-zA-Z_]\w*)\s*:/g, '$1"$2":');
    // Replace single quotes with double quotes (for string values)  
    json = json.replace(/'/g, '"');
    // Fix trailing commas before }
    json = json.replace(/,\s*}/g, '}');
    const obj = JSON.parse(json);
    results.push(obj);
  } catch(e) {
    console.log('Error at obj ' + idx + ': ' + e.message);
  }
});
console.log('Parsed ' + results.length + ' objects');
fs.writeFileSync('数控操作工_招聘数据.json', JSON.stringify(results, null, 2), 'utf8');
console.log('Done: ' + results.length + ' records');
