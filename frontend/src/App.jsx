import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import EHRManager from './components/EHRManager';
import RiskPredictor from './components/RiskPredictor';
import QRVerifier from './components/QRVerifier';
import AdminFLDashboard from './components/AdminFLDashboard';
import { apiFetch } from './api';

export default function App() {
  const [activeTab, setActiveTab] = useState('doctor');
  const [session, setSession] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem('securehealth-user')); } catch { return null; }
  });
  const [email, setEmail] = useState('doctor@securehealth.org');
  const [password, setPassword] = useState('doctor');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [name, setName] = useState('');

  useEffect(() => {
    const expireSession = () => {
      sessionStorage.removeItem('securehealth-token');
      sessionStorage.removeItem('securehealth-user');
      setSession(null);
    };
    window.addEventListener('securehealth-session-expired', expireSession);
    return () => window.removeEventListener('securehealth-session-expired', expireSession);
  }, []);

  useEffect(() => {
    if (!session) return undefined;
    let active = true;

    apiFetch('/api/auth/me').then(async (response) => {
      if (!response.ok) throw new Error('Session expired');
      const data = await response.json();
      const user = data.user;
      if (!data.success || !user || !['admin', 'doctor', 'patient'].includes(user.role)) {
        throw new Error('Invalid account session');
      }
      if (!active) return;
      // Trust the server's current session role, never a browser-edited cached role.
      sessionStorage.setItem('securehealth-user', JSON.stringify(user));
      setSession(user);
    }).catch(() => {
      if (!active) return;
      sessionStorage.removeItem('securehealth-token');
      sessionStorage.removeItem('securehealth-user');
      setSession(null);
    });

    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (session?.role === 'admin') setActiveTab('fl');
    if (session?.role === 'patient') setActiveTab('verify');
    if (session?.role === 'doctor') setActiveTab('doctor');
  }, [session?.role]);

  const login = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || 'Unable to sign in');
      sessionStorage.setItem('securehealth-token', data.token);
      sessionStorage.setItem('securehealth-user', JSON.stringify(data.user));
      setSession(data.user);
      setActiveTab(data.user.role === 'admin' ? 'fl' : data.user.role === 'patient' ? 'verify' : 'doctor');
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  const register = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const response = await fetch('/api/auth/register', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, name, password })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || 'Unable to create account');
      setRegistering(false);
      setNotice('Patient account created. Sign in with your new credentials.');
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  const logout = async () => {
    try { await apiFetch('/api/auth/logout', { method: 'POST' }); } catch {}
    sessionStorage.removeItem('securehealth-token');
    sessionStorage.removeItem('securehealth-user');
    setSession(null);
  };

  if (!session) return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-4">
      <form onSubmit={registering ? register : login} className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-8 space-y-5 shadow-xl">
        <div><p className="text-cyan-400 font-bold">SecureHealth Chain</p><h1 className="text-2xl font-bold mt-2">{registering ? 'Create patient account' : 'Sign in'}</h1><p className="text-sm text-slate-400 mt-1">{registering ? 'New accounts are assigned the patient role.' : 'Use your project account to open the role dashboard.'}</p></div>
        {registering && <label className="block text-sm text-slate-300">Full name<input required value={name} onChange={(e) => setName(e.target.value)} className="mt-1 w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white" /></label>}
        <label className="block text-sm text-slate-300">Email<input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white" /></label>
        <label className="block text-sm text-slate-300">Password<input required minLength={registering ? 8 : undefined} type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1 w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white" /></label>
        {error && <p role="alert" className="text-sm text-rose-400">{error}</p>}
        {notice && <p role="status" className="text-sm text-emerald-400">{notice}</p>}
        <button disabled={busy} className="w-full bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 rounded-lg py-2.5 font-semibold">{busy ? 'Please wait…' : registering ? 'Create patient account' : 'Sign in'}</button>
        <button type="button" onClick={() => { setRegistering(!registering); setError(''); setNotice(''); }} className="w-full text-sm text-cyan-400 hover:text-cyan-300">{registering ? 'Back to sign in' : 'Create a patient account'}</button>
        {!registering && <p className="text-xs text-slate-500">Demo accounts: doctor@securehealth.org / doctor, patient@securehealth.org / patient, admin@securehealth.org / admin</p>}
      </form>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      <Navbar
        user={session}
        onLogout={logout}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
      />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full">
        {activeTab === 'doctor' && session.role === 'doctor' && <EHRManager hospitalName={session.hospital_name} />}
        {activeTab === 'predict' && session.role !== 'patient' && <RiskPredictor />}
        {activeTab === 'verify' && <QRVerifier role={session.role} />}
        {activeTab === 'fl' && session.role === 'admin' && <AdminFLDashboard />}
      </main>

      <footer className="border-t border-slate-800 bg-slate-900/60 py-6 text-center text-xs text-slate-400">
        <p className="font-semibold text-slate-300">SecureHealth Chain: Privacy-Preserving Healthcare Platform</p>
        <p className="mt-1">Grounded in Nature Scientific Reports EPP-BCFL Framework (2025)</p>
      </footer>
    </div>
  );
}
