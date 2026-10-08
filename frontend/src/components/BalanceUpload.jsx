// src/components/BalanceUpload.jsx
// En-tête + étape d'import communs aux balances âgées (clients / fournisseurs),
// même charte que SAGE → BFC (classes de ./sage-bfc/SageBfcParser.css).
import React, { useRef, useState } from 'react';
import ReactDOM from 'react-dom';
import './sage-bfc/SageBfcParser.css';

const MAX_SIZE = 20 * 1024 * 1024; // 20 Mo (limite du backend)

const TEXTES = {
  clients: {
    titre: 'Balance âgée clients',
    sous: "Analyse de l'ancienneté des créances à partir du Grand Livre auxiliaire Sage",
    drop: 'Glissez-déposez le Grand Livre auxiliaire clients',
    bouton: 'Générer la balance âgée clients',
    chargement: "Extraction des écritures, imputation des règlements et calcul de l'ancienneté des créances.",
  },
  fournisseurs: {
    titre: 'Balance âgée fournisseurs',
    sous: "Analyse de l'ancienneté des dettes à partir du Grand Livre auxiliaire fournisseurs Sage",
    drop: 'Glissez-déposez le Grand Livre auxiliaire fournisseurs',
    bouton: 'Générer la balance âgée fournisseurs',
    chargement: "Extraction des écritures, imputation des paiements et calcul de l'ancienneté des dettes.",
  },
};

const Svg = ({ children }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">{children}</svg>
);

const IconTitre = ({ variant }) => (variant === 'fournisseurs' ? (
  <Svg><path d="M12 22L2 17l10-5 10 5-10 5z" /><path d="M2 12l10-5 10 5" /><path d="M2 7l10-5 10 5" /></Svg>
) : (
  <Svg><path d="M12 2L2 7l10 5 10-5-10-5z" /><path d="M2 17l10 5 10-5" /><path d="M2 12l10 5 10-5" /></Svg>
));

const formatTaille = (n) => (n < 1024 * 1024 ? `${(n / 1024).toFixed(0)} Ko` : `${(n / 1024 / 1024).toFixed(2)} Mo`);

/* ───────── En-tête + navigation Import / Analyse ───────── */
// count : nombre de balances générées (petit badge sur « Analyse »). canList : droit de consulter l'historique.
export const BalanceHeader = ({ variant = 'clients', step, setStep, count = null, canList = true, hasData = false }) => {
  const t = TEXTES[variant];
  const showAnalyse = canList || hasData;
  return (
    <div className="sage-bfc-header">
      <div>
        <h2 className="sage-bfc-title">
          <span className="sage-bfc-title-icon"><IconTitre variant={variant} /></span>
          {t.titre}
        </h2>
        <p className="sage-bfc-subtitle">{t.sous}</p>
      </div>
      <div className="sage-bfc-nav">
        <button type="button" className={`sage-nav-btn ${step === 'upload' ? 'active' : ''}`} onClick={() => setStep('upload')}>
          <Svg><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></Svg>
          Import
        </button>
        {showAnalyse && (
          <button type="button" className={`sage-nav-btn ba-nav-has-count ${step === 'list' || step === 'detail' ? 'active' : ''}`}
            onClick={() => setStep(canList ? 'list' : 'detail')}>
            <Svg><line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" /></Svg>
            Analyse
            {canList && count !== null && <span className="ba-nav-count" title={`${count} balance(s) générée(s)`}>{count}</span>}
          </button>
        )}
      </div>
    </div>
  );
};

/* ───────── Étape 1 : import du PDF ───────── */
const BalanceUpload = ({
  variant = 'clients', file, setFile, dateReference, setDateReference,
  loading, error, setError, onSubmit, onShowHistory, canGenerate = true,
}) => {
  const t = TEXTES[variant];
  const inputRef = useRef(null);
  const [drag, setDrag] = useState(false);

  const choisir = (f) => {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith('.pdf')) return setError('Seuls les fichiers PDF sont acceptés.');
    if (f.size > MAX_SIZE) return setError('Fichier trop volumineux (max 20 Mo).');
    setError('');
    setFile(f);
  };
  const retirer = (e) => {
    e.stopPropagation();
    setFile(null);
    setError('');
    if (inputRef.current) inputRef.current.value = '';
  };
  const ouvrir = () => { if (!file && inputRef.current) inputRef.current.click(); };

  // Même encart que SAGE → BFC pour un utilisateur qui peut seulement consulter
  if (!canGenerate) {
    return (
      <div className="sage-upload-section">
        <div className="sage-bfc-error">
          <div><strong>Consultation uniquement</strong><p>Vous n'avez pas l'autorisation d'importer une balance.</p></div>
        </div>
        {onShowHistory && (
          <button type="button" className="btn btn-primary" style={{ width: '100%' }} onClick={onShowHistory}>
            Consulter les balances générées
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="sage-upload-section">
      {loading && ReactDOM.createPortal(
        <div className="sage-close-overlay" role="status" aria-live="polite" aria-label="Analyse en cours">
          <div className="sage-close-overlay-card">
            <div className="sage-close-spinner" />
            <h4>Analyse du grand livre en cours...</h4>
            <p>{t.chargement}</p>
          </div>
        </div>,
        document.body
      )}
      <div
        className={`sage-dropzone ${drag ? 'drag-active' : ''} ${file ? 'has-file' : ''} ${error ? 'has-error' : ''}`}
        role="button" tabIndex={0}
        onClick={ouvrir}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); ouvrir(); } }}
        onDragEnter={(e) => { e.preventDefault(); setDrag(true); }}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={(e) => { e.preventDefault(); setDrag(false); }}
        onDrop={(e) => { e.preventDefault(); setDrag(false); choisir(e.dataTransfer.files && e.dataTransfer.files[0]); }}
      >
        <input ref={inputRef} type="file" accept="application/pdf,.pdf" className="sage-file-input"
          onChange={(e) => choisir(e.target.files && e.target.files[0])} />
        {!file ? (
          <div className="dropzone-content">
            <div className={`dropzone-icon ${drag ? 'bounce' : ''}`}>
 <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="2">
                                <rect x="8" y="8" width="48" height="48" rx="8" strokeDasharray="6 3" />
                                <path d="M32 22v20M22 32h20" strokeWidth="3" strokeLinecap="round" />
                            </svg>             </div>
            <p className="dropzone-title">{t.drop}</p>
            <p className="dropzone-hint">ou <span className="dropzone-link">parcourez</span> vos fichiers</p>
            <div className="dropzone-formats">
              <span className="format-tag">.PDF</span>
              <span className="format-size">Max 20 Mo</span>
            </div>
          </div>
        ) : (
          <div className="dropzone-file-preview">
            <span className="file-preview-icon">📄</span>
            <div className="file-preview-info">
              <span className="file-preview-name">{file.name}</span>
              <span className="file-preview-size">{formatTaille(file.size)}</span>
            </div>
            <button type="button" className="file-preview-remove" onClick={retirer} title="Retirer le fichier" aria-label="Retirer le fichier">
              <Svg><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></Svg>
            </button>
          </div>
        )}
      </div>

      {error && (
        <div className="dropzone-error">
          <Svg><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></Svg>
          <span>{error}</span>
        </div>
      )}

      <div className="sage-upload-periode">
        <div className="periode-group">
          <label className="periode-label" htmlFor={`ba-date-${variant}`}>
            <Svg><rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" /></Svg>
            Situation arrêtée au
          </label>
          <input id={`ba-date-${variant}`} type="date" className="periode-input" value={dateReference}
            onChange={(e) => setDateReference(e.target.value)} />
          <span className="dropzone-hint">Optionnel · vide = fin de période imprimée sur le PDF</span>
        </div>
      </div>

      <button type="button" className="btn-sage-parse" disabled={!file || loading} onClick={onSubmit}>
        {loading ? (<><span className="spinner" />Analyse en cours…</>) : (
          <><Svg><line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" /></Svg>{t.bouton}</>
        )}
      </button>

      {!loading && onShowHistory && (
        <button type="button" className="btn btn-secondary" style={{ marginTop: '0.75rem', width: '100%' }} onClick={onShowHistory}>
          Consulter les balances générées
        </button>
      )}
    </div>
  );
};

export default BalanceUpload;
