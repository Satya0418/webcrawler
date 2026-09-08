from typing import List, Optional
from backend.models.schemas import DocumentBlock, BlockType, ValidationChecklist


class ExtractionValidator:
    """
    Validates the extraction outcome against the requested boundaries and calculates
    traceability metrics, boundary exclusions, and a confidence score.
    """

    @staticmethod
    def validate(
        extracted_blocks: List[DocumentBlock],
        main_section: str,
        target_subsection: Optional[str],
        stop_section_num: Optional[str],
        all_discovered_sections: List[str]
    ) -> ValidationChecklist:
        checklist = ValidationChecklist()
        warnings: List[str] = []

        if not extracted_blocks:
            checklist.status_message = f"Section {main_section} was not found in the document."
            checklist.warnings.append("No blocks extracted. The requested section might not exist or could be in an unsupported format.")
            checklist.confidence_score = 0.0
            return checklist

        # Check start and end pages
        pages = [b.page_num for b in extracted_blocks]
        checklist.start_page = min(pages)
        checklist.end_page = max(pages)
        checklist.total_blocks_extracted = len(extracted_blocks)

        # Count tables
        checklist.tables_included_count = sum(
            1 for b in extracted_blocks if b.block_type == BlockType.TABLE
        )

        # Identify unique section numbers in extracted blocks
        extracted_sections = sorted(
            list({b.section_number for b in extracted_blocks if b.section_number})
        )
        checklist.included_sections = extracted_sections

        # Check 1: Was main section found?
        checklist.was_main_section_found = main_section in extracted_sections
        if not checklist.was_main_section_found:
            warnings.append(f"Main section {main_section} heading was not directly located in extracted content.")

        # Check 2: Was target subsection found (if requested)?
        if target_subsection:
            checklist.was_target_subsection_found = target_subsection in extracted_sections
            if not checklist.was_target_subsection_found:
                warnings.append(f"Target subsection {target_subsection} was not found inside section {main_section}.")
        else:
            checklist.was_target_subsection_found = True

        # Check 3: Check excluded sections
        excluded = []
        if stop_section_num and stop_section_num in all_discovered_sections:
            if stop_section_num not in extracted_sections:
                excluded.append(stop_section_num)
            else:
                warnings.append(f"Boundary section {stop_section_num} was unexpectedly included in extracted blocks.")

        # Also verify any section numerically > stop_section_num is excluded
        for sec in all_discovered_sections:
            if sec not in extracted_sections and sec not in excluded:
                # If sec starts with a later number or is later sibling
                if stop_section_num and sec >= stop_section_num:
                    excluded.append(sec)

        checklist.excluded_sections = sorted(list(set(excluded)))
        checklist.warnings = warnings

        # Calculate confidence score (0.0 to 1.0)
        score = 0.5  # Base for finding blocks
        if checklist.was_main_section_found:
            score += 0.25
        if checklist.was_target_subsection_found:
            score += 0.15
        if not warnings:
            score += 0.10
        else:
            score -= (0.10 * len(warnings))
        checklist.confidence_score = max(0.0, min(1.0, round(score, 2)))

        if checklist.confidence_score >= 0.8:
            checklist.status_message = "Extraction completed with high confidence."
        elif checklist.confidence_score >= 0.5:
            checklist.status_message = "Extraction completed with warnings."
        else:
            checklist.status_message = "Extraction completed with low confidence."

        return checklist
