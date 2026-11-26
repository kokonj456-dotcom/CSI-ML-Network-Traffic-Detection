function managementError(message) {
  const status=byId('management-message');
  if (!status) return;
  status.textContent=message;
  if (message && location.protocol==='file:') {
    const link=document.createElement('a');
    link.href='http://127.0.0.1:8794/';
    link.textContent='Open local Flowwatch';
    status.append(' ',link);
  }
}
async function refreshManagement() {
  try {
    const data=await managementRequest();
    if (state.view!=='management') return;
    managementData=data;renderManagementBody();pollManagement();
  } catch(error) {
    if (state.view==='management') managementError(error.message);
  }
}
function renderManagementBody() {
  const host=byId('management-body');
  if (!host || !managementData) return;
  managementError(managementData.warning||'');
  if (managementTab==='feedback') host.innerHTML=feedbackPage();
  else if (managementTab==='train') {host.innerHTML=trainingPage();updateTrainingCounts();updateTrainingReference();}
  else if (managementTab==='registry') {host.innerHTML=registryPage();renderComparison();}
  else host.innerHTML=managementOverview();
}
