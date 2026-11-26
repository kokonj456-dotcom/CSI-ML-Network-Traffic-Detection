export async function managementRequest(path='', payload) {
  if (location.protocol==='file:') throw Error('Model Management requires the local Flowwatch backend.');
  const options=payload?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}:{};
  let response;
  try {
    response=await fetch('/api/management'+path,options);
  } catch {
    throw Error('Could not reach the Flowwatch backend. Check that it is running, then select Refresh.');
  }
  if (!(response.headers.get('content-type')||'').includes('application/json')) throw Error('Start the local Flowwatch backend to use Model Management.');
  const data=await response.json();
  if (!response.ok) throw Error(typeof data.detail==='string'?data.detail:'Invalid request.');
  return data;
}
