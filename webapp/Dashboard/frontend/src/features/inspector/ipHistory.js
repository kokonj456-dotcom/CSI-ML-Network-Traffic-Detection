'use strict';

function peerIp(flow,ip) {
  return flow.src===ip?flow.dst:flow.src;
}
function ipTimeline(flows) {
  if (!flows.length) return '<section class="ip-timeline"><h3>'+uiSymbol('⌁')+'Activity timeline</h3><p class="case-note">No activity in this selection.</p></section>';
  const first=flows.at(-1).timestamp;
  const last=flows[0].timestamp;
  const duration=[60_000,300_000,900_000,3_600_000,21_600_000,86_400_000,604_800_000,2_592_000_000]
    .find(ms=>Math.floor(last/ms)-Math.floor(first/ms)<12) || Math.max(1,Math.ceil((last-first)/11));
  const start=Math.floor(first/duration)*duration;
  const bins=Array.from({length:Math.floor((last-start)/duration)+1},(_,i)=>({at:start+i*duration,total:0,flagged:0}));
  for (const flow of flows) {
    const bin=bins[Math.floor((flow.timestamp-start)/duration)];
    bin.total++;
    if(flow.kind==='flag') bin.flagged++;
  }
  const max=Math.max(1,...bins.map(bin=>bin.total));
  const date=ts=>shortDay.format(ts)+' '+time(ts).slice(0,5);
  const {ipBin}=state.selection;
  const bars=bins.map(bin=>{
    const active=ipBin?.start===bin.at;
    const label=date(bin.at)+' ICT · '+num(bin.total)+' flows · '+num(bin.flagged)+' suspicious';
    return '<button type="button" class="ip-bar" data-action="ipBin" data-value="'+bin.at+','+duration+'" aria-pressed="'+active+
      '" aria-label="'+escape(label)+'" title="'+escape(label)+'"'+(bin.total?'':' disabled')+'>'+
      '<span style="height:'+Math.max(2,100*bin.total/max)+'%"><i style="height:'+
      (bin.total?100*bin.flagged/bin.total:0)+'%"></i></span></button>';
  }).join('');
  return '<section class="ip-timeline"><div class="panel-head"><h3>'+uiSymbol('⌁')+'Activity timeline</h3><div class="chart-key"><span class="key"></span> Flows <span class="key alert"></span> Suspicious</div></div>'+
    '<div class="ip-bars" style="--slots:'+bins.length+'">'+bars+'</div><div class="ip-axis"><span>'+date(start)+
    '</span><span>'+date(bins.at(-1).at)+' ICT</span></div>'+
    (ipBin?'<div class="ip-selection"><span>'+date(ipBin.start)+' – '+date(ipBin.end)+' ICT</span>'+button('Clear time filter','ipBin','','text-button')+'</div>':
      '<p class="case-note ip-hint">Select a bar to filter connections by time.</p>')+'</section>';
}
function ipPeerMap(ip,flows) {
  const groups=new Map();
  for (const flow of flows) {
    const peer=peerIp(flow,ip);
    if (!groups.has(peer)) groups.set(peer,{peer,count:0,services:new Set()});
    const group=groups.get(peer);
    group.count++;
    group.services.add(flow.app+(flow.dport!=null?' / '+flow.dport:''));
  }
  if (groups.size<2) return '';
  const items=[...groups.values()].sort((a,b)=>b.count-a.count || a.peer.localeCompare(b.peer));
  return '<section class="ip-peer-map"><div class="panel-head"><h3>'+uiSymbol('⤢')+'Peer map</h3>'+
    (state.selection.peer?button('Clear peer filter','ipPeer','','text-button'):'')+'</div>'+
    '<div class="peer-hub mono">'+escape(ip)+'</div><ul class="peer-branches">'+items.map(item=>
      '<li><button type="button" class="peer-node" data-action="ipPeer" data-value="'+escape(item.peer)+'" aria-pressed="'+(state.selection.peer===item.peer)+'">'+
      '<span><strong class="mono">'+escape(item.peer)+'</strong><small>'+escape([...item.services].join(' · '))+'</small></span>'+
      '<span class="badge">'+num(item.count)+' flows</span></button></li>').join('')+'</ul></section>';
}
function ipInspector(ip) {
  const {start,end}=timeBounds();
  const matches=allFlows().filter(f=>f.timestamp>=start&&f.timestamp<=end&&(f.src===ip||f.dst===ip));
  const scoped=matches.filter(f=>state.role==='all'||f[state.role]===ip);
  const {peer,ipBin}=state.selection;
  const activity=peer?scoped.filter(f=>peerIp(f,ip)===peer):scoped;
  const visible=ipBin?activity.filter(f=>f.timestamp>=ipBin.start&&f.timestamp<ipBin.end):activity;
  const expanded=Boolean(state.selection.showAllIpConnections);
  const rows=expanded?visible:visible.slice(0,12);
  const peers=new Set(matches.map(f=>peerIp(f,ip)));
  const domains=[...new Set(matches.map(f=>f.domain).filter(Boolean))];
  const alerts=matches.filter(f=>f.kind==='flag').length;
  return drawerHeader('IP history',ip,'<p>Observed in '+escape(rangeText())+'</p>')+
    '<div class="drawer-body">'+(state.selection.parent?button('‹ Back to flow','backToFlow','','text-button return-flow'):'')+formatFields([['Flows / peers',matches.length+' / '+peers.size],['Suspicious flows',alerts],['First seen',matches.length?time(matches.at(-1).timestamp)+' ICT':'—'],['Last seen',matches.length?time(matches[0].timestamp)+' ICT':'—'],['Observed domains',domains.join(', ')||'Unavailable']])+
    '<div class="actions">'+button('Search this IP','searchIp',ip,'primary')+blockSourceButton(ip)+'</div><h3>'+uiSymbol('↔')+'Connections</h3><div class="tabs" aria-label="IP connection role">'+[['all','Both roles'],['src','As source'],['dst','As destination']].map(([key,label])=>
    '<button class="tab" aria-pressed="'+(state.role===key)+'" data-action="role" data-value="'+key+'">'+uiSymbol({all:'↔',src:'↗',dst:'↘'}[key])+label+'</button>').join('')+
    '</div>'+ipTimeline(activity)+ipPeerMap(ip,scoped)+
    '<div class="ip-connection-toolbar"><p class="case-note ip-connection-count">'+(visible.length>12&&!expanded?'Showing latest 12 of '+num(visible.length):'Showing '+num(rows.length)+' of '+num(visible.length))+' matching connections</p>'+
    (visible.length>12?'<button type="button" class="btn related-toggle" data-action="toggleIpConnections" aria-controls="ip-connection-list" aria-expanded="'+expanded+'">'+
      (expanded?'Show latest 12':'Show all '+num(visible.length))+'</button>':'')+'</div>'+
    '<div class="table-scroll"><table class="flow-table"><thead><tr><th>Time</th><th>Peer</th><th>App</th><th>Verdict</th></tr></thead><tbody id="ip-connection-list">'+
    (rows.map(f=>'<tr><td>'+button(time(f.timestamp),'flow',f.id,'text-button mono')+'</td><td class="mono">'+escape(peerIp(f,ip))+'</td><td>'+escape(f.app)+'</td><td>'+verdict(f)+'</td></tr>').join('')||'<tr><td colspan="4" class="empty">No connections match these filters.</td></tr>')+
    '</tbody></table></div></div>';
}
