import React from 'react';

export default function Navbar({ currentRole, setRole, activeTab, setActiveTab }) {
  const tabs = [
    { id: 'doctor', label: '📋 Clinical Records & Sealing' },
    { id: 'predict', label: '🧠 AI Disease Risk Predictor' },
    { id: 'verify', label: '🔍 QR Scan & Blockchain Verification' },
    { id: 'fl', label: '🌐 Federated Learning & Telemetry' },
  ];

  return (
    <header className="border-b border-slate-800 bg-slate-900/90 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-emerald-500 flex items-center justify-center font-bold text-white shadow-lg text-xl">
            ⚕️
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-extrabold text-lg tracking-tight bg-gradient-to-r from-cyan-400 to-emerald-400 bg-clip-text text-transparent">
                SecureHealth Chain
              </span>
              <span className="text-xs bg-slate-800 text-cyan-400 border border-cyan-800/60 px-2 py-0.5 rounded-full font-mono">
                S7/S8 CSE
              </span>
            </div>
            <p className="text-xs text-slate-400 hidden sm:block">
              EPP-BCFL: Lightweight Blockchain-Based Federated Learning for EHRs
            </p>
          </div>
        </div>

        {/* Role Selector */}
        <div className="flex items-center space-x-3">
          <div className="flex bg-slate-800 p-1 rounded-lg border border-slate-700 text-xs font-medium">
            {['doctor', 'patient', 'admin'].map((role) => (
              <button
                key={role}
                onClick={() => setRole(role)}
                className={`px-3 py-1.5 rounded-md capitalize transition ${
                  currentRole === role
                    ? 'bg-cyan-600 text-white font-semibold'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                {role === 'doctor' && '👨‍⚕️ Doctor'}
                {role === 'patient' && '👤 Patient'}
                {role === 'admin' && '⚙️ Admin / FL'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="bg-slate-900/80 border-t border-slate-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex space-x-6 text-sm font-medium overflow-x-auto">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`py-3 border-b-2 flex items-center space-x-2 transition whitespace-nowrap ${
                activeTab === tab.id
                  ? 'border-cyan-500 text-cyan-400 font-bold'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <span>{tab.label}</span>
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}
