import React, { useState, useEffect } from 'react';
import { apiFetch } from '../api';

export default function AdminFLDashboard() {
  const [flState, setFlState] = useState(null);
  const [loading, setLoading] = useState(false);
  const [audit, setAudit] = useState(null);
  const [logs, setLogs] = useState(['[*] Ready. Start a training simulation to see round output.']);

  const fetchStatus = async () => {
    try {
      const res = await apiFetch('/api/fl/status');
      const data = await res.json();
      if (data.fl_state) setFlState(data.fl_state);
    } catch (e) {
      console.error(e);
    }
  };

  const verifyUpdates = async () => {
    setAudit(null);
    try {
      const res = await apiFetch('/api/fl/verify');
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.message || 'Verification failed');
      setAudit(data);
    } catch (e) { setAudit({ error: e.message }); }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleTriggerRound = async () => {
    setLoading(true);
    setLogs((prev) => [...prev, '[*] Initializing local edge training from the configured EHR dataset...']);
    try {
      const res = await apiFetch('/api/fl/trigger-round', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rounds: 1, epsilon: 1.0 })
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.message || 'Training request failed');
      const lastRound = data.results.history?.[data.results.history.length - 1];
      setLogs((prev) => [
        ...prev,
        `   -> Dataset: ${data.results.dataset || 'configured sample dataset'}`,
        `   -> Patients: ${data.results.dataset_summary?.patient_count ?? 'n/a'}; local edge nodes: ${data.results.dataset_summary?.edge_node_count ?? 'n/a'}`,
        `   -> Training target: ${data.results.dataset_summary?.target ?? 'see dataset documentation'}`,
        `   -> Rejected ${data.results.rejected_edge_rows ?? 0} invalid edge row(s) during preprocessing`,
        `   -> Differential privacy: ${data.results.privacy_note}`,
        `   -> Homomorphic encryption: ${data.results.homomorphic_encryption_note}`,
        '   -> Aggregated with paper FedAvg on encrypted vectors, weighted by each node training sample count',
        `   -> Round Aggregated Successfully! Held-out accuracy: ${data.results.final_accuracy ?? 'n/a'}%`,
        `   -> Local simulation hash: ${data.results.latest_tx_hash?.substring(0, 24) || 'not available'}...`,
        ...(lastRound?.node_updates || []).map((node) => `   -> ${node.hospital}: ${node.samples} local training rows, holdout ${node.local_accuracy}%`)
      ]);
      fetchStatus();
    } catch (err) {
      setLogs((prev) => [...prev, `[!] Round failed: ${err}`]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl shadow">
          <span className="text-xs text-slate-400 block">FL Rounds Completed</span>
          <span className="text-2xl font-black text-cyan-400">{flState?.total_rounds ?? 0}</span>
        </div>
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl shadow">
          <span className="text-xs text-slate-400 block">Global Model Accuracy</span>
          <span className="text-2xl font-black text-emerald-400">{flState?.current_accuracy == null ? '—' : `${flState.current_accuracy}%`}</span>
        </div>
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl shadow">
          <span className="text-xs text-slate-400 block">Participating Silos</span>
          <span className="text-2xl font-black text-purple-400">3 Nodes</span>
        </div>
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl shadow">
          <span className="text-xs text-slate-400 block">Noise Setting</span>
          <span className="text-xs font-mono text-amber-400 block mt-2">Gaussian noise (demo only)</span>
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h3 className="text-lg font-bold text-white">Run Local Federated Learning Simulation</h3>
            <p className="text-xs text-slate-400">
              Trains locally from the Synthea ZIP in Downloads when present, using three virtual edge partitions. Per-patient gradients are clipped and noised with a composed RDP budget; CKKS encrypts node models for sample-weighted FedAvg. This single-process demo keeps the key custodian in the same process, and exact evaluation metrics are not DP. The data and model are for education, not clinical use.
            </p>
          </div>
          <button onClick={verifyUpdates} className="px-4 py-2.5 bg-slate-800 border border-slate-700 text-cyan-300 rounded-lg text-sm">Verify FL updates</button><div className="flex gap-2 flex-wrap"><button
            onClick={handleTriggerRound}
            disabled={loading}
            className="px-5 py-2.5 bg-gradient-to-r from-purple-600 to-cyan-600 hover:from-purple-500 hover:to-cyan-500 text-white font-bold rounded-lg text-sm transition flex items-center gap-2"
          >
            {loading ? '⏳ Training Across Nodes...' : '🚀 Start FL Training Round'}
          </button></div>
        </div>

        <div className="bg-slate-950 rounded-lg p-4 border border-slate-800 text-xs font-mono space-y-2 text-slate-300 max-h-56 overflow-y-auto">
          {logs.map((log, idx) => (
            <div key={idx} className={log.includes('Converged') || log.includes('Global Accuracy') ? 'text-emerald-400 font-bold' : (log.includes('Ready') ? 'text-cyan-400 font-bold' : 'text-slate-400')}>
              {log}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}        {audit && <p role="status" className="text-sm text-cyan-300">Ledger verification: {audit.error || (audit.verified_rounds + "/" + audit.total_rounds + " rounds verified")}</p>}
        <div className="rounded-lg border border-slate-800 p-4"><h4 className="text-sm font-semibold text-white mb-2">Latest shared model updates (hashes only)</h4>{(flState?.history || []).slice().reverse().slice(0, 3).map((round) => <div key={round.round} className="border-t border-slate-800 py-2 text-xs text-slate-400"><div>Round {round.round} · global hash: <span className="font-mono break-all">{round.global_model_hash || "—"}</span></div>{(round.node_updates || []).map((node) => <div key={node.hospital}>{node.hospital} update: <span className="font-mono break-all">{node.update_hash || "—"}</span></div>)}</div>)}</div>

