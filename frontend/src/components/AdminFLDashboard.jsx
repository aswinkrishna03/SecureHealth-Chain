import React, { useEffect, useState } from 'react';
import { apiFetch } from '../api';

export default function AdminFLDashboard() {
  const [flState, setFlState] = useState(null);
  const [loading, setLoading] = useState(false);
  const [audit, setAudit] = useState(null);
  const [logs, setLogs] = useState(['[*] Ready. Start a training simulation to see round output.']);

  const fetchStatus = async () => {
    try {
      const response = await apiFetch('/api/fl/status');
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.message || 'Could not load FL status');
      setFlState(data.fl_state);
    } catch (error) {
      setLogs((previous) => [...previous, `[!] Could not load FL status: ${error.message}`]);
    }
  };

  useEffect(() => { fetchStatus(); }, []);

  const verifyUpdates = async () => {
    try {
      const response = await apiFetch('/api/fl/verify');
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.message || 'Verification failed');
      setAudit(data);
    } catch (error) {
      setAudit({ error: error.message });
    }
  };

  const handleTriggerRound = async () => {
    setLoading(true);
    setLogs((previous) => [...previous, '[*] Starting local training from the configured EHR dataset…']);
    try {
      const response = await apiFetch('/api/fl/trigger-round', {
        method: 'POST',
        body: JSON.stringify({ rounds: 1, epsilon: 1.0 })
      });
      const data = await response.json();
      if (!response.ok || !data.success || !data.results) throw new Error(data.message || 'Training failed');
      const result = data.results;
      const lastRound = result.history?.[result.history.length - 1];
      setLogs((previous) => [...previous,
        `Dataset: ${result.dataset || 'configured sample dataset'}`,
        `Patients: ${result.dataset_summary?.patient_count ?? 'n/a'}; edge nodes: ${result.dataset_summary?.edge_node_count ?? 'n/a'}`,
        `Target: ${result.dataset_summary?.target ?? 'see dataset documentation'}`,
        `Rejected rows: ${result.rejected_edge_rows ?? 0}`,
        `Differential privacy: ${result.privacy_note || 'demo noise'}`,
        `Homomorphic encryption: ${result.homomorphic_encryption_note || 'not reported'}`,
        `Held-out accuracy: ${result.final_accuracy ?? 'n/a'}%`,
        `Simulation hash: ${result.latest_tx_hash || 'not available'}`,
        ...(lastRound?.node_updates || []).map((node) => `${node.hospital}: ${node.samples} training rows; update ${node.update_hash || 'hash unavailable'}`)
      ]);
      await fetchStatus();
    } catch (error) {
      setLogs((previous) => [...previous, `[!] Round failed: ${error.message}`]);
    } finally {
      setLoading(false);
    }
  };

  const history = flState?.history || [];

  return (
    <section className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl"><span className="text-xs text-slate-400 block">FL rounds completed</span><span className="text-2xl font-black text-cyan-400">{flState?.total_rounds ?? 0}</span></div>
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl"><span className="text-xs text-slate-400 block">Global model accuracy</span><span className="text-2xl font-black text-emerald-400">{flState?.current_accuracy == null ? '—' : `${flState.current_accuracy}%`}</span></div>
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl"><span className="text-xs text-slate-400 block">Training participants</span><span className="text-sm text-purple-300">3 virtual hospital nodes</span></div>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div><h2 className="text-lg font-bold text-white">Federated learning administration</h2><p className="text-xs text-slate-400">Synthetic/demo training only. Admin receives model update hashes and aggregate metrics, not patient rows.</p></div>
          <div className="flex flex-wrap gap-2"><button onClick={verifyUpdates} className="px-4 py-2 bg-slate-800 border border-slate-700 text-cyan-300 rounded-lg text-sm">Verify FL updates</button><button onClick={handleTriggerRound} disabled={loading} className="px-4 py-2 bg-cyan-700 disabled:opacity-50 text-white rounded-lg text-sm">{loading ? 'Training…' : 'Start FL round'}</button></div>
        </div>

        {audit && <div role="status" className="rounded-lg border border-slate-700 p-3 text-sm text-cyan-200">{audit.error || `Ledger verification: ${audit.verified_rounds}/${audit.total_rounds} rounds verified.`}{(audit.rounds || []).map((round) => <div key={round.round} className="mt-1 text-xs">Round {round.round}: {round.verified ? 'verified' : 'mismatch'} · nodes {round.node_count} · global hash {round.global_model_hash || '—'}</div>)}</div>}

        <div className="rounded-lg border border-slate-800 p-4"><h3 className="text-sm font-semibold text-white mb-2">Recent shared model updates (hashes only)</h3>{history.slice().reverse().slice(0, 3).map((round) => <div key={round.round} className="border-t border-slate-800 py-2 text-xs text-slate-400"><div>Round {round.round} · global hash: <span className="font-mono break-all">{round.global_model_hash || '—'}</span></div>{(round.node_updates || []).map((node) => <div key={node.hospital}>{node.hospital} · update hash: <span className="font-mono break-all">{node.update_hash || '—'}</span></div>)}</div>)}{history.length === 0 && <p className="text-xs text-slate-500">No model updates yet.</p>}</div>

        <div className="bg-slate-950 rounded-lg p-4 border border-slate-800 text-xs font-mono space-y-2 text-slate-300 max-h-56 overflow-y-auto">{logs.map((log, index) => <div key={`${index}-${log}`}>{log}</div>)}</div>
      </div>
    </section>
  );
}
