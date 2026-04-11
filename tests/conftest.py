import pytest
from io import BytesIO
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Minimal valid JPEG (1x1 red pixel, generated via Pillow)
JPEG_BYTES = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000"
    "ffdb004300080606070605080707070909080a0c"
    "140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20"
    "242e2720222c231c1c2837292c30313434341f27"
    "393d38323c2e333432ffdb0043010909090c0b0c"
    "180d0d1832211c21323232323232323232323232"
    "3232323232323232323232323232323232323232"
    "323232323232323232323232323232323232ffc0"
    "0011080001000103012200021101031101ffc400"
    "1f00000105010101010101000000000000000001"
    "02030405060708090a0bffc400b5100002010303"
    "020403050504040000017d010203000411051221"
    "31410613516107227114328191a1082342b1c115"
    "52d1f02433627282090a161718191a2526272829"
    "2a3435363738393a434445464748494a53545556"
    "5758595a636465666768696a737475767778797a"
    "838485868788898a92939495969798999aa2a3a4"
    "a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6"
    "c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7"
    "e8e9eaf1f2f3f4f5f6f7f8f9faffc4001f010003"
    "0101010101010101010000000000000102030405"
    "060708090a0bffc400b511000201020404030407"
    "0504040001027700010203110405213106124151"
    "0761711322328108144291a1b1c109233352f015"
    "6272d10a162434e125f11718191a262728292a35"
    "363738393a434445464748494a53545556575859"
    "5a636465666768696a737475767778797a828384"
    "85868788898a92939495969798999aa2a3a4a5a6"
    "a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8"
    "c9cad2d3d4d5d6d7d8d9dae2e3e4e5e6e7e8e9ea"
    "f2f3f4f5f6f7f8f9faffda000c03010002110311"
    "003f00e2e8a28af993f713ffd9"
)

# Minimal valid PNG (1x1 red pixel, generated via Pillow)
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080200000090"
    "7753de0000000c49444154789c63f8cfc0000003010100c9fe92ef000000"
    "0049454e44ae426082"
)


@pytest.fixture
def db_session():
    """Function-scoped in-memory SQLite database."""
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.database import Base
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def test_client(db_session):
    """FastAPI test client with overridden DB dependency."""
    from app.main import app
    from app.database import get_db
    from fastapi.testclient import TestClient

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def mock_ai_success():
    """Mock AI client returning valid classification."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"category":"pothole","severity":"high","department":"roads","description":"Large pothole"}'
    mock_client.models.generate_content.return_value = mock_response
    return mock_client


@pytest.fixture
def mock_ai_timeout():
    """Mock AI client that raises a timeout."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = TimeoutError("API timeout")
    return mock_client


@pytest.fixture
def sample_image():
    """Valid JPEG upload file."""
    return {"photo": ("test.jpg", BytesIO(JPEG_BYTES), "image/jpeg")}


@pytest.fixture
def sample_png():
    """Valid PNG upload file."""
    return {"photo": ("test.png", BytesIO(PNG_BYTES), "image/png")}
