import React, { useState } from 'react';

export default function RiskPredictor() {
  const [formData, setFormData] = useState({
    age: 54,
    resting_bp: 138,
    cholesterol: 248,
    max_hr: 128,
    fbs: 0,
    angina: 0
  });

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handlePredict = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch('/api/ai/predict-risk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });
      const data = await res.json();
      setResult(data);
    } catch (err) {
      alert('Prediction failed: ' + err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Form Inputs */}
        <div className="lg:col-span-7 bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-5">
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-xl font-bold text-white">AI Health Risk Predictor</h2>
              <span className="text-xs bg-emerald-950 text-emerald-400 border border-emerald-800 px-2 py-0.5 rounded">
                Module 2 & 4
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Evaluates clinical vitals using the globally trained Federated Neural Model.
            </p>
          </div>

          <form onSubmit={handlePredict} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1">Patient Age</label>
                <input
                  type="number"
                  value={formData.age}
                  onChange={(e) => setFormData({ ...formData, age: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-cyan-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1">Resting Blood Pressure (mm Hg)</label>
                <input
                  type="number"
                  value={formData.resting_bp}
                  onChange={(e) => setFormData({ ...formData, resting_bp: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-cyan-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1">Serum Cholesterol (mg/dl)</label>
                <input
                  type="number"
                  value={formData.cholesterol}
                  onChange={(e) => setFormData({ ...formData, cholesterol: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-cyan-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1">Max Heart Rate</label>
                <input
                  type="number"
                  value={formData.max_hr}
                  onChange={(e) => setFormData({ ...formData, max_hr: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-cyan-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1">Fasting Blood Sugar &gt; 120 mg/dl</label>
                <select
                  value={formData.fbs}
                  onChange={(e) => setFormData({ ...formData, fbs: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-cyan-500 focus:outline-none"
                >
                  <option value="0">False (&le; 120 mg/dl)</option>
                  <option value="1">True (&gt; 120 mg/dl)</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1">Exercise Induced Angina</label>
                <select
                  value={formData.angina}
                  onChange={(e) => setFormData({ ...formData, angina: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white focus:border-cyan-500 focus:outline-none"
                >
                  <option value="0">No</option>
                  <option value="1">Yes</option>
                </select>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 bg-gradient-to-r from-cyan-600 to-emerald-600 hover:from-cyan-500 hover:to-emerald-500 text-white font-bold rounded-lg shadow-lg flex items-center justify-center gap-2 transition"
            >
              {loading ? 'Evaluating...' : '⚡ Run Federated AI Risk Inference'}
            </button>
          </form>
        </div>

        {/* Prediction Results */}
        <div className="lg:col-span-5 bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400">Clinical Risk Assessment</h3>
            <div className="mt-6 text-center">
              <div className="inline-flex items-center justify-center w-36 h-36 rounded-full border-4 border-cyan-500/30 bg-slate-950 shadow-inner">
                <span className={`text-4xl font-extrabold ${result?.risk_probability >= 65 ? 'text-rose-400' : (result?.risk_probability >= 40 ? 'text-amber-400' : 'text-cyan-400')}`}>
                  {result ? `${result.risk_probability}%` : '--%'}
                </span>
              </div>
              <div className={`mt-4 inline-block text-xs font-bold uppercase px-3 py-1 rounded-full ${result?.risk_probability >= 65 ? 'bg-rose-950 text-rose-400 border border-rose-800' : (result?.risk_probability >= 40 ? 'bg-amber-950 text-amber-400 border border-amber-800' : 'bg-slate-800 text-slate-300')}`}>
                {result ? result.risk_level : 'Awaiting Input'}
              </div>
            </div>
          </div>

          <div className="mt-6 p-4 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-400 space-y-2">
            <span className="font-semibold text-slate-300 block">System Clinical Notes:</span>
            <ul className="list-disc pl-4 space-y-1">
              {result?.recommendations ? (
                result.recommendations.map((rec, i) => <li key={i}>{rec}</li>)
              ) : (
                <>
                  <li>Input clinical parameters and click "Run Federated AI Risk Inference".</li>
                  <li>Federated model incorporates Differential Privacy to guarantee patient data locality.</li>
                </>
              )}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
