'use strict';

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
