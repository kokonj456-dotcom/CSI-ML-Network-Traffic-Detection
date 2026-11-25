import { SystemStatus } from '../pages/SystemStatus.jsx';
import { LiveMonitor } from '../pages/LiveMonitor.jsx';

function Brand({ login = false }) {
  return (
    <div className={login ? 'brand login-brand' : 'brand'}>
      <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
      {login ? 'Flowwatch' : <div>Flowwatch<small>Network Defense</small></div>}
    </div>
  );
}

function Sidebar({ views, view, alerts, theme }) {
  return (
    <aside className="rail">
      <Brand />
      <nav aria-label="Workspace" id="navigation">
        {Object.entries(views).map(([key, [icon, title]]) => (
          <button key={key} type="button" className={key === view ? 'nav-item active' : 'nav-item'}
            aria-current={key === view ? 'page' : undefined} data-action="navigate" data-value={key}>
            <span className="nav-icon" aria-hidden="true">{icon}</span>{title}
            {key === 'alerts' && alerts > 0 && <span className="nav-count">{alerts}</span>}
          </button>
        ))}
      </nav>
      <div className="rail-bottom">
        <div className="theme-switch" role="group" aria-label="Color theme">
          {Object.entries({light: ['☀', 'Light'], dark: ['☾', 'Dark']}).map(([key, [icon, label]]) => (
            <button key={key} type="button" data-action="theme" data-value={key} aria-pressed={key === theme}>
              <span aria-hidden="true">{icon}</span> {label}
            </button>
          ))}
        </div>
        <button type="button" className="account" data-action="lock" aria-label="Lock workspace">
          <span className="avatar">LA</span>
          <span><strong>Local analyst</strong><small>Lock workspace</small></span>
          <span aria-hidden="true">↗</span>
        </button>
      </div>
    </aside>
  );
}

function Topbar({ title, modelAvailable }) {
  return (
    <header className="topbar">
      <div><span>Workspace</span><span className="slash">/</span><strong id="breadcrumb">{title}</strong></div>
      <div className="top-right">
        <span className="demo">{modelAvailable ? 'Offline model available' : 'Backend unavailable'}</span>
        <button type="button" className="icon-button" data-action="navigate" data-value="alerts" aria-label="Open alerts">♧<i /></button>
      </div>
    </header>
  );
}

function ModelManagement({ title, description, tab, tabs }) {
  return (
    <>
      <div className="page-heading">
        <div><h1>{title}</h1><p>{description}</p></div>
        <div className="actions"><button type="button" className="btn" data-management="refresh">Refresh</button></div>
      </div>
      <div className="tabs blocklist-tabs" aria-label="Model management sections">
        {Object.entries(tabs).map(([key, label]) => (
          <button key={key} type="button" className="tab" aria-pressed={key === tab} data-management="tab" data-value={key}>{label}</button>
        ))}
      </div>
      <p className="form-error" role="status" id="management-message" />
      <div id="management-body" />
    </>
  );
}

export function Workspace({ views, view, alerts, theme, locked, modelAvailable, modelInfo, captureCount, latestCapture, liveStatus, monitor, management }) {
  const pageProps = { title: views[view][1], description: views[view][2], modelInfo };
  return (
    <>
      <div className="shell" id="workspace" hidden={locked}>
        <Sidebar views={views} view={view} alerts={alerts} theme={theme} />
        <main>
          <Topbar title={views[view][1]} modelAvailable={modelAvailable} />
          <div key={view} className="content" id="page">
            {view === 'live' && <LiveMonitor {...monitor} description={pageProps.description} />}
            {view === 'management' && <ModelManagement {...pageProps} {...management} />}
            {view === 'status' && <SystemStatus {...pageProps} captureCount={captureCount} latestCapture={latestCapture} liveStatus={liveStatus} />}
          </div>
        </main>
      </div>
      <dialog id="inspector" aria-label="Investigation details" />
      <section id="login" className="login" hidden={!locked}>
        <div className="login-card">
          <Brand login />
          <h1>Analyst workspace</h1>
          <p>Open the local workspace to investigate packet capture results.</p>
          <button type="button" className="primary" data-action="unlock">Enter workspace <span aria-hidden="true">→</span></button>
        </div>
      </section>
      <div id="toast" className="toast" role="status" hidden />
    </>
  );
}

