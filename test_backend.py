import os
import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine
from app.worker import process_one_job

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db():
    os.environ['USE_MOCK_GENERATOR'] = '1'
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield

def test_root():
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"

def test_full_couple_lifecycle():
    # 1. Register Partner A and Partner B
    r_a = client.post("/api/auth/register", data={"username": "alice", "password": "password123", "display_name": "Alice"})
    assert r_a.status_code == 200
    token_a = r_a.json()["token"]
    assert token_a is not None

    r_b = client.post("/api/auth/register", data={"username": "bob", "password": "password123", "display_name": "Bob"})
    assert r_b.status_code == 200
    token_b = r_b.json()["token"]
    assert token_b is not None

    # 2. Partner A creates invite code
    invite_res = client.post("/api/pairing/invitations", headers={"Authorization": f"Bearer {token_a}"})
    assert invite_res.status_code == 200
    code = invite_res.json()["invite_code"]
    assert len(code) == 6

    # 3. Partner B accepts invite
    pair_res = client.post("/api/pairing/accept", data={"invite_code": code}, headers={"Authorization": f"Bearer {token_b}"})
    assert pair_res.status_code == 200
    assert pair_res.json()["status"] == "paired"

    # 4. Partner A sends affection
    emo_res = client.post("/api/emotions", data={"emotion_type": "missing_you", "note": "Thinking of you!"}, headers={"Authorization": f"Bearer {token_a}"})
    assert emo_res.status_code == 200

    # 5. Partner B reads emotions
    feed = client.get("/api/emotions", headers={"Authorization": f"Bearer {token_b}"})
    assert feed.status_code == 200
    assert len(feed.json()) == 1
    assert feed.json()[0]["emotion_type"] == "missing_you"

    # 6. Partner A queues an AI job
    job_res = client.post("/api/generation-jobs", data={"prompt": "Walking in the snow together"}, headers={"Authorization": f"Bearer {token_a}"})
    assert job_res.status_code == 200
    job_id = job_res.json()["job_id"]
    assert job_res.json()["status"] == "queued"

    # 7. Background Worker picks and completes the job
    worked = process_one_job()
    assert worked is True

    # 8. Partner B checks job status
    status_check = client.get(f"/api/generation-jobs/{job_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert status_check.status_code == 200
    assert status_check.json()["status"] == "succeeded"
    assert status_check.json()["result_image_id"] is not None

    # 9. Test Gallery and Collage functionality
    # Upload valid image
    img = Image.new("RGB", (200, 200), color=(255, 192, 203))
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="JPEG")
    img_bytes.seek(0)
    upload_res = client.post(
        "/api/gallery/upload",
        files={"file": ("photo.jpg", img_bytes, "image/jpeg")},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert upload_res.status_code == 200
    assert "filename" in upload_res.json()

    # Get Gallery
    gallery_res = client.get("/api/gallery", headers={"Authorization": f"Bearer {token_b}"})
    assert gallery_res.status_code == 200
    assert len(gallery_res.json()) >= 2  # The AI image and the uploaded image

    # Generate recent collage
    collage_res = client.get("/api/gallery/recent-collage", headers={"Authorization": f"Bearer {token_b}"})
    assert collage_res.status_code == 200
    assert "collage_url" in collage_res.json()

def test_auto_permutation_queueing():
    # 1. Register Alice and Bob
    r_a = client.post("/api/auth/register", data={"username": "alice_perm", "password": "password123", "display_name": "Alice"})
    token_a = r_a.json()["token"]
    r_b = client.post("/api/auth/register", data={"username": "bob_perm", "password": "password123", "display_name": "Bob"})
    token_b = r_b.json()["token"]

    # 2. Pair them
    code = client.post("/api/pairing/invitations", headers={"Authorization": f"Bearer {token_a}"}).json()["invite_code"]
    client.post("/api/pairing/accept", data={"invite_code": code}, headers={"Authorization": f"Bearer {token_b}"})

    # 3. Bob uploads 2 photos
    dummy_img = io.BytesIO()
    Image.new("RGB", (100, 100), color="blue").save(dummy_img, format="JPEG")
    dummy_bytes = dummy_img.getvalue()

    r1 = client.post("/api/gallery/upload", files={"file": ("bob1.jpg", dummy_bytes, "image/jpeg")}, headers={"Authorization": f"Bearer {token_b}"})
    assert r1.status_code == 200
    assert r1.json()["permutations_queued"] == 0

    r2 = client.post("/api/gallery/upload", files={"file": ("bob2.jpg", dummy_bytes, "image/jpeg")}, headers={"Authorization": f"Bearer {token_b}"})
    assert r2.status_code == 200
    assert r2.json()["permutations_queued"] == 0

    # 4. Alice uploads 1 photo -> should trigger 2 permutation jobs (Alice1 + Bob1, Alice1 + Bob2)
    r3 = client.post("/api/gallery/upload", files={"file": ("alice1.jpg", dummy_bytes, "image/jpeg")}, headers={"Authorization": f"Bearer {token_a}"})
    assert r3.status_code == 200
    assert r3.json()["permutations_queued"] == 2


def test_worker_bridge_flow():
    # 1. Register and pair
    r_a = client.post("/api/auth/register", data={"username": "alice_bridge", "password": "password123", "display_name": "Alice"})
    token_a = r_a.json()["token"]
    r_b = client.post("/api/auth/register", data={"username": "bob_bridge", "password": "password123", "display_name": "Bob"})
    token_b = r_b.json()["token"]

    code = client.post("/api/pairing/invitations", headers={"Authorization": f"Bearer {token_a}"}).json()["invite_code"]
    client.post("/api/pairing/accept", data={"invite_code": code}, headers={"Authorization": f"Bearer {token_b}"})

    # 2. Queue a job
    job_res = client.post("/api/generation-jobs", data={"prompt": "Stargazing on a roof"}, headers={"Authorization": f"Bearer {token_a}"})
    job_id = job_res.json()["job_id"]

    # 3. Test Unauthorized claim
    bad_claim = client.get("/api/worker/claim-job", params={"secret": "wrong_secret"})
    assert bad_claim.status_code == 403

    # 4. Test Authorized claim
    good_claim = client.get("/api/worker/claim-job", params={"secret": "my-super-private-couple-secret-2026"})
    assert good_claim.status_code == 200
    claim_data = good_claim.json()
    assert claim_data["has_job"] is True
    assert claim_data["job_id"] == job_id
    assert claim_data["prompt"] == "Stargazing on a roof"

    # 5. Submit completed result from worker
    res_img = Image.new("RGB", (100, 100), color="pink")
    res_bytes = io.BytesIO()
    res_img.save(res_bytes, format="JPEG")
    res_bytes.seek(0)

    sub_res = client.post(
        "/api/worker/submit-job",
        data={"secret": "my-super-private-couple-secret-2026", "job_id": job_id},
        files={"file": ("result.jpg", res_bytes, "image/jpeg")}
    )
    assert sub_res.status_code == 200
    assert sub_res.json()["status"] == "saved"
    gallery_id = sub_res.json()["gallery_id"]

    # 6. Verify job is marked SUCCEEDED
    status_res = client.get(f"/api/generation-jobs/{job_id}", headers={"Authorization": f"Bearer {token_a}"})
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "succeeded"
    assert status_res.json()["result_image_id"] == gallery_id

def test_cloud_worker_execution():
    from app.worker_cloud import process_one_cloud_job

    # 1. Register and pair
    r_a = client.post("/api/auth/register", data={"username": "alice_cloud", "password": "password123", "display_name": "Alice"})
    token_a = r_a.json()["token"]
    r_b = client.post("/api/auth/register", data={"username": "bob_cloud", "password": "password123", "display_name": "Bob"})
    token_b = r_b.json()["token"]

    code = client.post("/api/pairing/invitations", headers={"Authorization": f"Bearer {token_a}"}).json()["invite_code"]
    client.post("/api/pairing/accept", data={"invite_code": code}, headers={"Authorization": f"Bearer {token_b}"})

    # 2. Queue a job
    job_res = client.post("/api/generation-jobs", data={"prompt": "Cozy cabin by the fire"}, headers={"Authorization": f"Bearer {token_a}"})
    job_id = job_res.json()["job_id"]

    # 3. Process via cloud worker
    success = process_one_cloud_job()
    assert success is True

    # 4. Verify job succeeded
    status_res = client.get(f"/api/generation-jobs/{job_id}", headers={"Authorization": f"Bearer {token_a}"})
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "succeeded"


def test_worker_fail_and_empty_queue():
    # 1. When queue is empty
    empty_claim = client.get("/api/worker/claim-job", params={"secret": "my-super-private-couple-secret-2026"})
    assert empty_claim.status_code == 200
    assert empty_claim.json()["has_job"] is False

    # 2. Register & pair
    r_a = client.post("/api/auth/register", data={"username": "alice_fail", "password": "password123", "display_name": "Alice"})
    token_a = r_a.json()["token"]
    r_b = client.post("/api/auth/register", data={"username": "bob_fail", "password": "password123", "display_name": "Bob"})
    token_b = r_b.json()["token"]
    code = client.post("/api/pairing/invitations", headers={"Authorization": f"Bearer {token_a}"}).json()["invite_code"]
    client.post("/api/pairing/accept", data={"invite_code": code}, headers={"Authorization": f"Bearer {token_b}"})

    # 3. Queue job & claim
    job_res = client.post("/api/generation-jobs", data={"prompt": "Under the rain"}, headers={"Authorization": f"Bearer {token_a}"})
    job_id = job_res.json()["job_id"]
    claim = client.get("/api/worker/claim-job", params={"secret": "my-super-private-couple-secret-2026"})
    assert claim.json()["has_job"] is True

    # 4. Fail job
    fail_res = client.post(
        "/api/worker/fail-job",
        data={"secret": "my-super-private-couple-secret-2026", "job_id": job_id, "error_code": "LOCAL_ERROR"}
    )
    assert fail_res.status_code == 200

    # 5. Verify failed status
    check = client.get(f"/api/generation-jobs/{job_id}", headers={"Authorization": f"Bearer {token_a}"})
    assert check.json()["status"] == "failed"
    assert check.json()["error_code"] == "LOCAL_ERROR"
