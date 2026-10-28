import React, { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '../api';

export default function PatientPortal() {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [verification, setVerification] = useState({});
  const [qrImages, setQrImages] = useState({});
  const qrUrls = useRef({});

  const loadRecords = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await apiFetch('/api/ehr/list');
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.message || 'Could not load your records');
      setRecords(Array.isArray(data.records) ? data.records : []);
    } catch (err) {
      setError(err.message || 'Could not load your records');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRecords();
    return () => Object.values(qrUrls.current).forEach((url) => URL.revokeObjectURL(url));
  }, [loadRecords]);

  const verifyRecord = async (recordUuid) => {
    setVerification((current) => ({ ...current, [recordUuid]: { loading: true } }));
    try {
      const response = await apiFetch('/api/verify/record', {
        method: 'POST',
        body: JSON.stringify({ record_uuid: recordUuid })
      });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.message || 'Verification was denied');
      setVerification((current) => ({ ...current, [recordUuid]: { result: data } }));
    } catch (err) {
      setVerification((current) => ({ ...current, [recordUuid]: { error: err.message || 'Verification failed' } }));
    }
  };

  const showQr = async (record) => {
    try {
      const response = await apiFetch(record.qr_code_url);
      if (!response.ok) throw new Error('QR code access was denied');
      const imageUrl = URL.createObjectURL(await response.blob());
      const oldUrl = qrUrls.current[record.record_uuid];
      if (oldUrl) URL.revokeObjectURL(oldUrl);
      qrUrls.current[record.record_uuid] = imageUrl;
      setQrImages((current) => ({ ...current, [record.record_uuid]: imageUrl }));
    } catch (err) {
      setError(err.message || 'Could not load QR code');
    }
  };

  return (
    <section className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-cyan-400">Patient Portal</p>
          <h2 className="mt-2 text-2xl font-bold text-white">My Health Records</h2>
          <p className="mt-2 text-sm text-slate-400">This page loads records for your signed-in account only. Verify a record’s integrity or open its QR code.</p>
        </div>
        <button onClick={loadRecords} disabled={loading} className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-sm text-cyan-300">
          {loading ? 'Loading…' : 'Refresh records'}
        </button>
      </div>

      {error && <p role="alert" className="rounded-lg border border-rose-800 bg-rose-950/50 p-3 text-sm text-rose-300">{error}</p>}
      {loading && <p role="status" className="text-sm text-slate-400">Loading your records…</p>}
      {!loading && !error && records.length === 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm text-slate-300">
          No records are linked to your account yet. Ask your doctor to add a record after your visit.
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {records.map((record) => {
          const check = verification[record.record_uuid];
          const recordedAt = record.recorded_at || record.created_at;
          return (
            <article key={record.record_uuid} className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
              <div>
                <p className="font-mono text-xs text-cyan-400">{record.record_uuid}</p>
                <h3 className="mt-1 text-lg font-semibold text-white">{record.diagnosis || 'Clinical record'}</h3>
                <p className="mt-2 text-xs text-slate-400">
                  {record.doctor_name || 'Doctor not listed'} · {record.hospital_name || 'Hospital not listed'}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {recordedAt && !Number.isNaN(Date.parse(recordedAt)) ? new Date(recordedAt).toLocaleString() : 'Date not available'}
                </p>
              </div>

              {record.clinical_metrics && (
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2 border-t border-slate-800 pt-3 text-xs">
                  {Object.entries(record.clinical_metrics).map(([key, value]) => (
                    <div key={key} className="min-w-0">
                      <dt className="capitalize text-slate-500">{({ age: 'Age', resting_bp: 'Blood pressure (mm Hg)', cholesterol: 'Cholesterol (mg/dL)', heart_rate: 'Heart rate (bpm)', max_hr: 'Maximum heart rate (bpm)', blood_glucose: 'Blood glucose (mg/dL)', oxygen_saturation: 'Oxygen saturation (%)' })[key] || key.replaceAll('_', ' ')}</dt>
                      <dd className="break-words text-slate-200">{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd>
                    </div>
                  ))}
                </dl>
              )}

              <div className="flex flex-wrap gap-2">
                <button onClick={() => verifyRecord(record.record_uuid)} disabled={check?.loading} className="rounded-lg bg-cyan-700 px-3 py-2 text-sm font-semibold text-white hover:bg-cyan-600 disabled:opacity-50">
                  {check?.loading ? 'Verifying…' : 'Verify integrity'}
                </button>
                {record.qr_code_url && (
                  <button onClick={() => showQr(record)} className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-cyan-300 hover:bg-slate-700">
                    {qrImages[record.record_uuid] ? 'Refresh QR code' : 'Show QR code'}
                  </button>
                )}
              </div>

              {check?.result && (
                <p role="status" className={check.result.is_authentic ? 'text-sm text-emerald-400' : 'text-sm text-rose-400'}>
                  {check.result.is_authentic ? 'Verified: record matches its sealed hash.' : 'Alert: record does not match its sealed hash.'}
                </p>
              )}
              {check?.error && <p role="alert" className="text-sm text-rose-400">{check.error}</p>}
              {qrImages[record.record_uuid] && (
                <div className="inline-block rounded-lg bg-white p-3">
                  <img src={qrImages[record.record_uuid]} alt={`QR code for record ${record.record_uuid}`} className="h-40 w-40" />
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
