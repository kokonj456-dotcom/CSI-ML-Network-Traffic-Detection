'use strict';

function openCount() {
  return savedAlertFlows.filter(flow=>!review[flow.id]).length;
}
function nav() {
  renderWorkspace({
    views, view:state.view, alerts:openCount(), theme:document.documentElement.dataset.theme,
    locked:state.locked, modelAvailable:Boolean(modelInfo),
    modelInfo, captureCount:totalFlowCount, latestCapture:allFlows()[0]?.timestamp,
    liveStatus,
    monitor:{filters:state.filters,presets,sourceOptions,ranking:state.ranking},
    management:{tab:managementTab,tabs:managementTabs},
    flows: allFlows(),
  });
}
function heading(actions='') {
  const [,title,description] = views[state.view];
  return '<div class="page-heading"><div><h1>' + title + '</h1><p>' + description + '</p></div><div class="actions">' + actions + '</div></div>';
}
function select(field,label,options) {
  return '<select data-filter="' + field + '" aria-label="' + label + '">' + options.map(([value, text]) =>
    '<option value="' + escape(value) + '"' + (String(state.filters[field])===value?' selected':'') + '>' + escape(text) + '</option>').join('') + '</select>';
}

function formatFields(values) {
  return '<dl class="fields">' + values.map(([name,value])=>'<div><dt>'+name+'</dt><dd>'+escape(value)+'</dd></div>').join('') + '</dl>';
}

function render() {
  nav();
  const page=byId('page');
  if (state.view==='live') {
    const chart=byId('timeline');
    if (!chart || chart.dataset?.interactive) return;
    renderMetrics();
    const indexAt=event=>Math.min(chartGeometry.bins.length-1,Math.max(0,Math.round((event.offsetX-chartGeometry.left)/chartGeometry.step)));
    chart.dataset.interactive='true';
    let selected=0;
    const showBin=index=>{
      selected=index;
      const {bins,width,left,step,span,interval}=drawChart(index);
      const bin=bins[index], tip=byId('chart-tip');
      if (!bin || !tip) return;
      const timeLabel=span<=day?
        time(bin.time).slice(0,5)+'–'+time(bin.time+interval).slice(0,5):
        localDay.format(bin.time)+' · '+time(bin.time).slice(0,5);
      const alertRate=bin.total?(100*bin.flags/bin.total).toFixed(1):'0.0';

      tip.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:8px;">
          <span style="font-weight:700;color:#ffffff;font-size:12px;font-family:Consolas,monospace;">${timeLabel}</span>
          <span style="font-size:10px;font-weight:700;color:#818cf8;letter-spacing:0.5px;">CLICK TO FILTER</span>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
          <div style="background:rgba(99,102,241,0.12);border:1px solid rgba(99,102,241,0.3);border-radius:6px;padding:5px 8px;">
            <div style="color:#a5b4fc;font-size:10px;font-weight:600;display:flex;align-items:center;gap:3px;">
              <span>⇄</span> Flows
            </div>
            <div style="color:#ffffff;font-size:13px;font-weight:700;margin-top:2px;">
              ${num(bin.total)}
            </div>
          </div>
          <div style="background:rgba(239,68,68,0.12);border:1px solid rgba(239,68,68,0.3);border-radius:6px;padding:5px 8px;">
            <div style="color:#f87171;font-size:10px;font-weight:600;display:flex;align-items:center;gap:3px;">
              <span>🚩</span> Alerts
            </div>
            <div style="color:#ffffff;font-size:13px;font-weight:700;margin-top:2px;">
              ${num(bin.flags)} <span style="color:#94a3b8;font-size:10px;font-weight:normal;">(${alertRate}%)</span>
            </div>
          </div>
        </div>
      `;
      tip.hidden=false;
      const tipWidth=tip.getBoundingClientRect().width;
      tip.style.left=Math.max(10,Math.min(width-tipWidth-10,left+index*step+6))+'px';
    };
    const openBin=index=>{
      const {bins,interval}=chartGeometry;
      const bounds=timeBounds();
      const start=Math.max(bounds.start,bins[index].time);
      const end=Math.min(bounds.end,bins[index].time+interval-1);
      if (start<=end) go('explorer',overviewScope({bucket:{start,end}}));
    };
    chart.addEventListener('pointermove',event=>showBin(indexAt(event)));
    chart.addEventListener('pointerleave',()=>{byId('chart-tip').hidden=true;drawChart();});
    chart.addEventListener('click',event=>openBin(indexAt(event)));
    chart.addEventListener('keydown',event=>{
      if (event.key==='Enter' || event.key===' ') {event.preventDefault();openBin(selected);}
      if (event.key==='ArrowLeft' || event.key==='ArrowRight') {
        event.preventDefault();
        showBin(Math.min(chartGeometry.bins.length-1,Math.max(0,selected+(event.key==='ArrowRight'?1:-1))));
      }
    });
  } else if (state.view==='blocklist') {
    page.innerHTML=blockPage();
    renderBlocks();
  } else if (state.view==='management') {
    refreshManagement();
  } else if (state.view==='explorer' || state.view==='alerts') {
    page.innerHTML=heading()+tableSection(state.view==='alerts'?'Alert queue':'Recorded flows',state.view==='alerts'?'Triage recurring detections or inspect individual alerts.':'Search flows extracted from packet captures.');
    renderTable();
  }
}

function toast(message) {
  const element=byId('toast');
  element.textContent=message;
  element.hidden=false;
  clearTimeout(state.toastTimer);
  state.toastTimer=setTimeout(()=>{element.hidden=true;},2400);
}
function go(view, filters={}) {
  if (!Object.hasOwn(views,view)) return;
  state.view=view;
  if (view==='alerts') state.alertMode='grouped';
  state.page=0;
  state.filters={search:'',protocol:'',range:view==='live'?'15':'',from:'',to:'',decision:'',origin:'',status:'',...filters};
  state.selection=null;
  showInspector();
  render();
  window.scrollTo(0,0);
}
function overviewScope(extra={}) {
  const {range,from,to,origin}=state.filters;
  return {range,from,to,origin,...extra};
}
function updateFilters() {
  state.page=0;
  const custom=byId('custom-dates');
  if (custom) {
    const wasHidden = custom.hidden;
    custom.hidden=state.filters.range!=='custom';
    if (wasHidden && !custom.hidden) {
      setTimeout(() => {
        const firstInput = custom.querySelector('input[type="date"]');
        if (firstInput) {
          try { firstInput.showPicker(); } catch {}
        }
      }, 50);
    }
    const {from,to}=state.filters;
    byId('date-error').textContent=!custom.hidden && from && to && from>to ? 'End date must be on or after start date.' : '';
  }
  document.querySelectorAll('[data-action="period"]').forEach(button=>
    button.setAttribute('aria-pressed',String(button.dataset.value===state.filters.range)));
  renderMetrics();
  renderTable();
}
