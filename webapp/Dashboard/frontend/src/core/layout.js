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
    renderMetrics();
    const chart=byId('timeline');
    const indexAt=event=>Math.min(chartGeometry.bins.length-1,Math.max(0,Math.round((event.offsetX-chartGeometry.left)/chartGeometry.step)));
    if (chart.dataset.interactive) return;
    chart.dataset.interactive='true';
    let selected=0;
    const showBin=index=>{
      selected=index;
      const {bins,width,left,step,span,interval}=drawChart(index);
      const bin=bins[index], tip=byId('chart-tip');
      const timeLabel=span<=day?
        time(bin.time).slice(0,5)+'–'+time(bin.time+interval).slice(0,5):
        localDay.format(bin.time)+' · '+time(bin.time).slice(0,5);
      const alertRate=bin.total?(100*bin.flags/bin.total).toFixed(1):'0.0';
      tip.textContent=timeLabel+'\n'+num(bin.total)+' flows · '+num(bin.flags)+' alerts ('+alertRate+'% flagged)';
      tip.hidden=false;
      const tipWidth=tip.getBoundingClientRect().width;
      tip.style.left=Math.max(0,Math.min(width-tipWidth,left+index*step+6))+'px';
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
    custom.hidden=state.filters.range!=='custom';
    const {from,to}=state.filters;
    byId('date-error').textContent=!custom.hidden && from && to && from>to ? 'End date must be on or after start date.' : '';
  }
  document.querySelectorAll('[data-action="period"]').forEach(button=>
    button.setAttribute('aria-pressed',String(button.dataset.value===state.filters.range)));
  renderMetrics();
  renderTable();
}
