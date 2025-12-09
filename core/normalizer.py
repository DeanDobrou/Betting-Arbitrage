"""
Universal team name normalizer using fuzzy string matching.
No manual mappings - works automatically for any team name.

IMPORTANT: This normalizer only handles cosmetic differences like accents,
spacing, and punctuation. It does NOT remove age groups (U19, U21) or
B teams as these represent DIFFERENT teams!
"""
from __future__ import annotations

import re
from unidecode import unidecode
from rapidfuzz import fuzz


def normalize_team_name(name: str) -> str:
    """
    Normalize a team name for better matching.

    Only handles cosmetic differences:
    1. Remove accents/diacritics
    2. Convert to lowercase
    3. Normalize spacing
    4. Normalize punctuation

    Does NOT remove:
    - Age groups (U19, U21, U23) - these are different teams!
    - B/B' teams - these are reserve teams, different from first team!
    - Women's team markers (W) - these are different teams!

    Args:
        name: Raw team name from bookmaker

    Returns:
        Normalized team name
    """
    if not name:
        return ""

    # Convert to lowercase first
    name = name.lower()

    # Remove accents/diacritics using unidecode (handles Greek text properly)
    name = unidecode(name)

    # Normalize common abbreviations
    # Remove FC, CF, AC, SC at the END only (not in middle like "FC Barcelona")
    name = re.sub(r'\s+fc$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+cf$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+sc$', '', name, flags=re.IGNORECASE)
    # Note: AC at the START is kept (like "AC Milan"), only removed at end
    name = re.sub(r'\s+ac$', '', name, flags=re.IGNORECASE)

    # Remove parentheses for virtual/friendly markers like (Γ) for friendlies
    name = re.sub(r'\s*\(γ\)\s*$', '', name, flags=re.IGNORECASE)

    # Keep (W) marker for women's teams - these are different teams!

    # Normalize punctuation - replace with space
    name = re.sub(r'[.\-_]', ' ', name)

    # Remove other special characters
    name = re.sub(r'[^\w\s]', ' ', name)

    # Collapse multiple spaces
    name = re.sub(r'\s+', ' ', name)

    # Trim
    name = name.strip()

    return name


def teams_match(team1: str, team2: str, threshold: int = 85) -> bool:
    """
    Check if two team names match using fuzzy string matching.

    Args:
        team1: First team name
        team2: Second team name
        threshold: Similarity threshold (0-100). Default 85.

    Returns:
        True if teams match, False otherwise
    """
    # Normalize both names
    norm1 = normalize_team_name(team1)
    norm2 = normalize_team_name(team2)

    # Exact match after normalization
    if norm1 == norm2:
        return True

    # If either is empty after normalization, no match
    if not norm1 or not norm2:
        return False

    # Calculate similarity using token sort ratio
    # This handles word order differences (e.g., "AC Milan" vs "Milan AC")
    similarity = fuzz.token_sort_ratio(norm1, norm2)

    return similarity >= threshold


def get_best_match(target: str, candidates: list[str], threshold: int = 85) -> tuple[str | None, int]:
    """
    Find the best matching team name from a list of candidates.

    Args:
        target: Team name to match
        candidates: List of candidate team names
        threshold: Minimum similarity threshold

    Returns:
        Tuple of (best_match, score) or (None, 0) if no match above threshold
    """
    target_norm = normalize_team_name(target)

    if not target_norm:
        return None, 0

    best_match = None
    best_score = 0

    for candidate in candidates:
        candidate_norm = normalize_team_name(candidate)

        if not candidate_norm:
            continue

        score = fuzz.token_sort_ratio(target_norm, candidate_norm)

        if score > best_score:
            best_score = score
            best_match = candidate

    if best_score >= threshold:
        return best_match, best_score

    return None, 0
