export function fetchModelMetadata() {
  return fetch('/api/model');
}

export function fetchRecentTraffic() {
  return Promise.all([
    fetch('/api/traffic/live'),
    fetch('/api/traffic/flows?limit=250'),
    fetch('/api/traffic/flows?limit=250&alerts_only=true'),
  ]);
}

export function uploadCaptureFile(file) {
  return fetch('/api/capture-uploads?name='+encodeURIComponent(file.name), {
    method:'POST', headers:{'Content-Type':'application/octet-stream'}, body:file,
  });
}

export function fetchCaptureFlows(captureId, alertsOnly=false) {
  return fetch('/api/traffic/flows?limit=250&capture_id='+encodeURIComponent(captureId)+(alertsOnly?'&alerts_only=true':''));
}

export function fetchTrafficPage({beforeId, captureId, alertsOnly=false}={}) {
  const query=new URLSearchParams({limit:'250'});
  if (beforeId) query.set('before_id',beforeId);
  if (captureId) query.set('capture_id',captureId);
  if (alertsOnly) query.set('alerts_only','true');
  return fetch('/api/traffic/flows?'+query);
}

export function saveAlertStatus(id, status) {
  return fetch('/api/traffic/alerts/' + encodeURIComponent(id) + '?status=' + encodeURIComponent(status), {
    method: 'PATCH',
  });
}
