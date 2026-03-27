// src/components/sage-bfc/SageBfcLignes.js
import React, { useState, useMemo } from 'react';

// Normalisation pour les anciennes données stockées avant la migration
const AGREGAT_ALIASES = {
    'Brand Fees': 'Honoraires & Sous-traitance',
    'Management Fees': 'Honoraires & Sous-traitance'
};
const CATEGORIE_ALIASES = {
    'COÛTS INTERCO': 'COÛTS'
};

function normalizeLigne(l) {
    const agregat = AGREGAT_ALIASES[l.agregat_bfc] || l.agregat_bfc;
    const categorie = CATEGORIE_ALIASES[l.categorie] || l.categorie;
    if (agregat === l.agregat_bfc && categorie === l.categorie) return l;
    return { ...l, agregat_bfc: agregat, categorie };
}

function SageBfcLignes({ lignes, sortedMonths, formatMonthShort }) {
    const [searchTerm, setSearchTerm] = useState('');
    const [filterType, setFilterType] = useState('all'); // all | Produit | Charge
    const [filterCategorie, setFilterCategorie] = useState('all');
    const [filterAgregat, setFilterAgregat] = useState('all');
    const [filterMois, setFilterMois] = useState('all');
    const [sortField, setSortField] = useState('montant_absolu');
    const [sortDir, setSortDir] = useState('desc');
    const [currentPage, setCurrentPage] = useState(1);
    const pageSize = 25;

    // Normaliser les lignes (pour compatibilité avec anciennes données en base)
    const normalizedLignes = useMemo(() => lignes.map(normalizeLigne), [lignes]);

    // Extraire les catégories et agrégats uniques
    const categories = useMemo(() => {
        return [...new Set(normalizedLignes.map(l => l.categorie))].sort();
    }, [normalizedLignes]);

    const agregats = useMemo(() => {
        return [...new Set(normalizedLignes.map(l => l.agregat_bfc))].sort();
    }, [normalizedLignes]);

    // Filtrage et tri
    const filteredLignes = useMemo(() => {
        let result = [...normalizedLignes];

        // Filtre mois
        if (filterMois !== 'all') {
            result = result.filter(l => l.mois === filterMois);
        }

        // Filtre texte
        if (searchTerm) {
            const search = searchTerm.toLowerCase();
            result = result.filter(l =>
                l.code_sage.toLowerCase().includes(search) ||
                l.libelle_sage.toLowerCase().includes(search) ||
                l.agregat_bfc.toLowerCase().includes(search)
            );
        }

        // Filtre type
        if (filterType !== 'all') {
            result = result.filter(l => l.type_ligne === filterType);
        }

        // Filtre catégorie
        if (filterCategorie !== 'all') {
            result = result.filter(l => l.categorie === filterCategorie);
        }

        // Filtre agrégat
        if (filterAgregat !== 'all') {
            result = result.filter(l => l.agregat_bfc === filterAgregat);
        }

        // Tri
        result.sort((a, b) => {
            let valA = a[sortField];
            let valB = b[sortField];
            if (typeof valA === 'string') valA = valA.toLowerCase();
            if (typeof valB === 'string') valB = valB.toLowerCase();
            if (valA < valB) return sortDir === 'asc' ? -1 : 1;
            if (valA > valB) return sortDir === 'asc' ? 1 : -1;
            return 0;
        });

        return result;
    }, [lignes, searchTerm, filterType, filterCategorie, filterAgregat, filterMois, sortField, sortDir]);

    // Pagination
    const totalPages = Math.ceil(filteredLignes.length / pageSize);
    const paginatedLignes = filteredLignes.slice(
        (currentPage - 1) * pageSize,
        currentPage * pageSize
    );

    // Totaux filtrés
    const totaux = useMemo(() => {
        const totalProduits = filteredLignes.filter(l => l.type_ligne === 'Produit').reduce((s, l) => s + parseFloat(l.montant), 0);
        const totalCharges = filteredLignes.filter(l => l.type_ligne === 'Charge').reduce((s, l) => s + parseFloat(l.montant_absolu), 0);
        return { produits: totalProduits, charges: totalCharges };
    }, [filteredLignes]);

    const fmt = (val) => {
        return new Intl.NumberFormat('fr-TN', {
            minimumFractionDigits: 3,
            maximumFractionDigits: 3
        }).format(val);
    };

    const handleSort = (field) => {
        if (sortField === field) {
            setSortDir(prev => prev === 'asc' ? 'desc' : 'asc');
        } else {
            setSortField(field);
            setSortDir('desc');
        }
    };

    const SortIcon = ({ field }) => {
        if (sortField !== field) return <span className="sort-icon inactive">⇅</span>;
        return <span className="sort-icon active">{sortDir === 'asc' ? '↑' : '↓'}</span>;
    };

    const resetFilters = () => {
        setSearchTerm('');
        setFilterType('all');
        setFilterCategorie('all');
        setFilterAgregat('all');
        setFilterMois('all');
        setCurrentPage(1);
    };

    const hasActiveFilters = searchTerm || filterType !== 'all' || filterCategorie !== 'all' || filterAgregat !== 'all' || filterMois !== 'all';

    return (
        <div className="sage-lignes-container">
            {/* ─── Mini KPI Strip ─── */}
            <div className="lignes-kpi-strip">
                <div className="lignes-kpi lignes-kpi-total">
                    <div className="lignes-kpi-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                            <polyline points="14 2 14 8 20 8"/>
                            <line x1="16" y1="13" x2="8" y2="13"/>
                            <line x1="16" y1="17" x2="8" y2="17"/>
                        </svg>
                    </div>
                    <div className="lignes-kpi-content">
                        <span className="lignes-kpi-value">{filteredLignes.length}</span>
                        <span className="lignes-kpi-label">
                            Ligne{filteredLignes.length > 1 ? 's' : ''}
                            {hasActiveFilters && <span className="lignes-kpi-sub"> / {lignes.length}</span>}
                        </span>
                    </div>
                </div>
                <div className="lignes-kpi lignes-kpi-produits">
                    <div className="lignes-kpi-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>
                            <polyline points="17 6 23 6 23 12"/>
                        </svg>
                    </div>
                    <div className="lignes-kpi-content">
                        <span className="lignes-kpi-value">{fmt(totaux.produits)}</span>
                        <span className="lignes-kpi-label">Produits</span>
                    </div>
                </div>
                <div className="lignes-kpi lignes-kpi-charges">
                    <div className="lignes-kpi-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <polyline points="23 18 13.5 8.5 8.5 13.5 1 6"/>
                            <polyline points="17 18 23 18 23 12"/>
                        </svg>
                    </div>
                    <div className="lignes-kpi-content">
                        <span className="lignes-kpi-value">{fmt(totaux.charges)}</span>
                        <span className="lignes-kpi-label">Charges</span>
                    </div>
                </div>
            </div>

            {/* ─── Barre de filtres ─── */}
            <div className="lignes-filters">
                <div className="filter-search">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="11" cy="11" r="8"/>
                        <line x1="21" y1="21" x2="16.65" y2="16.65"/>
                    </svg>
                    <input
                        type="text"
                        placeholder="Rechercher par code, libellé ou agrégat..."
                        value={searchTerm}
                        onChange={(e) => { setSearchTerm(e.target.value); setCurrentPage(1); }}
                        className="filter-input"
                    />
                    {searchTerm && (
                        <button className="filter-clear-btn" onClick={() => { setSearchTerm(''); setCurrentPage(1); }}>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <line x1="18" y1="6" x2="6" y2="18"/>
                                <line x1="6" y1="6" x2="18" y2="18"/>
                            </svg>
                        </button>
                    )}
                </div>

                <div className="filter-selects">
                    {sortedMonths && sortedMonths.length > 1 && (
                        <select
                            value={filterMois}
                            onChange={(e) => { setFilterMois(e.target.value); setCurrentPage(1); }}
                            className="filter-select"
                        >
                            <option value="all">Tous les mois</option>
                            {sortedMonths.map(m => (
                                <option key={m} value={m}>{formatMonthShort ? formatMonthShort(m) : m}</option>
                            ))}
                        </select>
                    )}

                    <select
                        value={filterType}
                        onChange={(e) => { setFilterType(e.target.value); setCurrentPage(1); }}
                        className="filter-select"
                    >
                        <option value="all">Tous types</option>
                        <option value="Produit">Produits</option>
                        <option value="Charge">Charges</option>
                    </select>

                    <select
                        value={filterCategorie}
                        onChange={(e) => { setFilterCategorie(e.target.value); setCurrentPage(1); }}
                        className="filter-select"
                    >
                        <option value="all">Toutes catégories</option>
                        {categories.map(cat => (
                            <option key={cat} value={cat}>{cat}</option>
                        ))}
                    </select>

                    <select
                        value={filterAgregat}
                        onChange={(e) => { setFilterAgregat(e.target.value); setCurrentPage(1); }}
                        className="filter-select"
                    >
                        <option value="all">Tous agrégats</option>
                        {agregats.map(ag => (
                            <option key={ag} value={ag}>{ag}</option>
                        ))}
                    </select>

                    {hasActiveFilters && (
                        <button className="filter-reset" onClick={resetFilters}>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <polyline points="1 4 1 10 7 10"/>
                                <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
                            </svg>
                            Réinitialiser
                        </button>
                    )}
                </div>
            </div>

            {/* ─── Table ─── */}
            <div className="lignes-table-wrapper">
                <table className="lignes-table">
                    <thead>
                        <tr>
                            {sortedMonths && sortedMonths.length > 1 && (
                                <th className="th-center">Mois</th>
                            )}
                            <th onClick={() => handleSort('code_sage')} className="sortable">
                                Code SAGE <SortIcon field="code_sage" />
                            </th>
                            <th onClick={() => handleSort('libelle_sage')} className="sortable">
                                Libellé <SortIcon field="libelle_sage" />
                            </th>
                            <th onClick={() => handleSort('agregat_bfc')} className="sortable">
                                Agrégat BFC <SortIcon field="agregat_bfc" />
                            </th>
                            <th onClick={() => handleSort('categorie')} className="sortable">
                                Catégorie <SortIcon field="categorie" />
                            </th>
                            <th className="th-center">Type</th>
                            <th onClick={() => handleSort('montant')} className="sortable th-right">
                                Montant <SortIcon field="montant" />
                            </th>
                            <th onClick={() => handleSort('montant_absolu')} className="sortable th-right">
                                |Montant| <SortIcon field="montant_absolu" />
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        {paginatedLignes.map((ligne, idx) => (
                            <tr key={idx} className={`${ligne.is_principal ? 'row-principal' : ''}`}>
                                {sortedMonths && sortedMonths.length > 1 && (
                                    <td className="cell-center">
                                        <span className="month-mini-badge">
                                            {formatMonthShort ? formatMonthShort(ligne.mois) : ligne.mois}
                                        </span>
                                    </td>
                                )}
                                <td className="cell-code">{ligne.code_sage}</td>
                                <td className="cell-libelle" title={ligne.libelle_sage}>
                                    {ligne.libelle_sage}
                                </td>
                                <td>
                                    <span className="agregat-badge">{ligne.agregat_bfc}</span>
                                </td>
                                <td>
                                    <span className="categorie-tag">{ligne.categorie}</span>
                                </td>
                                <td className="cell-center">
                                    <span className={`type-badge ${ligne.type_ligne === 'Produit' ? 'type-produit' : 'type-charge'}`}>
                                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{width: '10px', height: '10px'}}>
                                            {ligne.type_ligne === 'Produit'
                                                ? <polyline points="18 15 12 9 6 15"/>
                                                : <polyline points="6 9 12 15 18 9"/>
                                            }
                                        </svg>
                                        {ligne.type_ligne}
                                    </span>
                                </td>
                                <td className={`cell-montant ${parseFloat(ligne.montant) < 0 ? 'negative' : ''}`}>
                                    {fmt(ligne.montant)}
                                </td>
                                <td className="cell-montant">
                                    {fmt(ligne.montant_absolu)}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>

                {filteredLignes.length === 0 && (
                    <div className="lignes-empty">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <circle cx="11" cy="11" r="8"/>
                            <line x1="21" y1="21" x2="16.65" y2="16.65"/>
                            <line x1="8" y1="11" x2="14" y2="11"/>
                        </svg>
                        <span>Aucune ligne ne correspond aux filtres</span>
                        {hasActiveFilters && (
                            <button className="filter-reset" onClick={resetFilters} style={{marginTop: '0.5rem'}}>
                                Réinitialiser les filtres
                            </button>
                        )}
                    </div>
                )}
            </div>

            {/* ─── Pagination ─── */}
            {totalPages > 1 && (
                <div className="lignes-pagination">
                    <button
                        className="pagination-btn"
                        disabled={currentPage === 1}
                        onClick={() => setCurrentPage(1)}
                        title="Première page"
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{width: '14px', height: '14px'}}>
                            <polyline points="11 17 6 12 11 7"/>
                            <polyline points="18 17 13 12 18 7"/>
                        </svg>
                    </button>
                    <button
                        className="pagination-btn"
                        disabled={currentPage === 1}
                        onClick={() => setCurrentPage(p => p - 1)}
                        title="Page précédente"
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{width: '14px', height: '14px'}}>
                            <polyline points="15 18 9 12 15 6"/>
                        </svg>
                    </button>

                    <div className="pagination-pages">
                        {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                            let page;
                            if (totalPages <= 5) {
                                page = i + 1;
                            } else if (currentPage <= 3) {
                                page = i + 1;
                            } else if (currentPage >= totalPages - 2) {
                                page = totalPages - 4 + i;
                            } else {
                                page = currentPage - 2 + i;
                            }
                            return (
                                <button
                                    key={page}
                                    className={`pagination-page ${currentPage === page ? 'active' : ''}`}
                                    onClick={() => setCurrentPage(page)}
                                >
                                    {page}
                                </button>
                            );
                        })}
                    </div>

                    <button
                        className="pagination-btn"
                        disabled={currentPage === totalPages}
                        onClick={() => setCurrentPage(p => p + 1)}
                        title="Page suivante"
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{width: '14px', height: '14px'}}>
                            <polyline points="9 18 15 12 9 6"/>
                        </svg>
                    </button>
                    <button
                        className="pagination-btn"
                        disabled={currentPage === totalPages}
                        onClick={() => setCurrentPage(totalPages)}
                        title="Dernière page"
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{width: '14px', height: '14px'}}>
                            <polyline points="13 17 18 12 13 7"/>
                            <polyline points="6 17 11 12 6 7"/>
                        </svg>
                    </button>
                </div>
            )}
        </div>
    );
}

export default SageBfcLignes;
