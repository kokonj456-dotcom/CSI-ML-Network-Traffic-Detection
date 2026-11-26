'use strict';

function dashboardFlow(row) {
  const prediction = row.evidence.prediction || {status:'not_scored'};
  const id = 'DB-'+row.id;
  const status = {acknowledged:'Acknowledged',resolved:'Resolved'}[row.alert_status];
  if (status) review[id] = status;
  else delete review[id];
  const protocol = row.transport_protocol.toUpperCase();
  const observation = row.evidence.protocol_observation;
  const app = observation?.label ?? ({https_ssl:protocol==='UDP'?'QUIC?':'HTTPS/TLS',other:protocol}[row.service_group] ||
    (row.service_group || protocol).toUpperCase());
  return {
    id, alertId:row.alert_id, falsePositiveReported:Boolean(row.false_positive_reported), timestamp:Date.parse(row.started_at),
    src:row.src, dst:row.dst, sport:row.src_port, dport:row.dst_port,
    protocol, app, source:row.source_type==='central_test'?'CENTRAL Test':row.source_type==='live_capture'?'Live Capture':captureSource,
    dataset:row.evidence.dataset,
    interface:row.interface_name, run:row.capture_file_id ?? 0, file:row.capture_file,
    packets:row.packets_forward+row.packets_backward, bytes:row.bytes_forward+row.bytes_backward,
    duration:((Date.parse(row.ended_at)-Date.parse(row.started_at))/1000).toFixed(3),
    firewall:'Unavailable', frames:row.evidence.frames||[], raw:row.evidence.raw||{},
    serviceBasis:observation?.basis,
    prediction, score:prediction.binary_score, label:category(prediction),
    kind:prediction.status!=='scored'?'unscored':prediction.flagged?'flag':'normal',
  };
}
