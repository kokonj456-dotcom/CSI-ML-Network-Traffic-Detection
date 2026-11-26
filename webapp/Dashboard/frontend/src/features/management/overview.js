function managementOverview() {
  const active=managementData.versions.find(version=>version.version===managementData.active);
  const manifest=active?.manifest;
  const metrics=active?.evaluation?.test_feature_group_disjoint;
  const eligible=managementData.feedback.filter(row=>row.status==='approved'&&row.eligible).length;
  const stats=[
    ['Alert threshold',scoreText(manifest?.threshold)],
    ['Binary F1',scoreText(metrics?.binary?.f1)],
    ['False-positive rate',scoreText(metrics?.binary?.fpr)],
    ['Eligible feedback',num(eligible)],
  ];
  return '<section class="panel panel-pad model-overview"><div class="panel-head model-overview-header"><div><h2>Active model</h2>'+
    '<p class="model-overview-id">'+escape(manifest?.model_id||'Unavailable')+'</p><p>Training finished · '+escape(dateText(manifest?.training?.finished_at))+'</p></div>'+
    '<div class="actions">'+managedButton('Model Registry','tab','registry')+managedButton('Train & Tune','tab','train','primary')+'</div></div>'+
    '<dl class="model-overview-stats">'+stats.map(([label,value])=>'<div><dt>'+label+'</dt><dd>'+value+'</dd></div>').join('')+
    '</dl><p class="case-note">F1 and false-positive rate are from the offline CENTRAL test with feature groups held out.</p></section>'+
    '<div class="grid-two model-overview-details"><section class="panel panel-pad"><h2>Evaluation details</h2>'+
    (metrics?'<p class="case-note">Feature-group-disjoint CENTRAL test</p>'+assessmentSummary(metrics):'<p class="case-note">No saved evaluation for this model.</p>')+
    '</section><section class="panel panel-pad"><h2>Training jobs</h2><p class="case-note">Running jobs and completed jobs with a model bundle currently available.</p><div id="management-jobs">'+jobCards()+'</div></section></div>';
}
