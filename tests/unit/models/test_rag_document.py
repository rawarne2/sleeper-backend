from models.entities import RagDocument
from models.extensions import db


def test_rag_document_roundtrip_sqlite(app_context):
    from datetime import UTC, datetime

    row = RagDocument(
        id="doc-1",
        corpus="strategy_kb",
        source_id="grading",
        content="Grading guidance...",
        metadata_={"section": "Grading"},
        created_at=datetime.now(UTC),
    )
    db.session.add(row)
    db.session.commit()
    loaded = RagDocument.query.filter_by(source_id="grading").one()
    assert loaded.corpus == "strategy_kb"
    assert loaded.metadata_["section"] == "Grading"
