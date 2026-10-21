# laptop_worker.py (Runs on your laptop)
import os
import time
import requests
from playwright.sync_api import sync_playwright

RENDER_BASE_URL = os.getenv("RENDER_BASE_URL", "https://cord-backend-api.onrender.com")
WORKER_SECRET = os.getenv("WORKER_SECRET", "my-super-private-couple-secret-2026")
PROFILE_DIR = os.path.abspath("./chatgpt_profile")
MAX_JOBS_PER_BATCH = 5
COOLDOWN_SECONDS = 5 * 3600  # 5 hours

def download_file(url: str, local_path: str) -> bool:
    try:
        r = requests.get(url, stream=True, timeout=30)
        if r.status_code == 200:
            with open(local_path, "wb") as f:
                for chunk in r:
                    f.write(chunk)
            return True
        print(f"[Download Error] HTTP {r.status_code} for {url}")
        return False
    except Exception as e:
        print(f"[Download Exception] {e} for {url}")
        return False

def generate_via_chatgpt(prompt: str, ref_images: list[str], output_path: str) -> bool:
    """Generates an image via ChatGPT browser automation or mock generator for testing."""
    if os.environ.get("USE_MOCK_GENERATOR") == "1":
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (800, 1000), color=(253, 238, 244))
        draw = ImageDraw.Draw(img)
        draw.polygon([(0, 700), (350, 400), (700, 700)], fill=(244, 182, 194))
        draw.text((40, 850), f"Laptop AI Scene:\n{prompt[:60]}...", fill=(92, 64, 74))
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        img.save(output_path, "JPEG")
        return True

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto("https://chatgpt.com", wait_until="domcontentloaded", timeout=45000)
            time.sleep(2)

            prompt_box = page.locator("#prompt-textarea, div[contenteditable='true']")
            prompt_box.wait_for(state="visible", timeout=15000)

            # Upload downloaded photos from the cloud
            valid_refs = [f for f in ref_images if os.path.exists(f)]
            if valid_refs:
                print(f"[Laptop Worker] Attaching {len(valid_refs)} downloaded photos to ChatGPT...")
                page.locator("input[type='file']").set_input_files(valid_refs)
                time.sleep(4)

            full_prompt = (
                f"Combine these two partners into a single romantic cute anime illustration: {prompt}. "
                f"Match their real features, hair, and expressions."
            )
            prompt_box.fill(full_prompt)
            time.sleep(1)
            page.keyboard.press("Enter")

            # Wait for generation to finish
            print("[Laptop Worker] Waiting for ChatGPT image generation...")
            img_loc = page.locator("article:last-child img, [data-message-author-role='assistant']:last-child img").first
            img_loc.wait_for(state="visible", timeout=90000)
            time.sleep(3)

            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            img_loc.screenshot(path=output_path)
            print(f"[Laptop Worker] Screenshot saved to: {output_path}")
            return True
        except Exception as e:
            print(f"[ChatGPT Error] {e}")
            return False
        finally:
            time.sleep(2)
            context.close()

def main():
    print("=" * 60)
    print("Laptop Bridge Worker Listening to Cloud Render Server...")
    print(f"Target Server: {RENDER_BASE_URL}")
    print(f"Batch Limit: {MAX_JOBS_PER_BATCH} jobs, then {COOLDOWN_SECONDS // 3600}h cooldown.")
    print("=" * 60)

    consecutive_jobs = 0

    while True:
        try:
            # 1. Check if 5-job batch limit was hit
            if consecutive_jobs >= MAX_JOBS_PER_BATCH:
                print(f"[Cooldown] 5 jobs finished! Sleeping for 5 hours to protect free ChatGPT tier...")
                time.sleep(COOLDOWN_SECONDS)
                consecutive_jobs = 0

            # 2. Poll Render for next job
            resp = requests.get(
                f"{RENDER_BASE_URL}/api/worker/claim-job",
                params={"secret": WORKER_SECRET},
                timeout=15
            )
            if resp.status_code != 200:
                print(f"[Worker] Server returned {resp.status_code}. Retrying in 10s...")
                time.sleep(10)
                continue

            data = resp.json()

            if not data.get("has_job"):
                time.sleep(10)  # Check cloud again in 10 seconds
                continue

            job_id = data["job_id"]
            prompt = data["prompt"]
            print(f"\n[Worker] Claimed Job {job_id} from cloud!")

            # 3. Download the two partners' photos locally
            local_refs = []
            for i, key in enumerate(["ref_image_1_url", "ref_image_2_url"]):
                rel_url = data.get(key)
                if rel_url:
                    full_url = rel_url if rel_url.startswith("http") else f"{RENDER_BASE_URL.rstrip('/')}{rel_url}"
                    local_img_path = f"./temp_ref_{i}_{job_id[:8]}.jpg"
                    if download_file(full_url, local_img_path):
                        local_refs.append(os.path.abspath(local_img_path))

            # 4. Generate the image in ChatGPT
            local_result_path = os.path.abspath(f"./temp_result_{job_id}.jpg")
            success = generate_via_chatgpt(prompt, local_refs, local_result_path)

            # 5. Push completed image back to Render
            if success and os.path.exists(local_result_path):
                with open(local_result_path, "rb") as f:
                    upload_resp = requests.post(
                        f"{RENDER_BASE_URL}/api/worker/submit-job",
                        data={"secret": WORKER_SECRET, "job_id": job_id},
                        files={"file": f},
                        timeout=60
                    )
                if upload_resp.status_code == 200:
                    print(f"[Worker] Successfully synced job {job_id} back to cloud gallery!")
                    consecutive_jobs += 1
                else:
                    print(f"[Worker Error] Submit job returned {upload_resp.status_code}: {upload_resp.text}")
            else:
                print(f"[Worker] Job {job_id} failed locally. Notifying cloud server...")
                requests.post(
                    f"{RENDER_BASE_URL}/api/worker/fail-job",
                    data={"secret": WORKER_SECRET, "job_id": job_id, "error_code": "LOCAL_GEN_FAILED"},
                    timeout=15
                )

            # Clean up temp files
            for f in local_refs + [local_result_path]:
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

        except Exception as e:
            print(f"[Worker Loop Exception] {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
