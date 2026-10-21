import React, { useEffect, useMemo, useState } from "react";
import { EvidenceChart, useDataApp } from "../../data-app-public.jsx";
import "./dashboard.css";
import "./jobs.css";

const fitChart = { type: "bar", x: "fitBand", y: "jobs", sortOrder: "descending", showXAxisLabel: false };
const fitOrder = { "Strong title match": 0, "Possible title match": 1, "Limited title evidence": 2 };
const MAX_SELECTED_JOBS = 200;

export function DashboardContent() {
  const app = useDataApp();
  const initialRows = app.snapshot?.queries?.job_postings?.rows ?? [];
  const initialWindow = app.snapshot?.lastSearch?.window ?? (["24h", "3d", "7d"].find(window => initialRows.some(row => (row.searchWindows ?? [row.searchWindow ?? "any"]).includes(window))) ?? "any");
  const [rows, setRows] = useState(initialRows);
  const [lastSearch, setLastSearch] = useState(app.snapshot?.lastSearch ?? null);
  const [selected, setSelected] = useState([]);
  const [fitFilter, setFitFilter] = useState("All fit bands");
  const [statusFilter, setStatusFilter] = useState("All statuses");
  const [windowFilter, setWindowFilter] = useState(initialWindow);
  const [status, setStatus] = useState({ running: false, message: "" });
  const [error, setError] = useState("");

  async function refresh() {
    try {
      const [dataResponse, statusResponse] = await Promise.all([fetch("/api/data"), fetch("/api/status")]);
      if (dataResponse.ok) {
        const data = await dataResponse.json();
        // An older dashboard server may still return the all-time archive without
        // latest-search metadata. Never present that archive as current results.
        const nextRows = data.lastSearch ? (data.rows ?? []) : [];
        setRows(nextRows);
        setLastSearch(data.lastSearch ?? null);
        const newIds = new Set(nextRows.filter(row => row.applicationStatus === "New").map(row => row.id));
        setSelected(current => current.filter(id => newIds.has(id)).slice(0, MAX_SELECTED_JOBS));
      }
      if (statusResponse.ok) setStatus(await statusResponse.json());
      setError("");
    } catch { setError("Dashboard server is not reachable. Start it with START_JOB_BOT.bat."); }
  }
  useEffect(() => { refresh(); const timer = setInterval(refresh, 5000); return () => clearInterval(timer); }, []);

  const visible = useMemo(() => {
    const windowRows = rows.filter(row => windowFilter === "any" || (row.searchWindows ?? [row.searchWindow ?? "any"]).includes(windowFilter));
    return windowRows.filter(row => {
      return (fitFilter === "All fit bands" || row.fitBand === fitFilter) &&
        (statusFilter === "All statuses" || row.applicationStatus === statusFilter);
    });
  }, [rows, fitFilter, statusFilter, windowFilter]);
  const windowRows = useMemo(() => rows.filter(row => windowFilter === "any" || (row.searchWindows ?? [row.searchWindow ?? "any"]).includes(windowFilter)), [rows, windowFilter]);
  const summary = useMemo(() => ({
    total: windowRows.length,
    strong: windowRows.filter(r => r.fitBand === "Strong title match").length,
    ready: windowRows.filter(r => r.applicationStatus === "New" && r.fitBand === "Strong title match").length,
    applied: windowRows.filter(r => r.applicationStatus === "Applied").length,
  }), [windowRows]);
  const chartRows = ["Strong title match", "Possible title match", "Limited title evidence"].map(fitBand => ({ fitBand, jobs: windowRows.filter(r => r.fitBand === fitBand).length }));
  const selectableVisible = visible.filter(row => row.applicationStatus === "New");
  const visibleIds = selectableVisible.map(row => row.id);
  const visibleSelectionTarget = Math.min(visibleIds.length, MAX_SELECTED_JOBS);
  const allVisibleSelected = visibleSelectionTarget > 0 && visibleIds.filter(id => selected.includes(id)).length >= visibleSelectionTarget;
  function toggleAllVisible() {
    setError("");
    if (allVisibleSelected) {
      setSelected(selected.filter(id => !visibleIds.includes(id)));
      return;
    }
    const additions = visibleIds.filter(id => !selected.includes(id));
    const remaining = Math.max(0, MAX_SELECTED_JOBS - selected.length);
    if (additions.length > remaining) {
      setError(`Selected ${remaining} of ${additions.length} remaining visible jobs to keep the total at ${MAX_SELECTED_JOBS}. Deselect jobs to choose different ones.`);
    }
    setSelected([...selected, ...additions.slice(0, remaining)]);
  }
  const toggle = (id) => {
    setError("");
    if (selected.includes(id)) {
      setSelected(selected.filter(x => x !== id));
      return;
    }
    if (selected.length >= MAX_SELECTED_JOBS) {
      setError(`You can select up to ${MAX_SELECTED_JOBS} jobs at a time. Deselect a job before adding another.`);
      return;
    }
    setSelected([...selected, id]);
  };

  async function collectJobs() {
    setError("");
    try {
      const response = await fetch("/api/collect", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ window: windowFilter }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not start job search");
      setStatus(result);
    } catch (e) { setError(e.message); }
  }

  async function startApplications() {
    if (!selected.length) return;
    try {
      const response = await fetch("/api/prepare-application", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids: selected }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not start browser application preparation");
      setStatus(current => ({ ...current, applicationSession: result }));
      setError("");
    } catch (e) { setError(e.message); }
  }

  async function applicationAction(path, confirmation) {
    if (confirmation && !window.confirm(confirmation)) return;
    try {
      const response = await fetch(path, { method: "POST" });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "The browser application action failed");
      setStatus(current => ({ ...current, applicationSession: result }));
      setError("");
      await refresh();
    } catch (e) { setError(e.message); }
  }

  return <article className="jobs-page">
    <div className="jobs-heading"><div><h1>Gogoi — job fit and applications</h1><p>Review matching jobs, then prepare each application in a visible browser.</p></div><button className="refresh" disabled={status.running || status.applicationSession?.active} onClick={collectJobs}>{status.running ? "Searching…" : "Check for new jobs"}</button></div>
    {error && <div className="jobs-alert" role="alert">{error}</div>}
    {status.running && <div className="jobs-running" role="status">{status.message} Keep this dashboard open while the search completes.</div>}
    {!status.running && status.message && <div className="jobs-status" role="status">{status.message} {status.exitCode != null && status.exitCode !== 0 && ` (exit ${status.exitCode})`}</div>}
    {status.applicationSession && !status.applicationSession.active && !["idle", "stopped"].includes(status.applicationSession.phase) && <div className="jobs-status" role="status">{status.applicationSession.message}</div>}
    <div className="jobs-metrics">
      <div><span>Unique jobs</span><strong>{summary.total}</strong></div><div><span>Strong title matches</span><strong>{summary.strong}</strong></div><div><span>Strong matches to review</span><strong>{summary.ready}</strong></div><div><span>Recorded applications</span><strong>{summary.applied}</strong></div>
    </div>
    <div className="jobs-chart">
      <EvidenceChart id="job-fit-bands" title="Jobs by résumé-match evidence" queryId="job_postings" spec={fitChart} rows={chartRows} sourceRows={rows} height={230} description="First-pass matching uses listing titles and indexed snippets; verify against the complete posting." />
    </div>
    <p className="jobs-caveat">Check for new jobs runs a fresh search and replaces the table with that search’s results. Listings come from public search indexes, not live job-board feeds, so a result can still be stale or closed; verify the original posting. Gogoi fills recognized résumé fields and stops before Submit.</p>
    <div className="jobs-toolbar">
      <label>Search index window <select value={windowFilter} onChange={e => setWindowFilter(e.target.value)}><option value="any">Any indexed date</option><option value="24h">Indexed in last 24 hours</option><option value="3d">Indexed in past 3 days</option><option value="7d">Indexed in past 7 days</option></select></label>
      <label>Title fit <select value={fitFilter} onChange={e => setFitFilter(e.target.value)}><option>All fit bands</option><option>Strong title match</option><option>Possible title match</option><option>Limited title evidence</option></select></label>
      <label>Status <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}><option>All statuses</option><option>New</option><option>Ready for review</option><option>Applied</option><option>Failed</option><option>Skipped</option></select></label>
      <button className="apply-button" disabled={!selected.length || status.running || status.applicationSession?.active} onClick={startApplications}>Start selected jobs ({selected.length})</button>
    </div>
    <p className="jobs-search-meta">{lastSearch?.searchedAt ? `Latest search: ${new Date(lastSearch.searchedAt).toLocaleString()} · ${lastSearch.count} listings returned · Indexed window: ${lastSearch.window === "24h" ? "24 hours" : lastSearch.window === "3d" ? "3 days" : lastSearch.window === "7d" ? "7 days" : "any date"}${lastSearch.engine ? ` · ${lastSearch.engine}` : ""}${lastSearch.errors?.length ? ` · ${lastSearch.errors.length} search groups had errors` : ""}` : "No fresh search snapshot yet."}</p>
    {!lastSearch && <div className="jobs-alert" role="status">Saved results from older searches are kept for duplicate detection, but are hidden until you run a fresh search. Choose an index window and click Check for new jobs.</div>}
    {lastSearch && lastSearch.count === 0 && <div className="jobs-alert" role="status">The latest search returned no listings. Try a wider index window or search again later.</div>}
    {status.applicationSession?.active && <section className="jobs-running application-session" role="status">
      <strong>{status.applicationSession.title} · {status.applicationSession.company} ({status.applicationSession.index}/{status.applicationSession.total})</strong>
      <p>{status.applicationSession.message}</p>
      {status.applicationSession.filled?.length > 0 && <small>Filled: {status.applicationSession.filled.join(", ")}</small>}
      {status.applicationSession.needsYourAnswer?.length > 0 && <small>Needs your answer: {status.applicationSession.needsYourAnswer.join(", ")}</small>}
      {!status.applicationSession.resumeAvailable && <small>Résumé PDF not found at the configured path; upload it manually in Chrome.</small>}
      <div className="jobs-toolbar">
        {status.applicationSession.phase !== "awaiting_review" && <button className="refresh" onClick={() => applicationAction("/api/fill-application")}>Continue</button>}
        {status.applicationSession.phase === "awaiting_review" && <button className="apply-button" onClick={() => applicationAction("/api/application-submitted")}>I submitted — next job</button>}
        <button className="refresh" onClick={() => applicationAction("/api/application-skip")}>Skip this job</button>
        <button className="refresh" onClick={() => applicationAction("/api/application-stop", "Stop the browser session and close its Chrome window?")}>Stop session</button>
      </div>
    </section>}
    {rows.length > 0 && windowRows.length === 0 && <div className="jobs-alert" role="status">The latest search used a different index window. Choose that window or click Check for new jobs to search this one.</div>}
    <div className="jobs-table-wrap"><table className="jobs-table" data-reviewed-rows>
      <thead><tr><th><label className="select-all"><input type="checkbox" aria-label={`Select up to ${MAX_SELECTED_JOBS} visible new jobs`} title={`Select visible New jobs, up to ${MAX_SELECTED_JOBS} jobs total; processed jobs are excluded`} checked={allVisibleSelected} disabled={!selectableVisible.length || status.running || status.applicationSession?.active} onChange={toggleAllVisible} />Select all new (up to {MAX_SELECTED_JOBS}; {selectableVisible.length} available)</label></th><th>Job</th><th>Company</th><th>Location</th><th>Board</th><th>Resume-match evidence</th><th>Status</th><th>Posting</th></tr></thead>
      <tbody>{visible.map(row => <tr key={row.id}>
        <td><input type="checkbox" aria-label={`Select ${row.title}${row.applicationStatus !== "New" ? `; not selectable because status is ${row.applicationStatus}` : ""}`} title={row.applicationStatus === "New" ? "Available to select" : `Not selectable: status is ${row.applicationStatus}`} disabled={row.applicationStatus !== "New" || status.running || status.applicationSession?.active} checked={selected.includes(row.id)} onChange={() => toggle(row.id)} /></td>
        <td><strong>{row.title}</strong>{row.newFinding && <small>First found in this search</small>}{!row.newFinding && row.firstSeenAt && <small>Seen before · first found {new Date(row.firstSeenAt).toLocaleDateString()}</small>}{row.duplicateCount > 1 && <small>Duplicate listings merged: {row.duplicateCount}</small>}</td>
        <td>{row.company}<small>{row.companyEvidence ? `From ${row.companyEvidence.toLowerCase()}` : "Company needs verification"} · {row.companyType ?? "Unclassified"}</small></td><td>{row.location}<small>{row.locationEvidence ? `From ${row.locationEvidence.toLowerCase()}; verify on posting` : "Location needs verification"} · Search priority: {row.priorityArea}</small></td><td>{row.source}</td><td><span className={`fit fit-${fitOrder[row.fitBand]}`}>{row.fitBand}</span><small>{row.fitReason}</small>{row.matchedResumeKeywords?.length > 0 && <small>Profile terms: {row.matchedResumeKeywords.slice(0, 4).join(", ")}</small>}{row.snippet && <details><summary>Search snippet</summary><small>{row.snippet}</small></details>}</td>
        <td>{row.applicationStatus}{row.applicationStatus !== "New" && <small>Processed listings are excluded from selection.</small>}</td><td><a href={row.link} target="_blank" rel="noreferrer">Open posting ↗</a></td>
      </tr>)}</tbody>
    </table>{visible.length === 0 && <p className="jobs-empty">No listings match these filters.</p>}</div>
    <p className="jobs-footnote">The browser session uses a separate local Chrome profile; sign in there yourself. Review each completed form and click Submit yourself, then choose “I submitted — next job” so the dashboard records the outcome correctly.</p>
  </article>;
}
