import React, { useState, useMemo } from 'react';
import ApiService from '../services/api'; // Ajustez le chemin

const BUCKETS = [
  { key: 'non_echu', field: 'non_echu',  label: 'Non échu',   bar: 'bg-green-500',  txt: 'text-green-700' },
  { key: '1-30',     field: 'echu_30',   label: '1-30 j',     bar: 'bg-yellow-400', txt: 'text-yellow-700' },
  { key: '31-60',    field: 'echu_60',   label: '31-60 j',    bar: 'bg-orange-400', txt: 'text-orange-700' },
  { key: '61-90',    field: 'echu_90',   label: '61-90 j',    bar: 'bg-red-400',    txt: 'text-red-600' },
  { key: '+90',      field: 'echu_plus', label: '+90 j',      bar: 'bg-red-700',    txt: 'text-red-800' },
];

const fmt = (n) =>
  new Intl.NumberFormat('fr-TN', { minimumFractionDigits: 3, maximumFractionDigits: 3 }).format(n || 0);
const dash = (n) => (n > 0.0005 ? fmt(n) : '–');

const BalanceAgee = () => {
  const [file, setFile] = useState(null);
  const [dateReference, setDateReference] = useState(''); // vide = fin de période du PDF
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState(null);
  const [vue, setVue] = useState('debiteurs'); // debiteurs | crediteurs | tous
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(null);
  const [showWarn, setShowWarn] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!file) return setError('Veuillez sélectionner un fichier PDF.');
    setLoading(true); setError(''); setData(null); setOpen(null);
    try {
      setData(await ApiService.parseBalanceAgee(file, dateReference || null));
    } catch (err) {
      setError(err.message || 'Erreur lors du traitement.');
    } finally {
      setLoading(false);
    }
  };

  const clients = useMemo(() => {
    if (!data) return [];
    const q = search.trim().toLowerCase();
    return data.clients.filter((c) =>
      (vue === 'tous' || (vue === 'debiteurs' ? c.total_solde > 0 : c.total_solde < 0)) &&
      (!q || c.nom.toLowerCase().includes(q) || c.code.toLowerCase().includes(q)));
  }, [data, vue, search]);

  const totalEchu = data ? BUCKETS.slice(1).reduce((s, b) => s + (data.totaux_buckets?.[b.key] || 0), 0) : 0;
  const creances = data?.total_debiteur || 0;
  const pctEchu = creances > 0 ? (totalEchu / creances) * 100 : 0;

  const exportCsv = () => {
    const head = ['Code', 'Client', 'Solde', ...BUCKETS.map((b) => b.label), 'Avance'];
    const rows = clients.map((c) => [c.code, c.nom, c.total_solde, ...BUCKETS.map((b) => c[b.field]), c.credit_non_affecte]);
    const csv = [head, ...rows].map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(';')).join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' }));
    a.download = `balance_agee_${data.date_reference}.csv`;
    a.click();
  };

  const Kpi = ({ label, value, sub, tone = 'text-gray-900' }) => (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      <div className="text-xs uppercase tracking-wide text-gray-500">{label}</div>
      <div className={`text-xl font-bold mt-1 ${tone}`}>{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </div>
  );

  return (
    <div className="p-6 max-w-7xl mx-auto bg-gray-50 min-h-screen space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Balance âgée clients</h1>
        <p className="text-sm text-gray-500">Import du Grand Livre auxiliaire Sage (PDF) – règlements imputés sur les factures les plus anciennes (FIFO).</p>
      </div>

      <form onSubmit={submit} className="bg-white p-5 rounded-lg shadow-sm border border-gray-200 grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Arrêtée au <span className="text-gray-400 font-normal">(optionnel)</span></label>
          <input type="date" value={dateReference} onChange={(e) => setDateReference(e.target.value)}
            className="w-full border border-gray-300 rounded-md p-2" />
          <p className="text-xs text-gray-400 mt-1">Vide = fin de période du PDF</p>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Grand Livre (PDF)</label>
          <input type="file" accept="application/pdf" required
            onChange={(e) => { setFile(e.target.files[0]); setError(''); }}
            className="w-full border border-gray-300 rounded-md p-2 file:mr-3 file:py-1 file:px-3 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700" />
        </div>
        <button type="submit" disabled={loading}
          className="bg-blue-600 text-white font-medium py-2 px-4 rounded-md hover:bg-blue-700 disabled:bg-blue-300">
          {loading ? 'Traitement…' : 'Générer la balance âgée'}
        </button>
        {error && <div className="md:col-span-3 p-3 bg-red-50 text-red-700 border border-red-200 rounded-md text-sm">{error}</div>}
      </form>

      {data && (
        <>
          {data.avertissements?.length > 0 && (
            <div className="bg-amber-50 border border-amber-300 rounded-md text-sm text-amber-900">
              <button type="button" className="w-full text-left p-3 font-semibold" onClick={() => setShowWarn(!showWarn)}>
                ⚠ {data.avertissements.length} point(s) d'attention {showWarn ? '▲' : '▼'}
              </button>
              {showWarn && <ul className="list-disc ml-8 pb-3 pr-4 space-y-1">{data.avertissements.map((a, i) => <li key={i}>{a}</li>)}</ul>}
            </div>
          )}

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <Kpi label="Créances clients" value={fmt(creances)} sub={`Situation au ${new Date(data.date_reference).toLocaleDateString('fr-FR')}`} tone="text-blue-800" />
            <Kpi label="Dont échu" value={fmt(totalEchu)} sub={`${pctEchu.toFixed(0)} % des créances`} tone="text-red-700" />
            <Kpi label="Avances / avoirs" value={fmt(data.total_crediteur)} sub="À affecter ou rembourser" tone="text-purple-700" />
            <Kpi label="Solde net Sage" value={fmt(data.total_general)} sub={`${data.nb_clients} clients non soldés`} />
          </div>

          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-5">
            <h2 className="font-semibold text-gray-800 mb-3">Ancienneté des créances</h2>
            {creances > 0 ? (
              <>
                <div className="flex h-5 rounded overflow-hidden bg-gray-100">
                  {BUCKETS.map((b) => {
                    const v = data.totaux_buckets?.[b.key] || 0;
                    return v > 0 ? <div key={b.key} className={b.bar} style={{ width: `${(v / creances) * 100}%` }} title={`${b.label} : ${fmt(v)}`} /> : null;
                  })}
                </div>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-4">
                  {BUCKETS.map((b) => {
                    const v = data.totaux_buckets?.[b.key] || 0;
                    return (
                      <div key={b.key} className="flex items-start gap-2">
                        <span className={`mt-1 w-3 h-3 rounded-sm ${b.bar}`} />
                        <div>
                          <div className="text-xs text-gray-500">{b.label}</div>
                          <div className={`font-semibold ${b.txt}`}>{fmt(v)}</div>
                          <div className="text-xs text-gray-400">{((v / creances) * 100).toFixed(0)} %</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            ) : <p className="text-sm text-gray-500">Aucune créance ouverte.</p>}
          </div>

          <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
            <div className="p-4 border-b border-gray-200 flex flex-wrap gap-3 items-center justify-between">
              <div className="flex rounded-md overflow-hidden border border-gray-300 text-sm">
                {[['debiteurs', 'Débiteurs'], ['crediteurs', 'Créditeurs'], ['tous', 'Tous']].map(([k, l]) => (
                  <button key={k} type="button" onClick={() => setVue(k)}
                    className={`px-3 py-1.5 ${vue === k ? 'bg-blue-600 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'}`}>{l}</button>
                ))}
              </div>
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Rechercher un client…"
                className="border border-gray-300 rounded-md px-3 py-1.5 text-sm flex-1 min-w-[200px] max-w-xs" />
              <div className="flex items-center gap-3 text-sm text-gray-500">
                {clients.length} client(s)
                <button type="button" onClick={exportCsv} className="px-3 py-1.5 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50">Exporter CSV</button>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                  <tr>
                    <th className="px-4 py-3 text-left">Client</th>
                    <th className="px-4 py-3 text-right">Solde</th>
                    {BUCKETS.map((b) => <th key={b.key} className={`px-4 py-3 text-right ${b.txt}`}>{b.label}</th>)}
                    <th className="px-4 py-3 text-right text-purple-700">Avance</th>
                    <th className="w-8" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {clients.map((c) => (
                    <React.Fragment key={c.code}>
                      <tr className="hover:bg-gray-50 cursor-pointer" onClick={() => setOpen(open === c.code ? null : c.code)}>
                        <td className="px-4 py-3">
                          <div className="font-medium text-gray-900">{c.nom}</div>
                          <div className="text-xs text-gray-400">{c.code}</div>
                        </td>
                        <td className={`px-4 py-3 text-right font-bold whitespace-nowrap ${c.total_solde < 0 ? 'text-purple-700' : 'text-gray-900'}`}>{fmt(c.total_solde)}</td>
                        {BUCKETS.map((b) => <td key={b.key} className={`px-4 py-3 text-right whitespace-nowrap ${b.txt}`}>{dash(c[b.field])}</td>)}
                        <td className="px-4 py-3 text-right whitespace-nowrap text-purple-700">{dash(c.credit_non_affecte)}</td>
                        <td className="text-gray-400">{open === c.code ? '▲' : '▼'}</td>
                      </tr>
                      {open === c.code && (
                        <tr className="bg-gray-50">
                          <td colSpan={BUCKETS.length + 4} className="p-4">
                            <div className="bg-white border rounded-md overflow-x-auto">
                              <table className="min-w-full text-xs">
                                <thead className="bg-gray-100 text-gray-500">
                                  <tr>
                                    <th className="px-3 py-2 text-left">Date</th>
                                    <th className="px-3 py-2 text-left">Libellé</th>
                                    <th className="px-3 py-2 text-right">Débit</th>
                                    <th className="px-3 py-2 text-right">Crédit</th>
                                    <th className="px-3 py-2 text-right">Solde</th>
                                    <th className="px-3 py-2 text-right">Reste dû</th>
                                    <th className="px-3 py-2 text-right">Retard</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-100">
                                  {c.lignes.map((l, i) => (
                                    <tr key={i} className={l.reste_du > 0 ? 'bg-red-50/40' : ''}>
                                      <td className="px-3 py-1.5 whitespace-nowrap">{l.date}</td>
                                      <td className="px-3 py-1.5 max-w-xs truncate" title={l.libelle}>{l.libelle}</td>
                                      <td className="px-3 py-1.5 text-right">{dash(l.debit)}</td>
                                      <td className="px-3 py-1.5 text-right">{dash(l.credit)}</td>
                                      <td className="px-3 py-1.5 text-right font-medium">{fmt(l.solde)}</td>
                                      <td className="px-3 py-1.5 text-right font-semibold">{dash(l.reste_du)}</td>
                                      <td className="px-3 py-1.5 text-right">{l.reste_du > 0 ? (l.jours_retard > 0 ? `+${l.jours_retard} j` : 'À jour') : ''}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                  {clients.length === 0 && (
                    <tr><td colSpan={BUCKETS.length + 4} className="p-8 text-center text-gray-400">Aucun client.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default BalanceAgee;
