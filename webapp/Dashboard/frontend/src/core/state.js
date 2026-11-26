'use strict';

const byId = id => document.getElementById(id);
const views = {
  live: ['◈', 'Live Monitor', 'Track network activity, detection trends, and system health.'],
  explorer: ['⌕', 'Traffic Explorer', 'Search recorded flows and pivot into connected IPs.'],
  alerts: ['⚑', 'Alerts', 'Review flows whose model score crossed the alert threshold.'],
  blocklist: ['⊘', 'IP Blocklist', 'Manage Flowwatch source IP rules in Windows Firewall.'],
  management: ['◫', 'Model Management', 'Review false positives, train candidate models, and manage versions.'],
  status: ['◉', 'System Status', 'Inspect capture analysis and the inference service.']
};
const attackClasses = [
  'Benign / Normal','Denial of Service (DoS)','Reconnaissance & Probing',
  'Exploits & PrivEsc','Credential Abuse (R2L)','Malware, C2 & Botnet'
];
const unclearCategory='Attack category unclear';
const noCategory='Not scored';
let modelInfo=null;
const captureSource="Analyzed PCAP";
const alertPageSize = 15;
const day = 86400000;
const presets = [
  ['5','Last 5 min'], ['15','Last 15 min'], ['60','Last hour'],
  ['10080','Last 7 days'], ['43200','Last 30 days'], ['525600','Last 365 days'],
  ['','All time'], ['custom','Custom dates']
];
let state = {
  view:'live', locked:false, ranking:'destinations',
  alertMode:'grouped', explorerSize:15, explorerSort:'newest',
  filters:{search:'', protocol:'', range:'15', from:'', to:'', decision:'', origin:'', status:''}, page:0,
  selection:null, tab:'Overview', role:'all', toastTimer:null
};
let review = {};
try { review = JSON.parse(localStorage.getItem('flowwatch-demo-review-v1') || '{}') || {}; } catch {}

let blocks = [];
let firewallInfo = null;
let blockSearch = '', blockFilter = '';
let capturedFlows=[];
let savedAlertFlows=[];
let totalFlowCount=null;
let totalAlertFlowCount=null;
let flowsNextBeforeId=null;
let alertsNextBeforeId=null;
let flowsPageInitialized=false;
let alertsPageInitialized=false;
let flowsLoadedMore=false;
let alertsLoadedMore=false;
let captureFlowCursors={};
let captureFlowCounts={};
let captureFlowLoadedMore={};
let captureAlertFlowCursors={};
let captureAlertFlowCounts={};
let captureAlertFlowLoadedMore={};
let loadingMoreFlows=false;
let liveStatus = null;
const allFlows = () => {
  const rows=new Map(capturedFlows.map(flow=>[flow.id,flow]));
  for (const flow of savedAlertFlows) {
    if (state.view==='alerts'||!rows.has(flow.id)) rows.set(flow.id,flow);
  }
  return [...rows.values()].sort((a,b)=>b.timestamp-a.timestamp);
};
const localDay = new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Bangkok',day:'numeric',month:'short',year:'numeric'});
const shortDay = new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Bangkok',day:'numeric',month:'short'});

function timeBounds() {
  const {range, from, to, bucket} = state.filters;
  if (bucket) return bucket;
  const flows = state.view==='alerts'?savedAlertFlows:capturedFlows;
  const latest = Math.max(...flows.map(flow=>flow.timestamp));
  const last = Math.max(latest,Date.now());
  const first = Math.min(last,...flows.map(flow=>flow.timestamp));
  if (range === 'custom') {
    const start = from ? Date.parse(from+'T00:00:00+07:00') : first;
    const end = to ? Date.parse(to+'T00:00:00+07:00')+day-1 : last;
    return {start,end};
  }
  return {start:range ? last-Number(range)*60000 : first,end:last};
}
function rangeText() {
  const {range,from,to,bucket}=state.filters;
  if (bucket) return localDay.format(bucket.start)+' '+time(bucket.start)+' – '+localDay.format(bucket.end)+' '+time(bucket.end);
  if (range!=='custom') return presets.find(([value])=>value===range)[1];
  return (from || 'Earliest')+' to '+(to || 'Latest');
}
function dateFilters() {
  return '<div class="date-fields" id="custom-dates"'+(state.filters.range!=='custom'?' hidden':'')+'>'+
    ['from','to'].map(key=>'<label>'+ (key==='from'?'From':'Through') +
      ' <input type="date" data-filter="'+key+'" value="'+escape(state.filters[key])+'"></label>').join('')+
    '<span id="date-error" role="alert"></span></div>';
}
const escape = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const num = value => new Intl.NumberFormat('en').format(value);
const time = timestamp => new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Bangkok',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(timestamp);
const valueText = value => value ?? '—';
const runName = run => 'RUN-' + String(run).padStart(3,'0');
const snapshot = flow => flow.file || flow.interface || flow.source;
const uiSymbol = glyph => '<span class="ui-symbol" aria-hidden="true">'+escape(glyph)+'</span>';
const actionSymbols = {blockIp:'⊘',unblockIp:'↶',editBlock:'✎',exportBlockIps:'↓',firewallRules:'⊙',
  searchIp:'⌕',reportFalsePositive:'⚑',clearRelatedDates:'↺'};
const button = (label, action, value = '', kind = 'btn') =>
  '<button type="button" class="' + kind + '" data-action="' + action + '" data-value="' + escape(value) + '">' +
  (action==='review'?uiSymbol(value==='Resolved'?'✓':'↶'):
    action==='bulkAlert'?uiSymbol({resolve:'✓',block:'⊘',report:'⚑'}[value]):
    actionSymbols[action]?uiSymbol(actionSymbols[action]):'') + label + '</button>';
const badge = (label, variant = '') => '<span class="badge ' + variant + '">' + label + '</span>';
const verdict = flow => badge(flow.kind==='flag'?'Suspicious':flow.kind==='unscored'?'Not scored':'No alert',flow.kind);
const scoreText = value => value==null?'—':(value*100).toFixed(1)+'%';
const modelVersion = flow => flow.prediction.model_id;
function category(prediction) {
  if (prediction.status!=='scored') return noCategory;
  return prediction.category_unclear?unclearCategory:attackClasses[prediction.class_id];
}
const sourceOptions=[['','All sources'],['Live Capture','Live Capture'],[captureSource,captureSource],['CENTRAL Test','CENTRAL Test']];
