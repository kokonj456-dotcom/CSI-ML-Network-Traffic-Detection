'use strict';

function metric(label,symbol,value,note,action,extra='') {
  return button('<span class="metric-label"><span class="metric-symbol" aria-hidden="true">' + symbol + '</span>' + label +
    '</span><span class="metric-value">' + value + '</span><span class="metric-note">' + note + '</span>',
    'summary',action,'metric '+extra);
}
function rankFlows(flows, group) {
  const items = new Map();
  for (const flow of flows) {
    const name = group(flow);
    const item = items.get(name) || {name, total:0, flags:0};
    item.total++;
    if (flow.kind==='flag') item.flags++;
    items.set(name,item);
  }
  return [...items.values()].sort((a,b)=>b.total-a.total || a.name.localeCompare(b.name)).slice(0,5);
}
function rankingRows(items,action,showFlags=false) {
  if (!items.length) return '<p class="muted">No records for this selection.</p>';
  const max=items[0].total;
  return items.map(({name,total,flags})=>{
    const group=action==='destination' ? destinationLabel(JSON.parse(name)) : name;
    const info=showFlags ? num(flags)+' suspicious of '+num(total)+' flows' : num(total)+' records';
    return button('<span class="rank-label">'+escape(group)+'</span><span class="rank-bar"><i style="width:'+(100*total/max)+'%">'+
      (showFlags&&flags?'<b style="width:'+(100*flags/total)+'%"></b>':'')+'</i></span><span class="rank-value" title="'+info+'">'+
      num(total)+(showFlags&&flags?' <em>('+num(flags)+')</em>':'')+'</span>',action,name,'rank-item');
  }).join('');
}
function renderMetrics() {
  if (!byId('metrics')) return;
  const flows=filtered();
  const alerts=flows.filter(flow=>flow.kind==='flag');
  const unreviewed=alerts.filter(flow=>!review[flow.id]).length;
  const ratio=flows.length ? (100*alerts.length/flows.length).toFixed(1) : '0.0';
  byId('trend-range').textContent=rangeText()+' · ICT';
  const latestFlow=allFlows()[0];
  byId('run-status').textContent=latestFlow?'Latest flow '+localDay.format(latestFlow.timestamp)+' '+time(latestFlow.timestamp)+' ICT':
    liveStatus?.running?'Waiting for inbound flows':'Live capture not connected';
  byId('metrics').innerHTML=
    metric('Analyzed flows','⇄',num(flows.filter(flow=>flow.prediction.status==='scored').length),'In selected range','flows')+
    metric('Flagged flows','⚑',num(alerts.length),ratio+'% of matching flows','flagged','alert-metric')+
    metric('Destination IPs','◎',num(new Set(flows.map(flow=>flow.dst).filter(Boolean)).size),'Unique observed destinations','destinations')+
    metric('Unreviewed alerts','◉',num(unreviewed),'In selected range','unreviewed');
  byId('inference-health').textContent=num(flows.filter(flow=>flow.prediction.status==='not_scored').length)+' not scored';
  const protocols=state.ranking==='protocols';
  byId('ranking-title').textContent=protocols?'Top Protocols':'Top Destinations';
  byId('rank-rows').innerHTML=rankingRows(rankFlows(protocols?flows:flows.filter(flow=>flow.dst),flow=>protocols?flow.app:JSON.stringify([flow.dst,flow.dport])),protocols?'protocol':'destination',true);
  byId('alert-rows').innerHTML=rankingRows(rankFlows(alerts,flow=>flow.label),'alertType');
  const latest=alerts[0];
  byId('latest-alert').innerHTML=latest
    ? '<span><strong>Latest alert</strong> '+shortDay.format(latest.timestamp)+' '+time(latest.timestamp)+' ICT · '+escape(latest.app)+' · '+escape(destinationLabel([latest.dst,latest.dport]))+'</span>'+button('View alert ›','latestAlert',latest.id,'text-button')
    : '<span>No alerts in this selection.</span>';
  byId('health').innerHTML=button('<strong>System health</strong>', 'navigate','status','health-link')+
    [['Live capture',liveStatus?.running?'Running':liveStatus?.error?'Stopped with error':'Not connected'],
      ['Recent flows',num(capturedFlows.length)],['Model',modelInfo?'Available':'Unavailable']]
      .map(([name,value])=>'<div><span>'+name+'</span><strong>'+value+'</strong></div>').join('');
  drawChart();
}
const themeKey='flowwatch-color-theme';
function setTheme(theme,save=false) {
  document.documentElement.dataset.theme=theme;
  document.querySelectorAll('[data-action="theme"]').forEach(control=>
    control.setAttribute('aria-pressed',String(control.dataset.value===theme)));
  if (save) {
    try {localStorage.setItem(themeKey,theme);} catch {}
  }
  drawChart();
}
function initialTheme() {
  try {return localStorage.getItem(themeKey)==='dark'?'dark':'light';}
  catch {return 'light';}
}
let chartGeometry;
function drawChart(active=-1) {
  const canvas=byId('timeline');
  if (!canvas) return;
  const width=canvas.clientWidth, height=canvas.clientHeight;
  if (!width || !height) return;
  const palette=getComputedStyle(document.documentElement);
  const grid=palette.getPropertyValue('--grid-chart').trim();
  const chartText=palette.getPropertyValue('--muted').trim();
  const dpr=window.devicePixelRatio || 1;
  canvas.width=width*dpr;
  canvas.height=height*dpr;
  const ctx=canvas.getContext('2d');
  ctx.scale(dpr,dpr);
  const left=75,right=width-10,top=10,bottom=height-24;
  const {start:from,end}=timeBounds();
  const span=Math.max(0,end-from);
  const interval=[60000,300000,900000,3600000,21600000,day,7*day,14*day,30*day,60*day]
    .find(bucket=>span/bucket<=24) || Math.ceil(span/(24*day))*day;
  const offset = 7*3600000;
  const start=Math.floor((from+offset)/interval)*interval-offset;
  const count=Math.max(2,Math.ceil((end-start+1)/interval));
  const bins=Array.from({length:count},(_,i)=>({time:start+i*interval,total:0,flags:0}));
  for (const flow of filtered()) {
    const bin=bins[Math.floor((flow.timestamp-start)/interval)];
    if (bin) { bin.total++; if (flow.kind==='flag') bin.flags++; }
  }
  const step=(right-left)/(count-1);
  const x=i=>left+i*step;
  const split=Math.round(height*.55);
  const labels=Math.min(count,width>380?6:4);
  ctx.font='11px Segoe UI';
  for (const [key,label,color,regionTop,regionBottom] of [
    ['total','Flows',palette.getPropertyValue('--flows-chart').trim(),top,split-10],
    ['flags','Alerts',palette.getPropertyValue('--alerts-chart').trim(),split+2,bottom]
  ]) {
    const cap=Math.max(1,...bins.map(bin=>bin[key]));
    const y=value=>regionBottom-(regionBottom-regionTop-3)*value/cap;
    ctx.textAlign='left';
    ctx.fillStyle=color;
    ctx.fillText(label,0,regionTop+10);
    ctx.fillStyle=chartText;
    ctx.textAlign='right';
    ctx.fillText(cap,left-8,regionTop+10);
    ctx.fillText('0',left-8,regionBottom);
    for (const line of [regionTop,Math.round((regionTop+regionBottom)/2),regionBottom]) {
      ctx.strokeStyle=grid;
      ctx.beginPath();ctx.moveTo(left,line);ctx.lineTo(right,line);ctx.stroke();
    }
    const trace=()=>bins.forEach((bin,i)=>i===0?ctx.moveTo(x(i),y(bin[key])):ctx.lineTo(x(i),y(bin[key])));
    ctx.beginPath();trace();ctx.lineTo(right,regionBottom);ctx.lineTo(left,regionBottom);ctx.closePath();
    ctx.fillStyle=color+'19';ctx.fill();
    ctx.beginPath();trace();ctx.strokeStyle=color;ctx.lineWidth=2;ctx.stroke();ctx.lineWidth=1;
    if (bins[active]) {
      ctx.strokeStyle='#9aa4bc';ctx.beginPath();ctx.moveTo(x(active),regionTop);ctx.lineTo(x(active),regionBottom);ctx.stroke();
      ctx.fillStyle=color;ctx.beginPath();ctx.arc(x(active),y(bins[active][key]),3.5,0,Math.PI*2);ctx.fill();
    }
  }
  ctx.fillStyle=chartText;
  for (let label=0;label<labels;label++) {
    const i=Math.round(label*(count-1)/(labels-1));
    ctx.textAlign=i===0?'left':i===count-1?'right':'center';
    ctx.fillText(span<=day ? time(bins[i].time).slice(0,5) : shortDay.format(bins[i].time),x(i),height-6);
  }
  chartGeometry={left,step,bins,width,span,interval};
  return chartGeometry;
}
