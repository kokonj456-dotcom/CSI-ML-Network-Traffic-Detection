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
  const strategy=form.elements.namedItem('strategy')?.value||trainingStrategy;
  byId('training-strategy-summary').textContent=trainingStrategies[strategy]?.short||'—';
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
  const strategyOptions=Object.entries(trainingStrategies).map(([value,strategy])=>
    '<option value="'+escape(value)+'"'+(trainingStrategy===value?' selected':'')+'>'+escape(strategy.label)+'</option>').join('');
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
    '<fieldset><legend>Training strategy</legend><label for="training-strategy">How should the candidate be trained?'+
    '<select id="training-strategy" name="strategy">'+strategyOptions+'</select></label>'+
    '<small class="case-note" id="training-strategy-help">'+escape(trainingStrategies[trainingStrategy]?.help||'')+'</small></fieldset>'+
    '<fieldset><legend>XGBoost parameters</legend><p class="case-note">The form starts with M9 Production values.</p>'+
    '<label>Reference model <select id="training-reference" aria-describedby="training-reference-date">'+referenceOptions+'</select>'+
    '<small class="comparison-picked-date" id="training-reference-date"></small></label>'+
    '<div class="actions training-param-actions">'+managedButton('Use reference values','useReference','')+
    managedButton('Reset to defaults','resetTrainingParameters','')+'</div>'+
    formFields('stage1')+formFields('stage2')+'</fieldset></form></section>'+
    '<div class="training-sidebar"><section class="panel panel-pad"><h2>Training summary</h2>'+
    '<dl class="fields"><div><dt>CENTRAL training rows</dt><dd id="training-base-count"></dd></div>'+
    '<div><dt>Feedback selected</dt><dd id="training-selected-count"></dd></div>'+
    '<div><dt>Validation rows</dt><dd id="training-validation-count"></dd></div>'+
    '<div><dt>Selected strategy</dt><dd id="training-strategy-summary"></dd></div></dl>'+
    '<p class="case-note">A completed job creates a candidate for review in Model Registry.</p>'+
    '<button id="start-training" class="primary" type="submit" form="train-model-form"'+(managementData.jobs.some(job=>job.status==='running')?' disabled':'')+
    '>Start training</button></section><section class="panel panel-pad"><h2>Training jobs</h2>'+
    '<div id="management-jobs">'+jobCards()+'</div></section></div></div>';
}
