const fs=require('fs');
// 读取CSV
let csv=fs.readFileSync('c:/Users/Huawei/Desktop/职教智能体/数控操作工_mohrss_raw.csv','utf8');
let lines=csv.split('\n').slice(1).filter(l=>l.trim());
let records=[];
lines.forEach(l=>{
  let cols=l.split('\t');
  if(cols.length>=7){
    records.push({
      co:cols[0].replace(/有限公司.*/,'有限公司').replace(/（代.*/,'').trim(),
      title:cols[1].trim(),
      city:cols[2].trim(),
      salary:cols[3].trim(),
      count:cols[4].trim(),
      req:cols[5].trim(),
      date:cols[6].trim(),
      org:cols[7].trim()
    });
  }
});
console.log('Total raw:',records.length);

// 去重：公司+城市相同合并，保留最新的日期和最详细的描述
let map={};
records.forEach(r=>{
  let key=r.co+'|'+r.city.split('省').pop().split('市').pop().split('区').pop().split('县').pop().split('街道').shift().trim();
  if(!map[key] || r.date>map[key].date) map[key]=r;
  else if(r.date===map[key].date && r.req.length>map[key].req.length) map[key]=r;
});
let uniq=Object.values(map);
console.log('After dedup:',uniq.length);

// 输出JSON
fs.writeFileSync('c:/Users/Huawei/Desktop/职教智能体/mohrss_dedup.json',JSON.stringify(uniq,null,2),'utf8');
console.log('Done');
