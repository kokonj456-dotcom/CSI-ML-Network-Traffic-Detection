export function fetchModelMetadata() {
  return fetch('/api/model');
}

export function fetchRecentTraffic() {
  return Promise.all([
    fetch('/api/traffic/live'),
    fetch('/api/traffic/flows?limit=250'),
  ]);
}

export function uploadCaptureFile(file) {
  return fetch('/api/capture-uploads?name='+encodeURIComponent(file.name), {
    method:'POST', headers:{'Content-Type':'application/octet-stream'}, body:file,
  });
}

export function fetchCaptureFlows(captureId) {
  return fetch('/api/traffic/flows?limit=250&capture_id='+encodeURIComponent(captureId));
}

export function saveAlertStatus(id, status) {
  return fetch('/api/traffic/alerts/' + encodeURIComponent(id) + '?status=' + encodeURIComponent(status), {
    method: 'PATCH',
  });
}
