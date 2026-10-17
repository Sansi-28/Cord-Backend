import os
import time
import uuid
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models import GenerationJob, GalleryImage, JobStatus

MAX_JOBS_PER_BATCH = 5
COOLDOWN_HOURS = 5

def check_rate_limit(db) -> tuple[bool, int]:
    """
    Enforces maximum of MAX_JOBS_PER_BATCH successful jobs in any COOLDOWN_HOURS window.
    Returns: (is_allowed, seconds_left_to_wait)
    """
    cutoff = datetime.utcnow() - timedelta(hours=COOLDOWN_HOURS)
    recent_jobs = db.query(GenerationJob).filter(
        GenerationJob.status == JobStatus.SUCCEEDED,
        GenerationJob.updated_at >= cutoff
    ).order_by(GenerationJob.updated_at.asc()).all()

    if len(recent_jobs) >= MAX_JOBS_PER_BATCH:
        earliest = recent_jobs[0].updated_at
        ready_time = earliest + timedelta(hours=COOLDOWN_HOURS)
        seconds_left = max(0, int((ready_time - datetime.utcnow()).total_seconds()))
        return False, seconds_left
    return True, 0

def generate_couple_cloud(prompt: str, output_path: str) -> bool:
    """
    Zero-budget, 24/7 cloud generation that runs in headless Linux (Render)
    without browser automation or CAPTCHA blocks.
    """
    if os.environ.get("USE_MOCK_GENERATOR") == "1":
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (800, 1000), color=(253, 238, 244))
        draw = ImageDraw.Draw(img)
        draw.polygon([(0, 700), (350, 400), (700, 700)], fill=(244, 182, 194))
        draw.polygon([(250, 750), (600, 350), (950, 750)], fill=(248, 198, 208))
        draw.ellipse([(600, 100), (750, 250)], fill=(255, 228, 233))
        draw.text((40, 850), f"Cloud AI Scene:\n{prompt[:60]}...", fill=(92, 64, 74))
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        img.save(output_path, "JPEG")
        return True

    try:
        enhanced_prompt = (
            f"romantic couple anime illustration, two lovers together, {prompt}, "
            f"pastel soft cherry blossoms, detailed expressive faces, high quality"
        )
        encoded = urllib.parse.quote(enhanced_prompt)
        # Uses Pollinations AI cloud engine (100% free, zero API key, runs on cloud datacenters)
        seed = int(time.time())
        image_url = f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=1000&nologo=true&seed={seed}"

        req = urllib.request.Request(
            image_url, 
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(data)

        return True
    except Exception as e:
        print(f"[Cloud Worker Error] {e}")
        return False

def process_one_cloud_job() -> bool:
    """Processes a single queued job for cloud environment."""
    db = SessionLocal()
    job = None
    try:
        allowed, wait_seconds = check_rate_limit(db)
        if not allowed:
            print(f"[Cloud Worker] Cooldown active. {wait_seconds}s remaining.")
            return False

        job = db.query(GenerationJob).filter(GenerationJob.status == JobStatus.QUEUED).first()
        if not job:
            return False

        job.status = JobStatus.RUNNING
        db.commit()

        storage_filename = f"gen_cloud_{uuid.uuid4().hex[:10]}.jpg"
        output_dir = os.path.abspath("./generated")
        output_path = os.path.join(output_dir, storage_filename)

        success = generate_couple_cloud(job.prompt, output_path)

        if success:
            gallery_img = GalleryImage(
                id=str(uuid.uuid4()),
                relationship_id=job.relationship_id,
                creator_id=job.requester_id,
                storage_filename=storage_filename,
                source_type="ai_generated"
            )
            db.add(gallery_img)
            job.result_image_id = gallery_img.id
            job.status = JobStatus.SUCCEEDED
            print(f"[Cloud Worker] Job {job.id} SUCCEEDED on Render!")
        else:
            job.status = JobStatus.FAILED
            job.error_code = "CLOUD_GEN_FAILED"
            print(f"[Cloud Worker] Job {job.id} FAILED!")

        db.commit()
        return True

    except Exception as e:
        print(f"[Worker Exception] {e}")
        db.rollback()
        if 'job' in locals() and job:
            job.status = JobStatus.FAILED
            job.error_code = str(e)[:100]
            db.commit()
        return False
    finally:
        db.close()

def run_cloud_worker_loop():
    print("=" * 60)
    print("Cloud 24/7 Worker started on Render...")
    print(f"Policy: Maximum {MAX_JOBS_PER_BATCH} generations, then {COOLDOWN_HOURS}-hour cooldown.")
    print("=" * 60)

    while True:
        try:
            db = SessionLocal()
            allowed, wait_seconds = check_rate_limit(db)
            db.close()

            if not allowed:
                sleep_duration = min(wait_seconds, 300)
                print(f"[Cloud Worker] Rate limit reached. Sleeping {sleep_duration}s...")
                time.sleep(sleep_duration)
                continue

            worked = process_one_cloud_job()
            if not worked:
                time.sleep(5)
            else:
                time.sleep(1)

        except Exception as e:
            print(f"[Cloud Worker Loop Exception] {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_cloud_worker_loop()
