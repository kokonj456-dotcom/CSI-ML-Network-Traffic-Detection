'use strict';

function alertKey(flow) {
  return JSON.stringify([flow.label,flow.src,flow.dst,flow.dport,flow.app,modelVersion(flow),flow.dataset?.record_id]);
}
const selectedAlerts = new Set();
let alertSelectionRows = [];
let bulkAlertPending = false;

function alertCheckbox(id, label) {
  return '<td class="alert-select"><input type="checkbox" data-alert-select="'+escape(id)+
    '" aria-label="'+escape(label)+'"></td>';
}

function updateAlertSelection() {
  const header=byId('select-alert-page');
  if (!header) return;
  const update=(checkbox, ids)=>{
    const count=ids.filter(id=>selectedAlerts.has(id)).length;
    checkbox.checked=ids.length>0 && count===ids.length;
    checkbox.indeterminate=count>0 && count<ids.length;
    return count>0;
  };
  const pageIds=alertSelectionRows.flat();
  header.disabled=!pageIds.length;
  update(header,pageIds);
  document.querySelectorAll('#table-rows [data-alert-select]').forEach((checkbox,index)=>{
    checkbox.closest('tr').classList.toggle('selected-alert',update(checkbox,alertSelectionRows[index]));
  });
  byId('alert-selected-count').textContent=num(selectedAlerts.size)+' selected';
  byId('clear-alert-selection').disabled=!selectedAlerts.size;
  document.querySelectorAll('[data-action="bulkAlert"]').forEach(control=>{
    control.disabled=bulkAlertPending || !selectedAlerts.size;
  });
}

async function bulkAlertAction(action) {
  if (bulkAlertPending) return;
  const flows=allFlows().filter(flow=>selectedAlerts.has(flow.id));
  if (!flows.length) return toast('Selected alerts are no longer visible.');
  if (action==='block') {
    const targets=new Map();
    for (const flow of flows) {
      const ip=canonicalIp(flow.src||'');
      if (ip && !activeBlock(ip)) targets.set(ip,flow);
    }
    if (!targets.size) return toast('No new source IPs to add to the blocklist.');
    state.selection={type:'bulkBlock',targets,flows};
    showInspector();
    return;
  }
  bulkAlertPending=true;
  updateAlertSelection();
  let succeeded=0, failed=selectedAlerts.size-flows.length;
  try {
    for (const flow of flows) {
      try {
        if (!flow.alertId) throw Error('Alert is not saved.');
        if (action==='resolve') {
          const response=await saveAlertStatus(flow.alertId,'resolved');
          if (!response.ok) throw Error('Could not resolve alert.');
          review[flow.id]='Resolved';
        } else {
          await managementRequest('/feedback',{flow:{alert_id:flow.alertId}});
          markReportedFalsePositive(flow);
        }
        selectedAlerts.delete(flow.id);
        succeeded++;
      } catch {
        failed++;
      }
    }
  } finally {
    bulkAlertPending=false;
    nav();
    renderTable();
  }
  const message=succeeded+(action==='resolve'?' resolved':' reported as false positive');
  toast(message+(failed?' · '+failed+' could not be changed':''));
}

function changeAlertSelection(checkbox) {
  const ids=checkbox.id==='select-alert-page'?alertSelectionRows.flat():alertSelectionRows[Number(checkbox.dataset.alertSelect)];
  for (const id of ids || []) {
    if (checkbox.checked) selectedAlerts.add(id);
    else selectedAlerts.delete(id);
  }
  updateAlertSelection();
}
