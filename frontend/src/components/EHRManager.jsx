import React, { useState, useEffect } from 'react';
import { apiFetch } from '../api';

export default function EHRManager({ hospitalName }) {
  const [records, setRecords] = useState([]);
  const [patients, setPatients] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [selectedQR, setSelectedQR] = useState(null);
  const [formData, setFormData] = useState({
    patient_id: '3',
    diagnosis: 'Cardiovascular Assessment - Normal Sinus',
    resting_bp: 122,
    cholesterol: 195,
  });

  const fetchRecords = async () => {
    try {
      const res = await apiFetch('/api/ehr/list');
      const data = await res.json();
      if (data.records) setRecords(data.records);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchRecords();
    apiFetch('/api/ehr/patients').then((res) => res.json()).then((data) => {
      if (data.patients) {
        setPatients(data.patients);
        if (data.patients.length) setFormData((current) => ({ ...current, patient_id: String(data.patients[0].id) }));
      }
    }).catch((e) => console.error(e));
  }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      const res = await apiFetch('/api/ehr/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          patient_id: Number(formData.patient_id),
          diagnosis: formData.diagnosis,
          clinical_metrics: {
            resting_bp: formData.resting_bp,
            cholesterol: formData.cholesterol
          }
        })
      });
      const data = await res.json();
      setShowModal(false);
      fetchRecords();
      if (data.record) setSelectedQR(data.record);
    } catch (err) {
      alert('Error creating record: ' + err);
    }
  };

  return (
    <section className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            Electronic Health Record (EHR) Hub
            <span className="text-xs bg-cyan-900 text-cyan-300 px-2 py-0.5 rounded border border-cyan-700">Module 1 & 3</span>
          </h2>
          <p className="text-sm text-slate-400">
            Create clinical patient records. The local demo ledger stores a tamper-evident hash; connect a deployed contract for Ethereum transactions.
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="px-4 py-2 bg-gradient-to-r from-cyan-600 to-emerald-600 hover:from-cyan-500 hover:to-emerald-500 text-white rounded-lg text-sm font-semibold shadow-md transition"
        >
          ➕ New Patient Diagnosis & Hash Seal
        </button>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <span className="text-sm font-semibold text-slate-300">Registered Patient Records</span>
          <button onClick={fetchRecords} className="text-xs text-cyan-400 hover:underline">
            🔄 Refresh List
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-300">
            <thead className="bg-slate-950/60 text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
              <tr>
                <th className="px-4 py-3">Record UUID</th>
                <th className="px-4 py-3">Patient</th>
                <th className="px-4 py-3">Hospital</th>
                <th className="px-4 py-3">Diagnosis</th>
                <th className="px-4 py-3">SHA-256 Hash</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80">
              {records.map((r) => (
                <tr key={r.record_uuid} className="hover:bg-slate-800/40 transition">
                  <td className="px-4 py-3 font-mono font-semibold text-cyan-400">{r.record_uuid}</td>
                  <td className="px-4 py-3 font-medium text-white">{r.patient_name || 'Patient'}</td>
                  <td className="px-4 py-3 text-xs text-slate-400">{r.hospital_name}</td>
                  <td className="px-4 py-3 text-xs text-slate-200">{r.diagnosis}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400 truncate max-w-xs">{r.record_hash?.substring(0, 14)}...</td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> Sealed
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => setSelectedQR(r)}
                      className="text-xs bg-slate-800 hover:bg-slate-700 text-cyan-400 px-3 py-1 rounded border border-slate-700"
                    >
                      📱 QR Code
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal Create */}
      {showModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-lg font-bold text-white">Create EHR & Seal Its Hash</h3>
              <button onClick={() => setShowModal(false)} className="text-slate-400 hover:text-white">✕</button>
            </div>
            <form onSubmit={handleCreate} className="space-y-3 text-xs">
              <div>
                <label className="block font-semibold text-slate-400 mb-1">Registered Patient</label>
                <select required value={formData.patient_id} onChange={(e) => setFormData({ ...formData, patient_id: e.target.value })} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white">
                  {patients.map((patient) => <option key={patient.id} value={patient.id}>{patient.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block font-semibold text-slate-400 mb-1">Hospital / Clinic</label>
                <input readOnly value={hospitalName} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-400" />
              </div>
              <div>
                <label className="block font-semibold text-slate-400 mb-1">Diagnosis</label>
                <input
                  type="text"
                  value={formData.diagnosis}
                  onChange={(e) => setFormData({ ...formData, diagnosis: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-400 mb-1">Resting BP (mm Hg)</label>
                  <input
                    type="number"
                    value={formData.resting_bp}
                    onChange={(e) => setFormData({ ...formData, resting_bp: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-400 mb-1">Cholesterol (mg/dl)</label>
                  <input
                    type="number"
                    value={formData.cholesterol}
                    onChange={(e) => setFormData({ ...formData, cholesterol: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white"
                  />
                </div>
              </div>
              <div className="pt-3 border-t border-slate-800 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-gradient-to-r from-cyan-600 to-emerald-600 hover:from-cyan-500 hover:to-emerald-500 text-white rounded-lg text-xs font-bold shadow"
                >
                  🔐 Seal Record Hash & Generate QR
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* QR Modal */}
      {selectedQR && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-sm w-full p-6 shadow-2xl text-center space-y-4">
            <h3 className="text-base font-bold text-white">Cryptographic QR Code</h3>
            <div className="p-4 bg-white rounded-xl inline-block shadow-lg mx-auto">
              <img src={selectedQR.qr_code_url} alt="EHR QR" className="w-48 h-48 mx-auto" />
            </div>
            <p className="text-xs font-mono text-cyan-400">{selectedQR.record_uuid}</p>
            <p className="text-xs text-slate-400">
              Scan this QR code during clinical checks to verify the record hash against the local demo ledger.
            </p>
            <button
              onClick={() => setSelectedQR(null)}
              className="w-full py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-semibold"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
