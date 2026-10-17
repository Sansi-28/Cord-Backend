import os
import time
import uuid
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from playwright.sync_api import sync_playwright
from app.database import SessionLocal
from app.models import GenerationJob, GalleryImage, Relationship, User, JobStatus

MAX_JOBS_PER_BATCH = 5
COOLDOWN_HOURS = 5

def check_rate_limit(db) -> tuple[bool, int]:
    """
    Checks if 5 jobs have been processed in the last 5 hours.
    Returns: (is_allowed, seconds_remaining_to_wait)
    """
    cutoff = datetime.utcnow() - timedelta(hours=COOLDOWN_HOURS)
    recent_jobs = db.query(GenerationJob).filter(
        GenerationJob.status == JobStatus.SUCCEEDED,
        GenerationJob.updated_at >= cutoff
    ).order_by(GenerationJob.updated_at.asc()).all()

    if len(recent_jobs) >= MAX_JOBS_PER_BATCH:
        # Calculate time remaining until the 1st of the 5 jobs drops outside the 5-hour window
        earliest_job_time = recent_jobs[0].updated_at
        ready_time = earliest_job_time + timedelta(hours=COOLDOWN_HOURS)
        seconds_left = max(0, int((ready_time - datetime.utcnow()).total_seconds()))
        return False, seconds_left

    return True, 0

class ImageGeneratorAdapter(ABC):
    @abstractmethod
    def generate(self, prompt: str, output_path: str, ref_images: list[str] = None) -> bool:
        pass

class ZeroBudgetMockAdapter(ImageGeneratorAdapter):
    """Fallback / test generator that creates a local aesthetic couple graphic."""
    def generate(self, prompt: str, output_path: str, ref_images: list[str] = None) -> bool:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (800, 1000), color=(253, 238, 244))
        draw = ImageDraw.Draw(img)
        draw.polygon([(0, 700), (350, 400), (700, 700)], fill=(244, 182, 194))
        draw.polygon([(250, 750), (600, 350), (950, 750)], fill=(248, 198, 208))
        draw.ellipse([(600, 100), (750, 250)], fill=(255, 228, 233))
        draw.text((40, 850), f"AI Couple Scene:\n{prompt[:60]}...", fill=(92, 64, 74))
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        img.save(output_path, "JPEG")
        return True

class ChatGPTBrowserAdapter(ImageGeneratorAdapter):
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.profile_dir = os.path.abspath("./chatgpt_profile")

    def generate(self, prompt: str, output_path: str, ref_images: list[str] = None) -> bool:
        print(f"\n[ChatGPT Worker] Starting generation for: '{prompt}'")
        if ref_images:
            print(f"[ChatGPT Worker] Using {len(ref_images)} partner reference photo(s):")
            for img_p in ref_images:
                print(f"  -> {img_p}")
        else:
            print("[ChatGPT Worker] No partner reference photos found; generating from prompt text.")

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                headless=self.headless,
                args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 900}
            )
            page = context.pages[0] if context.pages else context.new_page()

            try:
                # 1. Open ChatGPT
                page.goto("https://chatgpt.com", wait_until="domcontentloaded", timeout=45000)
                time.sleep(2)

                prompt_box = page.locator("#prompt-textarea, div[contenteditable='true']")
                prompt_box.wait_for(state="visible", timeout=15000)

                # 2. Attach reference images if present
                if ref_images and len(ref_images) >= 1:
                    print(f"[ChatGPT Worker] Attaching {len(ref_images)} photos to ChatGPT...")
                    page.locator("input[type='file']").set_input_files(ref_images)
                    time.sleep(4)  # Wait for upload preview

                instruction = (
                    f"Look at the uploaded photos of the two partners in a relationship. "
                    f"Generate a single cohesive, cute, romantic illustration featuring both of them: {prompt}. "
                    f"Adapt their likeness, hairstyles, and vibe into a heartwarming anime/digital art style with soft atmospheric lighting."
                )
                prompt_box.fill(instruction)
                time.sleep(1)
                page.keyboard.press("Enter")

                print("[ChatGPT Worker] Generation in progress... waiting for result...")
                img_loc = page.locator("article:last-child img, [data-message-author-role='assistant']:last-child img").first
                img_loc.wait_for(state="visible", timeout=90000)
                time.sleep(3)

                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                img_loc.screenshot(path=output_path)
                print(f"[ChatGPT Worker] Image captured and saved to: {output_path}")
                return True

            except Exception as e:
                print(f"[ChatGPT Worker Error] {e}")
                return False
            finally:
                time.sleep(2)
                context.close()

def process_one_job():
    db = SessionLocal()
    job = None
    try:
        job = db.query(GenerationJob).filter(GenerationJob.status == JobStatus.QUEUED).first()
        if not job:
            return False

        print(f"\n[Worker] Claimed Job {job.id}...")
        job.status = JobStatus.RUNNING
        db.commit()

        # Gather the 2 reference photos
        upload_dir = os.path.abspath("./uploads")
        ref_paths = []
        for fname in [job.ref_image_1_filename, job.ref_image_2_filename]:
            if fname:
                p = os.path.join(upload_dir, fname)
                if os.path.exists(p):
                    ref_paths.append(p)

        # Fallback to latest photo from each partner if not on job
        if not ref_paths:
            rel = db.query(Relationship).filter(Relationship.id == job.relationship_id).first()
            if rel and rel.members:
                for member in rel.members:
                    latest_photo = db.query(GalleryImage).filter(
                        GalleryImage.relationship_id == rel.id,
                        GalleryImage.creator_id == member.id,
                        GalleryImage.source_type == "upload"
                    ).order_by(GalleryImage.created_at.desc()).first()
                    if latest_photo:
                        p = os.path.join(upload_dir, latest_photo.storage_filename)
                        if os.path.exists(p):
                            ref_paths.append(p)

        storage_filename = f"couple_gen_{uuid.uuid4().hex[:10]}.jpg"
        output_path = os.path.join(os.path.abspath("./generated"), storage_filename)

        if os.environ.get("USE_MOCK_GENERATOR") == "1":
            adapter = ZeroBudgetMockAdapter()
        else:
            adapter = ChatGPTBrowserAdapter(headless=False)

        success = adapter.generate(job.prompt, output_path, ref_images=ref_paths)

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
            print(f"[Worker] Job {job.id} SUCCEEDED!")
        else:
            job.status = JobStatus.FAILED
            job.error_code = "GENERATION_ERROR"
            print(f"[Worker] Job {job.id} FAILED!")

        db.commit()
        return True
    except Exception as e:
        db.rollback()
        if 'job' in locals() and job:
            job.status = JobStatus.FAILED
            job.error_code = str(e)[:100]
            db.commit()
        return False
    finally:
        db.close()

def run_worker_loop():
    print("=" * 60)
    print("Couple Space Worker Active")
    print(f"Policy: Maximum {MAX_JOBS_PER_BATCH} generations, then {COOLDOWN_HOURS}-hour cooldown.")
    print("=" * 60)

    while True:
        db = SessionLocal()
        try:
            allowed, wait_seconds = check_rate_limit(db)
            if not allowed:
                hours = wait_seconds // 3600
                minutes = (wait_seconds % 3600) // 60
                print(f"[Rate-Limit Cooldown] {MAX_JOBS_PER_BATCH} jobs reached. Next generation opens in {hours}h {minutes}m. Sleeping...")
                time.sleep(min(wait_seconds, 300))
                continue
        except Exception as e:
            print(f"[Rate-Limit Check Error] {e}")
        finally:
            db.close()

        if not process_one_job():
            time.sleep(3)

if __name__ == "__main__":
    run_worker_loop()
