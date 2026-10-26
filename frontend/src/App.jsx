import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import EHRManager from './components/EHRManager';
import RiskPredictor from './components/RiskPredictor';
import QRVerifier from './components/QRVerifier';
import AdminFLDashboard from './components/AdminFLDashboard';

export default function App() {
  const [activeTab, setActiveTab] = useState('doctor');
  const [currentRole, setCurrentRole] = useState('doctor');

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      <Navbar 
        currentRole={currentRole} 
        setRole={(role) => {
          setCurrentRole(role);
          if (role === 'doctor') setActiveTab('doctor');
          if (role === 'patient') setActiveTab('verify');
          if (role === 'admin') setActiveTab('fl');
        }}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
      />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full">
        {activeTab === 'doctor' && <EHRManager />}
        {activeTab === 'predict' && <RiskPredictor />}
        {activeTab === 'verify' && <QRVerifier />}
        {activeTab === 'fl' && <AdminFLDashboard />}
      </main>

      <footer className="border-t border-slate-800 bg-slate-900/60 py-6 text-center text-xs text-slate-400">
        <p className="font-semibold text-slate-300">SecureHealth Chain: Privacy-Preserving Healthcare Platform</p>
        <p className="mt-1">Grounded in Nature Scientific Reports EPP-BCFL Framework (2025)</p>
      </footer>
    </div>
  );
}
