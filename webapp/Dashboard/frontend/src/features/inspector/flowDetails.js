'use strict';

const detailSymbols = {'Connection overview':'◈','Protocol and service':'↔','Connection state':'⎓','Payload':'⌘','Stage 1 · Attack detection':'◉','Stage 2 · Category':'◇','Inference details':'ⓘ','Evidence source':'▤','Observations':'⌕'};

function detailSection(title, content, variant = '') {
  return '<section class="flow-detail-section '+variant+'"><h3>'+(detailSymbols[title]?uiSymbol(detailSymbols[title]):'')+escape(title)+'</h3>'+content+'</section>';
}

function protocolDetails(flow) {
  return detailSection('Protocol and service',formatFields([['Application',flow.app],['Transport',flow.protocol],
    ['Service group',flow.raw.service_group],['Service detected by',flow.serviceBasis]]))+
    detailSection('Connection state',formatFields([['State',flow.raw.conn_state_group],['State detected by',flow.stateBasis]]))+
    detailSection('Payload','<p class="case-note">Payload is unavailable for this flow. Open Evidence to see what was recorded.</p>');
}
function relatedFlows(flow) {
  if (!flow.src || !flow.dst) return '';
  const dates=state.selection.relatedDates;
  const start=dates?Date.parse(dates.from+'T00:00:00+07:00'):flow.timestamp-5*60_000;
  const end=dates?Date.parse(dates.to+'T00:00:00+07:00')+day:flow.timestamp+5*60_000+1;
  const distance=other=>Math.abs(other.timestamp-flow.timestamp);
  const matches=allFlows().filter(other=>other.id!==flow.id && other.run===flow.run && other.source===flow.source &&
    other.timestamp>=start && other.timestamp<end && ((other.src===flow.src && other.dst===flow.dst)||(other.src===flow.dst && other.dst===flow.src))
  ).sort((a,b)=>distance(a)-distance(b) || b.timestamp-a.timestamp);
  const expanded=Boolean(state.selection.showAllRelated);
  const visible=expanded?matches:matches.slice(0,5);
  function relativeTime(other) {
    const seconds=Math.round((other.timestamp-flow.timestamp)/1000);
    if (!seconds) return '<1 s apart';
    const magnitude=Math.abs(seconds);
    const elapsed=magnitude<60?magnitude+' s':Math.floor(magnitude/60)+'m '+magnitude%60+'s';
    return elapsed+(seconds<0?' before':' after');
  }
  return '<section class="related-flows"><div class="panel-head"><div><h3>'+uiSymbol('◷')+'Related flows</h3><p>Same IP pair and run · '+(dates?'selected dates (ICT)':'within ±5 minutes')+'</p></div>'+
    '<div class="related-controls">'+badge('Showing '+num(visible.length)+' of '+num(matches.length))+
    (matches.length>5?'<button type="button" class="btn related-toggle" data-action="toggleRelated" aria-controls="related-flow-list" aria-expanded="'+expanded+'">'+
      (expanded?'Show closest 5':'Show all '+num(matches.length))+'</button>':'')+'</div></div>'+
    '<form class="related-date-form date-fields" id="related-date-form"><label>From <input type="date" name="from" value="'+escape(dates?.from||'')+'"></label>'+
    '<label>Through <input type="date" name="to" value="'+escape(dates?.to||'')+'"></label>'+
    '<button class="btn" type="submit">'+uiSymbol('▦')+'Apply dates</button>'+
    (dates?button('Reset to ±5 min','clearRelatedDates','','text-button'):'')+
    '<span id="related-date-error" class="form-error" role="alert"></span></form>'+
    (matches.length?'<p class="case-note related-order">Closest to '+time(flow.timestamp)+' ICT first</p><ul id="related-flow-list">'+visible.map(other=>'<li>'+
      button('<span class="related-time mono">'+time(other.timestamp)+'<small>'+escape((dates?shortDay.format(other.timestamp)+' · ':'')+other.id+' · '+relativeTime(other))+'</small></span>'+
        '<span>'+badge(escape(other.app))+'</span>'+verdict(other)+'<span aria-hidden="true">›</span>'+
        '<span class="sr-only">Open related flow '+escape(other.id)+'</span>','relatedFlow',other.id,'related-flow')+
      '</li>').join('')+'</ul>':'<p class="case-note">No other flows match this IP pair in the time window.</p>')+
    '</section>';
}
function topFactors(contributions) {
  if (!contributions?.length) return '';
  const largest = Math.max(...contributions.map(item => Math.abs(item.log_odds_delta)), 0.001);
  const rows = contributions.map(({feature, log_odds_delta: delta}) => {
    const direction = delta > 0 ? 'raises' : delta < 0 ? 'lowers' : 'neutral';
    const value = (delta > 0 ? '+' : '') + delta.toFixed(3);
    const width = (Math.abs(delta) / largest * 100).toFixed(1);
    return '<li class="model-factor '+direction+'"><span class="mono">'+escape(feature)+'</span><strong class="mono">'+value+
      '</strong><div class="model-factor-track" aria-hidden="true"><i style="width:'+width+'%"></i></div></li>';
  }).join('');
  return '<details class="feature-contract"><summary>'+uiSymbol('≡')+'Top factors · Stage 1</summary>'+
    '<p class="case-note"><span class="factor-raises">+ Raises attack score</span> · <span class="factor-lowers">− Lowers attack score</span><br>'+
    'Values show changes in model log-odds.</p><ul class="model-factors">'+rows+'</ul></details>';
}

function modelDetails(flow) {
  const p=flow.prediction;
  if (p.status!=='scored') return formatFields([['Status','Not scored'],['Reason',p.reason],['Model',p.model_id]]);
  const scorePosition = value => (Math.min(1,Math.max(0,value))*100).toFixed(2)+'%';
  const scoreBar='<div class="flow-score '+(p.flagged?'is-flagged':'')+'"><div class="flow-score-label"><span>Attack score</span><strong>'+
    scoreText(p.binary_score)+'</strong></div><div class="flow-score-track" aria-hidden="true"><i style="width:'+scorePosition(p.binary_score)+
    '"></i><b style="left:'+scorePosition(p.threshold)+'"></b></div><p class="case-note">Alert threshold '+scoreText(p.threshold)+
    ' · '+(p.flagged?'Alert':'Below threshold')+'</p></div>';
  const stage2='<div class="model-category"><div><small>Predicted category</small><strong>'+escape(flow.label)+
    '</strong></div><div><small>Class score</small><strong>'+scoreText(p.class_score)+'</strong></div></div>'+
    (p.category_unclear?formatFields([['Stage 2 top result','Benign / Normal · '+scoreText(p.stage2_top_score)],
      ['Best attack candidate',attackClasses[p.best_attack_candidate_id]+' · '+scoreText(p.best_attack_candidate_score)]]):'');
  const rawLabels={duration:'Duration (seconds)',protocol:'Transport protocol',bytes_forward:'Bytes forward',
    bytes_backward:'Bytes backward',service_group:'Service group',conn_state_group:'Connection state'};
  return detailSection('Stage 1 · Attack detection',scoreBar)+
    (p.flagged?detailSection('Stage 2 · Category',stage2):'')+
    topFactors(p.binary_contributions)+
    detailSection('Inference details',formatFields([['Model',p.model_id],['Data source',flow.source],
      ['Inference time',p.inference_ms==null?'—':p.inference_ms.toFixed(2)+' ms'],
      ['Review status',flow.kind==='flag'?(review[flow.id]||'New'):'—']])+
      (p.preprocessor_sha256?'<details class="model-fingerprint"><summary>Preprocessor SHA-256</summary><code>'+escape(p.preprocessor_sha256)+'</code></details>':''))+
    (p.raw_inputs?'<details class="feature-contract"><summary>'+uiSymbol('▦')+'Raw inputs · '+Object.keys(p.raw_inputs).length+' fields</summary>'+
      formatFields(Object.entries(p.raw_inputs).map(([name,value])=>[rawLabels[name]||name,
        name==='duration'&&typeof value==='number'?Number(value.toPrecision(5)):value]))+'</details>':'')+
    '<details class="feature-contract"><summary>'+uiSymbol('▤')+'CENTRAL training schema · 19 inputs</summary>'+
    (p.encoded_inputs?formatFields(Object.entries(p.encoded_inputs).map(([name,value])=>[name,value.toFixed(5)])):
      '<p class="case-note">Encoded feature values are unavailable for this flow.</p>')+
    '</details>';
}
function flowInspector(flow) {
  const tabs=['Overview','Protocol','Model','Evidence'].map(name=>
    '<button class="tab" aria-pressed="'+(state.tab===name)+'" data-action="tab" data-value="'+name+'">'+uiSymbol({Overview:'◈',Protocol:'↔',Model:'◫',Evidence:'▤'}[name])+name+'</button>').join('');
  let details;
  if (state.tab==='Protocol') details=protocolDetails(flow);
  else if (state.tab==='Model') {
    details=modelDetails(flow);
    if (flow.kind==='flag') {
      const status=review[flow.id]||'New';
      details='<div class="actions flow-detail-actions">'+
        (status==='Resolved'?button('Reopen','review','New'):button('Resolve','review','Resolved','primary'))+
        (flow.src?blockSourceButton(flow.src,flow.id):'')+
        (flow.falsePositiveReported
          ? badge('False positive reported','reviewed')
          : flow.alertId&&!flow.dataset?button('Report false positive','reportFalsePositive',flow.id):'')+'</div>'+details;
    }
  } else if (state.tab==='Evidence') {
    details=detailSection('Evidence source',formatFields([['Data source',flow.source],['Capture file',flow.file],
      ['Observed at (UTC)',new Date(flow.timestamp).toISOString()],...(flow.dataset?[['CENTRAL record',flow.dataset.record_id]]:[])])+
      (flow.dataset?'<p class="case-note">This result was scored from CENTRAL Test features.</p>':
        flow.source==='Live Capture'?'<p class="case-note">Live capture stores flow metadata without attaching a packet file.</p>':
          '<p class="case-note">Packet metadata was extracted offline from this capture.</p>'))+
      detailSection('Observations',formatFields([['Observed frames',flow.frames.join(', ') || 'Unavailable'],
        ['Service basis',flow.serviceBasis],['State basis',flow.stateBasis]]));
  } else {
    const metrics=[['Packets',flow.dataset||flow.packets==null?'—':num(flow.packets)],['Bytes',num(flow.bytes)],['Duration',flow.duration+' s']];
    details='<dl class="flow-detail-metrics">'+metrics.map(([label,value])=>'<div><dt>'+uiSymbol({Packets:'▣',Bytes:'▥',Duration:'◷'}[label])+label+'</dt><dd>'+escape(value)+'</dd></div>').join('')+'</dl>'+
      detailSection('Connection overview',formatFields([['Observed at',localDay.format(flow.timestamp)+' '+time(flow.timestamp)+' ICT'],
        ['Data source',flow.source],['Capture / interface',flow.file||flow.interface],
        ['Application / transport',flow.app+' / '+flow.protocol],['Domain',flow.domain],['Firewall decision',flow.firewall],
        ...(flow.dataset?[['Actual category',attackClasses[flow.dataset.attack_category_id]]]:[])]));
    if (flow.kind==='flag') details+=review[flow.id]==='Resolved'?
      button('Reopen','review','New'):button('Resolve','review','Resolved','primary');
    details+=relatedFlows(flow);
  }
  return drawerHeader(escape(flow.source),flow.id,verdict(flow))+'<div class="drawer-body flow-inspector">'+flowEndpoints(flow)+
    '<div class="tabs flow-inspector-tabs" role="group" aria-label="Flow detail sections">'+tabs+'</div>'+
    '<div class="flow-detail-content">'+details+'</div></div>';
}
function flowEndpoints(flow) {
  return '<dl class="flow-endpoints" aria-label="Flow endpoints">'+
    '<div><dt>'+uiSymbol('↗')+'Source</dt><dd>'+flowEndpoint(flow,'src')+'</dd></div>'+
    '<div><dt>'+uiSymbol('↘')+'Destination</dt><dd>'+flowEndpoint(flow,'dst')+'</dd></div></dl>';
}
function drawerHeader(label,title,sub) {
  return '<div class="drawer-top"><div><p>'+label+'</p><h2>'+escape(title)+'</h2>'+sub+'</div>'+button('<span aria-hidden="true">×</span><span class="sr-only">Close details</span>','close','','icon-button')+'</div>';
}
