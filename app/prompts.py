import random

ROMANTIC_SETTINGS = [
    "sharing a warm blanket on a wooden cabin porch during a gentle winter snowfall with mugs of hot cocoa",
    "walking side-by-side along a Kyoto canal lined with glowing lanterns and falling cherry blossom petals",
    "cooking together in a sunlit rustic kitchen, sharing a sweet laugh while making pasta",
    "stargazing together on the roof of a vintage camper van parked by a serene mountain lake",
    "sheltering under a single transparent umbrella in the rain under glowing city neon reflections",
    "a golden-hour picnic in an open wildflower meadow, relaxing peacefully together",
    "dancing slowly in a cozy living room decorated with warm fairy lights",
    "watching the ocean sunset from a seaside cliffside cafe with gentle coastal breeze"
]

def generate_flexible_prompt(user_note: str = None) -> str:
    setting = random.choice(ROMANTIC_SETTINGS)
    base = f"Setting: {setting}."
    if user_note and user_note.strip():
        base += f" Additional inspiration from couple: {user_note.strip()}."

    return (
        f"{base} Please creatively adapt both partners' likeness, expressions, and hairstyles "
        f"into a cohesive, heartwarming romantic illustration. Focus on gentle eye contact, natural intimacy, "
        f"soft atmospheric lighting, and romantic aesthetic colors."
    )
