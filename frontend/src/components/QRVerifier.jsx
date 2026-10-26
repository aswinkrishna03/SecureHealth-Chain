import React, { useState } from 'react';

export default function QRVerifier() {
  const [uuid, setUuid] = useState('EHR-DEMO-001');
  const [auditResult, setAuditResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleVerify = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/verify/record', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ record_uuid: uuid })
      });
      const data = await res.json();
      setAuditResult(data);
    } catch (err) {
      alert('Verification failed: ' + err);
    } finally {
      setLoading(false);
    }
  };

  const handleTamperDemo = async () => {
    try {
      const res = await fetch('/api/demo/tamper-record', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ record_uuid: uuid })
      });
      const data = await res.json();
      alert(data.message);
      handleVerify();
    } catch (err) {
      alert('Tamper demo failed: ' + err);
    }
  };

  return (
    <section className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        <div className="lg:col-span-6 bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-5">
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-xl font-bold text-white">QR Integrity Verification Engine</h2>
              <span className="text-xs bg-purple-950 text-purple-300 border border-purple-800 px-2 py-0.5 rounded">
                Module 4
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Cross-checks the current record data against the immutable Ethereum Ganache ledger.
            </p>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-1">Record UUID</label>
            <input
              type="text"
              value={uuid}
              onChange={(e) => setUuid(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white font-mono text-sm focus:border-cyan-500 focus:outline-none"
            />
          </div>

          <button
            onClick={handleVerify}
            disabled={loading}
            className="w-full py-2.5 bg-cyan-600 hover:bg-cyan-500 text-white font-semibold rounded-lg text-sm shadow transition"
          >
            {loading ? 'Querying Blockchain...' : '🔍 Verify Authenticity on Blockchain'}
          </button>

          <div className="pt-4 border-t border-slate-800">
            <span className="text-xs font-bold text-rose-400 uppercase tracking-wide block mb-1">
              Examiner Viva Demonstration:
            </span>
            <p className="text-xs text-slate-400 mb-3">
              Simulate an unauthorized database hack or record modification without blockchain consensus:
            </p>
            <button
              onClick={handleTamperDemo}
              className="w-full py-2 bg-rose-950 hover:bg-rose-900 text-rose-300 border border-rose-800 font-semibold rounded-lg text-xs transition flex items-center justify-center gap-2"
            >
              ⚠️ Maliciously Alter Database Record (Simulate Tampering)
            </button>
          </div>
        </div>

        {/* Audit Result Display */}
        <div className="lg:col-span-6 bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 mb-4">Verification Audit Result</h3>
            
            <div className={`p-6 rounded-xl border text-center space-y-3 ${
              auditResult?.is_authentic 
                ? 'bg-emerald-950/40 border-emerald-600' 
                : (auditResult ? 'bg-rose-950/60 border-rose-600' : 'bg-slate-950 border-slate-800')
            }`}>
              <div className="text-4xl">
                {auditResult?.is_authentic ? '✅' : (auditResult ? '🚨' : '🛡️')}
              </div>
              <h4 className={`text-lg font-bold ${
                auditResult?.is_authentic 
                  ? 'text-emerald-400' 
                  : (auditResult ? 'text-rose-500 animate-pulse' : 'text-slate-300')
              }`}>
                {auditResult?.is_authentic 
                  ? 'VERIFIED AUTHENTIC & IMMUTABLE' 
                  : (auditResult ? 'CRITICAL ALERT: RECORD TAMPERED!' : 'Ready to Verify')}
              </h4>
              <p className="text-xs text-slate-400">
                {auditResult?.is_authentic 
                  ? 'SHA-256 hash matches the on-chain Ganache smart contract ledger. Record is intact and untampered.' 
                  : (auditResult ? 'Hash mismatch detected! The clinical database record was modified without blockchain consensus!' : 'Click "Verify Authenticity" to perform cryptographic hash matching against Ganache.')}
              </p>
            </div>

            <div className="mt-4 space-y-2 text-xs font-mono">
              <div className="p-2 rounded bg-slate-950 border border-slate-800/80">
                <span className="text-slate-500 block">On-Chain Blockchain Hash:</span>
                <span className="text-slate-300 break-all">{auditResult?.stored_hash || '--'}</span>
              </div>
              <div className="p-2 rounded bg-slate-950 border border-slate-800/80">
                <span className="text-slate-500 block">Recomputed Database Hash:</span>
                <span className="text-slate-300 break-all">{auditResult?.recomputed_hash || '--'}</span>
              </div>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-800 flex items-center justify-between text-xs text-slate-500">
            <span>Consensus: PoS-BFT Ganache</span>
            <span>Checked: {auditResult ? new Date().toLocaleTimeString() : '--'}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
