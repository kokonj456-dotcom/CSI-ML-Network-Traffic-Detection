'use strict';

function ipLink(ip) { return ip?button(escape(ip), 'ip', ip, 'text-button mono'):'<span class="muted">—</span>'; }
function endpoint(ip, port) {
  return (ip ? ipLink(ip) : '<span class="muted">—</span>') + (port == null ? '' : '<span class="port mono">:' + port + '</span>');
}
function flowEndpoint(flow, direction, includePort = true) {
  const ip = flow[direction];
  const port = includePort ? flow[direction === 'src' ? 'sport' : 'dport'] : null;
  if (ip || !flow.dataset) return endpoint(ip, port);
  const demoIp = direction === 'src' ? '192.0.2.10' : '198.51.100.20';
  return '<span class="mono">' + demoIp + '</span><small class="flow-sub">Demo IP</small>';
}
