# laptop_worker.py (Runs on your laptop)
import os
import time
import requests
import io
from PIL import Image
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

            prompt_box = page.locator("#prompt-textarea, div[contenteditable='true']").first
            prompt_box.wait_for(state="visible", timeout=15000)

            # Upload downloaded photos from the cloud
            valid_refs = [f for f in ref_images if os.path.exists(f)]
            if valid_refs:
                print(f"[Playwright] Uploading {len(valid_refs)} reference photos to ChatGPT...")
                # Target the 'multiple' photo upload input using .first to bypass strict mode
                file_input = page.locator("input[type='file'][accept*='image'][multiple], input[type='file'][multiple]").first
                file_input.set_input_files(valid_refs)

                # Give ChatGPT 5 seconds to upload and render the image pills in the chat bar
                print("[Playwright] Waiting for images to upload to chat bar...")
                time.sleep(5)

            # One-liner dynamic prompt: realistic, cute, looks like a couple, ChatGPT decides dynamically
            default_prompt = "Look at these images and create a realistic and cute photo of us as a couple, and dynamically decide what will be best."
            if not prompt or "anime" in prompt.lower() or "artwork" in prompt.lower() or "combine these two" in prompt.lower():
                full_prompt = default_prompt
            else:
                full_prompt = prompt.strip()
            prompt_box.fill(full_prompt)
            time.sleep(1)
            page.keyboard.press("Enter")

            # NEW: Resilient multi-strategy image detection
            print("[Playwright] Waiting for ChatGPT to generate image...")
            max_wait_seconds = 300  # 5 minutes
            poll_interval = 4
            start_time = time.time()
            img_captured = False

            while (time.time() - start_time) < max_wait_seconds:
                elapsed = int(time.time() - start_time)

                # 1. Scroll page to bottom so any lazy-loaded image renders
                try:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except Exception:
                    pass

                # 2. Gather image candidates using Playwright's .last (NOT CSS :last-child)
                candidates = []
                
                # Check images in the last assistant response
                assistant_msgs = page.locator("[data-message-author-role='assistant']")
                if assistant_msgs.count() > 0:
                    candidates.extend(assistant_msgs.last.locator("img").all())

                # Check images in the last article
                articles = page.locator("article")
                if articles.count() > 0:
                    candidates.extend(articles.last.locator("img").all())

                # Fallback: check any large image on the page
                candidates.extend(page.locator("img").all())

                # 3. Check candidates in reverse (newest at bottom first)
                for candidate in reversed(candidates):
                    try:
                        candidate.scroll_into_view_if_needed(timeout=1500)
                        box = candidate.bounding_box()
                        # User thumbnails and icons are <120px. The generated DALL-E image is 250px+
                        if box and box["width"] > 200 and box["height"] > 200:
                            print(f"\n[Playwright] Target image found ({int(box['width'])}x{int(box['height'])}) after {elapsed}s!")
                            print("[Playwright] Extracting high-resolution source URL...")
                            
                            # ⚠️ NEW: Get the actual high-res image URL instead of screenshotting
                            img_url = candidate.get_attribute("src")
                            
                            if img_url:
                                print(f"[Playwright] Downloading original image from OpenAI servers...")
                                r = requests.get(img_url)
                                
                                if r.status_code == 200:
                                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                                    
                                    # Convert to standard JPEG using Pillow to ensure AWS/Android compatibility
                                    img = Image.open(io.BytesIO(r.content))
                                    if img.mode in ("RGBA", "P"):
                                        img = img.convert("RGB")
                                        
                                    img.save(output_path, "JPEG", quality=95)
                                    print(f"[Playwright] Successfully downloaded high-res memory to: {output_path}")
                                    img_captured = True
                                    break
                                else:
                                    print(f"[Playwright Error] Failed to download URL. Status: {r.status_code}")
                            else:
                                # Fallback just in case OpenAI hides the src
                                print("[Playwright] No src found, falling back to screenshot...")
                                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                                candidate.screenshot(path=output_path)
                                img_captured = True
                                break
                    except Exception as e:
                        continue

                if img_captured:
                    break

                print(f"[Playwright] Still rendering... ({elapsed}s elapsed)")
                time.sleep(poll_interval)

            if not img_captured:
                print(f"[Playwright Error] Image generation exceeded 5 minutes.")
                return False

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
                        files={"file": (f"couple_gen_{job_id}.jpg", f, "image/jpeg")},
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
