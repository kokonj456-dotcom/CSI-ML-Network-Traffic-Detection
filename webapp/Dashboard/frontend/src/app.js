'use strict';

let firewallLogPending=false;

document.addEventListener('click',async event=>{
  if (event.target.closest('.alert-select')) return;
  const control=event.target.closest('[data-action]');
  if (!control) return;
  const {action,value}=control.dataset;
  switch(action) {
    case 'importPcap':
      byId('capture-upload-file').click();break;
    case 'clearAlertSelection':
      selectedAlerts.clear();updateAlertSelection();break;
    case 'bulkAlert':
      await bulkAlertAction(value);break;
    case 'theme': setTheme(value,true);break;
    case 'navigate': go(value); break;
    case 'protocol': go('explorer',overviewScope({protocol:value})); break;
    case 'destination': go('explorer',overviewScope({destination:JSON.parse(value)}));break;
    case 'alertMode':
      state.alertMode=value;
      if (value==='grouped') delete state.filters.alertGroup;
      state.page=0;render();break;
    case 'alertGroup':
      state.alertMode='individual';
      state.filters.alertGroup=value;
      state.page=0;render();break;
    case 'alertType': go('alerts',overviewScope({label:value}));break;
    case 'latestAlert':
      go('alerts',overviewScope({search:value}));
      state.selection={type:'flow',id:value};state.tab='Model';showInspector();break;
    case 'summary':
      if (value==='flagged' || value==='unreviewed') go('alerts',overviewScope({status:value==='unreviewed'?'New':''}));
      else go('explorer',overviewScope());
      break;
    case 'period':
      state.filters.range=value;
      document.querySelector('[data-filter="range"]').value=value;
      updateFilters();
      break;
    case 'resetFilters': go(state.view); break;
    case 'page':
      state.page+=Number(value);
      renderTable();
      if (state.view==='explorer') document.querySelector('.explorer-table .table-head').scrollIntoView({block:'nearest'});
      break;
    case 'explorerDomain':
      state.filters.search='domain:'+value;
      byId('search').value=state.filters.search;
      updateFilters();
      byId('search').focus();
      break;
    case 'firewallRules':
      state.selection={type:'firewallRules'};showInspector();break;
    case 'openFirewallLog':
      if (firewallLogPending) break;
      firewallLogPending=true;
      control.disabled=true;
      try {
        const path='/api/firewall/open-log'+(value?'?rule_id='+encodeURIComponent(value):'');
        await firewallRequest(path,'POST');
        toast('Opening the Windows Firewall log in Notepad.');
      } catch (error) {
        toast(error.message);
      } finally {
        firewallLogPending=false;
        control.disabled=false;
      }
      break;
    case 'exportBlockIps':
      exportBlockIps();break;
    case 'editBlock':
      state.selection={type:'editBlock',id:value};showInspector();break;
    case 'blockIp': {
      const [ip,flowId]=JSON.parse(value);
      const flow=flowId?allFlows().find(row=>row.id===flowId):null;
      state.selection={type:'block',ip,flowId,flowTime:flow?.timestamp,reason:flow?.label,parent:state.selection};
      showInspector();break;
    }
    case 'unblockIp':
      state.selection={type:'unblock',id:value};
      showInspector();break;
    case 'cancelBlock':
      state.selection=state.selection.parent || null;
      showInspector();break;
    case 'clearRelatedDates':
      delete state.selection.relatedDates;
      state.selection.showAllRelated=false;
      showInspector();
      byId('related-date-form')?.elements.from.focus();
      break;
    case 'toggleRelated':
      state.selection.showAllRelated=!state.selection.showAllRelated;
      showInspector();
      byId('inspector').querySelector('[data-action="toggleRelated"]')?.focus({preventScroll:true});
      break;
    case 'toggleIpConnections':
      state.selection.showAllIpConnections=!state.selection.showAllIpConnections;
      showInspector();
      byId('inspector').querySelector('[data-action="toggleIpConnections"]')?.focus({preventScroll:true});
      break;
    case 'reportFalsePositive': {
      const flow=allFlows().find(item=>item.id===value);
      if (!flow || flow.kind!=='flag') break;
      await reportFalsePositive(flow,control);break;
    }
    case 'relatedFlow':
      state.selection={type:'flow',id:value};state.tab='Overview';showInspector();break;
    case 'flow': state.selection={type:'flow',id:value};state.tab=state.view==='alerts'?'Model':'Overview';showInspector();break;
    case 'ip': {
      const parent=state.selection?.type==='flow'?{...state.selection,tab:state.tab}:null;
      state.selection={type:'ip',id:value,parent,showAllIpConnections:false};
      state.role='all';showInspector();break;
    }
    case 'backToFlow': {
      const parent=state.selection?.parent;
      if (!parent) break;
      state.selection=parent;state.tab=parent.tab;showInspector();break;
    }
    case 'searchIp': go('explorer',{...state.filters,search:'ip:'+value});break;
    case 'close': state.selection=null;showInspector();renderTable();break;
    case 'tab': state.tab=value;showInspector();break;
    case 'role':
    case 'ipPeer':
    case 'ipBin': {
      if (action==='role') {
        state.role=value;
        state.selection.peer=null;
      } else if (action==='ipPeer') {
        state.selection.peer=value===state.selection.peer?null:value;
      }
      if (action==='ipBin' && value) {
        const [start,duration]=value.split(',').map(Number);
        state.selection.ipBin=state.selection.ipBin?.start===start?null:{start,end:start+duration};
      } else state.selection.ipBin=null;
      showInspector();
      const controls=[...byId('inspector').querySelectorAll('[data-action="'+action+'"]')];
      (controls.find(item=>item.dataset.value===value) || controls[0])?.focus();
      break;
    }
    case 'review': {
      const id=state.selection.id;
      const flow=allFlows().find(item=>item.id===id);
      if (flow?.alertId) {
        try {
          const response=await saveAlertStatus(flow.alertId,value.toLowerCase());
          if (!response.ok) throw Error();
        } catch {
          toast('Alert status could not be saved.');
          break;
        }
      }
      if (value==='New') delete review[id];
      else review[id]=value;
      try { localStorage.setItem('flowwatch-demo-review-v1', JSON.stringify(review)); } catch {}
      nav();renderMetrics();renderTable();showInspector();toast('Alert '+value.toLowerCase());break;
    }
    case 'export': exportFlows();break;
    case 'lock':
      state.locked=true; nav();
      byId('login').querySelector('button').focus();break;
    case 'unlock':
      state.locked=false; nav();
      document.querySelector('.nav-item.active').focus();break;
  }
});
document.addEventListener('submit',async event=>{
  if (event.target.id==='related-date-form') {
    event.preventDefault();
    const values=new FormData(event.target);
    const from=String(values.get('from') || values.get('to') || '');
    const to=String(values.get('to') || values.get('from') || '');
    if (!from || from>to) {
      byId('related-date-error').textContent=from?'End date must be on or after start date.':'Choose at least one date.';
      return;
    }
    state.selection.relatedDates={from,to};
    state.selection.showAllRelated=false;
    showInspector();
    byId('related-date-form')?.querySelector('[type="submit"]').focus({preventScroll:true});
    return;
  }
  if (event.target.id!=='block-form') return;
  event.preventDefault();
  const values=new FormData(event.target);
  const selection=state.selection;
  const submit=event.submitter || event.target.querySelector('[type="submit"]');
  if (submit.disabled) return;
  const reason=String(values.get('reason')||'').trim();
  const duration=Number(values.get('duration'));
  submit.disabled=true;
  try {
    const endpoint='/api/firewall';
    if (selection.type==='unblock') {
      await firewallRequest(endpoint+'/'+encodeURIComponent(selection.id),'DELETE');
    } else if (selection.type==='editBlock') {
      await firewallRequest(endpoint+'/'+encodeURIComponent(selection.id),'PATCH',{reason,duration});
    } else {
      const targets=selection.type==='bulkBlock'?[...selection.targets].map(([ip,flow])=>({ip,flowId:flow.id,flowTime:flow.timestamp})):
        [{ip:canonicalIp(String(values.get('ip')||'')),flowId:selection.flowId||null,flowTime:selection.flowTime||null}];
      if (targets.some(target=>!target.ip)) throw Error('Enter one valid IPv4 or IPv6 address.');
      await firewallRequest(endpoint,'POST',{targets,reason,duration});
      if (selection.type==='bulkBlock') for (const flow of selection.flows) selectedAlerts.delete(flow.id);
    }
    await refreshFirewall();
    blockSearch='';blockFilter='';
    go('blocklist');
    toast(selection.type==='unblock'?'Windows Firewall rule disabled':'Windows Firewall updated');
  } catch (error) {
    const message=byId('block-error');
    if (message) message.textContent=error.message;
    else toast(error.message);
  } finally {
    submit.disabled=false;
  }
});
document.addEventListener('input',event=>{
  if(event.target.id==='block-search') {blockSearch=event.target.value;renderBlocks();}
  if(event.target.id==='search') {state.filters.search=event.target.value;updateFilters();}
  if(event.target.dataset?.filter && ['from','to','from_time','to_time'].includes(event.target.dataset.filter)) {
    state.filters[event.target.dataset.filter]=event.target.value;
    updateFilters();
  }
});
document.addEventListener('change',event=>{
  const {id,value,dataset}=event.target;
  if (id==='capture-upload-file') {
    const file=event.target.files[0];
    event.target.value='';
    if (file) importCaptureFile(file);
    return;
  }
  if (id==='select-alert-page' || Object.hasOwn(dataset,'alertSelect')) {
    changeAlertSelection(event.target);return;
  }
  if (dataset.filter && id!=='search') {
    if (['range','from','to','from_time','to_time'].includes(dataset.filter) && state.filters.bucket) {
      delete state.filters.bucket;
      const scope=byId('page').querySelector('.scope-summary');
      if (scope) scope.outerHTML=investigationScope();
    }
    state.filters[dataset.filter]=value;updateFilters();
  }
  if (id==='block-filter') {blockFilter=value;renderBlocks();}
  if (id==='explorer-size') {state.explorerSize=Number(value);state.page=0;renderTable();}
  if (id==='explorer-sort') {state.explorerSort=value;state.page=0;renderTable();}
  if (id==='ranking') {state.ranking=value;renderMetrics();}
});
let renderWorkspace;
function startWorkspace(mount) {
  renderWorkspace=mount;
  setTheme(initialTheme());
  render();
  const inspector=byId('inspector');
  inspector.addEventListener('close',event=>{if (!event.currentTarget.open) state.selection=null;});
  inspector.addEventListener('click',event=>{if(event.target===inspector) inspector.close();});
  window.addEventListener('resize',()=>drawChart());
  setInterval(()=>{if (state.view==='blocklist' && !state.locked) refreshFirewall();},15000);
  refreshFirewall();
  loadModelInfo();
  refreshTraffic();
}
