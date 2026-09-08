from typing import List, Optional, Tuple, Dict
from backend.models.schemas import DocumentBlock
from backend.pdf.sections import SectionNode


class BoundaryDetector:
    """
    Calculates precise block-level extraction boundaries based on requested
    main section, target subsection, and discovered section hierarchy.
    """

    @staticmethod
    def find_stop_section_number(
        main_section: str,
        target_subsection: Optional[str],
        root_nodes: List[SectionNode],
        node_index: Dict[str, SectionNode]
    ) -> Optional[str]:
        """
        Determines the section number that acts as the stop boundary.
        For 16 -> 16.1, this is typically 16.2 (or 17 if 16.2 doesn't exist).
        """
        if not target_subsection:
            # If no target subsection, stop at the next root section after main_section
            root_nums = [r.number for r in root_nodes]
            if main_section in root_nums:
                idx = root_nums.index(main_section)
                if idx + 1 < len(root_nums):
                    return root_nums[idx + 1]
            return None

        # When target_subsection is provided (e.g. "16.1")
        target_node = node_index.get(target_subsection)
        main_node = node_index.get(main_section)

        if target_node and main_node and target_node.parent == main_node:
            # Find next sibling in parent's children
            siblings = main_node.children
            if target_node in siblings:
                idx = siblings.index(target_node)
                if idx + 1 < len(siblings):
                    return siblings[idx + 1].number

        # Fallback: check if next numerical sibling exists in node_index
        # e.g., "16.1" -> parts ["16", "1"] -> try "16.2"
        parts = target_subsection.split(".")
        if parts and parts[-1].isdigit():
            next_last = str(int(parts[-1]) + 1)
            candidate_sibling = ".".join(parts[:-1] + [next_last])
            if candidate_sibling in node_index:
                return candidate_sibling

        # If no sibling, find next section after parent
        root_nums = [r.number for r in root_nodes]
        if main_section in root_nums:
            idx = root_nums.index(main_section)
            if idx + 1 < len(root_nums):
                return root_nums[idx + 1]

        return None

    @staticmethod
    def extract_blocks_within_boundary(
        blocks: List[DocumentBlock],
        main_section: str,
        target_subsection: Optional[str],
        stop_section_num: Optional[str]
    ) -> Tuple[List[DocumentBlock], List[str], List[str]]:
        """
        Iterates through ordered blocks and extracts:
        - Parent section heading and introductory content
        - Target subsection and all its recursive descendants
        Stops strictly when stop_section_num or later section begins.

        Returns:
            (extracted_blocks, included_sections_list, excluded_sections_list)
        """
        extracted_blocks: List[DocumentBlock] = []
        included_sections: set = set()
        excluded_sections: set = set()

        has_started = False
        target_prefix = f"{target_subsection}." if target_subsection else None

        for b in blocks:
            # Never include header or footer blocks in section body
            if b.block_type in ("header", "footer"):
                continue

            sec = b.section_number

            # Check if this block triggers the stop boundary
            if has_started and stop_section_num:
                if sec == stop_section_num or (b.is_heading and b.section_number == stop_section_num):
                    excluded_sections.add(stop_section_num)
                    break
                # If a higher section number appears (e.g. section 17)
                if b.is_heading and b.section_number:
                    # Check if heading is past the main section or target
                    if b.section_number not in (main_section, target_subsection) and (
                        target_prefix and not b.section_number.startswith(target_prefix)
                    ):
                        # Verify if this heading is after main/target
                        excluded_sections.add(b.section_number)
                        break

            # Check start boundary: Section 16 heading
            if not has_started:
                if b.is_heading and b.section_number == main_section:
                    has_started = True
                    extracted_blocks.append(b)
                    included_sections.add(main_section)
                    continue
                # Or if user only requested subsection directly without parent
                elif target_subsection and b.is_heading and b.section_number == target_subsection:
                    has_started = True
                    extracted_blocks.append(b)
                    included_sections.add(target_subsection)
                    continue
                else:
                    continue

            # If we have started:
            # 1. Blocks belonging to main_section prior to target_subsection
            if sec == main_section:
                extracted_blocks.append(b)
                included_sections.add(main_section)
            # 2. Blocks belonging to target_subsection exactly
            elif target_subsection and sec == target_subsection:
                extracted_blocks.append(b)
                included_sections.add(target_subsection)
            # 3. Blocks belonging to any recursive descendant of target_subsection (e.g. 16.1.1, 16.1.2)
            elif target_prefix and sec and sec.startswith(target_prefix):
                extracted_blocks.append(b)
                included_sections.add(sec)
            # 4. If no target_subsection was requested, all children of main_section are included
            elif not target_subsection and sec and sec.startswith(f"{main_section}."):
                extracted_blocks.append(b)
                included_sections.add(sec)
            else:
                # Any other section encountered after starting triggers stop
                if b.is_heading and b.section_number:
                    excluded_sections.add(b.section_number)
                    break

        return (
            extracted_blocks,
            sorted(list(included_sections)),
            sorted(list(excluded_sections)),
        )
