from database import db
from .router import router


def init_saisie_caisse_tables():
    """Initialise les tables de saisie caisse et migration sage (si absentes), ou y ajoute les nouvelles colonnes."""
    with db.get_cursor() as cursor:
        # Table ecritures_caisse
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ecritures_caisse (
                id INT AUTO_INCREMENT PRIMARY KEY,
                date_ecriture DATE NOT NULL,
                libelle_ecriture VARCHAR(255) NOT NULL,
                debit DOUBLE NOT NULL DEFAULT 0,
                credit DOUBLE NOT NULL DEFAULT 0,
                solde DOUBLE NOT NULL DEFAULT 0,
                est_migree BOOLEAN DEFAULT FALSE,
                compte_contrepartie VARCHAR(20) DEFAULT NULL,
                tiers VARCHAR(50) DEFAULT NULL,
                section_analytique VARCHAR(50) DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        # S'assurer que les nouvelles colonnes existent sur ecritures_caisse au cas où la table existait déjà sans elles
        cursor.execute("SHOW COLUMNS FROM ecritures_caisse")
        columns = [col['Field'] for col in cursor.fetchall()]
        if 'compte_contrepartie' not in columns:
            cursor.execute("ALTER TABLE ecritures_caisse ADD COLUMN compte_contrepartie VARCHAR(20) DEFAULT NULL")
        if 'tiers' not in columns:
            cursor.execute("ALTER TABLE ecritures_caisse ADD COLUMN tiers VARCHAR(50) DEFAULT NULL")
        if 'section_analytique' not in columns:
            cursor.execute("ALTER TABLE ecritures_caisse ADD COLUMN section_analytique VARCHAR(50) DEFAULT NULL")

        # Table libelles_frequents
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS libelles_frequents (
                libelle VARCHAR(255) PRIMARY KEY,
                compte_suggestion VARCHAR(20) DEFAULT NULL,
                tiers_suggestion VARCHAR(50) DEFAULT NULL,
                section_analytique_suggestion VARCHAR(50) DEFAULT NULL,
                usage_count INT DEFAULT 1
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)

        # S'assurer que les colonnes de suggestion existent dans libelles_frequents
        cursor.execute("SHOW COLUMNS FROM libelles_frequents")
        lf_columns = [col['Field'] for col in cursor.fetchall()]
        if 'compte_suggestion' not in lf_columns:
            cursor.execute("ALTER TABLE libelles_frequents ADD COLUMN compte_suggestion VARCHAR(20) DEFAULT NULL")
        if 'tiers_suggestion' not in lf_columns:
            cursor.execute("ALTER TABLE libelles_frequents ADD COLUMN tiers_suggestion VARCHAR(50) DEFAULT NULL")
        if 'section_analytique_suggestion' not in lf_columns:
            cursor.execute("ALTER TABLE libelles_frequents ADD COLUMN section_analytique_suggestion VARCHAR(50) DEFAULT NULL")

        # Table ecritures_sage
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ecritures_sage (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ecriture_caisse_id INT NOT NULL,
                societe VARCHAR(20) NOT NULL DEFAULT 'TN01',
                journal VARCHAR(10) NOT NULL DEFAULT 'CAI',
                date_compta DATE NOT NULL,
                compte VARCHAR(20) NOT NULL,
                tiers VARCHAR(50) DEFAULT NULL,
                montant_debit DOUBLE NOT NULL DEFAULT 0,
                montant_credit DOUBLE NOT NULL DEFAULT 0,
                section_analytique VARCHAR(50) DEFAULT NULL,
                numero_piece VARCHAR(50) NOT NULL,
                libelle_ecriture VARCHAR(255) NOT NULL,
                devise VARCHAR(10) NOT NULL DEFAULT 'TND',
                type_piece VARCHAR(10) NOT NULL DEFAULT 'OD',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ecriture_caisse_id) REFERENCES ecritures_caisse(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)


__all__ = ["router", "init_saisie_caisse_tables"]

