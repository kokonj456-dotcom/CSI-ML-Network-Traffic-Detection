'use strict';

let captureUploadPending=false;

async function importCaptureFile(file) {
  if (captureUploadPending) return;
  if (!/\.pcap(?:ng)?$/i.test(file.name)) return toast('Choose a PCAP or PCAPNG file.');
  if (file.size>32*1024*1024) return toast('Capture exceeds 32 MiB.');
  captureUploadPending=true;
  const control=byId('capture-upload-button');
  control.disabled=true;
  control.setAttribute('aria-busy','true');
  control.textContent='Importing…';
  try {
    const response=await uploadCaptureFile(file);
    const result=await response.json();
    if (!response.ok) throw Error(typeof result.detail==='string'?result.detail:'Capture import failed.');
    captureUploadPending=false;
    go('explorer',{captureFileId:result.capture_id,captureFileName:result.file,origin:captureSource});
    await refreshTraffic(false);
    toast(num(result.flow_count)+' flows analyzed · '+num(result.alert_count)+' alerts'+
      (result.flow_count>250?' · showing up to 250 flows':''));
  } catch (error) {
    toast(error.message);
  } finally {
    captureUploadPending=false;
    if (control.isConnected) {
      control.disabled=false;
      control.removeAttribute('aria-busy');
      control.textContent='Import PCAP';
    }
  }
}

async function loadModelInfo() {
  if (location.protocol!=='http:') return;
  try {
    const response=await fetchModelMetadata();
    if (!response.ok) return;
    modelInfo=await response.json();
    nav();
    if (state.view==='live') renderMetrics();
  } catch {}
}

async function refreshTraffic(schedule=true) {
  try {
    const captureId=state.filters.captureFileId;
    const [statusResponse, flowsResponse] = await fetchRecentTraffic();
    if (statusResponse.ok) liveStatus = await statusResponse.json();
    if (flowsResponse.ok) {
      const {flows} = await flowsResponse.json();
      if (captureId) {
        const captureResponse=await fetchCaptureFlows(captureId);
        if (captureResponse.ok && captureId===state.filters.captureFileId) {
          const {flows:imported}=await captureResponse.json();
          const known=new Set(flows.map(row=>row.id));
          flows.push(...imported.filter(row=>!known.has(row.id)));
        }
      }
      capturedFlows = flows.map(row => {
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
          id, alertId:row.alert_id, timestamp:Date.parse(row.started_at),
          src:row.src, dst:row.dst, sport:row.src_port, dport:row.dst_port,
          protocol, app, source:row.source_type==='live_capture'?'Live Capture':captureSource,
          interface:row.interface_name, run:row.capture_file_id ?? 0, file:row.capture_file,
          packets:row.packets_forward+row.packets_backward, bytes:row.bytes_forward+row.bytes_backward,
          duration:((Date.parse(row.ended_at)-Date.parse(row.started_at))/1000).toFixed(3),
          firewall:'Unavailable', frames:row.evidence.frames||[], raw:row.evidence.raw||{},
          serviceBasis:observation?.basis,
          prediction, score:prediction.binary_score, label:category(prediction),
          kind:prediction.status!=='scored'?'unscored':prediction.flagged?'flag':'normal',
        };
      });
    }
    nav();
    if (!byId('inspector').open) {
      if (state.view==='live' && !document.activeElement.closest('#metrics, #rank-rows, #alert-rows, #latest-alert, #timeline')) renderMetrics();
      if (['explorer','alerts'].includes(state.view) && !byId('table-rows')?.contains(document.activeElement)) renderTable();
    }
  } catch {
    liveStatus=null;
  } finally {
    if (schedule) setTimeout(refreshTraffic, 3000);
  }
}
