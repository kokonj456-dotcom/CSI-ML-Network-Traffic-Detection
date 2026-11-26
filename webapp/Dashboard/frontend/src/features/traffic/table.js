'use strict';

function renderTable() {
  const explorer = state.view==='explorer';
  const pageSize = explorer ? state.explorerSize : alertPageSize;
  const alerts = state.view==='alerts';
  const individual=filtered();
  const grouped=alerts && state.alertMode==='grouped';
  const rows=grouped?groupedAlerts(individual):individual;
  if (explorer && state.explorerSort==='oldest') rows.sort((a,b)=>a.timestamp-b.timestamp || a.id.localeCompare(b.id));
  if (explorer && state.explorerSort==='score') rows.sort((a,b)=>(b.score ?? -1)-(a.score ?? -1) || b.timestamp-a.timestamp);
  const index = Math.min(state.page,Math.max(0,Math.ceil(rows.length/pageSize)-1));
  state.page = index;
  const first = index * pageSize;
  const table = byId('table-rows');
  if (!table) return;
  if (explorer) {
    const suspicious=rows.filter(flow=>flow.kind==='flag').length;
    byId('explorer-system').textContent=totalFlowCount==null?'—':num(totalFlowCount);
    byId('explorer-flagged').textContent=num(suspicious);
    byId('explorer-peers').textContent=num(new Set(rows.map(flow=>flow.dst).filter(Boolean)).size);
  }
  if (alerts) {
    const counts={total:individual.length,new:0,ack:0,resolved:0};
    for (const flow of individual) counts[review[flow.id]==='Resolved'?'resolved':review[flow.id]==='Acknowledged'?'ack':'new']++;
    for (const [key,count] of Object.entries(counts)) byId('alert-total-'+key).textContent=num(count);
  }
  const visible=rows.slice(first,first+pageSize);
  if (alerts) alertSelectionRows=visible.map(row=>grouped?row.ids:[row.id]);
  table.innerHTML = (grouped?visible.map(alertGroupRow):visible.map((flow,index) =>
    '<tr data-action="flow" data-value="'+escape(flow.id)+'"'+(explorer&&flow.kind==='flag'?' class="flagged-row"':'')+'>'+
    (alerts?alertCheckbox(index,'Select alert '+flow.id):'')+'<td class="mono">' + button((explorer||state.filters.range==='custom'||Number(state.filters.range)>1440||!state.filters.range?shortDay.format(flow.timestamp)+' ':'')+time(flow.timestamp),'flow',flow.id,'text-button') +
    (explorer || flow.dataset ? '<small class="flow-sub">'+escape(flow.dataset?.record_id||flow.id)+'</small>' : '')+
    '</td><td>' + flowEndpoint(flow,'src') + '</td><td>' + flowEndpoint(flow,'dst') +
    (explorer && flow.domain ? '<small class="flow-sub flow-domain" title="'+escape(flow.domain)+'">'+
      button(escape(flow.domain),'explorerDomain',flow.domain,'text-button')+'</small>' : '')+
    '</td><td>' + badge(escape(flow.app)) +
    (explorer && flow.app!==flow.protocol ? ' <small class="transport">'+escape(flow.protocol)+'</small>' : '')+
    '</td><td>' + (alerts?escape(flow.label):verdict(flow)) + '</td>'+
    (explorer?'<td>'+escape(flow.label)+(flow.dataset?'<small class="flow-sub">Actual · '+escape(attackClasses[flow.dataset.attack_category_id])+'</small>':'')+'</td>':'')+'<td class="mono">' +scoreText(flow.score)+ '</td>' +
    (explorer ? '<td>'+badge(escape(flow.source))+'</td>' : '')+
    (alerts ? '<td>' + badge(escape(review[flow.id] || 'New'),review[flow.id]?'reviewed':'flag') +
      (flow.falsePositiveReported?' '+badge('False positive reported','reviewed'):'') + '</td>' : '') +
    '<td>' + button('<span aria-hidden="true">›</span><span class="sr-only">Inspect ' + flow.id + '</span>','flow',flow.id,'text-button row-arrow') + '</td></tr>'
  )).join('') || '<tr><td class="empty" colspan="' + (explorer||alerts?9:7) + '">No flows match these filters. Try a wider time range or reset the filters.</td></tr>';
  if (alerts) updateAlertSelection();
  byId('table-prev').disabled = index===0;
  byId('table-next').disabled = (index+1)*pageSize>=rows.length;
  byId('export').disabled = !rows.length;
  const loadMore=byId('load-more-flows');
  if (loadMore) {
    const captureId=state.filters.captureFileId;
    const cursor=captureId
      ? alerts?captureAlertFlowCursors[captureId]:captureFlowCursors[captureId]
      : alerts?alertsNextBeforeId:flowsNextBeforeId;
    loadMore.disabled=loadingMoreFlows||!cursor;
    loadMore.hidden=!cursor&&!loadingMoreFlows;
    loadMore.textContent=loadingMoreFlows?'Loading…':'Load 250 more';
  }
  const total=state.filters.captureFileId
    ? alerts
      ? (captureAlertFlowCounts[state.filters.captureFileId]??totalAlertFlowCount)
      : (captureFlowCounts[state.filters.captureFileId]??totalFlowCount)
    : alerts?totalAlertFlowCount:totalFlowCount;
  const totalLabel=state.filters.captureFileId?'in selected capture':alerts?'alerts in system':'flows in system';
  const systemTotal=total==null?'Database total unavailable':num(total)+' '+totalLabel;
  byId('result-count').textContent=rows.length
    ? (first+1)+'–'+Math.min(first+pageSize,rows.length)+' of '+num(rows.length)+' loaded '+(grouped?'groups':alerts?'alerts':'flows')+
      ' · '+systemTotal
    : (alerts?'0 alerts':'0 flows')+' · '+systemTotal;
}
function tableSection(title, subtitle) {
  const alerts = state.view==='alerts';
  const explorer = state.view==='explorer';
  const sort = explorer ? '<label class="sort-field">Sort <select id="explorer-sort" aria-label="Sort flows">'+
    [['newest','Newest first'],['oldest','Oldest first'],['score','Highest score']].map(([value,label])=>
      '<option value="'+value+'"'+(value===state.explorerSort?' selected':'')+'>'+label+'</option>').join('')+'</select></label>' : '';
  const groupHeader=['Last seen · ICT','Detection','Source IP','Destination','Occurrences','Needs review','Peak score',''];
  const columns=alerts&&state.alertMode==='grouped'?groupHeader:
    ['Time · ICT','Source','Destination','Protocol',alerts?'Detection':'Verdict',...(explorer?['Predicted category']:[]),'Attack score',alerts?'Review':'Data source',''];
  const header=(alerts?'<th scope="col" class="alert-select"><input id="select-alert-page" type="checkbox" aria-label="Select alerts on this page"></th>':'')+
    columns.map(label=>'<th scope="col">'+(label||'<span class="sr-only">Details</span>')+'</th>').join('');
  const modes=alerts?'<div class="alert-modes" aria-label="Alert view">'+[['grouped','Grouped'],['individual','Individual']].map(([key,label])=>
    '<button type="button" class="btn period" aria-pressed="'+(state.alertMode===key)+'" data-action="alertMode" data-value="'+key+'">'+uiSymbol(key==='grouped'?'▦':'≡')+label+'</button>').join('')+'</div>':'';
  const importer=explorer?'<button type="button" class="primary" id="capture-upload-button" data-action="importPcap"'+
    (captureUploadPending?' disabled aria-busy="true"':'')+'>'+(captureUploadPending?'Importing…':uiSymbol('↑')+'Import PCAP')+
    '</button><input type="file" id="capture-upload-file" accept=".pcap,.pcapng" hidden>':'';
  return (explorer?explorerOverview():alerts?alertSummary():'')+'<section class="panel table-panel'+(explorer?' explorer-table':'')+'"><div class="panel-head table-head"><div><h2>' + title + '</h2><p>' + subtitle + '</p></div><div class="actions">'+modes+importer+'<button class="btn" id="export" data-action="export">'+uiSymbol('↓')+'Export CSV</button></div></div>' +
    '<div class="filters"><label class="search"><span aria-hidden="true">⌕</span><input id="search" data-filter="search" aria-label="Search flows" placeholder="Search IP, port, domain, or flow ID" value="' + escape(state.filters.search) + '"></label>' +
    (state.view==='live'?'':select('range','Time range',presets)+dateFilters()) +
    select('protocol','Protocol',[['','All protocols'],...['TCP','UDP','HTTP','HTTPS/TLS','TLS','QUIC?','DNS','SSH','ICMP'].map(x=>[x,x])]) +
    (alerts ? select('status','Review status',[['','All statuses'],['New','New'],['Acknowledged','Acknowledged'],['Resolved','Resolved']]) :
      select('decision','Verdict',[['','All verdicts'],['normal','Normal'],['flag','Suspicious']])) +
    (state.view!=='live' ? select('origin','Source',sourceOptions) : '') +
    ((explorer||alerts)?select('label','Predicted category',[['','All categories'],...[...attackClasses,unclearCategory,noCategory]
      .filter(name=>!alerts||name!==attackClasses[0]&&name!==noCategory).map(name=>[name,name])]):'')+
    (explorer?select('inference','Inference status',[['','All inference states'],['scored','Scored'],['not_scored','Not scored']])+
      select('model','Model version',[['','All models'],...[...new Set(allFlows().map(modelVersion))].map(id=>[id,id])]):'')+
    button('Reset','resetFilters') + sort + '</div>' + investigationScope() +
    '<div class="table-scroll"><table class="flow-table"><thead><tr>'+header+'</tr></thead><tbody id="table-rows"></tbody></table></div>' +
    '<div class="table-foot"><div class="actions"><span id="result-count"></span>'+
    (alerts?'<span id="alert-selected-count" aria-live="polite"></span>'+
      button('Resolve','bulkAlert','resolve','primary')+button('Block source IPs','bulkAlert','block')+
      button('Report false positive','bulkAlert','report')+
      '<button type="button" class="btn" id="clear-alert-selection" data-action="clearAlertSelection">Clear selection</button>':'')+
    '</div><div class="pagination">'+(explorer?'<label class="sort-field">Rows <select id="explorer-size" aria-label="Rows per page">'+
    [15,25,50].map(size=>'<option'+(size===state.explorerSize?' selected':'')+'>'+size+'</option>').join('')+'</select></label>':'')+
    (explorer||alerts?'<button class="btn" id="load-more-flows" data-action="loadMoreFlows">Load 250 more</button>':'')+
    '<button class="btn" id="table-prev" data-action="page" data-value="-1">‹ Previous</button><button class="btn" id="table-next" data-action="page" data-value="1">Next ›</button></div></div></section>';
}

function explorerOverview() {
  return '<section class="explorer-overview" aria-label="Filtered flow summary">'+
    [['system','Total flows in system'],['flagged','Suspicious flows loaded'],['peers','Destination IPs loaded']].map(([key,label])=>
      '<div><span>'+label+'</span><strong id="explorer-'+key+'">0</strong></div>').join('')+
    '</section>';
}

function investigationScope() {
  const {bucket,label,destination,alertGroup,captureFileName}=state.filters;
  if (!(bucket || label || destination || alertGroup || captureFileName)) return '';
  const values=[captureFileName,bucket && rangeText()+' ICT',label,destination && destinationLabel(destination)].filter(Boolean);
  if (alertGroup) {
    const [detection,src]=JSON.parse(alertGroup);
    values.push(detection+' · '+src);
  }
  return '<div class="scope-summary"><strong>'+ (alertGroup?'Selected alert group':'From Live Monitor')+'</strong> '+
    values.map(value=>badge(escape(value))).join(' ')+(alertGroup?button('Back to groups','alertMode','grouped','text-button'):'')+'</div>';
}
function destinationLabel([ip,port]) {
  return port==null ? ip : ip+':'+port;
}

function exportFlows() {
  const keys=['id','timestamp','src','sport','dst','dport','protocol','app','domain','kind','score','source','run','firewall','label','model_id'];
  const alerts=state.view==='alerts';
  if (alerts) keys.push('review_status');
  const rows=filtered();
  const quote=value=>'"'+String(value??'').replaceAll('"','""')+'"';
  const lines=rows.map(f=>{
    const cells={...f,timestamp:new Date(f.timestamp).toISOString(),model_id:modelVersion(f),review_status:review[f.id]||'New'};
    return keys.map(key=>quote(cells[key])).join(',');
  });
  if (!lines.length) return;
  const url=URL.createObjectURL(new Blob([keys.join(',')+'\r\n'+lines.join('\r\n')],{type:'text/csv;charset=utf-8'}));
  const link=document.createElement('a');
  link.href=url; link.download='flowwatch-'+state.view+'.csv';
  link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
  toast('Exported '+num(lines.length)+(alerts?' alerts':' flows'));
}
