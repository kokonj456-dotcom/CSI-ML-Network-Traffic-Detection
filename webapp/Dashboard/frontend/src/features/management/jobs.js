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
