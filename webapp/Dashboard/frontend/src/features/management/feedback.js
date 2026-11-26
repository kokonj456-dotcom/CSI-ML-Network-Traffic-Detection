function feedbackPage() {
  const rows=managementData.feedback;
  const options=(id,label,values)=>'<select id="'+id+'" aria-label="'+label+'"><option value="">All '+label.toLowerCase()+
    '</option>'+values.map(value=>'<option value="'+escape(value)+'">'+escape(value)+'</option>').join('')+'</select>';
  return '<section class="panel panel-pad"><h2>False positive feedback</h2><p class="case-note">Reported flows with verified inputs can be selected as benign training examples.</p>'+
    (rows.length?'<div class="feedback-filters">'+options('feedback-status','Statuses',['pending','approved','rejected'])+
    options('feedback-source','Sources',[...new Set(rows.map(row=>row.source))])+
    options('feedback-model','Models',[...new Set(rows.map(row=>row.snapshot.prediction?.model_id).filter(Boolean))])+
    options('feedback-class','Categories',[...new Set(rows.map(row=>row.snapshot.prediction).filter(Boolean).map(category).filter(Boolean))])+
    '</div>':'')+'<div id="feedback-items">'+feedbackCards(rows)+'</div></section>';
}
function updateFeedbackFilters() {
  const status=byId('feedback-status').value,source=byId('feedback-source').value;
  const model=byId('feedback-model').value, predicted=byId('feedback-class').value;
  byId('feedback-items').innerHTML=feedbackCards(managementData.feedback.filter(row=>
    (!status||row.status===status)&&(!source||row.source===source)&&(!model||row.snapshot.prediction?.model_id===model)&&
    (!predicted||row.snapshot.prediction&&category(row.snapshot.prediction)===predicted)));
}
function feedbackCards(rows) {
  if (!managementData.feedback.length) return '<p class="case-note">No false positive reports yet. In Alerts, open a flagged flow, go to the Model tab, and select Report false positive.</p>';
  if (!rows.length) return '<p class="case-note">No reports match these filters. Change a filter to see more reports.</p>';
  return rows.map(row=>{
    const p=row.snapshot.prediction||{};
    const used=managementData.versions.filter(version=>version.manifest.training?.feedback_ids?.includes(row.id)).map(version=>version.manifest.model_id);
    const original=allFlows().find(flow=>flow.id===row.flow_id && flow.timestamp===row.snapshot.timestamp);
    return '<article class="management-card"><div class="panel-head"><div><strong>'+escape(row.record)+'</strong><p>'+
      escape(row.source+' · '+dateText(row.created))+'</p></div>'+badge(escape(row.status),row.status==='approved'?'normal':row.status==='rejected'?'flag':'')+'</div>'+
      formatFields([...(row.reason?[['Reason',row.reason]]:[]),...(row.evidence_note?[['Evidence note',row.evidence_note]]:[]),['Model',p.model_id||'—'],
        ['Attack score / threshold',scoreText(p.binary_score)+' / '+scoreText(p.threshold)],['Original dataset label',row.actual_label||'—'],
        ['Training eligibility',row.eligible?'Verified capture · requires approval and duplicate checks':'Analysis only'],
        ['Used by',used.join(', ')||'—'],...(row.note?[['Review note',row.note],['Reviewed',dateText(row.reviewed)]]:[])])+
      '<details><summary>Original snapshot</summary><pre class="evidence">'+escape(JSON.stringify(row.snapshot,null,2))+'</pre></details>'+
      (original?'<div class="actions">'+button('Open flow','flow',original.id)+'</div>':'')+
      '</article>';
  }).join('');
}
