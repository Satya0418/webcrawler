from __future__ import annotations
from typing import List, Optional, Dict, Any, Tuple
from backend.models.schemas import DocumentBlock, BlockType, SectionSummary


class SectionNode:
    """Represents a hierarchical node in the document's section tree."""

    def __init__(
        self,
        number: str,
        title: str,
        level: int,
        start_page: int,
        start_block_id: str,
    ):
        self.number = number
        self.title = title
        self.level = level
        self.start_page = start_page
        self.end_page = start_page
        self.start_block_id = start_block_id
        self.end_block_id = start_block_id
        self.parent: Optional[SectionNode] = None
        self.children: List[SectionNode] = []
        self.blocks: List[DocumentBlock] = []

    def add_child(self, child: SectionNode) -> None:
        child.parent = self
        self.children.append(child)

    def get_all_descendant_blocks(self) -> List[DocumentBlock]:
        """Returns all blocks in this section and all its recursive children."""
        all_b = list(self.blocks)
        for child in self.children:
            all_b.extend(child.get_all_descendant_blocks())
        return all_b

    def get_all_descendant_nodes(self) -> List[SectionNode]:
        """Returns all child and descendant nodes."""
        nodes = []
        for child in self.children:
            nodes.append(child)
            nodes.extend(child.get_all_descendant_nodes())
        return nodes

    def update_page_bounds(self) -> None:
        """Recursively recalculates start_page, end_page, and end_block_id."""
        for child in self.children:
            child.update_page_bounds()

        all_b = self.get_all_descendant_blocks()
        if all_b:
            self.start_page = min(b.page_num for b in all_b)
            self.end_page = max(b.page_num for b in all_b)
            self.end_block_id = all_b[-1].block_id

    def to_summary(self) -> SectionSummary:
        """Converts to Pydantic SectionSummary model."""
        return SectionSummary(
            number=self.number,
            title=self.title,
            level=self.level,
            start_page=self.start_page,
            end_page=self.end_page,
            children=[c.to_summary() for c in self.children],
        )


class SectionTreeBuilder:
    """
    Constructs a hierarchical SectionNode tree from ordered DocumentBlocks
    and associates each content block with its parent section.
    """

    @staticmethod
    def build_tree(blocks: List[DocumentBlock]) -> Tuple[List[SectionNode], Dict[str, SectionNode]]:
        """
        Builds root section nodes and a fast lookup index {section_number: SectionNode}.
        """
        root_nodes: List[SectionNode] = []
        node_index: Dict[str, SectionNode] = {}
        active_section: Optional[SectionNode] = None

        for b in blocks:
            if b.is_heading and b.section_number:
                # Extract clean title from heading text
                raw_text = b.text.strip()
                title_part = ""
                # Strip section number prefix if present
                if raw_text.startswith(b.section_number):
                    title_part = raw_text[len(b.section_number):].strip(" .:-\t")
                else:
                    title_part = raw_text

                node = SectionNode(
                    number=b.section_number,
                    title=title_part,
                    level=b.heading_level or 1,
                    start_page=b.page_num,
                    start_block_id=b.block_id,
                )
                node_index[b.section_number] = node

                # Determine parent by prefix: e.g. "16.1.2" -> "16.1", "16.1" -> "16"
                parts = b.section_number.split(".")
                if len(parts) > 1:
                    parent_num = ".".join(parts[:-1])
                    parent_node = node_index.get(parent_num)
                    if parent_node:
                        parent_node.add_child(node)
                    else:
                        root_nodes.append(node)
                else:
                    root_nodes.append(node)

                active_section = node
                node.blocks.append(b)
            else:
                # Regular block (paragraph, list_item, table, etc.)
                if active_section:
                    b.section_number = active_section.number
                    active_section.blocks.append(b)

        # Update page ranges and boundary block IDs
        for root in root_nodes:
            root.update_page_bounds()

        return root_nodes, node_index
