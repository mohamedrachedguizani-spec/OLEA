// src/components/TresorerieGraphiques.jsx
// Analyse graphique du module Trésorerie (onglet Reporting) :
//   1. recette vs dépense par période, avec filtrage par banque ;
//   2. solde de chaque banque jour par jour, depuis son ancre figée.
import React, { useMemo } from 'react';
import {
    CartesianGrid, Legend, Line, LineChart,
    ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';

// Couleurs alignées sur les variables du module (Tresorerie.css).
const COULEUR_RECETTE = '#1f9d55';
const COULEUR_DEPENSE = '#b7482b';

// Palette des courbes de solde : assez contrastée pour 8 banques tout en
// restant dans la charte OLEA (terracotta / ambre / anthracite).
const PALETTE_SOLDES = [
    '#B4482B', '#1f9d55', '#2f343a', '#E09127',
    '#6a727b', '#93371E', '#2b7a78', '#7a4ea0',
];

const fmtCourt = (n) => {
    const valeur = Number(n) || 0;
    const abs = Math.abs(valeur);
    if (abs >= 1e6) return `${(valeur / 1e6).toFixed(1)} M`;
    if (abs >= 1e3) return `${Math.round(valeur / 1e3)} k`;
    return String(Math.round(valeur));
};

const fmtMontant = (n) => new Intl.NumberFormat('fr-TN', {
    minimumFractionDigits: 3, maximumFractionDigits: 3,
}).format(Number(n) || 0);

const fmtDateCourte = (iso) => {
    if (!iso) return '';
    const [a, m, j] = String(iso).slice(0, 10).split('-');
    return `${j}/${m}`;
};

const LABEL_GRANULARITE = { jour: 'jour', semaine: 'semaine', mois: 'mois' };

/* ───────── Infobulle du graphique recette / dépense ───────── */
const TooltipFlux = ({ active, payload, label }) => {
    if (!active || !payload || !payload.length) return null;
    const recette = payload.find((p) => p.dataKey === 'recette')?.value || 0;
    const depense = payload.find((p) => p.dataKey === 'depense')?.value || 0;
    const net = recette - depense;
    return (
        <div className="tr-chart-tip">
            <div className="tr-chart-tip-title">{fmtDateCourte(label)}</div>
            <div><span className="tr-chart-swatch" style={{ background: COULEUR_RECETTE }} />Recette <strong>{fmtMontant(recette)}</strong></div>
            <div><span className="tr-chart-swatch" style={{ background: COULEUR_DEPENSE }} />Dépense <strong>{fmtMontant(depense)}</strong></div>
            <div className="tr-chart-tip-net">Net <strong className={net < 0 ? 'neg' : ''}>{fmtMontant(net)}</strong></div>
        </div>
    );
};

/* ───────── Infobulle de la courbe de solde ───────── */
const TooltipSoldes = ({ active, payload, label }) => {
    if (!active || !payload || !payload.length) return null;
    return (
        <div className="tr-chart-tip">
            <div className="tr-chart-tip-title">{fmtDateCourte(label)}</div>
            {payload.map((entree) => (
                <div key={entree.dataKey}>
                    <span className="tr-chart-swatch" style={{ background: entree.stroke || entree.color }} />
                    {entree.name} <strong className={Number(entree.value) < 0 ? 'neg' : ''}>{fmtMontant(entree.value)}</strong>
                </div>
            ))}
        </div>
    );
};

/* ───────── Carte de graphique (titre + contenu) ───────── */
const Carte = ({ titre, sousTitre, children, actions }) => (
    <div className="tr-card tr-chart-card">
        <div className="tr-chart-head">
            <div>
                <h4 className="tr-chart-title">{titre}</h4>
                {sousTitre && <p className="tr-chart-sub">{sousTitre}</p>}
            </div>
            {actions}
        </div>
        {children}
    </div>
);

const Vide = ({ children }) => <p className="tr-empty tr-chart-empty">{children}</p>;

/* ───────── Graphique 1 : recette vs dépense ───────── */
export const GraphiqueFlux = ({ flux, granularite, banque, nomBanque }) => {
    // Les séries par banque permettent de changer de banque sans recharger :
    // le backend renvoie le détail de chaque période.
    // Attention : une période sans mouvement pour la banque choisie n'a pas
    // d'entrée dans `par_banque`. Elle doit alors valoir 0 — et surtout PAS le
    // total toutes banques, qui ferait apparaître les opérations des autres.
    const donnees = useMemo(() => (flux || []).map((ligne) => {
        if (!banque) {
            return {
                periode: ligne.periode,
                recette: ligne.recette,
                depense: ligne.depense,
            };
        }
        const detail = ligne.par_banque?.[banque];
        return {
            periode: ligne.periode,
            recette: detail ? detail.recette : 0,
            depense: detail ? detail.depense : 0,
        };
    }), [flux, banque]);

    // Avec une banque sélectionnée, une période où elle n'a rien fait n'a pas à
    // occuper un point vide : on ne garde que les périodes où elle a bougé.
    const donneesAffichees = useMemo(
        () => (banque
            ? donnees.filter((ligne) => ligne.recette !== 0 || ligne.depense !== 0)
            : donnees),
        [donnees, banque],
    );

    const libelleBanque = banque ? (nomBanque(banque) || banque) : 'toutes banques';

    return (
        <Carte
            titre="Recette vs dépense"
            sousTitre={`Par ${LABEL_GRANULARITE[granularite] || 'jour'} · ${libelleBanque}`}
        >
            {donneesAffichees.length === 0 ? (
                <Vide>
                    {banque
                        ? `Aucun mouvement pour ${nomBanque(banque) || banque} sur la période sélectionnée.`
                        : 'Aucun mouvement sur la période sélectionnée.'}
                </Vide>
            ) : (
                <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={donneesAffichees} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" vertical={false} />
                        <XAxis dataKey="periode" tickFormatter={fmtDateCourte} fontSize={11} tick={{ fill: 'var(--text-muted)' }} />
                        <YAxis tickFormatter={fmtCourt} fontSize={11} tick={{ fill: 'var(--text-muted)' }} width={56} />
                        <Tooltip content={<TooltipFlux />} />
                        <Legend wrapperStyle={{ fontSize: 12 }} />
                        <Line
                            type="monotone"
                            dataKey="recette"
                            name="Recette (crédits)"
                            stroke={COULEUR_RECETTE}
                            strokeWidth={2.2}
                            dot={{ r: 2.5, fill: COULEUR_RECETTE, strokeWidth: 0 }}
                            activeDot={{ r: 5 }}
                        />
                        <Line
                            type="monotone"
                            dataKey="depense"
                            name="Dépense (débits)"
                            stroke={COULEUR_DEPENSE}
                            strokeWidth={2.2}
                            dot={{ r: 2.5, fill: COULEUR_DEPENSE, strokeWidth: 0 }}
                            activeDot={{ r: 5 }}
                        />
                    </LineChart>
                </ResponsiveContainer>
            )}
        </Carte>
    );
};

/* ───────── Graphique 2 : solde des banques ───────── */
export const GraphiqueSoldes = ({ soldes, soldeTotal, banquesSansSolde, nomBanque, banque }) => {
    // « Toutes banques » affiche UNE courbe de solde cumulé (calculée par le
    // backend) ; choisir une banque affiche sa courbe seule. On ne superpose
    // donc jamais plusieurs courbes, pour que le total reste lisible.
    const { donnees, code } = useMemo(() => {
        if (banque) {
            const points = soldes?.[banque] || [];
            return {
                code: banque,
                donnees: points.map((p) => ({
                    periode: String(p.date).slice(0, 10),
                    valeur: p.solde,
                })),
            };
        }
        return {
            code: null,
            donnees: (soldeTotal || []).map((p) => ({
                periode: String(p.date).slice(0, 10),
                valeur: p.solde,
            })),
        };
    }, [soldes, soldeTotal, banque]);

    const sansSolde = banquesSansSolde || [];
    const aucunPoint = donnees.length === 0;

    return (
        <Carte
            titre="Solde des banques"
            sousTitre={
                sansSolde.length
                    ? `Solde figé + mouvements · ${sansSolde.length} banque(s) sans solde de départ figé`
                    : (code ? `Solde figé + mouvements · ${nomBanque(code)}` : 'Solde cumulé de toutes les banques')
            }
        >
            {aucunPoint ? (
                <Vide>
                    {code
                        ? `Aucun solde calculable pour ${code} sur cette période.`
                        : `Aucun solde calculable${sansSolde.length ? ` (sans solde de départ figé : ${sansSolde.join(', ')})` : ''}.`}
                </Vide>
            ) : (
                <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={donnees} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                        <XAxis dataKey="periode" tickFormatter={fmtDateCourte} fontSize={11} tick={{ fill: 'var(--text-muted)' }} />
                        <YAxis tickFormatter={fmtCourt} fontSize={11} tick={{ fill: 'var(--text-muted)' }} width={56} />
                        <Tooltip content={<TooltipSoldes />} />
                        <Legend wrapperStyle={{ fontSize: 12 }} />
                        <Line
                            type="monotone"
                            dataKey="valeur"
                            name={code ? nomBanque(code) : 'Toutes banques'}
                            stroke={PALETTE_SOLDES[0]}
                            strokeWidth={2.2}
                            dot={false}
                            activeDot={{ r: 4 }}
                            connectNulls
                        />
                    </LineChart>
                </ResponsiveContainer>
            )}
        </Carte>
    );
};

/* ───────── Sélecteur de granularité ───────── */
export const ChoixGranularite = ({ valeur, onChange }) => (
    <div className="tr-seg tr-seg-sm" role="group" aria-label="Granularité des graphiques">
        {Object.entries(LABEL_GRANULARITE).map(([cle, libelle]) => (
            <button
                key={cle}
                type="button"
                className={valeur === cle ? 'on' : ''}
                onClick={() => onChange(cle)}
                aria-pressed={valeur === cle}
            >
                {libelle.charAt(0).toUpperCase() + libelle.slice(1)}
            </button>
        ))}
    </div>
);
