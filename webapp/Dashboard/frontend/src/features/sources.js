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
      control.innerHTML=uiSymbol('↑')+'Import PCAP';
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

async function refreshTraffic(schedule=true) {
  try {
    const captureId=state.filters.captureFileId;
    const [statusResponse, flowsResponse, alertsResponse] = await fetchRecentTraffic();
    if (statusResponse.ok) liveStatus = await statusResponse.json();
    if (flowsResponse.ok) {
      let payload=await flowsResponse.json();
      if (!flowsPageInitialized) {
        payload=await fetchAllTrafficPages(payload);
        flowsLoadedMore=true;
      }
      const {flows}=payload;
      totalFlowCount=payload.total_flows ?? totalFlowCount;
      if (!flowsPageInitialized || !flowsLoadedMore) flowsNextBeforeId=payload.next_before_id;
      flowsPageInitialized=true;
      if (captureId) {
        const captureAlerts=state.view==='alerts';
        const captureResponse=await fetchCaptureFlows(captureId,captureAlerts);
        if (captureResponse.ok && captureId===state.filters.captureFileId) {
          let capturePayload=await captureResponse.json();
          if (captureAlerts && !captureAlertFlowLoadedMore[captureId]) {
            capturePayload=await fetchAllTrafficPages(capturePayload,{captureId,alertsOnly:true});
            captureAlertFlowLoadedMore[captureId]=true;
          } else if (!captureAlerts && !captureFlowLoadedMore[captureId]) {
            capturePayload=await fetchAllTrafficPages(capturePayload,{captureId});
            captureFlowLoadedMore[captureId]=true;
          }
          if (captureAlerts) {
            captureAlertFlowCounts[captureId]=capturePayload.total_flows ?? captureAlertFlowCounts[captureId] ?? null;
            if (!captureAlertFlowLoadedMore[captureId]) captureAlertFlowCursors[captureId]=capturePayload.next_before_id;
            savedAlertFlows=mergeDashboardFlows(savedAlertFlows,capturePayload.flows.map(dashboardFlow));
          } else {
            captureFlowCounts[captureId]=capturePayload.total_flows ?? captureFlowCounts[captureId] ?? null;
            if (!captureFlowLoadedMore[captureId]) captureFlowCursors[captureId]=capturePayload.next_before_id;
            const known=new Set(flows.map(row=>row.id));
            flows.push(...capturePayload.flows.filter(row=>!known.has(row.id)));
          }
        }
      }
      capturedFlows = mergeDashboardFlows(capturedFlows,flows.map(dashboardFlow));
    }
    if (alertsResponse.ok) {
      let payload=await alertsResponse.json();
      if (!alertsPageInitialized) {
        payload=await fetchAllTrafficPages(payload,{alertsOnly:true});
        alertsLoadedMore=true;
      }
      totalAlertFlowCount=payload.total_flows ?? totalAlertFlowCount;
      if (!alertsPageInitialized || !alertsLoadedMore) alertsNextBeforeId=payload.next_before_id;
      alertsPageInitialized=true;
      savedAlertFlows=mergeDashboardFlows(savedAlertFlows,payload.flows.map(dashboardFlow));
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

async function fetchAllTrafficPages(firstPage,{captureId,alertsOnly=false}={}) {
  const flows=[...firstPage.flows];
  let beforeId=firstPage.next_before_id;
  let total=firstPage.total_flows;
  while (beforeId) {
    const response=await fetchTrafficPage({beforeId,captureId,alertsOnly});
    const page=await response.json();
    if (!response.ok) throw Error(page.detail||'Could not load all traffic records.');
    if (!page.flows?.length) break;
    flows.push(...page.flows);
    beforeId=page.next_before_id;
    total=page.total_flows ?? total;
  }
  return {...firstPage,flows,next_before_id:null,total_flows:total};
}

function mergeDashboardFlows(existing,incoming) {
  const rows=new Map(existing.map(flow=>[flow.id,flow]));
  for (const flow of incoming) rows.set(flow.id,flow);
  return [...rows.values()].sort((a,b)=>b.timestamp-a.timestamp);
}

async function loadMoreTrafficFlows() {
  if (loadingMoreFlows) return;
  const captureId=state.filters.captureFileId;
  const isAlerts=state.view==='alerts';
  const beforeId=captureId
    ? isAlerts?captureAlertFlowCursors[captureId]:captureFlowCursors[captureId]
    : isAlerts?alertsNextBeforeId:flowsNextBeforeId;
  if (!beforeId) return;
  loadingMoreFlows=true;
  renderTable();
  try {
    const response=await fetchTrafficPage({beforeId,captureId,alertsOnly:isAlerts});
    const payload=await response.json();
    if (!response.ok) throw Error(payload.detail||'Could not load the next flow batch.');
    const received=payload.flows.map(dashboardFlow);
    if (captureId && isAlerts) {
      captureAlertFlowCursors[captureId]=payload.next_before_id;
      captureAlertFlowCounts[captureId]=payload.total_flows ?? captureAlertFlowCounts[captureId] ?? null;
      captureAlertFlowLoadedMore[captureId]=true;
      savedAlertFlows=mergeDashboardFlows(savedAlertFlows,received);
    } else if (captureId) {
      captureFlowCursors[captureId]=payload.next_before_id;
      captureFlowCounts[captureId]=payload.total_flows ?? captureFlowCounts[captureId] ?? null;
      captureFlowLoadedMore[captureId]=true;
      capturedFlows=mergeDashboardFlows(capturedFlows,received);
    } else if (isAlerts) {
      alertsNextBeforeId=payload.next_before_id;
      totalAlertFlowCount=payload.total_flows ?? totalAlertFlowCount;
      alertsLoadedMore=true;
      savedAlertFlows=mergeDashboardFlows(savedAlertFlows,received);
    } else {
      flowsNextBeforeId=payload.next_before_id;
      totalFlowCount=payload.total_flows ?? totalFlowCount;
      flowsLoadedMore=true;
      capturedFlows=mergeDashboardFlows(capturedFlows,received);
    }
    nav();
    renderTable();
    toast('Loaded '+num(received.length)+' more '+(isAlerts?'alerts':'flows'));
  } catch (error) {
    toast(error.message);
  } finally {
    loadingMoreFlows=false;
    renderTable();
  }
}
