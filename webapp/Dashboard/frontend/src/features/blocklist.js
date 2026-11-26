'use strict';

function canonicalIp(input) {
  const value=input.trim();
  if (/^(?:0|[1-9][0-9]{0,2})(?:[.](?:0|[1-9][0-9]{0,2})){3}$/.test(value) &&
      value.split('.').every(octet=>Number(octet)<=255)) return value;
  if (!value.includes(':') || !/^[0-9a-f:.]+$/i.test(value)) return null;
  try {return new URL('http://['+value+']').hostname.slice(1,-1);} catch {return null;}
}
function blockStatus(record,now=Date.now()) {
  if (record.unblockedAt) return 'Unblocked';
  if (!record.enabled) return record.expiresAt<=now?'Expired':'Disabled';
  return record.expiresAt<=now?'Expiry pending':'Active';
}
function activeBlock(ip,now=Date.now()) {
  return blocks.find(entry=>entry.ip===ip && entry.enabled);
}
async function firewallRequest(path, method='GET', body) {
  const response=await fetch(path,{method,...(body?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
  const data=await response.json();
  if (!response.ok) throw Error(typeof data.detail==='string'?data.detail:'Windows Firewall rejected the request.');
  return data;
}
async function refreshFirewall() {
  try {
    firewallInfo=await firewallRequest('/api/firewall');
    blocks=firewallInfo.rules;
  } catch (error) {
    firewallInfo={error:error.message};
  }
  renderBlocks();
}
function blockDate(value) {
  return localDay.format(value)+' '+time(value)+' ICT';
}
function blockSourceButton(ip, flowId='') {
  return activeBlock(ip)?badge('Windows Firewall rule enabled','flag'):
    button('Block source IP','blockIp',JSON.stringify([ip,flowId]),'btn danger');
}
function activeFirewallRules() {
  const now=Date.now();
  return blocks.filter(rule=>rule.enabled);
}
function firewallRulesInspector() {
  const rules=activeFirewallRules();
  return drawerHeader('Windows Firewall','Active rules',badge(num(rules.length)+' active','flag'))+
    '<div class="drawer-body"><p class="case-note">These Flowwatch rules block inbound connections in Windows Firewall.</p>'+
    formatFields([['Direction','Inbound'],['Action','Block'],['Protocols and ports','Any']])+
    '<h3>'+uiSymbol('⊘')+'Blocked source IPs</h3>'+
    (rules.length?'<ul class="firewall-rule-list">'+rules.map(rule=>'<li><strong class="mono">'+escape(rule.ip)+'</strong>'+
      '<span>'+escape(rule.reason)+'</span><small>Expires '+blockDate(rule.expiresAt)+'</small></li>').join('')+'</ul>':
      '<p class="case-note">There are no active blocks.</p>')+
    (rules.length?button('Export IPs (.txt)','exportBlockIps'):'')+'</div>';
}
function exportBlockIps() {
  const ips=[...new Set(activeFirewallRules().map(rule=>rule.ip))];
  if (!ips.length) {toast('No active IPs to export');return;}
  const url=URL.createObjectURL(new Blob([ips.join('\n')+'\n'],{type:'text/plain;charset=utf-8'}));
  const link=document.createElement('a');
  link.href=url;
  link.download='flowwatch-blocklist.txt';
  link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
  toast('Exported '+num(ips.length)+' active IPs');
}
function blockPage() {
  return heading(button('Read Firewall','openFirewallLog')+button('View active rules','firewallRules')+button('Export IPs (.txt)','exportBlockIps')+
    button('Block IP','blockIp','[]','primary'))+
    '<section class="block-banner"><div><strong>Windows Firewall</strong><p id="firewall-status" role="status">Checking firewall connection…</p></div><span id="block-count" class="badge flag"></span></section>'+
    '<section class="panel table-panel"><div class="panel-head table-head"><div><h2>'+uiSymbol('⊙')+'IP block rules</h2><p>Temporary blocks and their history</p></div></div>'+
    '<div class="filters"><label class="search"><span aria-hidden="true">⌕</span><input id="block-search" aria-label="Search blocklist" placeholder="Search IP, reason, or alert ID" value="'+escape(blockSearch)+'"></label>'+
    '<select id="block-filter" aria-label="Block status">'+['','Active','Expiry pending','Expired','Unblocked','Disabled'].map(status=>'<option value="'+status+'"'+(blockFilter===status?' selected':'')+'>'+(status||'All statuses')+'</option>').join('')+'</select></div>'+
    '<div class="table-scroll"><table class="flow-table block-table"><thead><tr><th>Source IP</th><th>Status</th><th>Reason / Alert</th><th>Blocked by</th><th>Started</th><th>Expires</th><th>Action</th></tr></thead><tbody id="block-rows"></tbody></table></div></section>';
}
function renderBlocks() {
  if (!byId('block-rows')) return;
  const now=Date.now();
  const query=blockSearch.trim().toLowerCase();
  const active=blocks.filter(b=>b.enabled).length;
  byId('firewall-status').textContent=firewallInfo?.error||(firewallInfo?.writable?
    'Flowwatch rules block inbound traffic. Keep the backend running to apply expiration times.':
    firewallInfo?.connected?'Run the backend as administrator to change Windows Firewall rules.':
    firewallInfo?'Windows Firewall integration is disabled.':'Checking firewall connection…');
  byId('block-count').textContent=num(active)+' active';
  if (!document.activeElement.closest('#block-rows')) {
    byId('block-rows').innerHTML=blocks.filter(b=>
      (!blockFilter || blockStatus(b,now)===blockFilter) &&
      [b.ip,b.reason,b.flowId].some(value=>String(value||'').toLowerCase().includes(query))
    ).map(b=>{
      const status=blockStatus(b,now);
      const ref=allFlows().find(flow=>flow.id===b.flowId && flow.timestamp===b.flowTime);
      return '<tr><td>'+ipLink(b.ip)+'</td><td>'+badge(status,status==='Active'?'flag':'')+'</td><td class="block-reason">'+escape(b.reason)+
        (b.flowId?'<small>'+(ref?button(escape(b.flowId),'flow',b.flowId,'text-button'):escape(b.flowId))+'</small>':'')+
        '</td><td>Local analyst</td><td>'+blockDate(b.createdAt)+'</td><td>'+blockDate(b.expiresAt)+
        '</td><td><div class="actions">'+button('View Log','openFirewallLog',b.id,'btn')+
        (b.enabled?button('Edit','editBlock',b.id,'btn')+button('Unblock','unblockIp',b.id,'btn'):
          b.unblockedAt?'<span class="muted">'+blockDate(b.unblockedAt)+'</span>':'')+'</div></td></tr>';
    }).join('') || '<tr><td class="empty" colspan="7">'+(blocks.length?'No blocks match these filters.':'No IPs have been blocked. Use Block IP or open a suspicious flow.')+'</td></tr>';
  }
}
function blockForm(selection) {
  if (selection.type==='bulkBlock') {
    return drawerHeader('Windows Firewall','Block source IPs','')+
      '<form class="drawer-body block-form" id="block-form"><p class="case-note">Block inbound traffic from '+num(selection.targets.size)+
      ' distinct source IPs.</p><ul>'+[...selection.targets.keys()].map(ip=>'<li>'+escape(ip)+'</li>').join('')+'</ul>'+
      '<label>Duration <select name="duration"><option value="15">15 minutes</option><option value="60" selected>1 hour</option><option value="1440">24 hours</option></select></label>'+
      '<label>Reason <input name="reason" required maxlength="160"></label>'+
      '<p id="block-error" class="form-error" role="alert"></p><div class="actions"><button class="primary" type="submit">Confirm firewall block</button>'+
      button('Cancel','cancelBlock')+'</div></form>';
  }
  const removing=selection.type==='unblock';
  const editing=selection.type==='editBlock';
  const record=removing||editing?blocks.find(b=>b.id===selection.id):null;
  const ip=record?.ip || selection.ip || '';
  return drawerHeader('Windows Firewall',removing?'Unblock IP':editing?'Edit rule':'Block source IP','')+
    '<form class="drawer-body block-form" id="block-form"><p class="case-note">'+
    (removing?'Disable this Flowwatch rule in Windows Firewall.':editing?'Set a new duration starting now and update the reason for this rule.':'Block inbound traffic from this source IP in Windows Firewall.')+'</p>'+
    '<label>Source IP <input name="ip" required maxlength="45" placeholder="203.0.113.24" value="'+escape(ip)+'"'+(ip?' readonly':'')+'></label>'+
    (removing?'':'<label>Duration <select name="duration"><option value="15">15 minutes</option><option value="60" selected>1 hour</option><option value="1440">24 hours</option></select></label><label>Reason <input name="reason" required maxlength="160" value="'+escape(record?.reason || selection.reason || '')+'"></label>'+
    (selection.flowId?'<p class="case-note">Related alert '+escape(selection.flowId)+'</p>':''))+
    '<p id="block-error" class="form-error" role="alert"></p><div class="actions"><button class="primary" type="submit">'+
    (removing?'Confirm unblock':editing?'Save firewall rule':'Confirm firewall block')+'</button>'+button('Cancel','cancelBlock')+'</div></form>';
}
