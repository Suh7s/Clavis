"""Simple hardcoded drug interaction checker for medication safety warnings."""

# Maps drug keyword -> set of conflicting drug keywords
INTERACTION_TABLE: dict[str, set[str]] = {
    "amoxicillin": {"warfarin", "methotrexate"},
    "warfarin": {"amoxicillin", "aspirin", "ibuprofen", "naproxen"},
    "aspirin": {"warfarin", "ibuprofen", "naproxen", "heparin"},
    "ibuprofen": {"warfarin", "aspirin", "lithium", "naproxen", "methotrexate"},
    "naproxen": {"warfarin", "aspirin", "ibuprofen", "lithium"},
    "metformin": {"contrast"},
    "lithium": {"ibuprofen", "naproxen", "furosemide", "hydrochlorothiazide"},
    "methotrexate": {"amoxicillin", "ibuprofen", "trimethoprim"},
    "trimethoprim": {"methotrexate"},
    "digoxin": {"amiodarone", "verapamil", "furosemide"},
    "amiodarone": {"digoxin", "warfarin", "simvastatin"},
    "simvastatin": {"amiodarone", "erythromycin", "clarithromycin"},
    "erythromycin": {"simvastatin", "theophylline"},
    "clarithromycin": {"simvastatin"},
    "theophylline": {"erythromycin", "ciprofloxacin"},
    "ciprofloxacin": {"theophylline", "warfarin"},
    "furosemide": {"lithium", "digoxin", "gentamicin"},
    "gentamicin": {"furosemide"},
    "heparin": {"aspirin"},
    "verapamil": {"digoxin"},
    "hydrochlorothiazide": {"lithium"},
}


def _extract_keywords(title: str) -> set[str]:
    """Extract lowercase words from title that might be drug names."""
    return {word.lower().rstrip(".,;:") for word in title.split() if len(word) > 2}


def check_interactions(
    new_title: str, existing_medication_titles: list[str]
) -> list[dict]:
    """Check if a new medication conflicts with existing active medications.

    Returns list of warning dicts: {new_drug, existing_drug, existing_title}.
    """
    new_keywords = _extract_keywords(new_title)
    warnings: list[dict] = []
    seen = set()

    for existing_title in existing_medication_titles:
        existing_keywords = _extract_keywords(existing_title)
        for nk in new_keywords:
            conflicts = INTERACTION_TABLE.get(nk, set())
            for ek in existing_keywords:
                if ek in conflicts:
                    pair = (nk, ek)
                    if pair not in seen:
                        seen.add(pair)
                        warnings.append({
                            "new_drug": nk,
                            "existing_drug": ek,
                            "existing_title": existing_title,
                            "message": f"Potential interaction: {nk} may interact with {ek} (in '{existing_title}')",
                        })
    return warnings
