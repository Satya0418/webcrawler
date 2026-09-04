"""Pytest configuration and fixtures."""
import pytest
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture
def sample_drug_record():
    """Sample normalized drug record for testing."""
    return {
        "display_name": "Warfarin",
        "normalized_name": "warfarin",
        "active_ingredient": "Warfarin",
        "application_number": "NDA-017388",
        "section": "Warnings and Precautions",
        "source_date": None,
        "approval_date": None,
        "effective_date": None,
        "original_text": "Original warning text here.",
        "updated_text": "Updated warning text here.",
        "fda_comment": "FDA comment on the change.",
        "source_url": "https://www.accessdata.fda.gov/scripts/cder/safetylabelingchanges/index.cfm?Search=warfarin",
        "source_record_id": "ABC123",
    }


@pytest.fixture
def sample_html_content():
    """Sample HTML content for parser testing."""
    return """
    <html>
        <head><title>Drug Safety-related Labeling Changes</title></head>
        <body>
            <h1>Drug Safety-related Labeling Changes (SrLC)</h1>
            <table>
                <tr>
                    <th>Drug Name</th>
                    <th>Active Ingredient</th>
                    <th>Section</th>
                    <th>Date</th>
                </tr>
                <tr>
                    <td>Warfarin</td>
                    <td>Warfarin</td>
                    <td>Warnings and Precautions</td>
                    <td>2026-01-15</td>
                </tr>
            </table>
        </body>
    </html>
    """
