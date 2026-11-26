function versionDetails(version, latest) {
  const {manifest,evaluation}=version;
  const finished=manifest.training?.finished_at;
  const isActive=version.version===managementData.active;
  const isBaseline=version.version==='baseline';
  const isLatest=version.version===latest;
  const role=isActive?['In use','version-in-use']:isBaseline?['Baseline','version-baseline']:['Candidate','version-candidate'];
  const classes=['management-version',isActive?'version-active':'',isLatest?'version-latest':'',isBaseline?'version-baseline':''].filter(Boolean).join(' ');
  return '<details class="'+classes+'"><summary><span class="version-title"><span class="version-model-id">'+escape(manifest.model_id)+'</span>'+
    badge(role[0],'version-state '+role[1])+(isLatest?badge('Latest trained','version-state version-newest'):'')+'</span>'+
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
  return '<section class="panel panel-pad"><h2>'+uiSymbol('↔')+'Compare versions</h2><p class="case-note">Compare evaluations by their test-data fingerprint.</p>'+
    '<div class="management-compare">'+['left','right'].map((side,index)=>'<label>Version '+(index+1)+
      ' <select id="compare-'+side+'" aria-describedby="compare-date-'+side+'">'+comparisonOptions(versions,index===0?first:second,latest)+
      '</select><small class="comparison-picked-date" id="compare-date-'+side+'"></small></label>').join('')+
    '</div><div id="model-comparison"></div></section><section class="panel panel-pad firewall-panel"><h2>'+uiSymbol('◫')+'Available models</h2>'+
    '<p class="case-note model-registry-note">In use serves new predictions. Latest trained is the newest run and may still need review.</p>'+
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
