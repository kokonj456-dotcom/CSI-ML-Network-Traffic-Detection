import { useEffect, useState } from 'react';

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

const defaultSettings = { max_flows_per_second: 128, packet_queue_capacity: 8192, flow_queue_capacity: 8192 };
const fmt = value => value == null ? '—' : number.format(Math.round(value));
const rateFmt = value => value == null ? '—' : `${value.toFixed(1)} / sec`;
const mb = value => value == null ? 'Collecting system sample' : `${value.toFixed(1)} MiB`;

function QueueMeter({ label, queue }) {
  const utilization = Math.min(100, Math.max(0, (queue?.utilization || 0) * 100));
  return (
    <div className="capacity-queue">
      <div className="capacity-queue-heading"><strong>{label}</strong><span>{fmt(queue?.waiting)} / {fmt(queue?.capacity)} waiting</span></div>
      <div className="capacity-track" role="meter" aria-label={`${label} usage`} aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(utilization)}>
        <i className={utilization >= 85 ? 'is-warning' : ''} style={{ width: `${utilization}%` }} />
      </div>
      <small>{utilization.toFixed(1)}% of queue capacity</small>
    </div>
  );
}

export function SystemStatus({ title, description, modelInfo, captureCount, latestCapture, liveStatus }) {
  const serverSettings = liveStatus?.settings;
  const settingsKey = JSON.stringify(serverSettings || defaultSettings);
  const [settings, setSettings] = useState(serverSettings || defaultSettings);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => setSettings(serverSettings || defaultSettings), [settingsKey]);

  async function saveSettings(event) {
    event.preventDefault();
    setSaving(true);
    setMessage('');
    try {
      const response = await fetch('/api/traffic/live/config', {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Could not save live capture settings.');
      setSettings(result.settings);
      setMessage('Settings saved and applied.');
    } catch (error) {
      setMessage(error.message || 'Could not save live capture settings.');
    } finally {
      setSaving(false);
    }
  }

  const queues = liveStatus?.queues || {};
  const rates = liveStatus?.rates || {};
  const resources = liveStatus?.resources || {};
  const systemRam = resources.system_ram_mb;
  const projectedRamPct = resources.estimated_ram_at_full_queues_mb != null && systemRam
    ? resources.estimated_ram_at_full_queues_mb / systemRam * 100 : null;
  const queueRisk = Boolean(liveStatus?.overload_risk);
  return (
    <>
      <Heading title={title} description={description} />
      <div className="grid-two" id="status-content">
        <section className="panel panel-pad">
          <h2>Capture analysis</h2>
          <Fields items={[
            ['Live capture', liveStatus?.running ? 'Running' : liveStatus?.error || 'Not connected'],
            ['Capture interface', liveStatus?.interface],
            ['Monitored IP', liveStatus?.address],
            ['HTTPS capture', liveStatus?.capture_https == null ? null : liveStatus.capture_https ? 'On' : 'Paused'],
            ['Dropped packets', liveStatus?.dropped],
            ['Dropped flows', liveStatus?.dropped_flows],
            ['Flows in system', captureCount == null ? '—' : number.format(captureCount)],
            ['Latest flow', latestCapture == null ? 'No traffic received' : captureDate.format(latestCapture) + ' ICT'],
          ]} />
        </section>
        <section className="panel panel-pad">
          <h2>Inference &amp; storage</h2>
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
      <section className="panel panel-pad capacity-panel" aria-labelledby="capacity-title">
        <div className="panel-head capacity-header">
          <div><h2 id="capacity-title">Live processing capacity</h2>
            <p>Monitor the capture and inference queues, then tune their limits for this machine.</p></div>
          <span className={`capacity-state ${queueRisk ? 'capacity-state-warning' : ''}`} role="status">
            <i />{queueRisk ? 'Overload risk' : 'Within limits'}
          </span>
        </div>
        <div className="capacity-queues">
          <QueueMeter label="Packet capture queue" queue={queues.packets} />
          <QueueMeter label="Completed flow queue" queue={queues.flows} />
        </div>
        <div className="capacity-metrics">
          <div><span>Flows arriving</span><strong>{rateFmt(rates.flows_in_per_second)}</strong></div>
          <div><span>Flows scored</span><strong>{rateFmt(rates.flows_processed_per_second)}</strong></div>
          <div><span>Flowwatch CPU now</span><strong>{resources.process_cpu_percent == null ? '—' : `${resources.process_cpu_percent.toFixed(1)}%`}</strong></div>
          <div><span>CPU if rate cap is reached</span><strong>{resources.estimated_model_cpu_percent == null ? 'Collecting sample' : `${resources.estimated_model_cpu_percent.toFixed(1)}%`}</strong></div>
          <div><span>Flowwatch RAM now</span><strong>{mb(resources.process_ram_mb)}</strong></div>
          <div><span>System RAM now</span><strong>{mb(resources.system_ram_used_mb)}</strong></div>
          <div><span>System RAM estimate with full queues</span><strong>{mb(resources.estimated_ram_at_full_queues_mb)}</strong>
            {projectedRamPct != null && <small>{projectedRamPct.toFixed(1)}% of installed RAM</small>}</div>
          <div><span>Packet drops this session</span><strong>{fmt(liveStatus?.dropped)}</strong></div>
          <div><span>Flow drops this session</span><strong>{fmt(liveStatus?.dropped_flows)}</strong></div>
          {liveStatus?.seconds_to_queue_full != null && <div><span>Estimated time to queue full</span><strong>{liveStatus.seconds_to_queue_full.toFixed(1)} sec</strong></div>}
        </div>
        <form className="capacity-settings" onSubmit={saveSettings}>
          <div className="panel-head"><div><h3>Processing limits</h3><p>Changes apply immediately and are saved locally for the next start.</p></div></div>
          <div className="capacity-inputs">
            <label>Maximum flows per second
              <input type="number" min="0" max="100000" step="1" required value={settings.max_flows_per_second}
                onChange={event => setSettings(current => ({ ...current, max_flows_per_second: Number(event.target.value) }))} />
              <small>0 means no configured cap; processing still depends on available CPU.</small>
            </label>
            <label>Packet queue capacity
              <input type="number" min="64" max="262144" step="64" required value={settings.packet_queue_capacity}
                onChange={event => setSettings(current => ({ ...current, packet_queue_capacity: Number(event.target.value) }))} />
              <small>Maximum packets waiting for flow extraction.</small>
            </label>
            <label>Completed flow queue capacity
              <input type="number" min="64" max="131072" step="64" required value={settings.flow_queue_capacity}
                onChange={event => setSettings(current => ({ ...current, flow_queue_capacity: Number(event.target.value) }))} />
              <small>Maximum flows waiting for model inference and storage.</small>
            </label>
          </div>
          <div className="capacity-actions"><p>When a queue is full, the newest item is dropped and counted above.</p>
            <button className="primary" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save limits'}</button></div>
          <p className="capacity-message" role="status">{message}</p>
          <p className="capacity-disclaimer">CPU forecast uses measured model inference time. System RAM at full queues is a rough estimate based on current RAM use plus an allowance per queued packet/flow; actual memory use varies.</p>
        </form>
      </section>
    </>
  );
}
