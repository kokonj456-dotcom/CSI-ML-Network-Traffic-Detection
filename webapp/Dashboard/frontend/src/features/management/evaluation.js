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
