'use strict';

function groupedAlerts(rows) {
  const groups = new Map();
  for (const flow of rows) {
    const key=alertKey(flow);
    if (!groups.has(key)) groups.set(key,{key,latest:flow,count:0,newCount:0,score:0,ids:[]});
    const group=groups.get(key);
    group.count++;
    group.ids.push(flow.id);
    group.score=Math.max(group.score,flow.score);
    if (!review[flow.id]) group.newCount++;
  }
  return [...groups.values()];
}
function alertSummary() {
  return '<section class="explorer-overview alert-summary" aria-label="Filtered alert summary">'+
    [['total','Matching alerts'],['new','Needs review'],['ack','Acknowledged'],['resolved','Resolved']].map(([key,label])=>
      '<div><span>'+label+'</span><strong id="alert-total-'+key+'">0</strong></div>').join('')+
    '</section>';
}
function alertGroupRow(group, index) {
  const f=group.latest;
  return '<tr class="flagged-row" data-action="flow" data-value="'+escape(f.id)+'">'+
    alertCheckbox(index,'Select group for '+f.src+' · '+f.label)+'<td class="mono">'+button(shortDay.format(f.timestamp)+' '+time(f.timestamp),'flow',f.id,'text-button')+
    '</td><td><strong class="alert-pattern">'+escape(f.label)+'</strong><small class="flow-sub">'+escape(f.dataset?.record_id || f.app)+'</small></td><td>'+flowEndpoint(f,'src',false)+
    '</td><td>'+flowEndpoint(f,'dst')+'</td><td class="mono">'+num(group.count)+
    '</td><td>'+badge(num(group.newCount)+' new',group.newCount?'flag':'')+
    '</td><td class="mono">'+(group.score*100).toFixed(0)+'%</td><td>'+
    button('View alerts ›','alertGroup',group.key,'text-button')+'</td></tr>';
}
