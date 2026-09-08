import pytest
from backend.models.schemas import DocumentBlock, BlockType
from backend.pdf.sections import SectionTreeBuilder, SectionNode


def test_section_tree_hierarchy():
    blocks = [
        DocumentBlock(
            block_id="b1",
            page_num=1,
            bbox=(50, 100, 500, 120),
            block_type=BlockType.HEADING,
            text="16. Safety Information",
            section_number="16",
            is_heading=True,
            heading_level=1,
        ),
        DocumentBlock(
            block_id="b2",
            page_num=1,
            bbox=(50, 130, 500, 150),
            block_type=BlockType.PARAGRAPH,
            text="General safety overview text.",
        ),
        DocumentBlock(
            block_id="b3",
            page_num=1,
            bbox=(50, 160, 500, 180),
            block_type=BlockType.HEADING,
            text="16.1 Adverse Events",
            section_number="16.1",
            is_heading=True,
            heading_level=2,
        ),
        DocumentBlock(
            block_id="b4",
            page_num=1,
            bbox=(50, 190, 500, 210),
            block_type=BlockType.HEADING,
            text="16.1.1 Serious Events",
            section_number="16.1.1",
            is_heading=True,
            heading_level=3,
        ),
        DocumentBlock(
            block_id="b5",
            page_num=1,
            bbox=(50, 220, 500, 240),
            block_type=BlockType.HEADING,
            text="16.2 Laboratory Findings",
            section_number="16.2",
            is_heading=True,
            heading_level=2,
        ),
        DocumentBlock(
            block_id="b6",
            page_num=2,
            bbox=(50, 100, 500, 120),
            block_type=BlockType.HEADING,
            text="17. Clinical Data",
            section_number="17",
            is_heading=True,
            heading_level=1,
        ),
    ]

    root_nodes, node_index = SectionTreeBuilder.build_tree(blocks)

    # Roots should be 16 and 17
    assert len(root_nodes) == 2
    assert root_nodes[0].number == "16"
    assert root_nodes[1].number == "17"

    # Node 16 should have children 16.1 and 16.2
    node_16 = node_index["16"]
    child_numbers = [c.number for c in node_16.children]
    assert child_numbers == ["16.1", "16.2"]

    # Node 16.1 should have child 16.1.1
    node_16_1 = node_index["16.1"]
    assert len(node_16_1.children) == 1
    assert node_16_1.children[0].number == "16.1.1"

    # Verify paragraph b2 was associated with section 16
    assert blocks[1].section_number == "16"
