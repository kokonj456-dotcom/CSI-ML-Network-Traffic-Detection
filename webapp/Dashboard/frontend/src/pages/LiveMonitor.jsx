function Filter({ name, label, options, value }) {
  return (
    <select data-filter={name} aria-label={label} defaultValue={value}>
      {options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}
    </select>
  );
}

export function LiveMonitor({ description, filters, presets, sourceOptions, ranking }) {
  return (
    <>
      <div className="page-heading">
        <div><h1>Live Monitor</h1><p>{description}</p></div>
      </div>
      <div className="time-toolbar">
        <strong>Time range</strong>
        <div className="periods">
          {[['10080', 'Week'], ['43200', 'Month'], ['525600', 'Year']].map(([value, label]) => (
            <button key={value} type="button" className="btn period" data-action="period" data-value={value}
              aria-pressed={filters.range === value}>{label}</button>
          ))}
        </div>
        <Filter name="range" label="Time range" options={presets} value={filters.range} />
        <Filter name="origin" label="Source" options={sourceOptions} value={filters.origin} />
        <div className="date-fields" id="custom-dates" hidden={filters.range !== 'custom'}>
          {[['from', 'From'], ['to', 'Through']].map(([key, label]) => (
            <label key={key}>{label} <input type="date" data-filter={key} defaultValue={filters[key]} /></label>
          ))}
          <span id="date-error" role="alert" />
        </div>
        <span id="run-status" />
      </div>
      <div className="metrics" id="metrics" />
      <section className="panel panel-pad overview-trend">
        <div className="panel-head">
          <div><h2>Traffic and alert trends</h2><p id="trend-range" /></div>
          <button className="btn" data-action="summary" data-value="flows">Explore flows ›</button>
        </div>
        <div className="chart-box">
          <canvas tabIndex={0} id="timeline" aria-label="Traffic timeline. Use arrow keys to select a time bin and Enter to explore flows." />
          <span className="chart-tooltip" id="chart-tip" hidden />
        </div>
        <p className="chart-hint">Select a time bin to investigate its flows.</p>
      </section>
      <div className="overview-ranks">
        <section className="panel panel-pad">
          <div className="panel-head">
            <div><h2 id="ranking-title" /><p>Ranked by flows · flagged counts in pink</p></div>
            <select id="ranking" aria-label="Rank by" defaultValue={ranking}>
              <option value="destinations">Destinations</option><option value="protocols">Protocols</option>
            </select>
          </div>
          <div className="ranks" id="rank-rows" />
        </section>
        <section className="panel panel-pad alert-ranks">
          <div className="panel-head">
            <div><h2>Alert Breakdown</h2><p>By predicted category</p></div>
            <button className="text-button" data-action="summary" data-value="flagged">View alerts ›</button>
          </div>
          <div className="ranks" id="alert-rows" /><div className="latest-alert" id="latest-alert" />
        </section>
      </div>
      <p className="case-note" id="inference-health" />
      <section className="panel health" id="health" aria-label="Current system health" />
    </>
  );
}
