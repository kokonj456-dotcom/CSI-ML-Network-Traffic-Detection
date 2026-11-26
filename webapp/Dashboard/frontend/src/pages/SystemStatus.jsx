const captureDate = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Bangkok', day: 'numeric', month: 'short', year: 'numeric',
  hour: '2-digit', minute: '2-digit', second: '2-digit',
});
const number = new Intl.NumberFormat('en');
const percent = value => value == null ? '—' : (100 * value).toFixed(1) + '%';

function Heading({ title, description }) {
  return <div className="page-heading"><div><h1>{title}</h1><p>{description}</p></div></div>;
}

function Fields({ items }) {
  return <dl className="fields">{items.map(([label, value]) => (
    <div key={label}><dt>{label}</dt><dd>{value ?? '—'}</dd></div>
  ))}</dl>;
}

function benchmark(test) {
  return test ? `F1 ${percent(test.binary.f1)} · FPR ${percent(test.binary.fpr)} · ${number.format(test.rows)} flows` : '—';
}

export function SystemStatus({ title, description, modelInfo, captureCount, latestCapture, liveStatus }) {
  return (
    <>
      <Heading title={title} description={description} />
      <div className="grid-two" id="status-content">
        <section className="panel panel-pad">
          <h2><span className="ui-symbol" aria-hidden="true">◉</span>Capture analysis</h2>
          <Fields items={[
            ['Live capture', liveStatus?.running ? 'Running' : liveStatus?.error || 'Not connected'],
            ['Capture interface', liveStatus?.interface],
            ['Monitored IPs', liveStatus?.addresses?.join(' / ') || liveStatus?.address],
            ['HTTPS capture', liveStatus?.capture_https == null ? null : liveStatus.capture_https ? 'On' : 'Paused'],
            ['Dropped packets', liveStatus?.dropped],
            ['Dropped flows', liveStatus?.dropped_flows],
            ['Flows in system', captureCount == null ? '—' : number.format(captureCount)],
            ['Latest flow', latestCapture == null ? 'No traffic received' : captureDate.format(latestCapture) + ' ICT'],
          ]} />
        </section>
        <section className="panel panel-pad">
          <h2><span className="ui-symbol" aria-hidden="true">◫</span>Inference &amp; storage</h2>
          <Fields items={[
            ['Model', modelInfo?.model_id],
            ['Alert threshold', modelInfo?.threshold],
            ['Feature schema', modelInfo?.schema_version],
            ['Preprocessor SHA-256', modelInfo?.preprocessor_sha256],
            ['CENTRAL test · offline', benchmark(modelInfo?.evaluation?.test_full)],
            ['Feature-group-disjoint test · offline', benchmark(modelInfo?.evaluation?.test_feature_group_disjoint)],
            ['Backend', modelInfo ? 'Local CENTRAL inference' : 'Unavailable'],
          ]} />
        </section>
      </div>
    </>
  );
}
