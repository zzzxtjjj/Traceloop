import pytest

from core.errors import CrossProjectReferenceError, ProjectAccessDeniedError
from core.models import Artifact, ProductEntityLink
from core.schemas import ProjectCreate
from services.auth_service import create_session
from services.document_fact_service import confirm_extraction_sources
from services.document_parser import extract_artifact
from services.file_service import upload_project_file
from services.membership_service import create_user
from services.product_identity_service import assign_product, create_product, product_for
from services.project_service import create_project
from tests.test_document_parser_formats import _zip_bytes


def test_real_docx_product_evidence_and_isolation(db_session, tmp_path):
    owner = create_user("Owner", "product-owner@example.test", session=db_session)
    token = create_session(owner.id, session=db_session)
    project = create_project(
        ProjectCreate(
            name="Product test",
            product_name="Any industry",
            access_code="secure-code",
            markets=["DE"],
        ),
        owner_user_id=owner.id,
        session=db_session,
    )
    product = create_product(
        project_id=project.id,
        session_token=token,
        external_key="explicit-001",
        display_name="Industry independent",
        session=db_session,
    )
    other = create_product(
        project_id=project.id,
        session_token=token,
        external_key="explicit-002",
        display_name="Other",
        session=db_session,
    )
    raw = _zip_bytes({"word/document.xml": '''<w:document
+        xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
+        <w:body><w:p><w:r><w:t>纺织品规格 / Textile</w:t></w:r></w:p>
+        <w:p><w:r><w:t>Cotton 100% / 纯棉</w:t></w:r></w:p>
+        <w:tbl><w:tr><w:tc><w:p><w:r><w:t>克重</w:t></w:r></w:p></w:tc>
+        <w:tc><w:p><w:r><w:t>180 g/m²</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
+        </w:body></w:document>'''.replace("\n+", "\n")})
    artifact = upload_project_file(
        project_id=project.id,
        session_token=token,
        source=raw,
        filename="spec.docx",
        upload_root=tmp_path,
        session=db_session,
    )
    extraction = extract_artifact(
        project_id=project.id,
        session_token=token,
        artifact_id=artifact.id,
        upload_root=tmp_path,
        session=db_session,
    )
    sources = confirm_extraction_sources(
        project_id=project.id,
        session_token=token,
        product_id=product.id,
        extraction_id=extraction.id,
        session=db_session,
    )
    assert len(sources) == 4
    assert any('"column_index":1' in source.locator_json for source in sources)
    assert product_for(db_session, "artifact", artifact.id) == product.id
    assert all(source.business_object_id == product.id for source in sources)
    with pytest.raises(CrossProjectReferenceError):
        assign_product(
            project_id=project.id,
            session_token=token,
            product_id=other.id,
            kind="artifact",
            entity_id=artifact.id,
            session=db_session,
        )
    outsider = create_user("Outsider", "outsider@example.test", session=db_session)
    other_token = create_session(outsider.id, session=db_session)
    with pytest.raises(ProjectAccessDeniedError):
        assign_product(
            project_id=project.id,
            session_token=other_token,
            product_id=product.id,
            kind="artifact",
            entity_id=artifact.id,
            session=db_session,
        )
    assert db_session.get(Artifact, artifact.id)
    assert db_session.query(ProductEntityLink).count() == len(sources) + 2
