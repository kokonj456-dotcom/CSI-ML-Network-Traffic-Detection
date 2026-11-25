'use strict';

let managementTab = 'overview';
let managementData = null;
let managementPoll = null;
let managementPending = false;
let trainingReference = 'm9';
const managementTabs = {overview:'Overview',feedback:'Feedback',train:'Train & Tune',registry:'Model Registry'};
const dateText = value => value ? localDay.format(new Date(value))+' '+time(new Date(value))+' ICT' : 'Not recorded';

async function managementRequest(path='', payload) {
  if (location.protocol==='file:') throw Error('Model Management requires the local Flowwatch backend.');
  const options=payload?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}:{};
  let response;
  try {
    response=await fetch('/api/management'+path,options);
  } catch {
    throw Error('Could not reach the Flowwatch backend. Check that it is running, then select Refresh.');
  }
  if (!(response.headers.get('content-type')||'').includes('application/json')) throw Error('Start the local Flowwatch backend to use Model Management.');
  const data=await response.json();
  if (!response.ok) throw Error(typeof data.detail==='string'?data.detail:'Invalid request.');
  return data;
}
function managedButton(label, action, value, css='btn') {
  return '<button type="button" class="'+css+'" data-management="'+action+'" data-value="'+escape(value)+'">'+label+'</button>';
}
function jobCards() {
  if (!managementData.jobs.length) return '<p class="case-note">No training runs yet.</p>';
  return managementData.jobs.map(job=>'<article class="management-card"><div class="panel-head"><div><strong>'+escape(job.config.strategy)+
    '</strong><p>'+escape(dateText(job.created))+'</p></div>'+badge(escape(job.status),job.status==='failed'?'flag':job.status==='completed'?'normal':'')+'</div>'+
    (job.finished?'<p class="case-note">Finished '+escape(dateText(job.finished))+'</p>':'')+
    (job.error?'<p class="form-error">'+escape(job.error)+'</p>':'')+
    (job.log_tail?'<details data-job="'+escape(job.id)+'"><summary>Training output</summary><pre class="evidence">'+escape(job.log_tail)+'</pre></details>':'')+'</article>').join('');
}
function renderJobs() {
  const panel=byId('management-jobs');
  if (!panel || panel.contains(document.activeElement)) return;
  const expanded=new Set([...panel.querySelectorAll('details[open]')].map(row=>row.dataset.job));
  panel.innerHTML=jobCards();
  panel.querySelectorAll('details').forEach(row=>{row.open=expanded.has(row.dataset.job);});
}
function pollManagement() {
  clearTimeout(managementPoll);
  if (state.view!=='management'||!managementData?.jobs.some(job=>job.status==='running')) return;
  managementPoll=setTimeout(async()=>{
    try {
      const data=await managementRequest();
      if (state.view!=='management') return;
      const finished=!data.jobs.some(job=>job.status==='running');
      managementData=data;
      if (finished && managementTab==='registry') renderManagementBody();
      else {
        renderJobs();
        const start=byId('start-training');
        if (start) start.disabled=!finished;
      }
      pollManagement();
    } catch (error) {managementError(error.message);}
  },1800);
}
function managementError(message) {
  const status=byId('management-message');
  if (!status) return;
  status.textContent=message;
  if (message && location.protocol==='file:') {
    const link=document.createElement('a');
    link.href='http://127.0.0.1:8794/';
    link.textContent='Open local Flowwatch';
    status.append(' ',link);
  }
}
async function refreshManagement() {
  try {
    const data=await managementRequest();
    if (state.view!=='management') return;
    managementData=data;renderManagementBody();pollManagement();
  } catch(error) {
    if (state.view==='management') managementError(error.message);
  }
}
function renderManagementBody() {
  const host=byId('management-body');
  if (!host || !managementData) return;
  managementError(managementData.warning||'');
  if (managementTab==='feedback') host.innerHTML=feedbackPage();
  else if (managementTab==='train') {host.innerHTML=trainingPage();updateTrainingCounts();updateTrainingReference();}
  else if (managementTab==='registry') {host.innerHTML=registryPage();renderComparison();}
  else host.innerHTML=managementOverview();
}
function assessmentFields(metrics) {
  const {fp,fn,tp}=metrics?.binary?.confusion||{};
  return [
    ['Rows',metrics?.rows,num],['Binary F1',metrics?.binary?.f1,scoreText],
    ['False-positive rate (lower is better)',metrics?.binary?.fpr,scoreText],
    ['Binary precision',tp+fp?tp/(tp+fp):null,scoreText],['Binary recall',tp+fn?tp/(tp+fn):null,scoreText],
    ['Macro F1 · best attack candidate',metrics?.forced_category_macro_f1,scoreText],
    ['Unclear categories',metrics?.category_unclear,num],
  ];
}
function assessmentSummary(metrics) {
  return formatFields(assessmentFields(metrics).map(([label,value,format])=>[label,value==null?'—':format(value)]));
}
function managementOverview() {
  const active=managementData.versions.find(version=>version.version===managementData.active);
  const manifest=active?.manifest;
  const confirmed=managementData.feedback.filter(row=>row.status==='approved'&&row.eligible).length;
  return '<div class="grid-two"><section class="panel panel-pad"><h2>Active model</h2>'+
    formatFields([['Version',manifest?.model_id||'Unavailable'],['Threshold',scoreText(manifest?.threshold)],
      ['Training completed',dateText(manifest?.training?.finished_at)],['Training strategy',manifest?.candidate||'Not recorded'],
      ['Confirmed training feedback',num(confirmed)]])+
    (active?'<h3>Feature-group-disjoint CENTRAL test</h3>'+assessmentSummary(active.evaluation.test_feature_group_disjoint):'')+
    '</section><section class="panel panel-pad"><h2>Training jobs</h2><div id="management-jobs">'+jobCards()+'</div></section></div>';
}
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
function updateTrainingCounts() {
  const form=byId('train-model-form');
  if (!form) return;
  const counts=managementData.dataset_counts||{};
  const rows=counts.train==null?'—':num(counts.train);
  const selected=new FormData(form).getAll('feedback_id').length;
  const choices=[...form.querySelectorAll('.feedback-choice')];
  const visible=choices.filter(choice=>!choice.hidden);
  if (choices.length) {
    byId('training-feedback-count').textContent=num(selected)+' selected · '+num(visible.length)+' of '+num(choices.length)+' shown';
    byId('training-feedback-empty').hidden=visible.length>0;
    byId('training-feedback-select').disabled=!visible.some(choice=>!choice.querySelector('input').checked);
    byId('training-feedback-clear').disabled=!selected;
  }
  byId('training-base-count').textContent=rows;
  byId('training-selected-count').textContent=num(selected);
  byId('training-validation-count').textContent=counts.validation==null?'—':num(counts.validation);
}
function trainingFeedbackPicker(rows) {
  if (!rows.length) return '<p class="case-note">No eligible feedback yet. Training can begin with CENTRAL Train.</p>';
  const choices=rows.map(row=>{
    const {src,dst,sport,dport,prediction}=row.snapshot||{};
    const endpoints=[[src,sport],[dst,dport]].filter(([ip])=>ip).map(([ip,port])=>{
      return port==null?ip:(ip.includes(':')?'['+ip+']':ip)+':'+port;
    }).join(' → ');
    const label=prediction?category(prediction):null;
    const id=row.flow_id||row.record||row.id;
    const date=dateText(row.created);
    const search=[id,row.record,row.source,endpoints,label,date].filter(Boolean).join(' ').toLowerCase();
    return '<label class="feedback-choice" data-search="'+escape(search)+'"><span class="alert-select">'+
      '<input type="checkbox" name="feedback_id" value="'+escape(row.id)+'"></span>'+
      '<span class="feedback-choice-detail"><strong>'+escape(id)+'</strong>'+
      (endpoints?'<span class="mono">'+escape(endpoints)+'</span>':'')+
      '<small>'+escape(row.source)+' · '+escape(date)+'</small></span>'+
      (label?badge(escape(label)):'')+'</label>';
  }).join('');
  return '<div class="training-feedback-toolbar">'+
    '<input id="training-feedback-search" type="search" aria-label="Search eligible feedback" placeholder="Search flow, IP, or category">'+
    '<div class="actions">'+
    '<button type="button" class="btn" id="training-feedback-select" data-management="selectFeedback">Select shown</button>'+
    '<button type="button" class="btn" id="training-feedback-clear" data-management="clearFeedback">Clear</button>'+
    '<span id="training-feedback-count" class="case-note" aria-live="polite"></span></div></div>'+
    '<div class="training-feedback-list" role="region" aria-label="Eligible feedback" tabindex="0">'+choices+
    '<p class="case-note" id="training-feedback-empty" hidden>No feedback matches your search.</p></div>';
}
function referenceConfig() {
  return trainingReference==='m9'?managementData.parameter_defaults:
    managementData.versions.find(version=>version.version===trainingReference)?.manifest.training?.config;
}
function referenceParameter(stage, name) {
  return referenceConfig()?.[stage]?.[name]??'Not recorded';
}
function updateTrainingReference() {
  document.querySelectorAll('[data-reference-stage]').forEach(cell=>{
    cell.textContent=referenceParameter(cell.dataset.referenceStage,cell.dataset.referenceParameter);
  });
  document.querySelector('[data-management="useReference"]').disabled=!referenceConfig();
  const model=managementData.versions.find(item=>item.version===trainingReference);
  const finished=model?.manifest.training?.finished_at;
  byId('training-reference-date').textContent=trainingReference==='m9'?
    'Default tuning preset':finished?'Trained '+dateText(finished):'Training date not recorded';
}
function setTrainingParameters(config) {
  const form=byId('train-model-form');
  for (const stage of ['stage1','stage2']) {
    for (const [name,rule] of Object.entries(managementData.parameters)) {
      const value=config?.[stage]?.[name];
      if (Number.isFinite(value)&&value>=rule.min&&value<=rule.max&&(!rule.integer||Number.isInteger(value))) {
        form.elements.namedItem(stage+'.'+name).value=value;
      }
    }
  }
}
function trainingPage() {
  const approved=managementData.feedback.filter(row=>row.status==='approved'&&row.eligible);
  const {versions,latest}=orderedVersions();
  if (trainingReference==='m9'&&!managementData.parameter_defaults || trainingReference!=='m9'&&!versions.some(item=>item.version===trainingReference)) {
    trainingReference=managementData.parameter_defaults?'m9':versions[0]?.version;
  }
  const preset=managementData.parameter_defaults?'<optgroup label="Tuning preset"><option value="m9"'+
    (trainingReference==='m9'?' selected':'')+'>M9 Production</option></optgroup>':'';
  const referenceOptions=preset+comparisonOptions(versions,versions.find(item=>item.version===trainingReference),latest);
  const formFields=stage=>'<details class="training-stage"><summary>'+ (stage==='stage1'?'Stage 1 · Attack detection':'Stage 2 · Category')+
    '</summary><div class="parameter-comparison"><div class="parameter-head" aria-hidden="true"><span>Parameter</span>'+
    '<span>Training input</span><span>Reference</span></div>'+Object.entries(managementData.parameters).map(([name,rule])=>
      '<div class="training-parameter"><label for="'+stage+'-'+name+'">'+escape(name)+'</label>'+
      '<div class="training-input-value"><input required type="number" id="'+stage+'-'+name+'" name="'+stage+'.'+name+'" min="'+rule.min+'" max="'+rule.max+'" step="'+
      (rule.integer?'1':'any')+'" value="'+(managementData.parameter_defaults?.[stage]?.[name]??rule.default)+'"></div>'+
      '<output class="training-reference-value" aria-label="Reference '+escape(name)+'" data-reference-stage="'+stage+'" data-reference-parameter="'+name+'">'+
      escape(String(referenceParameter(stage,name)))+'</output></div>').join('')+'</div></details>';
  return '<div class="training-layout"><section class="panel panel-pad"><h2>Configure training</h2>'+
    '<form class="management-form" id="train-model-form">'+
    '<fieldset><legend>Training feedback</legend>'+
    trainingFeedbackPicker(approved)+
    '<p class="case-note">Duplicate feature groups are excluded before training.</p></fieldset>'+
    '<fieldset><legend>XGBoost parameters</legend><p class="case-note">The form starts with M9 Production values.</p>'+
    '<label>Reference model <select id="training-reference" aria-describedby="training-reference-date">'+referenceOptions+'</select>'+
    '<small class="comparison-picked-date" id="training-reference-date"></small></label>'+
    '<div class="actions training-param-actions">'+managedButton('Use reference values','useReference','')+
    managedButton('Reset to defaults','resetTrainingParameters','')+'</div>'+
    formFields('stage1')+formFields('stage2')+'</fieldset></form></section>'+
    '<div class="training-sidebar"><section class="panel panel-pad"><h2>Training summary</h2>'+
    '<dl class="fields"><div><dt>CENTRAL training rows</dt><dd id="training-base-count"></dd></div>'+
    '<div><dt>Feedback selected</dt><dd id="training-selected-count"></dd></div>'+
    '<div><dt>Validation rows</dt><dd id="training-validation-count"></dd></div></dl>'+
    '<p class="case-note">A completed job creates a candidate for review in Model Registry.</p>'+
    '<button id="start-training" class="primary" type="submit" form="train-model-form"'+(managementData.jobs.some(job=>job.status==='running')?' disabled':'')+
    '>Start training</button></section><section class="panel panel-pad"><h2>Training jobs</h2>'+
    '<div id="management-jobs">'+jobCards()+'</div></section></div></div>';
}
function versionDetails(version, latest) {
  const {manifest,evaluation}=version;
  const finished=manifest.training?.finished_at;
  return '<details class="management-version"><summary><span class="version-title">'+escape(manifest.model_id)+' '+
    badge(version.version===managementData.active?'Active':version.version==='baseline'?'Baseline':'Candidate')+
    (version.version===latest?badge('Latest trained'):'')+'</span>'+
    '<small class="version-date">'+(finished?'Trained '+escape(dateText(finished)):'Training date not recorded')+'</small></summary>'+
    formatFields([['Training started',dateText(manifest.training?.started_at)],['Training finished',dateText(manifest.training?.finished_at)],['Strategy',manifest.candidate],
      ['Threshold',scoreText(manifest.threshold)],['Training rows',manifest.training?.train_rows??'Not recorded'],['Validation rows',manifest.training?.validation_rows??'Not recorded'],
      ['Dataset audit SHA-256',manifest.dataset_audit_sha256],['Evaluation data SHA-256',manifest.evaluation_sha256||'Not recorded'],
      ['Feedback used',manifest.training?.feedback_ids?.length??'Not recorded'],['Seed',manifest.training?.seed??'Not recorded']])+
    '<h3>Full CENTRAL test</h3>'+assessmentSummary(evaluation.test_full)+
    '<h3>Feature-group-disjoint CENTRAL test</h3>'+assessmentSummary(evaluation.test_feature_group_disjoint)+
    '<details><summary>Parameters and feedback lineage</summary><pre class="evidence">'+escape(JSON.stringify(manifest.training||{status:'Not recorded for this baseline'},null,2))+'</pre></details>'+
    '<details><summary>Per-class metrics, source breakdown and confusion matrices</summary><pre class="evidence">'+escape(JSON.stringify(evaluation,null,2))+'</pre></details>'+
    (version.version!==managementData.active?'<form class="management-form" data-activate-version="'+escape(version.version)+'">'+
      '<button type="submit" class="primary">'+(version.version==='baseline'?'Rollback to baseline':'Activate version')+'</button></form>':'')+
    '</details>';
}
function comparisonVersionLabel(item, latest) {
  const trained=item.manifest.training?.finished_at;
  const isBaseline=item.version==='baseline';
  return [
    trained?time(new Date(trained)):null,
    isBaseline?'Baseline':item.manifest.model_id.split('-').at(-1),
    item.version===latest?'Latest':null,
    item.version===managementData.active?'Active':null,
  ].filter(Boolean).join(' · ');
}
function comparisonOptions(versions, selected, latest) {
  const days=new Map();
  for (const item of versions) {
    const timestamp=Date.parse(item.manifest.training?.finished_at);
    const day=Number.isFinite(timestamp)?localDay.format(timestamp)+' · ICT':'Training date not recorded';
    if (!days.has(day)) days.set(day,[]);
    days.get(day).push('<option value="'+escape(item.version)+'"'+(item===selected?' selected':'')+'>'+
      escape(comparisonVersionLabel(item,latest))+'</option>');
  }
  return [...days].map(([day,items])=>'<optgroup label="'+escape(day)+'">'+items.join('')+'</optgroup>').join('');
}
function orderedVersions() {
  const trainedAt=item=>Date.parse(item.manifest.training?.finished_at)||0;
  const versions=[...managementData.versions].sort((a,b)=>trainedAt(b)-trainedAt(a));
  const latest=versions.find(item=>trainedAt(item))?.version;
  return {versions,latest};
}
function registryPage() {
  const {versions,latest}=orderedVersions();
  const first=versions.find(item=>item.version===managementData.active)||versions[0];
  const second=versions.find(item=>item!==first)||first;
  return '<section class="panel panel-pad"><h2>Compare versions</h2><p class="case-note">Compare evaluations by their test-data fingerprint.</p>'+
    '<div class="management-compare">'+['left','right'].map((side,index)=>'<label>Version '+(index+1)+
      ' <select id="compare-'+side+'" aria-describedby="compare-date-'+side+'">'+comparisonOptions(versions,index===0?first:second,latest)+
      '</select><small class="comparison-picked-date" id="compare-date-'+side+'"></small></label>').join('')+
    '</div><div id="model-comparison"></div></section><section class="panel panel-pad firewall-panel"><h2>Available models</h2>'+
    versions.map(item=>versionDetails(item,latest)).join('')+'</section>';
}
function renderComparison() {
  const host=byId('model-comparison');
  if (!host) return;
  const models=['left','right'].map(side=>managementData.versions.find(item=>item.version===byId('compare-'+side).value));
  if (models.some(item=>!item)) return;
  ['left','right'].forEach((side,index)=>{
    const finished=models[index].manifest.training?.finished_at;
    byId('compare-date-'+side).textContent=finished?localDay.format(new Date(finished))+' · ICT':'Training date not recorded';
  });
  const same=models[0].manifest.evaluation_sha256 && models[0].manifest.evaluation_sha256===models[1].manifest.evaluation_sha256;
  const fields=models.map(item=>{
      const {manifest,evaluation}=item;
      const training=manifest.training;
      const strategy={class_weighted:'Class weighting',baseline:'Baseline',smotenc:'SMOTENC'}[manifest.candidate]||manifest.candidate;
      return [['Training finished',dateText(training?.finished_at)],['Strategy',strategy],
        ['Training rows',training?.train_rows,num],['Feedback used',training?.feedback_ids?.length,num],
        ...assessmentFields(evaluation.test_feature_group_disjoint)];
  });
  const sections=[['Training details',0,4],['Feature-group-disjoint CENTRAL test',4,fields[0].length]];
  host.innerHTML='<p class="case-note">'+(same?'Evaluation fingerprints match.':'Shared evaluation data cannot be verified for these versions.')+
    '</p><p class="comparison-legend"><span class="compare-higher">↑ Higher</span><span class="compare-lower">↓ Lower</span>'+
    '<span>Arrows show numeric differences.</span></p>'+
    '<div class="table-scroll comparison-scroll"><table class="comparison-table"><thead><tr><th scope="col">Metric</th>'+
    models.map(item=>'<th scope="col">'+escape(item.manifest.model_id)+'</th>').join('')+'</tr></thead>'+
    sections.map(([title,start,end])=>'<tbody><tr class="comparison-section"><th scope="rowgroup" colspan="3">'+title+'</th></tr>'+
      fields[0].slice(start,end).map(([label,left,format],i)=>{
        const right=fields[1][start+i][1];
        const display=value=>value==null?'Not recorded':format?format(value):value;
        const compare=Number.isFinite(left)&&Number.isFinite(right)&&display(left)!==display(right);
        return '<tr><th scope="row">'+escape(label)+'</th>'+[left,right].map((value,side)=>{
          const higher=compare&&value>(side?left:right);
          const signal=compare?'<span aria-hidden="true">'+(higher?'↑':'↓')+'</span><span class="sr-only">'+
            (higher?'Higher value':'Lower value')+'</span>':'';
          return '<td><span class="comparison-value'+(compare?(higher?' compare-higher':' compare-lower'):'')+'">'+
            escape(display(value))+signal+'</span></td>';
        }).join('')+'</tr>';
      }).join('')+'</tbody>').join('')+'</table></div>';
}
async function reportFalsePositive(flow, control) {
  if (managementPending) return;
  managementPending=true;
  control.disabled=true;
  try {
    await managementRequest('/feedback',{flow:{id:flow.id,alert_id:flow.alertId,source:flow.source,receipt:flow.receipt}});
    managementTab='feedback';
    go('management');
    toast('False positive report saved');
  } catch (error) {
    toast(error.message);
  } finally {
    managementPending=false;
    control.disabled=false;
  }
}
async function submitManagement(path, payload, success, form) {
  if (managementPending) return;
  managementPending=true;
  const submitters=[...(form?.elements||[])].filter(control=>control.type==='submit'&&!control.disabled);
  submitters.forEach(button=>{button.disabled=true;});
  try {
    await managementRequest(path,payload);
    await success();
  } catch(error) {
    managementError(error.message);
  } finally {
    managementPending=false;
    if (form?.isConnected) submitters.forEach(button=>{button.disabled=false;});
  }
}
document.addEventListener('click',event=>{
  const target=event.target.closest('[data-management]');
  if (!target) return;
  const {management,value}=target.dataset;
  if (management==='useReference') {
    setTrainingParameters(referenceConfig());return;
  }
  if (management==='resetTrainingParameters') {
    byId('train-model-form').querySelectorAll('.training-parameter input').forEach(input=>{input.value=input.defaultValue;});
    return;
  }
  if (management==='selectFeedback'||management==='clearFeedback') {
    const selector=management==='selectFeedback'?'.feedback-choice:not([hidden]) input':'.feedback-choice input';
    byId('train-model-form').querySelectorAll(selector).forEach(input=>{input.checked=management==='selectFeedback';});
    updateTrainingCounts();
    return;
  }
  if (management==='refresh') refreshManagement();
  if (management==='tab') {
    managementTab=value;
    nav();
    renderManagementBody();
  }
});
document.addEventListener('input',event=>{
  if (event.target.id!=='training-feedback-search') return;
  const terms=event.target.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  byId('train-model-form').querySelectorAll('.feedback-choice').forEach(choice=>{
    choice.hidden=!terms.every(term=>choice.dataset.search.includes(term));
  });
  updateTrainingCounts();
});
document.addEventListener('invalid',event=>{
  const stage=event.target.closest('.training-stage');
  if (stage) stage.open=true;
},true);
document.addEventListener('change',event=>{
  if (event.target.id==='training-reference') {
    trainingReference=event.target.value;
    updateTrainingReference();
  }
  if (['feedback-status','feedback-source','feedback-model','feedback-class'].includes(event.target.id)) updateFeedbackFilters();
  if (event.target.form?.id==='train-model-form' && event.target.name==='feedback_id') updateTrainingCounts();
  if (event.target.id==='compare-left'||event.target.id==='compare-right') renderComparison();
});
document.addEventListener('submit',event=>{
  const form=event.target;
  const isTrain=form.id==='train-model-form';
  if (!isTrain&&!form.dataset.activateVersion) return;
  event.preventDefault();
  const values=new FormData(form);
  if (isTrain) {
    const config={strategy:'class_weighted',max_validation_fpr:.05,stage1:{},stage2:{}};
    for (const [key,value] of values) {
      const [stage,parameter]=key.split('.');
      if (parameter) config[stage][parameter]=Number(value);
    }
    submitManagement('/jobs',{config,feedback_ids:values.getAll('feedback_id')},async()=>{
      toast('Training started');await refreshManagement();
    },form);
  } else {
    submitManagement('/activate',{version:form.dataset.activateVersion},async()=>{
      await loadModelInfo();await refreshManagement();renderComparison();toast('Active model changed');
    },form);
  }
});

