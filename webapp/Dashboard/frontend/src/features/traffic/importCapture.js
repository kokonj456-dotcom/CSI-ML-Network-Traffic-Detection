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
