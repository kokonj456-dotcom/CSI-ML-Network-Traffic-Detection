'use strict';

function filtered() {
  const f = state.filters;
  const query = f.search.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const {start,end}=timeBounds();
  const flows=state.view==='alerts'?savedAlertFlows:capturedFlows;
  return [...flows].sort((a,b)=>b.timestamp-a.timestamp).filter(flow => {
    if (f.captureFileId && flow.run!==f.captureFileId) return false;
    if (state.view==='alerts' && flow.kind!=='flag') return false;
    if (state.view==='alerts' && !f.status && flow.falsePositiveReported && review[flow.id]==='Resolved') return false;
    if (flow.timestamp < start || flow.timestamp > end) return false;
    if (f.protocol && f.protocol !== flow.app && f.protocol !== flow.protocol) return false;
    if (f.decision && f.decision !== flow.kind) return false;
    if (f.origin && f.origin !== flow.source) return false;
    if (f.alertGroup && alertKey(flow)!==f.alertGroup) return false;
    if (f.label && flow.label !== f.label) return false;
    if (f.model && modelVersion(flow)!==f.model) return false;
    if (f.inference && flow.prediction.status!==f.inference) return false;
    if (f.destination && (flow.dst !== f.destination[0] || flow.dport !== f.destination[1])) return false;
    if (f.status && f.status !== (review[flow.id] || 'New')) return false;
    const fields = {ip:[flow.src,flow.dst], src:[flow.src], dst:[flow.dst], port:[flow.sport,flow.dport], domain:[flow.domain], run:[runName(flow.run)]};
    const searchable = [flow.id,flow.dataset?.record_id,flow.src,flow.dst,flow.sport,flow.dport,flow.protocol,flow.app,flow.domain,flow.label,runName(flow.run)].join(' ').toLowerCase();
    return query.every(term => {
      const [field,...parts] = term.split(':');
      if (parts.length && Object.hasOwn(fields,field)) {
        const value = parts.join(':');
        return fields[field].some(item => field==='domain' ? String(item).toLowerCase().includes(value) : String(item).toLowerCase()===value);
      }
      return searchable.includes(term);
    });
  });
}
