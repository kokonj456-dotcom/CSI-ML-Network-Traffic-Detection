function markReportedFalsePositive(flow) {
  for (const row of [...capturedFlows, ...savedAlertFlows]) {
    if (row.alertId === flow.alertId) row.falsePositiveReported = true;
  }
  review[flow.id] = 'Resolved';
  selectedAlerts.delete(flow.id);
}

async function reportFalsePositive(flow, control) {
  if (managementPending) return;
  managementPending=true;
  control.disabled=true;
  try {
    await managementRequest('/feedback',{flow:{id:flow.id,alert_id:flow.alertId,source:flow.source,receipt:flow.receipt}});
    markReportedFalsePositive(flow);
    nav();
    if (state.view==='alerts' || state.view==='explorer') renderTable();
    if (state.view==='live') renderMetrics();
    showInspector();
    toast('False positive reported · Alert resolved');
  } catch (error) {
    toast(error.message);
  } finally {
    managementPending=false;
    if (control.isConnected) control.disabled=false;
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
  if (management==='feedbackPage') {
    feedbackPageIndex+=Number(value);
    updateFeedbackFilters();
    byId('feedback-items').querySelector('summary')?.focus();
    return;
  }
  if (management==='resetFeedback') {
    document.querySelectorAll('.feedback-filters :is(select,input)').forEach(control=>{control.value='';});
    feedbackPageIndex=0;
    updateFeedbackFilters();
    return;
  }
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
  if (event.target.id==='feedback-search') {
    feedbackPageIndex=0;
    updateFeedbackFilters();
    return;
  }
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
  if (event.target.id==='training-strategy') {
    trainingStrategy=event.target.value;
    byId('training-strategy-help').textContent=trainingStrategies[trainingStrategy]?.help||'';
    byId('training-strategy-summary').textContent=trainingStrategies[trainingStrategy]?.short||'—';
  }
  if (['feedback-status','feedback-source','feedback-model','feedback-class'].includes(event.target.id)) {
    feedbackPageIndex=0;
    updateFeedbackFilters();
  }
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
    const config={strategy:String(values.get('strategy')||'class_weighted'),max_validation_fpr:.05,stage1:{},stage2:{}};
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
