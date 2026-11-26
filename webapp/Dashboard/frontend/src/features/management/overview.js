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
