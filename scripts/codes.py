"""
Code systems and the reviewed crosswalk for "Unknown" allergy codes.
"""

SNOMED = "http://snomed.info/sct"
RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"

# Legacy code_system value -> FHIR system URI
CODE_SYSTEMS = {"SNOMED-CT": SNOMED, "RxNorm": RXNORM}

# FHIR system URI -> short name, for people reading the workbook
SYSTEM_NAMES = {SNOMED: "SNOMED-CT", RXNORM: "RxNorm"}

# Allergy codes whose legacy code_system is "Unknown"
CROSSWALK = {
    # SNOMED: description ends in a SNOMED semantic tag
    "609328004": SNOMED,        # Allergic disposition (finding)
    "84489001": SNOMED,         # Mold (organism)
    "264287008": SNOMED,        # Animal dander (substance)
    "256277009": SNOMED,        # Grass pollen (substance)
    "260147004": SNOMED,        # House dust mite (organism)
    "782576004": SNOMED,        # Tree pollen (substance)
    "735029006": SNOMED,        # Shellfish (substance)
    "412071004": SNOMED,        # Wheat (substance)
    "111088007": SNOMED,        # Latex (substance)
    "288328004": SNOMED,        # Bee venom (substance)
    "102263004": SNOMED,        # Eggs (edible) (substance)
    "442571000124108": SNOMED,  # Tree nut (substance)
    "762952008": SNOMED,        # Peanut (substance)
    "3718001": SNOMED,          # Cow's milk (substance)
    "735971005": SNOMED,        # Fish (substance)
    "256355007": SNOMED,        # Glycine max (substance), i.e. soybean
    # RxNorm: no semantic tag; RxNorm ingredient code for the named drug
    "1191": RXNORM,             # Aspirin
    "29046": RXNORM,            # Lisinopril
    "7984": RXNORM,             # Penicillin V
    "10831": RXNORM,            # Sulfamethoxazole / Trimethoprim
    "25037": RXNORM,            # cefdinir
    "5640": RXNORM,             # Ibuprofen
}


def code_system(legacy_system, code):
    """FHIR system URI: known system, else the crosswalk, else None (-> quarantine)."""
    return CODE_SYSTEMS.get(legacy_system) or CROSSWALK.get(code)