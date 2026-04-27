// src/components/LibelleAutocomplete.jsx
import React, { useState, useEffect, useRef } from 'react';
import ApiService from '../services/api';

function LibelleAutocomplete({ value, onChange, onSelect, onEditingComplete }) {
    const [suggestions, setSuggestions] = useState([]);
    const [showSuggestions, setShowSuggestions] = useState(false);
    const containerRef = useRef(null);

    useEffect(() => {
        if (value.length > 2) {
            fetchSuggestions(value);
        } else {
            setSuggestions([]);
        }
    }, [value]);

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (containerRef.current && !containerRef.current.contains(event.target)) {
                setShowSuggestions(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const fetchSuggestions = async (search) => {
        try {
            const data = await ApiService.getLibellesSuggestions(search);
            setSuggestions(data);
            setShowSuggestions(true);
        } catch (error) {
            console.error('Erreur lors de la recherche:', error);
        }
    };

    const handleSelect = (libelle) => {
        onChange(libelle);
        onSelect(libelle);
        setShowSuggestions(false);
    };

    const handleBlur = () => {
        if (onEditingComplete) {
            onEditingComplete(value);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && onEditingComplete) {
            onEditingComplete(value);
        }
    };

    return (
        <div className="autocomplete-container" ref={containerRef}>
            <input
                type="text"
                value={value}
                onChange={(e) => onChange(e.target.value)}
                onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
                onBlur={handleBlur}
                onKeyDown={handleKeyDown}
                className="form-control"
                placeholder="Commencez à taper..."
            />
            
            {showSuggestions && suggestions.length > 0 && (
                <div className="autocomplete-suggestions fade-in">
                    {suggestions.map((suggestion, index) => (
                        <div
                            key={index}
                            className="autocomplete-item"
                            onClick={() => handleSelect(suggestion.libelle)}
                        >
                            {suggestion.libelle}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

export default LibelleAutocomplete;