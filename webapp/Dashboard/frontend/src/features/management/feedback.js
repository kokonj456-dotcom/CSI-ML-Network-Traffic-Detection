const FEEDBACK_PAGE_SIZE=15;
let feedbackPageIndex=0;

function feedbackPage() {
  const rows=managementData.feedback;
  feedbackPageIndex=0;
  if (!rows.length) return '<section class="panel panel-pad"><h2>'+uiSymbol('⚑')+'False positive feedback</h2>'+
    '<p class="case-note">No reports yet. Open an alert and choose Report false positive in the Model tab.</p>'+
    button('Open Alerts','navigate','alerts')+'</section>';

  const options=(id,label,values)=>'<select id="'+id+'" aria-label="'+label+'"><option value="">All '+label.toLowerCase()+
    '</option>'+values.map(value=>'<option value="'+escape(value)+'">'+escape(value)+'</option>').join('')+'</select>';
  return '<section class="panel panel-pad"><div class="panel-head"><div><h2>'+uiSymbol('⚑')+'False positive feedback</h2>'+
    '<p>Review reported flows and see which ones are available for training.</p></div>'+
    managedButton('Open Train & Tune','tab','train')+'</div>'+
    '<div class="feedback-filters"><label class="search"><span aria-hidden="true">⌕</span><input id="feedback-search" type="search"'+
    ' aria-label="Search feedback" placeholder="Search flow ID, IP, or model"></label>'+
    options('feedback-status','Statuses',['pending','approved','rejected'])+
    options('feedback-source','Sources',[...new Set(rows.map(row=>row.source))])+
    options('feedback-model','Models',[...new Set(rows.map(row=>row.snapshot?.prediction?.model_id).filter(Boolean))])+
    options('feedback-class','Categories',[...new Set(rows.map(row=>row.snapshot?.prediction).filter(Boolean).map(category).filter(Boolean))])+
    managedButton('Reset','resetFeedback','')+'</div>'+
    '<div id="feedback-items">'+feedbackCards(rows)+'</div></section>';
}

function updateFeedbackFilters() {
  const status=byId('feedback-status').value;
  const source=byId('feedback-source').value;
  const model=byId('feedback-model').value;
  const predicted=byId('feedback-class').value;
  const terms=byId('feedback-search').value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const matching=managementData.feedback.filter(row=>{
    const snapshot=row.snapshot||{};
    const prediction=snapshot.prediction;
    const label=prediction?category(prediction):null;
    const search=[row.flow_id,row.record,row.source,snapshot.src,snapshot.dst, prediction?.model_id,label]
      .filter(Boolean).join(' ').toLowerCase();
    return (!status||row.status===status)&&(!source||row.source===source)&&(!model||prediction?.model_id===model)&&
      (!predicted||label===predicted)&&terms.every(term=>search.includes(term));
  });
  byId('feedback-items').innerHTML=feedbackCards(matching);
}

function feedbackCards(rows) {
  if (!rows.length) return '<p class="case-note" role="status">No reports match these filters.</p>';
  const maxPage=Math.max(0,Math.ceil(rows.length/FEEDBACK_PAGE_SIZE)-1);
  feedbackPageIndex=Math.max(0,Math.min(feedbackPageIndex,maxPage));
  const start=feedbackPageIndex*FEEDBACK_PAGE_SIZE;
  const recentFlows=new Map(allFlows().map(flow=>[flow.id,flow]));
  const cards=rows.slice(start,start+FEEDBACK_PAGE_SIZE).map(row=>{
    const snapshot=row.snapshot||{};
    const prediction=snapshot.prediction||{};
    const label=prediction.status?category(prediction):null;
    const used=managementData.versions.filter(version=>version.manifest.training?.feedback_ids?.includes(row.id))
      .map(version=>version.manifest.model_id);
    const original=recentFlows.get(row.flow_id);
    const endpoints=[snapshot.src,snapshot.dst].filter(Boolean).join(' → ');
    return '<details class="feedback-report"><summary><span class="feedback-report-summary"><span><strong>'+
      escape(row.flow_id||row.record)+'</strong><small>'+escape([row.source,dateText(row.created)].join(' · '))+'</small>'+
      (endpoints?'<small class="mono">'+escape(endpoints)+'</small>':'')+'</span><span class="feedback-report-tags">'+
      (label?badge(escape(label)):'')+badge(row.status==='approved'&&row.eligible?'Eligible for training':escape(row.status),
        row.status==='approved'?'normal':row.status==='rejected'?'flag':'')+'</span></span></summary><div class="feedback-report-details">'+
      formatFields([...(row.reason?[['Reason',row.reason]]:[]),...(row.evidence_note?[['Evidence note',row.evidence_note]]:[]),
        ['Record',row.record],['Model',prediction.model_id||'—'],['Attack score / threshold',scoreText(prediction.binary_score)+' / '+scoreText(prediction.threshold)],
        ...(row.actual_label?[['Original dataset label',row.actual_label]]:[]),['Used by',used.join(', ')||'—'],
        ...(row.note?[['Review note',row.note],['Reviewed',dateText(row.reviewed)]]:[])])+
      '<details><summary>Original snapshot</summary><pre class="evidence">'+escape(JSON.stringify(snapshot,null,2))+'</pre></details>'+
      (original&&original.timestamp===snapshot.timestamp?'<div class="actions">'+button('Open flow','flow',original.id)+'</div>':'')+'</div></details>';
  }).join('');
  const pageControls=maxPage?'<div class="pagination"><button class="btn" type="button" data-management="feedbackPage" data-value="-1"'+
    (feedbackPageIndex===0?' disabled':'')+'>‹ Previous</button><button class="btn" type="button" data-management="feedbackPage" data-value="1"'+
    (feedbackPageIndex===maxPage?' disabled':'')+'>Next ›</button></div>':'';
  const end=Math.min(start+FEEDBACK_PAGE_SIZE,rows.length);
  const range=end===start+1?num(end):num(start+1)+'–'+num(end);
  return '<div class="feedback-report-list">'+cards+'</div><div class="feedback-report-footer"><span role="status">'+
    range+' of '+num(rows.length)+' reports</span>'+pageControls+'</div>';
}
