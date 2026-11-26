'use strict';

function showInspector() {
  const dialog=byId('inspector');
  if (!state.selection) { if (dialog.open) dialog.close(); return; }
  const {type,id}=state.selection;
  const flow=type==='flow'?allFlows().find(f=>f.id===id):null;
  if (type==='flow' && !flow) { dialog.close(); state.selection=null; return; }
  dialog.className='drawer';
  dialog.innerHTML=type==='ip'?ipInspector(id):type==='flow'?flowInspector(flow):type==='firewallRules'?firewallRulesInspector():blockForm(state.selection);
  if (!dialog.open) dialog.showModal();
  else if (document.activeElement===document.body) {
    (dialog.querySelector('[aria-pressed="true"]') || dialog.querySelector('button')).focus();
  }
}
