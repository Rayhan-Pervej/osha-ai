REGULATORY_PARTS = {
    "1910": "29 CFR Part 1910 (General Industry Standards)",
    "1926": "29 CFR Part 1926 (Construction Standards)",
    "1915": "29 CFR Part 1915 (Shipyard Employment)",
    "1917": "29 CFR Part 1917 (Marine Terminals)",
    "1918": "29 CFR Part 1918 (Longshoring)",
    "1919": "29 CFR Part 1919 (Gear Certification)",
    "1928": "29 CFR Part 1928 (Agriculture)",
    "1902": "29 CFR Part 1902 (State Plans — Approval and Certification)",
    "1903": "29 CFR Part 1903 (OSHA Inspections and Citations)",
    "1904": "29 CFR Part 1904 (Injury and Illness Recording and Reporting)",
    "1905": "29 CFR Part 1905 (Variances from Standards)",
    "1908": "29 CFR Part 1908 (Consultation Agreements)",
    "1911": "29 CFR Part 1911 (Rules of Procedure for Rulemaking)",
    "1912": "29 CFR Part 1912 (Advisory Committees on Standards)",
    "1913": "29 CFR Part 1913 (OSHA Records and Reports)",
    "1920": "29 CFR Part 1920 (Procedure for Variations)",
    "1921": "29 CFR Part 1921 (Rules of Practice — Variances)",
    "1922": "29 CFR Part 1922 (Investigational Hearings)",
    "1924": "29 CFR Part 1924 (Safety Standards — Federal Service Contracts)",
    "1925": "29 CFR Part 1925 (Safety Standards — Federal Supply Contracts)",
    "1949": "29 CFR Part 1949 (Office of Training and Education)",
    "1952": "29 CFR Part 1952 (Approved State Plans — Individual States)",
    "1953": "29 CFR Part 1953 (Changes to State Plans)",
    "1954": "29 CFR Part 1954 (Monitoring State Plans)",
    "1955": "29 CFR Part 1955 (Revocation of State Plan Approval)",
    "1956": "29 CFR Part 1956 (State Plans — Public Employees)",
    "1960": "29 CFR Part 1960 (Federal Agency Safety and Health Programs)",
    "1975": "29 CFR Part 1975 (Coverage of Employers)",
    "1977": "29 CFR Part 1977 (Whistleblower Protection — OSH Act)",
    "1978": "29 CFR Part 1978 (Whistleblower Protection — STAA: Surface Transportation Assistance Act)",
    "1979": "29 CFR Part 1979 (Whistleblower Protection — AIR21: Aviation Investment and Reform Act)",
    "1980": "29 CFR Part 1980 (Whistleblower Protection — SOX: Sarbanes-Oxley Act)",
    "1981": "29 CFR Part 1981 (Whistleblower Protection — PIPSA: Pipeline Safety Improvement Act)",
    "1982": "29 CFR Part 1982 (Whistleblower Protection — CPSA: Consumer Product Safety Act)",
    "1983": "29 CFR Part 1983 (Whistleblower Protection — FWPCA: Federal Water Pollution Control Act)",
    "1984": "29 CFR Part 1984 (Whistleblower Protection — ACA: Affordable Care Act)",
    "1985": "29 CFR Part 1985 (Whistleblower Protection — NTSSA: National Transit Systems Security Act)",
    "1986": "29 CFR Part 1986 (Whistleblower Protection — SDWA: Safe Drinking Water Act)",
    "1987": "29 CFR Part 1987 (Whistleblower Protection — TSCA: Toxic Substances Control Act)",
    "1988": "29 CFR Part 1988 (Whistleblower Protection — FSMA: Food Safety Modernization Act)",
    "1989": "29 CFR Part 1989 (Whistleblower Protection — Dodd-Frank Wall Street Reform Act)",
    "1991": "29 CFR Part 1991 (Whistleblower Protection — CGPA: Consumer Financial Protection Act)",
    "1992": "29 CFR Part 1992 (Whistleblower Protection — MAP-21: Moving Ahead for Progress)",
    "1990": "29 CFR Part 1990 (Identification of Carcinogens)",
    "FOM":  "OSHA Field Operations Manual (FOM) — inspection procedures, citation guidelines, penalty calculations, compliance directives",
    "OSH":  "Occupational Safety and Health Act (OSH Act) — the foundational law establishing OSHA, employer duties, employee rights, enforcement authority",
}


def get_cfr_part(section_id: str) -> str | None:
    for prefix in REGULATORY_PARTS:
        if section_id.startswith(prefix) and prefix not in ("FOM", "OSH"):
            return prefix
    if section_id.startswith("FOM"):
        return "FOM"
    if section_id.startswith("OSH"):
        return "OSH"
    return None
